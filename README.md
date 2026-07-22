# Instacall Monitoring Tool v2.0

Real-time balance and margin monitoring for the Instacall Switch Portal. Alerts via desktop notifications, audible sirens, and webhooks when thresholds are breached.

## Quick Start (Any Device)

```bash
# 1. Clone the repo
git clone https://github.com/siamakanda/instacall_monitoring_tool.git
cd instacall_monitoring_tool

# 2. Create your credentials file
cp .env.example .env
# Edit .env and add your portal credentials:
#   PORTAL_USERNAME="your_username"
#   PORTAL_PASSWORD="your_password"

# 3. One-click setup & run (Windows)
setup_and_run.bat
```

Or manually:

```bash
# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python menu.py

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python menu.py
```

## Move to Another Device

The repo is self-contained. Just clone, create `.env`, and run:

```bash
git clone https://github.com/siamakanda/instacall_monitoring_tool.git
cd instacall_monitoring_tool
cp .env.example .env       # then edit with your credentials
python -m venv venv && source venv/bin/activate   # or: venv\Scripts\activate on Windows
pip install -r requirements.txt
python menu.py
```

All settings are stored in `settings.json` and `profiles.json`. Copy those files if you want to carry your configuration to a new device. The database (`marginmonitor.db`) and logs stay local.

## Docker

```bash
docker compose up -d
```

Attach to the interactive menu:
```bash
docker attach marginmonitor
```

## Features

- **Balance monitoring** — polls customer edit pages, alerts when balance drops below threshold
- **Margin & Billed Min monitoring** — scrapes the Executive Summary report for per-customer margin and billed minutes
- **Async parallel quick checks** — fetch all balances concurrently (menu option 0)
- **Dual siren patterns** — rising/falling sweep (balance) vs alternating two-tone (margin)
- **Non-blocking alerts** — sirens play in background threads, monitoring continues
- **Desktop notifications** — Windows toast notifications via `plyer`
- **Webhook alerts** — Telegram and Slack webhook support with HTML formatting
- **Alert cooldown** — configurable cooldown per customer to prevent alert storms
- **SQLite history** — persistent balance and margin history with auto-retention
- **CSV export** — export balance/margin history for reporting
- **Named profiles** — save/load multiple config profiles (e.g. weekday, weekend, high-alert)
- **Active hours scheduling** — limit monitoring to specific days and time windows
- **Health HTTP endpoint** — Uptime Kuma / Prometheus compatible (`GET /health`)
- **JSON logging** — toggle structured JSON log output
- **Crash recovery** — auto-restarts after 10s on unexpected errors
- **DB dedup** — skips duplicate inserts when values haven't changed
- **Priority-aware display** — balance lines `[B]`, margin lines `[M]`, monitored flag

## Usage

```
  Instacall Monitoring Tool  v2.0
  ------------------------------------
  Profile: default
  Monitored: 18
  Interval: 30s  |  Balance alert below -500.0
  Margin alert below 30%  |  Billed min above 70
  Summary: outbound / 5m
  Cooldown: 300s
  Audio: ON  |  Webhooks: none
  ------------------------------------
  0. Quick Check - Parallel (Async)
  1. Start Monitor
  2. Quick Check - Balances
  3. Quick Check - Summary
  4. Quick Check - Full
  5. Settings
  6. Profiles
  7. History
  8. Export
  9. Exit
```

| Option | Description |
|--------|-------------|
| 0. Quick Check - Parallel (Async) | Fetch all balances + summary concurrently with aiohttp |
| 1. Start Monitor | Continuous loop — balancess → summary → repeat |
| 2. Quick Check - Balances | One-shot balance fetch for all monitored IDs |
| 3. Quick Check - Summary | One-shot margin/billed-min for all active customers |
| 4. Quick Check - Full | Balance + summary in a single pass |
| 5. Settings | Edit thresholds, interval, IDs, webhooks, siren, scheduling |
| 6. Profiles | Create, duplicate, delete, switch named config profiles |
| 7. History | View balance and margin history from SQLite DB |
| 8. Export | Export history to CSV files |

## Console Output

