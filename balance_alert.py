import json
import os
import re
import time
import logging
import traceback
from logging.handlers import RotatingFileHandler
import requests
import winsound
from datetime import date
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from plyer import notification

# ============================================================
#                      CONSTANTS
# ============================================================
LOGIN_URL = "https://switchportal.instacall.digital/login"
BASE_EDIT_URL = "https://switchportal.instacall.digital/customers?edit="
SUMMARY_REPORT_URL = "https://switchportal.instacall.digital/summary_report"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

LOG_FILE = "balance_monitor.log"

DEFAULT_SETTINGS = {
    "customer_ids": ["18"],
    "check_interval_seconds": 600,
    "balance_threshold": -365.0,
    "margin_threshold": 30.0,
    "billed_min_threshold": 70.0,
    "request_timeout": 10,
    "summary_direction": "outbound",
    "summary_interval": "5m",
    "siren_loops": 15,
    "siren_min_freq": 1500,
    "siren_max_freq": 2600,
    "siren_step_freq": 100,
    "siren_tone_duration": 20,
}

SETTINGS_FILE = "settings.json"

# Rotating log: 5 files, 1 MB each
handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S"))
logging.basicConfig(level=logging.INFO, handlers=[handler])
console = logging.StreamHandler()
console.setLevel(logging.ERROR)
logging.getLogger('').addHandler(console)


# ============================================================
#                      SETTINGS
# ============================================================
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


# ============================================================
#                      CORE FUNCTIONS
# ============================================================
def get_credentials():
    load_dotenv()
    username = os.getenv("PORTAL_USERNAME")
    password = os.getenv("PORTAL_PASSWORD")
    if not username or not password:
        raise ValueError("Error: PORTAL_USERNAME or PASSWORD not found in .env file.")
    return username, password


def perform_login(session, timeout=10):
    username, password = get_credentials()
    try:
        login_init = session.get(LOGIN_URL, timeout=timeout)
        soup_login = BeautifulSoup(login_init.text, 'html.parser')
        csrf_input = soup_login.find('input', {'name': '_csrf'})
        csrf_token = csrf_input.get('value', '') if csrf_input else ""

        login_data = {"_csrf": csrf_token, "username": username, "password": password}
        login_response = session.post(LOGIN_URL, data=login_data, timeout=timeout)

        if login_response.status_code in [200, 302]:
            logging.info("Login successful.")
            return True
        else:
            logging.error(f"Login failed with HTTP {login_response.status_code}")
            return False
    except Exception as e:
        logging.error(f"Login exception: {e}")
        return False


def fetch_balance(session, customer_id, timeout=10):
    """Returns (customer_name, balance, credit_limit, error_reason).
       error_reason is None on success, a string on failure."""
    edit_url = f"{BASE_EDIT_URL}{customer_id}"

    try:
        cust_res = session.get(edit_url, timeout=timeout, allow_redirects=True)

        if "login" in cust_res.url.lower():
            logging.warning(f"Session expired for customer {customer_id}. Attempting re-login...")
            if perform_login(session, timeout):
                cust_res = session.get(edit_url, timeout=timeout, allow_redirects=True)
            else:
                return None, None, None, "re-login failed"

        if cust_res.status_code != 200:
            return None, None, None, f"HTTP {cust_res.status_code}"

        soup = BeautifulSoup(cust_res.text, 'html.parser')

        name_input = (
            soup.find('input', {'name': 'name'}) or
            soup.find('input', {'id': 'name'}) or
            soup.find('input', {'name': 'customer_name'}) or
            soup.find('input', {'name': 'company'}) or
            soup.find('input', {'id': 'customer_name'})
        )
        customer_name = name_input.get('value', 'N/A').strip() if name_input else 'N/A'

        balance_input = (
            soup.find('input', {'name': 'balance'}) or
            soup.find('input', {'id': 'balance'})
        )
        balance = None
        if balance_input and balance_input.get('value'):
            try:
                balance = float(balance_input['value'])
            except ValueError:
                return None, None, None, f"non-numeric balance: '{balance_input['value']}'"
        else:
            return None, None, None, "balance field not found"

        credit_input = (
            soup.find('input', {'name': 'credit_limit'}) or
            soup.find('input', {'id': 'credit_limit'}) or
            soup.find('input', {'name': 'credit'}) or
            soup.find('input', {'id': 'credit'})
        )
        credit_limit = None
        if credit_input and credit_input.get('value'):
            try:
                credit_limit = float(credit_input['value'])
            except ValueError:
                credit_limit = None

        return customer_name, balance, credit_limit, None

    except requests.exceptions.Timeout:
        return None, None, None, f"timeout ({timeout}s)"
    except requests.exceptions.ConnectionError:
        return None, None, None, "connection error"
    except Exception as e:
        logging.error(f"Customer {customer_id} - Unexpected error: {e}\n{traceback.format_exc()}")
        return None, None, None, str(e)


