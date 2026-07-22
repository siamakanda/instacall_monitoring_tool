from __future__ import annotations

from typing import Optional


def fmt_margin(margin: Optional[float]) -> str:
    return f"{margin:.1f}%" if margin is not None else "N/A"


def fmt_billed_min(billed_min: Optional[float]) -> str:
    return f"{billed_min:.1f}" if billed_min is not None else "N/A"


def fmt_balance(balance: Optional[float]) -> str:
    return f"{balance:.4f}" if balance is not None else "N/A"


def print_balance_line(
    customer_name: str,
    cid: str,
    balance: Optional[float],
    credit_limit: Optional[float],
    error: Optional[str] = None,
    prefix: str = "[B]",
) -> None:
    if balance is not None:
        remaining: Optional[float] = None
        if credit_limit is not None:
            remaining = credit_limit + balance
        credit_str = f"  Credit: {credit_limit:.2f}" if credit_limit is not None else ""
        remaining_str = f"  Remaining: {remaining:.2f}" if remaining is not None else ""
        print(f"  {prefix} {customer_name:25s}  Balance {fmt_balance(balance)} {credit_str}{remaining_str}")
    else:
        print(f"  {prefix} ID {cid}  FETCH FAILED ({error})")


def print_summary_line(
    data: dict[str, object],
    cid: str,
    monitored: bool = False,
    prefix: str = "[M]",
) -> None:
    name = str(data.get("name", "N/A"))[:30]
    margin = data.get("margin")
    billed_min = data.get("billed_min")
    tag = " >> MONITORED" if monitored else ""
    print(f"  {prefix} {name:30s}  Margin {fmt_margin(margin):>6s}  |  Billed {fmt_billed_min(billed_min):>7s} min{tag}")
