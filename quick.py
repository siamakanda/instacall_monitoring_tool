from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp

from auth import create_session, perform_login
from config import Settings
from display import print_balance_line, print_summary_line
from persistence import BalanceRecord, MarginRecord, init_db, insert_balance, insert_margin, get_balance_history, get_margin_history
from scrapers import fetch_balance, fetch_summary_report
from async_fetch import fetch_balances_parallel, fetch_summary_async


def _balance_changed(cid: str, balance: float, credit_limit: Optional[float]) -> bool:
    rows = get_balance_history(customer_id=cid, hours=24, limit=1)
    if not rows:
        return True
    r = rows[0]
    prev_balance = r.get("balance")
    prev_credit = r.get("credit_limit")
    return prev_balance != balance or prev_credit != credit_limit


def _margin_changed(cid: str, margin: Optional[float], billed_min: Optional[float]) -> bool:
    rows = get_margin_history(customer_id=cid, hours=24, limit=1)
    if not rows:
        return True
    r = rows[0]
    prev_margin = r.get("margin")
    prev_billed = r.get("billed_min")
    return prev_margin != margin or prev_billed != billed_min


def run_quick_check_full(settings: Settings) -> None:
    customer_ids = settings.customer_ids
    timeout = settings.request_timeout
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, timeout):
        print("  Login failed.")
        return

    init_db()

    print()
    print("  Balances")
    print("  " + "-" * 30)
    for cid in customer_ids:
        name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        print_balance_line(name or "N/A", cid, balance, credit_limit, error)
        if balance is not None:
            remaining = credit_limit + balance if credit_limit is not None else None
            if _balance_changed(cid, balance, credit_limit):
                insert_balance(BalanceRecord(
                    customer_id=cid,
                    customer_name=name or "N/A",
                    balance=balance,
                    credit_limit=credit_limit,
                    remaining=remaining,
                ))
        time.sleep(0.3)

    print()
    print("  Summary Report")
    print("  " + "-" * 30)
    summary = fetch_summary_report(session, settings)
    if not summary:
        print("  No data.")
    else:
        for cid, data in summary.items():
            print_summary_line(data, cid, monitored=(cid in customer_ids))
            margin = data.get('margin')
            billed_min = data.get('billed_min')
            m = margin if isinstance(margin, float) else None
            b = billed_min if isinstance(billed_min, float) else None
            if _margin_changed(cid, m, b):
                insert_margin(MarginRecord(
                    customer_id=cid,
                    customer_name=str(data.get('name', 'N/A')),
                    margin=m,
                    billed_min=b,
                ))
    print()


def run_quick_check_balance(settings: Settings) -> None:
    customer_ids = settings.customer_ids
    timeout = settings.request_timeout
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, timeout):
        print("  Login failed.")
        return

    init_db()

    print()
    print("  Balances")
    print("  " + "-" * 30)
    for cid in customer_ids:
        name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        print_balance_line(name or "N/A", cid, balance, credit_limit, error)
        if balance is not None:
            remaining = credit_limit + balance if credit_limit is not None else None
            if _balance_changed(cid, balance, credit_limit):
                insert_balance(BalanceRecord(
                    customer_id=cid,
                    customer_name=name or "N/A",
                    balance=balance,
                    credit_limit=credit_limit,
                    remaining=remaining,
                ))
        time.sleep(0.3)
    print()


def run_quick_check_summary(settings: Settings) -> None:
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, settings.request_timeout):
        print("  Login failed.")
        return

    init_db()

    print()
    print("  Summary Report")
    print("  " + "-" * 30)
    summary = fetch_summary_report(session, settings)
    if not summary:
        print("  No data.")
    else:
        for cid, data in summary.items():
            print_summary_line(data, cid, monitored=(cid in settings.customer_ids))
            margin = data.get('margin')
            billed_min = data.get('billed_min')
            m = margin if isinstance(margin, float) else None
            b = billed_min if isinstance(billed_min, float) else None
            if _margin_changed(cid, m, b):
                insert_margin(MarginRecord(
                    customer_id=cid,
                    customer_name=str(data.get('name', 'N/A')),
                    margin=m,
                    billed_min=b,
                ))
    print()


def run_quick_check_parallel(settings: Settings) -> None:
    customer_ids = settings.customer_ids
    timeout = settings.request_timeout
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, timeout):
        print("  Login failed.")
        return

    init_db()
    cookies = {c.name: c.value for c in session.cookies}
    headers = dict(session.headers)

    async def _run() -> None:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as aio_session:
            print()
            print("  Balances (async parallel)")
            print("  " + "-" * 30)
            results = await fetch_balances_parallel(aio_session, customer_ids, timeout)
            for cid, name, balance, credit_limit, error in results:
                print_balance_line(name or "N/A", cid, balance, credit_limit, error)
                if balance is not None:
                    remaining = credit_limit + balance if credit_limit is not None else None
                    if _balance_changed(cid, balance, credit_limit):
                        insert_balance(BalanceRecord(
                            customer_id=cid,
                            customer_name=name or "N/A",
                            balance=balance,
                            credit_limit=credit_limit,
                            remaining=remaining,
                        ))

            print()
            print("  Summary Report (async)")
            print("  " + "-" * 30)
            summary_data = await fetch_summary_async(aio_session, settings)
            if not summary_data:
                print("  No data.")
            else:
                for cid, data in summary_data.items():
                    print_summary_line(data, cid, monitored=(cid in customer_ids))
                    m = data.get('margin')
                    b = data.get('billed_min')
                    margin_val = m if isinstance(m, float) else None
                    billed_val = b if isinstance(b, float) else None
                    if _margin_changed(cid, margin_val, billed_val):
                        insert_margin(MarginRecord(
                            customer_id=cid,
                            customer_name=str(data.get('name', 'N/A')),
                            margin=margin_val,
                            billed_min=billed_val,
                        ))
            print()

    asyncio.run(_run())
