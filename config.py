from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, fields
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

LOGIN_URL = "https://switchportal.instacall.digital/login"
BASE_EDIT_URL = "https://switchportal.instacall.digital/customers?edit="
SUMMARY_REPORT_URL = "https://switchportal.instacall.digital/summary_report"

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

LOG_FILE = "balance_monitor.log"
STATUS_FILE = "monitor.status"
SETTINGS_FILE = "settings.json"
DB_FILE = "marginmonitor.db"


@dataclass
class Settings:
    customer_ids: list[str] = field(default_factory=lambda: ["18"])
    check_interval_seconds: int = 600
    balance_threshold: float = -365.0
    margin_threshold: float = 30.0
    billed_min_threshold: float = 70.0
    db_retention_days: int = 30
    request_timeout: int = 10
    summary_direction: str = "outbound"
    summary_interval: str = "5m"
    audio_enabled: bool = True
    siren_loops: int = 10
    siren_min_freq: int = 2200
    siren_max_freq: int = 3500
    siren_step_freq: int = 130
    siren_tone_duration: int = 50
    alert_cooldown_seconds: int = 300
    webhook_url: str = ""
    webhook_type: str = "none"
    telegram_chat_id: str = ""
    active_hours_start: str = ""
    active_hours_end: str = ""
    active_days: str = ""
    logging_json: bool = False
    health_port: int = 0
    active_profile: str = "default"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(self):
            result[f.name] = getattr(self, f.name)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        field_names = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)


def get_credentials() -> tuple[str, str]:
    load_dotenv()
    username = os.getenv("PORTAL_USERNAME")
    password = os.getenv("PORTAL_PASSWORD")
    if not username or not password:
        raise ValueError("PORTAL_USERNAME or PASSWORD not found in .env file.")
    return username, password


def load_settings() -> Settings:
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data: dict[str, Any] = json.load(f)
        return Settings.from_dict(data)
    except (FileNotFoundError, json.JSONDecodeError):
        return Settings()


def save_settings(settings: Settings) -> None:
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings.to_dict(), f, indent=2)


def validate_settings(settings: Settings) -> list[str]:
    errors: list[str] = []

    if not isinstance(settings.customer_ids, list) or len(settings.customer_ids) == 0:
        errors.append("customer_ids must be a non-empty list")
    elif not all(str(i).strip().isdigit() for i in settings.customer_ids):
        errors.append("customer_ids contains non-numeric values")

    for key in ["check_interval_seconds", "request_timeout"]:
        val = getattr(settings, key, 0)
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"{key} must be a positive number")

    for key in ["siren_loops", "siren_min_freq", "siren_max_freq", "siren_step_freq", "siren_tone_duration"]:
        val = getattr(settings, key, 0)
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"{key} must be a positive number")

    if settings.summary_direction not in ("outbound", "inbound"):
        errors.append("summary_direction must be 'outbound' or 'inbound'")

    if settings.webhook_type not in ("none", "telegram", "slack"):
        errors.append("webhook_type must be 'none', 'telegram', or 'slack'")

    if settings.alert_cooldown_seconds < 0:
        errors.append("alert_cooldown_seconds must be >= 0")

    if settings.db_retention_days < 0:
        errors.append("db_retention_days must be >= 0")

    if settings.active_hours_start:
        if not re.match(r"^\d{2}:\d{2}$", settings.active_hours_start):
            errors.append("active_hours_start must be HH:MM format")
    if settings.active_hours_end:
        if not re.match(r"^\d{2}:\d{2}$", settings.active_hours_end):
            errors.append("active_hours_end must be HH:MM format")

    return errors


def write_status(alive: bool, last_check: str = "", error_count: int = 0, last_error: str = "") -> None:
    data: dict[str, Any] = {
        "alive": alive,
        "last_check": last_check,
        "error_count": error_count,
        "last_error": last_error,
    }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


def setup_logging() -> None:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)

    try:
        settings = load_settings()
    except Exception:
        settings = Settings()

    if settings.logging_json:
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"
        ))

    logging.basicConfig(level=logging.INFO, handlers=[handler])
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logging.getLogger('').addHandler(console)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
            "name": record.name,
        })


def load_profiles() -> dict[str, Settings]:
    profiles_file = Path("profiles.json")
    if not profiles_file.exists():
        return {"default": Settings()}
    try:
        data = json.loads(profiles_file.read_text())
        return {name: Settings.from_dict(cfg) for name, cfg in data.items()}
    except (json.JSONDecodeError, TypeError):
        return {"default": Settings()}


def save_profiles(profiles: dict[str, Settings]) -> None:
    data = {name: cfg.to_dict() for name, cfg in profiles.items()}
    with open("profiles.json", 'w') as f:
        json.dump(data, f, indent=2)