def play_siren(settings):
    for _ in range(settings["siren_loops"]):
        for freq in range(settings["siren_min_freq"], settings["siren_max_freq"], settings["siren_step_freq"]):
            winsound.Beep(freq, settings["siren_tone_duration"])
        for freq in range(settings["siren_max_freq"], settings["siren_min_freq"], -settings["siren_step_freq"]):
            winsound.Beep(freq, settings["siren_tone_duration"])


def trigger_alert(customer_id, current_balance, customer_name, settings):
    notification.notify(
        title="BALANCE CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) balance dropped to {current_balance:.4f}!",
        app_name="Instacall Balance Monitor",
        timeout=10
    )
    logging.warning(f"ALERT TRIGGERED for {customer_name} (ID: {customer_id}): Balance {current_balance:.4f} < {settings['balance_threshold']}")
    print(f"Playing siren for {customer_name} (ID: {customer_id})...")
    play_siren(settings)


def fetch_summary_report(session, settings):
    today = date.today().isoformat()
    timeout = settings["request_timeout"]
    direction = settings.get("summary_direction", "outbound")
    interval = settings.get("summary_interval", "5m")
    params = {
        "direction": direction,
        "interval": interval,
        "date_from": today,
        "date_to": today,
    }
    results = {}

    try:
        resp = session.get(SUMMARY_REPORT_URL, params=params, timeout=timeout, allow_redirects=True)

        if "login" in resp.url.lower():
            logging.warning("Summary report - session expired. Re-logging in...")
            if perform_login(session, timeout):
                resp = session.get(SUMMARY_REPORT_URL, params=params, timeout=timeout, allow_redirects=True)
            else:
                logging.error("Summary report - re-login failed.")
                return results

        if resp.status_code != 200:
            logging.error(f"Summary report returned HTTP {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, 'html.parser')

        cust_panel = soup.find('div', id='panel-cust')
        if not cust_panel:
            logging.error("Summary report - #panel-cust not found.")
            return results

        tbody = cust_panel.find('tbody')
        if not tbody:
            logging.error("Summary report - Customer table tbody not found.")
            return results

        for row in tbody.find_all('tr', recursive=False):
            classes = row.get('class', [])
            if 'sr-trunk-row' in classes:
                continue

            cells = row.find_all('td')
            if len(cells) < 13:
                continue

            vol_name = cells[1].find('span', class_='sr-vol-name')
            customer_name = vol_name.get_text(strip=True) if vol_name else 'N/A'

            billed_min = None
            billed_span = cells[7].find('span', class_='rpt-num')
            if billed_span:
                try:
                    billed_min = float(billed_span.get_text(strip=True).replace(',', ''))
                except ValueError:
                    pass

            margin = None
            margin_span = cells[12].find('span', class_='rpt-asr-pill')
            if margin_span:
                text = margin_span.get_text(strip=True).replace('%', '')
                try:
                    margin = float(text)
                except ValueError:
                    pass

            expand_btn = cells[0].find('button', class_='sr-expand-btn')
            cust_id_from_html = None
            if expand_btn and expand_btn.get('onclick'):
                match = re.search(r"ct(\d+)", expand_btn.get('onclick', ''))
                if match:
                    cust_id_from_html = match.group(1)

            if cust_id_from_html:
                results[cust_id_from_html] = {
                    'name': customer_name,
                    'margin': margin,
                    'billed_min': billed_min,
                }

        logging.info(f"Summary report parsed - {len(results)} customers found.")
        return results

    except requests.exceptions.Timeout:
        logging.error("Summary report - request timed out.")
        return results
    except requests.exceptions.ConnectionError:
        logging.error("Summary report - network connection error.")
        return results
    except Exception as e:
        logging.error(f"Summary report - unexpected error: {e}\n{traceback.format_exc()}")
        return results


# ============================================================
#                      MONITOR
# ============================================================
def run_monitor(settings):
    customer_ids = settings["customer_ids"]
    balance_threshold = settings["balance_threshold"]
    margin_threshold = settings["margin_threshold"]
    billed_min_threshold = settings["billed_min_threshold"]
    interval = settings["check_interval_seconds"]
    timeout = settings["request_timeout"]

    alert_status = {cid: False for cid in customer_ids}
    margin_alert_status = {cid: False for cid in customer_ids}

    print("=" * 60)
    print("Instacall Balance Monitor - MULTI-CUSTOMER MODE")
    print(f"Monitoring IDs: {customer_ids}")
    print(f"Interval: {interval // 60} min")
    print(f"Balance Threshold: < {balance_threshold}")
    print(f"Margin Alert: < {margin_threshold}% & Billed > {billed_min_threshold} min")
    print(f"Summary: {settings.get('summary_direction', 'outbound')} / {settings.get('summary_interval', '5m')}")
    print(f"Logging to: {LOG_FILE}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    if not perform_login(session, timeout):
        logging.critical("Initial login failed.")
        return

    try:
        while True:
            for cid in customer_ids:
                customer_name, balance, credit_limit, error = fetch_balance(session, cid, timeout)

                if balance is not None:
                    remaining_credit = None
                    if credit_limit is not None:
                        remaining_credit = credit_limit + balance

                    credit_str = f" / Credit: {credit_limit:.2f}" if credit_limit is not None else ""
                    remaining_str = f" (Remaining: {remaining_credit:.2f})" if remaining_credit is not None else ""
                    print(f"[{time.strftime('%H:%M:%S')}] {customer_name} (ID: {cid}) - Balance: {balance:.4f}{credit_str}{remaining_str}")

                    if credit_limit is not None and remaining_credit is not None:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f} | Credit: {credit_limit:.2f} | Remaining: {remaining_credit:.2f}")
                    elif credit_limit is not None:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f} | Credit: {credit_limit:.2f}")
                    else:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f}")

                    if balance < balance_threshold:
                        if not alert_status[cid]:
                            trigger_alert(cid, balance, customer_name, settings)
                            alert_status[cid] = True
                    else:
                        if alert_status[cid]:
                            logging.info(f"Customer {cid} ({customer_name}) - Balance recovered to {balance:.4f}. Alert disarmed.")
                            alert_status[cid] = False
                else:
                    logging.warning(f"Customer {cid} - fetch error: {error}")
                    print(f"[{time.strftime('%H:%M:%S')}] Customer {cid} - FETCH FAILED ({error})")

                time.sleep(0.5)

            summary = fetch_summary_report(session, settings)
            for cid, data in summary.items():
                margin = data['margin']
                billed_min = data['billed_min']
                name = data['name']

                margin_str = f"{margin:.1f}%" if margin is not None else "N/A"
                billed_str = f"{billed_min:.1f}" if billed_min is not None else "N/A"
                monitored = " [MONITORED]" if cid in customer_ids else ""
                print(f"[{time.strftime('%H:%M:%S')}] {name} (ID: {cid}) - Margin: {margin_str} | Billed Min: {billed_str}{monitored}")

                if margin is not None:
                    logging.info(f"Customer {cid} ({name}) - Margin: {margin:.1f}% | Billed Min: {billed_str}")

                if cid in customer_ids and margin is not None and billed_min is not None:
                    if margin < margin_threshold and billed_min > billed_min_threshold:
                        if not margin_alert_status[cid]:
                            notification.notify(
                                title="MARGIN CRITICAL ALERT",
                                message=f"{name} (ID: {cid}) Margin dropped to {margin:.1f}%! (Billed: {billed_min:.1f} min)",
                                app_name="Instacall Balance Monitor",
                                timeout=10
                            )
                            logging.warning(f"MARGIN ALERT for {name} (ID: {cid}): Margin {margin:.1f}% < {margin_threshold}%, Billed {billed_min:.1f} > {billed_min_threshold}")
                            print(f"Playing siren for {name} (ID: {cid}) - MARGIN ALERT...")
                            play_siren(settings)
                            margin_alert_status[cid] = True
                    else:
                        if margin_alert_status[cid]:
                            logging.info(f"Customer {cid} ({name}) - Margin recovered to {margin:.1f}%. Alert disarmed.")
                            margin_alert_status[cid] = False

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n[-] Interrupted. Shutting down...")
        logging.info("Monitor stopped by user (Ctrl+C).")


