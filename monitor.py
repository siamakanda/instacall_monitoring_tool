from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime
from typing import Optional

from auth import create_session, perform_login
from config import DB_FILE, Settings, write_status
from display import print_balance_line, print_summary_line
from persistence import BalanceRecord, MarginRecord, init_db, insert_balance, insert_margin, purge_old_records
from scrapers import fetch_balance, fetch_summary_report

from alerts import _siren_manager, trigger_balance_alert, trigger_margin_alert
from health import start_health_server


def _is_within_active_hours(
    start: str, end: str, days: str, now: Optional[datetime] = None
) -> bool:
    if not start and not end:
        return True

    if now is None:
        now = datetime.now()

    if days:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        allowed = set()
        for part in days.lower().replace(" ", "").split(","):
            if part in day_map:
                allowed.add(day_map[part])
        if allowed and now.weekday() not in allowed:
            return False

    if start and end:
        try:
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            now_minutes = now.hour * 60 + now.minute
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes <= end_minutes:
                if not (start_minutes <= now_minutes < end_minutes):
                    return False
            else:
                if not (now_minutes >= start_minutes or now_minutes < end_minutes):
                    return False
        except (ValueError, IndexError):
            return True

    return True


def _monitor_loop(settings: Settings) -> None:
    customer_ids = settings.customer_ids
    balance_threshold = settings.balance_threshold
    margin_threshold = settings.margin_threshold
    billed_min_threshold = settings.billed_min_threshold
    interval = settings.check_interval_seconds
    timeout = settings.request_timeout
    cooldown = settings.alert_cooldown_seconds

    alert_status: dict[str, bool] = {cid: False for cid in customer_ids}
    margin_alert_status: dict[str, bool] = {cid: False for cid in customer_ids}
    last_balance_vals: dict[str, tuple[float, Optional[float]]] = {}
    last_margin_vals: dict[str, tuple[Optional[float], Optional[float]]] = {}
    error_count = 0
    last_error: Optional[str] = None

    init_db()
    purge_old_records(settings.db_retention_days)
    session = create_session()

    if not perform_login(session, timeout):
        logging.critical("Initial login failed.")
        write_status(alive=False, error_count=1, last_error="Initial login failed")
        return

    write_status(alive=True, error_count=0)
    print(f"  Running first check now...")
    try:
        while True:
            last_check = time.strftime("%Y-%m-%d %H:%M:%S")

            if not _is_within_active_hours(
                settings.active_hours_start,
                settings.active_hours_end,
                settings.active_days,
            ):
                write_status(alive=True, last_check=last_check, error_count=error_count, last_error=last_error)
                next_time = time.strftime("%H:%M:%S", time.localtime(time.time() + interval))
                print(f"  [{time.strftime('%H:%M:%S')}] Outside active hours. Next wake at {next_time}")
                time.sleep(interval)
                continue

            for cid in customer_ids:
                customer_name, balance, credit_limit, fetch_error = fetch_balance(session, cid, timeout)

                if balance is not None:
                    remaining = credit_limit + balance if credit_limit is not None else None
                    print_balance_line(customer_name, cid, balance, credit_limit, fetch_error,
                                       prefix=f"B [{time.strftime('%H:%M:%S')}]")

                    prev = last_balance_vals.get(cid)
                    curr = (balance, credit_limit)
                    if prev != curr:
                        last_balance_vals[cid] = curr
                        insert_balance(BalanceRecord(
                            customer_id=cid,
                            customer_name=customer_name or "N/A",
                            balance=balance,
                            credit_limit=credit_limit,
                            remaining=remaining,
                        ))

                    if credit_limit is not None:
                        logging.info(
                            f"Customer {cid} ({customer_name}) - "
                            f"Balance: {balance:.4f} | Credit: {credit_limit:.2f} | Remaining: {remaining:.2f}"
                        )
                    else:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f}")

                    if balance < balance_threshold:
                        if not alert_status[cid] and _siren_manager.can_alert(cid, cooldown):
                            trigger_balance_alert(cid, balance, customer_name or "N/A", settings)
                            alert_status[cid] = True
                    else:
                        if alert_status[cid]:
                            logging.info(
                                f"Customer {cid} ({customer_name}) - Balance recovered to {balance:.4f}. Alert disarmed."
                            )
                            alert_status[cid] = False
                else:
                    error_count += 1
                    last_error = fetch_error
                    logging.warning(f"Customer {cid} - fetch error: {fetch_error}")
                    print_balance_line("N/A", cid, None, None, fetch_error,
                                       prefix=f"B [{time.strftime('%H:%M:%S')}]")

                time.sleep(0.5)

            print()
            summary = fetch_summary_report(session, settings)
            shown = 0
            total = len(summary)
            if settings.summary_show_all:
                show_ids = set(summary.keys())
            else:
                show_ids = set(customer_ids) | {
                    cid for cid, data in summary.items()
                    if (data.get('margin') is not None and data.get('margin') < margin_threshold
                        and data.get('billed_min') is not None and data.get('billed_min') > billed_min_threshold)
                }

            print(f"  ── Summary ({len(show_ids)} shown / {total} total) ──")
            for cid, data in summary.items():
                if cid not in show_ids:
                    continue
                margin = data.get('margin')
                billed_min = data.get('billed_min')
                name = str(data.get('name', 'N/A'))

                if (margin is not None and margin == 0 and billed_min is not None and billed_min == 0
                        and cid not in customer_ids):
                    continue

                print_summary_line(data, cid, monitored=(cid in customer_ids),
                                   prefix=f"[M] [{time.strftime('%H:%M:%S')}]")
                shown += 1

                if margin is not None:
                    logging.info(f"Customer {cid} ({name}) - Margin: {margin:.1f}% | Billed Min: {billed_min:.1f}")

                m_prev = last_margin_vals.get(cid)
                m_curr = (margin if isinstance(margin, float) else None,
                           billed_min if isinstance(billed_min, float) else None)
                if m_prev != m_curr:
                    last_margin_vals[cid] = m_curr
                    insert_margin(MarginRecord(
                        customer_id=cid,
                        customer_name=name,
                        margin=margin if isinstance(margin, float) else None,
                        billed_min=billed_min if isinstance(billed_min, float) else None,
                    ))

                if margin is not None and billed_min is not None:
                    if margin < margin_threshold and billed_min > billed_min_threshold:
                        if not margin_alert_status.get(cid, False) and _siren_manager.can_margin_alert(cid, cooldown):
                            trigger_margin_alert(cid, margin, billed_min, name, settings)
                            margin_alert_status[cid] = True
                    else:
                        if margin_alert_status.get(cid, False):
                            logging.info(
                                f"Customer {cid} ({name}) - Margin recovered to {margin:.1f}%. Alert disarmed."
                            )
                            margin_alert_status[cid] = False

            write_status(alive=True, last_check=last_check, error_count=error_count, last_error=last_error)
            purge_old_records(settings.db_retention_days)
            next_time = time.strftime("%H:%M:%S", time.localtime(time.time() + interval))
            print()
            print(f"  [{time.strftime('%H:%M:%S')}] Cycle complete. Next check at {next_time} (~{interval}s)")
            print(f"  {'─' * 40}")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n[-] Interrupted. Shutting down...")
        logging.info("Monitor stopped by user (Ctrl+C).")
        write_status(alive=False)


