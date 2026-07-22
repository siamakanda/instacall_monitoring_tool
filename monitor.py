import time
import logging
import traceback
from config import LOG_FILE, write_status
from auth import perform_login, create_session
from scrapers import fetch_balance, fetch_summary_report
from alerts import trigger_balance_alert, trigger_margin_alert
from display import print_balance_line, print_summary_line


def _monitor_loop(settings):
    customer_ids = settings["customer_ids"]
    balance_threshold = settings["balance_threshold"]
    margin_threshold = settings["margin_threshold"]
    billed_min_threshold = settings["billed_min_threshold"]
    interval = settings["check_interval_seconds"]
    timeout = settings["request_timeout"]

    alert_status = {cid: False for cid in customer_ids}
    margin_alert_status = {cid: False for cid in customer_ids}
    error_count = 0
    last_error = None

    session = create_session()

    if not perform_login(session, timeout):
        logging.critical("Initial login failed.")
        write_status(alive=False, error_count=1, last_error="Initial login failed")
        return

    write_status(alive=True, error_count=0)
    try:
        while True:
            last_check = time.strftime("%Y-%m-%d %H:%M:%S")

            for cid in customer_ids:
                customer_name, balance, credit_limit, fetch_error = fetch_balance(session, cid, timeout)

                if balance is not None:
                    print_balance_line(customer_name, cid, balance, credit_limit, fetch_error,
                                       prefix=f"[B] [{time.strftime('%H:%M:%S')}]")

                    if credit_limit is not None:
                        remaining = credit_limit + balance
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f} | Credit: {credit_limit:.2f} | Remaining: {remaining:.2f}")
                    else:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f}")

                    if balance < balance_threshold:
                        if not alert_status[cid]:
                            trigger_balance_alert(cid, balance, customer_name, settings)
                            alert_status[cid] = True
                    else:
                        if alert_status[cid]:
                            logging.info(f"Customer {cid} ({customer_name}) - Balance recovered to {balance:.4f}. Alert disarmed.")
                            alert_status[cid] = False
                else:
                    error_count += 1
                    last_error = fetch_error
                    logging.warning(f"Customer {cid} - fetch error: {fetch_error}")
                    print_balance_line("N/A", cid, None, None, fetch_error,
                                       prefix=f"[B] [{time.strftime('%H:%M:%S')}]")

                time.sleep(0.5)

            summary = fetch_summary_report(session, settings)
            for cid, data in summary.items():
                margin = data['margin']
                billed_min = data['billed_min']
                name = data['name']

                print_summary_line(data, cid, monitored=(cid in customer_ids),
                                   prefix=f"[M] [{time.strftime('%H:%M:%S')}]")

                if margin is not None:
                    logging.info(f"Customer {cid} ({name}) - Margin: {margin:.1f}% | Billed Min: {billed_min:.1f}")

                if margin is not None and billed_min is not None:
                    if margin < margin_threshold and billed_min > billed_min_threshold:
                        if not margin_alert_status.get(cid, False):
                            trigger_margin_alert(cid, margin, billed_min, name, settings)
                            margin_alert_status[cid] = True
                    else:
                        if margin_alert_status.get(cid, False):
                            logging.info(f"Customer {cid} ({name}) - Margin recovered to {margin:.1f}%. Alert disarmed.")
                            margin_alert_status[cid] = False

            write_status(alive=True, last_check=last_check, error_count=error_count, last_error=last_error)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n[-] Interrupted. Shutting down...")
        logging.info("Monitor stopped by user (Ctrl+C).")
        write_status(alive=False)


def run_monitor(settings):
    customer_ids = settings["customer_ids"]
    balance_threshold = settings["balance_threshold"]
    margin_threshold = settings["margin_threshold"]
    billed_min_threshold = settings["billed_min_threshold"]
    interval = settings["check_interval_seconds"]

    print(f"  Monitor started - {LOG_FILE}")
    print(f"  IDs: {', '.join(customer_ids)}")
    print(f"  Interval: {interval // 60} min")
    print(f"  Balance alert below {balance_threshold:+.1f}  |  Margin alert below {margin_threshold}% & Billed > {billed_min_threshold:.0f} min")
    print(f"  Summary: {settings.get('summary_direction', 'outbound')} / {settings.get('summary_interval', '5m')}")
    audio = settings.get("audio_enabled", True)
    print(f"  Audio: {'ON' if audio else 'OFF (quiet mode)'}")
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
