import time
from auth import perform_login, create_session
from scrapers import fetch_balance, fetch_summary_report
from display import print_balance_line, print_summary_line


def run_quick_check_full(settings):
    customer_ids = settings["customer_ids"]
    timeout = settings["request_timeout"]
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, timeout):
        print("  Login failed.")
        return

    print()
    print("  Balances")
    print("  " + "-" * 30)
    for cid in customer_ids:
        name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        print_balance_line(name, cid, balance, credit_limit, error)
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
    print()


def run_quick_check_balance(settings):
    customer_ids = settings["customer_ids"]
    timeout = settings["request_timeout"]
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, timeout):
        print("  Login failed.")
        return

    print()
    print("  Balances")
    print("  " + "-" * 30)
    for cid in customer_ids:
        name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        print_balance_line(name, cid, balance, credit_limit, error)
        time.sleep(0.3)
    print()


def run_quick_check_summary(settings):
    session = create_session()

    print("  Logging in...")
    if not perform_login(session, settings["request_timeout"]):
        print("  Login failed.")
        return

    print()
    print("  Summary Report")
    print("  " + "-" * 30)
    summary = fetch_summary_report(session, settings)
    if not summary:
        print("  No data.")
    else:
        for cid, data in summary.items():
            print_summary_line(data, cid, monitored=(cid in settings["customer_ids"]))
    print()
