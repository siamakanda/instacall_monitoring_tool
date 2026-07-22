# Instacall Monitoring Tool

Real-time balance and margin monitoring for the Instacall Switch Portal. Alerts via desktop notifications and audible sirens when thresholds are breached.

## Features

- **Balance monitoring** — polls customer edit pages, alerts when balance drops below threshold
- **Margin & Billed Min monitoring** — scrapes the Executive Summary report for per-customer margin and billed minutes
- **Dual siren patterns** — rising/falling sweep (balance) vs alternating two-tone (margin) so you know which alert fired without looking
- **Non-blocking alerts** — sirens play in background threads, monitoring continues uninterrupted
- **Desktop notifications** — Windows toast notifications via `plyer`
- **Crash recovery** — auto-restarts after 10s on unexpected errors
- **Health status file** — `monitor.status` for uptime/error tracking
- **Quick checks** — one-shot balance or summary pulls without starting the loop
- **Adjustable settings** — all thresholds, intervals, and siren params editable from the menu or `settings.json`

## Setup

```bash
# 1. Clone
git clone https://github.com/siamakanda/Client_Balance_Alert.git
cd Client_Balance_Alert

# 2. Create .env with your portal credentials
cp .env.example .env
# Edit .env: add PORTAL_USERNAME and PORTAL_PASSWORD

# 3. Run setup (creates venv, installs deps)
setup_and_run.bat
```

Or manually:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python menu.py
```

## Usage

```
  Instacall Monitoring Tool
  ------------------------------------
  Monitored: 18, 22, 35
  Interval: 10 min  |  Balance alert below -365.0
  Margin alert below 30%  |  Billed min above 70
  Summary: outbound / 5m
  Audio: ON
  ------------------------------------
  1. Start Monitor
  2. Quick Check - Balances
  3. Quick Check - Summary
  4. Quick Check - Full
  5. Settings
  6. Exit
```

| Option | Description |
|--------|-------------|
| 1. Start Monitor | Continuous loop — checks balances then summary, repeats |
| 2. Quick Check - Balances | One-shot balance fetch for all monitored IDs |
| 3. Quick Check - Summary | One-shot margin/billed-min for all active customers |
| 4. Quick Check - Full | Balance + summary in a single pass |
| 5. Settings | Edit thresholds, interval, IDs, siren params, audio toggle |
| 6. Exit | Quit |

## Output Format

```
[B] [22:39:35] See International (ID: 18)  Balance -229.8235  / Credit: 600.00 (Remaining: 370.18)
[M] [22:39:37] HMK LEADS (ID: 169)  Margin 39.5%  |  Billed 2779.2 min
[M] [22:39:37] See International (ID: 18)  Margin 52.9%  |  Billed 1167.8 min [MONITORED]
```

- `[B]` = Balance line
- `[M]` = Margin line
- `[MONITORED]` = Customer is in your monitored IDs list

## Settings

All configurable via menu option 5 or by editing `settings.json`:

| Key | Default | Description |
|-----|---------|-------------|
| `customer_ids` | `["18"]` | Monitored customer IDs (balance checks) |
| `check_interval_seconds` | `600` | Seconds between monitoring cycles |
| `balance_threshold` | `-365.0` | Alert when balance drops below this |
| `margin_threshold` | `30.0` | Alert when margin drops below this % |
| `billed_min_threshold` | `70.0` | Only alert if billed minutes exceed this |
| `request_timeout` | `10` | HTTP request timeout in seconds |
| `summary_direction` | `"outbound"` | Summary report direction |
| `summary_interval` | `"5m"` | Summary report time window |
| `audio_enabled` | `true` | Enable/disable siren (notifications still fire) |
| `siren_loops` | `10` | Number of siren sweep loops |
| `siren_min_freq` | `2200` | Lowest siren frequency (Hz) |
| `siren_max_freq` | `3500` | Highest siren frequency (Hz) |
| `siren_step_freq` | `130` | Frequency step between beeps |
| `siren_tone_duration` | `50` | Duration of each beep (ms) |

## Architecture

```
MarginMonitor/
  menu.py         — CLI entry point (numbered menu)
  config.py       — Settings load/save, validation, logging, status file
  auth.py         — Portal login (CSRF token flow), session creation
  scrapers.py     — fetch_balance (customer edit page), fetch_summary_report
  alerts.py       — Threaded sirens, desktop notifications, audio toggle
  monitor.py      — Continuous monitoring loop with crash supervisor
  quick.py        — One-shot balance/summary/full checks
  display.py      — Shared output formatting ([B]/[M] prefixes)
  retry.py        — Unified retry with 2s/5s backoff on transient failures
  settings.json   — All adjustable configuration
  .env            — Portal credentials (username/password)
```

## Files

| File | Purpose |
|------|---------|
| `balance_monitor.log` | Rotating log (5 files x 1 MB) |
| `monitor.status` | JSON health status (alive, last_check, error_count) |

## Requirements

- Python 3.10+
- Windows (uses `winsound` for audio)
- Portal credentials in `.env`