```
  Monitor started at 2026-07-22 23:45:00
  IDs: 18
  Interval: 30s
  Balance alert below -500.0  |  Margin alert below 30% & Billed > 70 min
  Summary: outbound / 5m
  Cooldown: 300s
  Audio: ON (quiet mode)
  Webhooks: none
  DB retention: 30 days
  Active hours: 24/7
  Database: marginmonitor.db
  Ctrl+C to stop.
  ------------------------------
  Running first check now...

  [B] [23:45:01] TestCo (ID: 18)  Balance -229.8235  / Credit: 600.00 (Remaining: 370.18)
  [M] [23:45:02] TestCo (ID: 18)  Margin 52.9%  |  Billed 1167.8 min [MONITORED]

  [23:45:05] Cycle complete. Next check at 23:45:35 (~30s)
```

## Settings

All configurable via menu option 5 or by editing `settings.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `customer_ids` | `["18"]` | Monitored customer IDs |
| `check_interval_seconds` | `600` | Seconds between cycles |
| `balance_threshold` | `-365.0` | Alert when balance drops below |
| `margin_threshold` | `30.0` | Alert when margin drops below % |
| `billed_min_threshold` | `70.0` | Only alert if billed minutes exceed |
| `request_timeout` | `10` | HTTP request timeout (seconds) |
| `summary_direction` | `outbound` | Summary report direction |
| `summary_interval` | `5m` | Summary report time window |
| `audio_enabled` | `true` | Enable/disable siren |
| `alert_cooldown_seconds` | `300` | Minimum seconds between alerts per customer |
| `db_retention_days` | `30` | Auto-purge history older than N days (0=keep all) |
| `webhook_url` | `""` | Slack or Telegram webhook URL |
| `webhook_type` | `none` | `none`, `telegram`, or `slack` |
| `telegram_chat_id` | `""` | Telegram chat ID for alerts |
| `active_hours_start` | `""` | HH:MM start (empty=24/7) |
| `active_hours_end` | `""` | HH:MM end (empty=24/7) |
| `active_days` | `""` | `mon,tue,wed,thu,fri` (empty=all) |
| `health_port` | `0` | Health HTTP server port (0=disabled) |
| `logging_json` | `false` | JSON structured log output |
| `siren_loops` | `10` | Siren sweep loops |
| `siren_min_freq` | `2200` | Lowest siren frequency (Hz) |
| `siren_max_freq` | `3500` | Highest siren frequency (Hz) |
| `siren_step_freq` | `130` | Frequency step between beeps |
| `siren_tone_duration` | `50` | Duration of each beep (ms) |

## Architecture

```
instacall_monitoring_tool/
  menu.py          — CLI entry point (interactive menu)
  config.py        — Settings dataclass, validation, logging, profiles
  auth.py          — CSRF login, session creation, re-auth helper
  scrapers.py      — fetch_balance (customer page), fetch_summary_report
  monitor.py       — Continuous loop with scheduling, dedup, crash recovery
  quick.py         — One-shot balance/summary/full/parallel checks
  async_fetch.py   — aiohttp parallel balance + summary fetchers
  alerts.py        — SirenManager, desktop notifications, webhook dispatch
  display.py       — Console formatting ([B]/[M] prefixes)
  retry.py         — Retry with 2s/5s backoff on transient failures
  persistence.py   — SQLite ORM (insert, query, purge, dedup helpers)
  notifications.py — Telegram/Slack webhook sender
  health.py        — HTTP health endpoint (/health returns monitor.status)
  export.py        — CSV export for balance/margin history
  settings.json    — Runtime configuration
  profiles.json    — Named config profiles
  .env             — Portal credentials (never committed)
  tests/           — 35 pytest tests
```

## Files (Runtime)

| File | Purpose |
|------|---------|
| `balance_monitor.log` | Rotating log (5 files x 1 MB) |
| `monitor.status` | JSON health status (alive, last_check, error_count) |
| `marginmonitor.db` | SQLite database — balance + margin history |

## Requirements

- Python 3.10+
- Windows for `winsound` audio (sirens silently skipped on macOS/Linux)
- Portal credentials in `.env`
