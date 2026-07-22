def fmt_margin(margin):
    return f"{margin:.1f}%" if margin is not None else "N/A"


def fmt_billed_min(billed_min):
    return f"{billed_min:.1f}" if billed_min is not None else "N/A"


def print_balance_line(customer_name, cid, balance, credit_limit, error, prefix="[B]"):
    if balance is not None:
        remaining = None
        if credit_limit is not None:
            remaining = credit_limit + balance
        credit_str = f"/ Credit: {credit_limit:.2f}" if credit_limit is not None else ""
        remaining_str = f" (Remaining: {remaining:.2f})" if remaining is not None else ""
        print(f"{prefix} {customer_name} (ID: {cid})  Balance {balance:.4f}  {credit_str}{remaining_str}")
    else:
        print(f"{prefix} ID {cid}  FETCH FAILED ({error})")


def print_summary_line(data, cid, monitored=False, prefix="[M]"):
    """Print a single summary line from a data dict."""
    name = data.get("name", "N/A")
    margin = data.get("margin")
    billed_min = data.get("billed_min")
    tag = " [MONITORED]" if monitored else ""
    print(f"{prefix} {name} (ID: {cid})  Margin {fmt_margin(margin)}  |  Billed {fmt_billed_min(billed_min)} min{tag}")