def _print_balance_line(cid, customer_name, balance, credit_limit, error):
    if balance is not None:
        remaining = None
        if credit_limit is not None:
            remaining = credit_limit + balance
        credit_str = f" / Credit: {credit_limit:.2f}" if credit_limit is not None else ""
        remaining_str = f" (Remaining: {remaining:.2f})" if remaining is not None else ""
        print(f"  [{cid}] {customer_name}: Balance {balance:.4f}{credit_str}{remaining_str}")
    else:
        print(f"  [{cid}] FETCH FAILED ({error})")


def run_quick_check_full(settings):
    customer_ids = settings["customer_ids"]
    timeout = settings["request_timeout"]
    session = requests.Session()
    session.headers.update(HEADERS)

    print("Logging in...")
    if not perform_login(session, timeout):
        print("Login failed!")
        return

    print(f"\n--- Balance Check ({len(customer_ids)} customers) ---")
    for cid in customer_ids:
        customer_name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        _print_balance_line(cid, customer_name, balance, credit_limit, error)
        time.sleep(0.3)

    print(f"\n--- Summary Report (Margin + Billed Min) ---")
    summary = fetch_summary_report(session, settings)
    if not summary:
        print("  No data returned.")
    else:
        for cid, data in summary.items():
            margin = data['margin']
            billed_min = data['billed_min']
            name = data['name']
            margin_str = f"{margin:.1f}%" if margin is not None else "N/A"
            billed_str = f"{billed_min:.1f}" if billed_min is not None else "N/A"
            monitored = " [MONITORED]" if cid in customer_ids else ""
            print(f"  [{cid}] {name}: Margin {margin_str} | Billed Min {billed_str}{monitored}")
    print("Done.\n")


