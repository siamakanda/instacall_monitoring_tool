import os
import sys
import time
import logging
import traceback
import requests
import winsound
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from plyer import notification

# ============================================================
#                      CONFIGURATION BLOCK
# ============================================================
# 1. Load Environment Variables
load_dotenv()
USERNAME = os.getenv("PORTAL_USERNAME")
PASSWORD = os.getenv("PORTAL_PASSWORD")

# 2. Multi-Customer Target List (comma-separated)
RAW_IDS = os.getenv("CUSTOMER_IDS", "18")
CUSTOMER_IDS = [cid.strip() for cid in RAW_IDS.split(',') if cid.strip()]

if not USERNAME or not PASSWORD:
    raise ValueError("Error: PORTAL_USERNAME or PASSWORD not found in .env file.")
if not CUSTOMER_IDS:
    raise ValueError("Error: CUSTOMER_IDS is empty or not set in .env file.")

# 3. Monitoring & Alert Settings
CHECK_INTERVAL_SECONDS = 10   # 5 minutes
ALERT_THRESHOLD = -365.0       # Trigger threshold

# 4. Portal Endpoints & Network Tuning
LOGIN_URL = "https://switchportal.instacall.digital/login"
BASE_EDIT_URL = "https://switchportal.instacall.digital/customers?edit="
REQUEST_TIMEOUT = 10

# 5. Browser Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

# 6. Siren Customization
SIREN_LOOPS = 15
SIREN_MIN_FREQ = 1500
SIREN_MAX_FREQ = 2600
SIREN_STEP_FREQ = 100
SIREN_TONE_DURATION = 20

# 7. Logging Setup
LOG_FILE = "balance_monitor.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# Also print ERROR level messages to console for immediate visibility
console = logging.StreamHandler()
console.setLevel(logging.ERROR)
logging.getLogger('').addHandler(console)

# ============================================================
#                      GLOBAL STATE
# ============================================================
# Tracks whether an alert is currently active for each customer
alert_status = {cid: False for cid in CUSTOMER_IDS}


# ============================================================
#                      CORE FUNCTIONS
# ============================================================
def perform_login(session):
    """Performs the full login flow (GET CSRF -> POST credentials). Returns True on success."""
    try:
        login_init = session.get(LOGIN_URL, timeout=REQUEST_TIMEOUT)
        soup_login = BeautifulSoup(login_init.text, 'html.parser')
        csrf_input = soup_login.find('input', {'name': '_csrf'})
        csrf_token = csrf_input.get('value', '') if csrf_input else ""

        login_data = {"_csrf": csrf_token, "username": USERNAME, "password": PASSWORD}
        login_response = session.post(LOGIN_URL, data=login_data, timeout=REQUEST_TIMEOUT)

        if login_response.status_code in [200, 302]:
            logging.info("Login successful.")
            return True
        else:
            logging.error(f"Login failed with HTTP {login_response.status_code}")
            return False
    except Exception as e:
        logging.error(f"Login exception: {e}")
        return False


