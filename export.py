from __future__ import annotations

import csv
from datetime import datetime
from typing import Optional

from persistence import get_balance_history, get_margin_history


def export_balance_csv(filename: Optional[str] = None, customer_id: Optional[str] = None, hours: int = 24) -> str:
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"balance_export_{ts}.csv"
    rows = get_balance_history(customer_id=customer_id, hours=hours, limit=5000)
    with open(filename, 'w', newline='') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    return filename


def export_margin_csv(filename: Optional[str] = None, customer_id: Optional[str] = None, hours: int = 24) -> str:
    if filename is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"margin_export_{ts}.csv"
    rows = get_margin_history(customer_id=customer_id, hours=hours, limit=5000)
    with open(filename, 'w', newline='') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    return filename