def run_quick_check_balance(settings):
    customer_ids = settings["customer_ids"]
    timeout = settings["request_timeout"]
    session = requests.Session()
    session.headers.update(HEADERS)

    print("Logging in...")
    if not perform_login(session, timeout):
        print("Login failed!")
        return

    print(f"\n--- Balance Check ({len(customer_ids)} customers) ---")
    for cid in customer_ids:
        customer_name, balance, credit_limit, error = fetch_balance(session, cid, timeout)
        _print_balance_line(cid, customer_name, balance, credit_limit, error)
        time.sleep(0.3)
    print("Done.\n")


def run_quick_check_summary(settings):
    session = requests.Session()
    session.headers.update(HEADERS)

    print("Logging in...")
    if not perform_login(session, settings["request_timeout"]):
        print("Login failed!")
        return

    print("\n--- Summary Report (Margin + Billed Min) ---")
    summary = fetch_summary_report(session, settings)
    if not summary:
        print("  No data returned.")
    else:
        for cid, data in summary.items():
            margin = data['margin']
            billed_min = data['billed_min']
            name = data['name']
            margin_str = f"{margin:.1f}%" if margin is not None else "N/A"
            billed_str = f"{billed_min:.1f}" if billed_min is not None else "N/A"
            monitored = " [MONITORED]" if cid in settings["customer_ids"] else ""
            print(f"  [{cid}] {name}: Margin {margin_str} | Billed Min {billed_str}{monitored}")
    print("Done.\n")