def fetch_balance(session, customer_id):
    """
    Fetches balance, customer name, and credit limit for a given customer ID.
    Handles session expiry by re-logging in automatically and retrying once.
    Returns a tuple: (customer_name, balance, credit_limit) or (None, None, None) on failure.
    """
    edit_url = f"{BASE_EDIT_URL}{customer_id}"

    try:
        # Attempt to fetch the customer edit page
        cust_res = session.get(edit_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)

        # --- SESSION EXPIRY DETECTION ---
        if "login" in cust_res.url.lower():
            logging.warning(f"Session expired for customer {customer_id}. Attempting re-login...")
            if perform_login(session):
                cust_res = session.get(edit_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            else:
                logging.error(f"Re-login failed for customer {customer_id}. Skipping.")
                return None, None, None

        # --- PARSE HTML ---
        if cust_res.status_code == 200:
            soup = BeautifulSoup(cust_res.text, 'html.parser')

            # ---- 1. Extract Customer Name ----
            name_input = (
                soup.find('input', {'name': 'name'}) or
                soup.find('input', {'id': 'name'}) or
                soup.find('input', {'name': 'customer_name'}) or
                soup.find('input', {'name': 'company'}) or
                soup.find('input', {'id': 'customer_name'})
            )
            customer_name = name_input.get('value', 'N/A').strip() if name_input else 'N/A'

            # ---- 2. Extract Balance ----
            balance_input = (
                soup.find('input', {'name': 'balance'}) or 
                soup.find('input', {'id': 'balance'})
            )
            balance = None
            if balance_input and balance_input.get('value'):
                try:
                    balance = float(balance_input['value'])
                except ValueError:
                    logging.error(f"Customer {customer_id} - Non-numeric balance: '{balance_input['value']}'")
                    return None, None, None
            else:
                logging.warning(f"Customer {customer_id} - Balance field not found.")
                return None, None, None

            # ---- 3. Extract Credit Limit ----
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
                    logging.warning(f"Customer {customer_id} - Non-numeric credit limit: '{credit_input['value']}'")
                    credit_limit = None

            # ---- 4. Debug logging: show which fields were found (optional) ----
            logging.debug(f"Customer {customer_id} - Name field found: {name_input['name'] if name_input else 'NOT FOUND'}")
            logging.debug(f"Customer {customer_id} - Credit field found: {credit_input['name'] if credit_input else 'NOT FOUND'}")

            return customer_name, balance, credit_limit

        else:
            logging.warning(f"Customer {customer_id} - Edit page returned HTTP {cust_res.status_code}")
            return None, None, None

    except requests.exceptions.Timeout:
        logging.error(f"Customer {customer_id} - Request timed out after {REQUEST_TIMEOUT}s.")
        return None, None, None
    except requests.exceptions.ConnectionError:
        logging.error(f"Customer {customer_id} - Network connection error (DNS / refused).")
        return None, None, None
    except Exception as e:
        logging.error(f"Customer {customer_id} - Unexpected error: {e}\n{traceback.format_exc()}")
        return None, None, None


def trigger_alert(customer_id, current_balance, customer_name="N/A"):
    """Fires a Windows notification and plays the siren for a specific customer."""
    notification.notify(
        title="⚠️ BALANCE CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) balance dropped to {current_balance:.4f}! Immediate top-up required.",
        app_name="Instacall Balance Monitor",
        timeout=10
    )

    logging.warning(f"🚨 ALERT TRIGGERED for {customer_name} (ID: {customer_id}): Balance {current_balance:.4f} < {ALERT_THRESHOLD}")

    print(f"🔊 Playing siren for {customer_name} (ID: {customer_id})...")
    for _ in range(SIREN_LOOPS):
        for freq in range(SIREN_MIN_FREQ, SIREN_MAX_FREQ, SIREN_STEP_FREQ):
            winsound.Beep(freq, SIREN_TONE_DURATION)
        for freq in range(SIREN_MAX_FREQ, SIREN_MIN_FREQ, -SIREN_STEP_FREQ):
            winsound.Beep(freq, SIREN_TONE_DURATION)


# ============================================================
#                      MAIN LOOP
# ============================================================
def main():
    print("=" * 60)
    print("Instacall Balance Monitor - MULTI-CUSTOMER MODE")
    print(f"Monitoring IDs: {CUSTOMER_IDS}")
    print(f"Interval: {CHECK_INTERVAL_SECONDS // 60} minutes")
    print(f"Threshold: < {ALERT_THRESHOLD}")
    print(f"Logging to: {LOG_FILE}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Initial login
    if not perform_login(session):
        logging.critical("Initial login failed. Exiting.")
        sys.exit(1)

    try:
        while True:
            for cid in CUSTOMER_IDS:
                customer_name, balance, credit_limit = fetch_balance(session, cid)

                if balance is not None:
                    # ---- Calculate Remaining Credit (deficit runway) ----
                    remaining_credit = None
                    if credit_limit is not None:
                        remaining_credit = credit_limit + balance  # e.g., 500 + (-328.82) = 171.18

                    # ---- CONSOLE OUTPUT (Human-readable) ----
                    credit_str = f" / Credit: {credit_limit:.2f}" if credit_limit is not None else ""
                    remaining_str = f" (Remaining: {remaining_credit:.2f})" if remaining_credit is not None else ""
                    print(f"[{time.strftime('%H:%M:%S')}] {customer_name} (ID: {cid}) - Balance: {balance:.4f}{credit_str}{remaining_str}")

                    # ---- LOG FILE OUTPUT (Detailed) ----
                    if credit_limit is not None and remaining_credit is not None:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f} | Credit: {credit_limit:.2f} | Remaining: {remaining_credit:.2f}")
                    elif credit_limit is not None:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f} | Credit: {credit_limit:.2f}")
                    else:
                        logging.info(f"Customer {cid} ({customer_name}) - Balance: {balance:.4f}")

                    # --- ALERT LOGIC (Spam Prevention) ---
                    if balance < ALERT_THRESHOLD:
                        if not alert_status[cid]:
                            trigger_alert(cid, balance, customer_name)
                            alert_status[cid] = True
                    else:
                        if alert_status[cid]:
                            logging.info(f"Customer {cid} ({customer_name}) - Balance recovered to {balance:.4f}. Alert disarmed.")
                            alert_status[cid] = False
                else:
                    logging.warning(f"Customer {cid} - Skipped due to fetch error.")
                    print(f"[{time.strftime('%H:%M:%S')}] Customer {cid} - ❌ FETCH FAILED (check log)")

                # Small delay between customers to avoid hammering the server
                time.sleep(0.5)

            # Wait for the next full cycle
            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n\n[-] Interrupted. Shutting down gracefully...")
        logging.info("Monitor stopped by user (Ctrl+C).")
        sys.exit(0)


if __name__ == "__main__":
    main()