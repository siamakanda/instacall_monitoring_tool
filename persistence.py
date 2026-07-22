from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Optional

from config import DB_FILE

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    balance REAL,
    credit_limit REAL,
    remaining REAL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS margin_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    margin REAL,
    billed_min REAL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_balance_customer ON balance_history(customer_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_margin_customer ON margin_history(customer_id, recorded_at);
"""


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.executescript(CREATE_TABLES_SQL)
        conn.commit()


@dataclass
class BalanceRecord:
    customer_id: str
    customer_name: str
    balance: Optional[float]
    credit_limit: Optional[float]
    remaining: Optional[float]

    @property
    def recorded_at(self) -> str:
        return datetime.now().isoformat()

    def to_tuple(self) -> tuple[str, str, Optional[float], Optional[float], Optional[float], str]:
        return (self.customer_id, self.customer_name, self.balance, self.credit_limit, self.remaining, self.recorded_at)


@dataclass
class MarginRecord:
    customer_id: str
    customer_name: str
    margin: Optional[float]
    billed_min: Optional[float]

    @property
    def recorded_at(self) -> str:
        return datetime.now().isoformat()

    def to_tuple(self) -> tuple[str, str, Optional[float], Optional[float], str]:
        return (self.customer_id, self.customer_name, self.margin, self.billed_min, self.recorded_at)


def insert_balance(record: BalanceRecord) -> None:
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO balance_history (customer_id, customer_name, balance, credit_limit, remaining, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            record.to_tuple(),
        )
        conn.commit()


def insert_margin(record: MarginRecord) -> None:
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO margin_history (customer_id, customer_name, margin, billed_min, recorded_at) "
            "VALUES (?, ?, ?, ?, ?)",
            record.to_tuple(),
        )
        conn.commit()


def get_balance_history(
    customer_id: Optional[str] = None, hours: int = 24, limit: int = 500
) -> list[dict[str, object]]:
    cutoff = datetime.now().isoformat()
    with _get_connection() as conn:
        if customer_id:
            rows = conn.execute(
                "SELECT * FROM balance_history WHERE customer_id = ? AND recorded_at > datetime(?, ?) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (customer_id, cutoff, f"-{hours} hours", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM balance_history WHERE recorded_at > datetime(?, ?) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (cutoff, f"-{hours} hours", limit),
            ).fetchall()

    cols = ["id", "customer_id", "customer_name", "balance", "credit_limit", "remaining", "recorded_at"]
    return [dict(zip(cols, row)) for row in rows]


def get_margin_history(
    customer_id: Optional[str] = None, hours: int = 24, limit: int = 500
) -> list[dict[str, object]]:
    cutoff = datetime.now().isoformat()
    with _get_connection() as conn:
        if customer_id:
            rows = conn.execute(
                "SELECT * FROM margin_history WHERE customer_id = ? AND recorded_at > datetime(?, ?) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (customer_id, cutoff, f"-{hours} hours", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM margin_history WHERE recorded_at > datetime(?, ?) "
                "ORDER BY recorded_at DESC LIMIT ?",
                (cutoff, f"-{hours} hours", limit),
            ).fetchall()

    cols = ["id", "customer_id", "customer_name", "margin", "billed_min", "recorded_at"]
    return [dict(zip(cols, row)) for row in rows]


def purge_old_records(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    with _get_connection() as conn:
        b = conn.execute(
            "DELETE FROM balance_history WHERE recorded_at < datetime('now', ?)",
            (f'-{retention_days} days',),
        ).rowcount
        m = conn.execute(
            "DELETE FROM margin_history WHERE recorded_at < datetime('now', ?)",
            (f'-{retention_days} days',),
        ).rowcount
        conn.commit()
    return b + m
