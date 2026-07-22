import os
import json
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

LOGIN_URL = "https://switchportal.instacall.digital/login"
BASE_EDIT_URL = "https://switchportal.instacall.digital/customers?edit="
SUMMARY_REPORT_URL = "https://switchportal.instacall.digital/summary_report"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

LOG_FILE = "balance_monitor.log"
STATUS_FILE = "monitor.status"
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "customer_ids": ["18"],
    "check_interval_seconds": 600,
    "balance_threshold": -365.0,
    "margin_threshold": 30.0,
    "billed_min_threshold": 70.0,
    "request_timeout": 10,
    "summary_direction": "outbound",
    "summary_interval": "5m",
    "audio_enabled": True,
    "siren_loops": 10,
    "siren_min_freq": 2200,
    "siren_max_freq": 3500,
    "siren_step_freq": 130,
    "siren_tone_duration": 50,
}


def get_credentials():
    load_dotenv()
    username = os.getenv("PORTAL_USERNAME")
    password = os.getenv("PORTAL_PASSWORD")
    if not username or not password:
        raise ValueError("PORTAL_USERNAME or PASSWORD not found in .env file.")
    return username, password


def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
        for key, default in DEFAULT_SETTINGS.items():
            if key not in settings:
                settings[key] = default
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


def validate_settings(settings):
    errors = []

    ids = settings.get("customer_ids", [])
    if not isinstance(ids, list) or len(ids) == 0:
        errors.append("customer_ids must be a non-empty list")
    elif not all(str(i).strip().isdigit() for i in ids):
        errors.append("customer_ids contains non-numeric values")

    for key in ["check_interval_seconds", "request_timeout"]:
        val = settings.get(key, 0)
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"{key} must be a positive number")

    for key in ["siren_loops", "siren_min_freq", "siren_max_freq", "siren_step_freq", "siren_tone_duration"]:
        val = settings.get(key, 0)
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"{key} must be a positive number")

    direction = settings.get("summary_direction", "")
    if direction not in ("outbound", "inbound"):
        errors.append("summary_direction must be 'outbound' or 'inbound'")

    return errors


def write_status(alive, last_check=None, error_count=0, last_error=None):
    data = {
        "alive": alive,
        "last_check": last_check or "",
        "error_count": error_count,
        "last_error": last_error or "",
    }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


def setup_logging():
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logging.getLogger('').addHandler(console)