def run_monitor(settings: Settings) -> None:
    customer_ids = settings.customer_ids
    balance_threshold = settings.balance_threshold
    margin_threshold = settings.margin_threshold
    billed_min_threshold = settings.billed_min_threshold
    interval = settings.check_interval_seconds

    print(f"  Monitor started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  IDs: {', '.join(customer_ids)}")
    if interval >= 60:
        if interval % 60 == 0:
            print(f"  Interval: {interval // 60} min")
        else:
            print(f"  Interval: {interval // 60}m {interval % 60}s")
    else:
        print(f"  Interval: {interval}s")
    print(f"  Balance alert below {balance_threshold:+.1f}  |  "
          f"Margin alert below {margin_threshold}% & Billed > {billed_min_threshold:.0f} min")
    print(f"  Summary: {settings.summary_direction} / {settings.summary_interval}")
    print(f"  Cooldown: {settings.alert_cooldown_seconds}s")
    audio = settings.audio_enabled
    print(f"  Audio: {'ON' if audio else 'OFF (quiet mode)'}")
    print(f"  Webhooks: {settings.webhook_type}")
    print(f"  DB retention: {settings.db_retention_days} days")
    if settings.active_hours_start and settings.active_hours_end:
        days = f" ({settings.active_days})" if settings.active_days else " (all days)"
        print(f"  Active hours: {settings.active_hours_start}-{settings.active_hours_end}{days}")
    else:
        print(f"  Active hours: 24/7")
    print(f"  Database: {DB_FILE}")
    if settings.health_port > 0:
        start_health_server(settings.health_port)
        print(f"  Health endpoint: http://localhost:{settings.health_port}/health")
    print("  Ctrl+C to stop.")
    print("  " + "-" * 30)

    while True:
        try:
            _monitor_loop(settings)
            break
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.critical(f"Monitor crashed: {e}\n{traceback.format_exc()}")
            print(f"  CRASH: {e}")
            print(f"  Restarting in 10 seconds...")
            write_status(alive=False, last_error=str(e))
            time.sleep(10)
