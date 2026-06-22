import os
import sys
import time
import requests
import winsound
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from plyer import notification

# Load credentials from .env file
load_dotenv()

USERNAME = os.getenv("PORTAL_USERNAME")
PASSWORD = os.getenv("PORTAL_PASSWORD")

if not USERNAME or not PASSWORD:
    raise ValueError("Error: PORTAL_USERNAME or PORTAL_PASSWORD not found in .env file.")

# Portal Endpoints
LOGIN_URL = "https://switchportal.instacall.digital/login"
CUSTOMER_EDIT_URL = "https://switchportal.instacall.digital/customers?edit=18"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
}

# --- CONFIGURATION ---
CHECK_INTERVAL_SECONDS = 30  # 10 minutes
ALERT_THRESHOLD = -260.0      # Triggers alert if balance drops past this value

def trigger_alert(current_balance):
    """Fires a Windows notification banner and loops an intense, rising/falling siren sound for an extended duration."""
    # Push Windows Toast Notification first
    notification.notify(
        title="⚠️ BALANCE CRITICAL ALERT",
        message=f"SeeInternational balance has dropped to {current_balance}! Immediate action required.",
        app_name="Instacall Balance Monitor",
        timeout=10
    )
    
    print("🔊 Playing extended high-intensity siren loop (approx. 10-12 seconds)...")
    
    # Increased to 15 iterations to make it ring for a much longer time
    for _ in range(15):
        # Rising pitch phase (1500Hz up to 2600Hz)
        for freq in range(1500, 2600, 100):
            winsound.Beep(freq, 20)
        # Falling pitch phase (2600Hz down to 1500Hz)
        for freq in range(2600, 1500, -100):
            winsound.Beep(freq, 20)

def fetch_balance():
    """Logs into the portal and retrieves the active balance."""
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        login_init = session.get(LOGIN_URL, timeout=10)
        soup_login = BeautifulSoup(login_init.text, 'html.parser')
        csrf_input = soup_login.find('input', {'name': '_csrf'})
        csrf_token = csrf_input.get('value', '') if csrf_input else ""
    except Exception:
        csrf_token = ""

    login_data = {"_csrf": csrf_token, "username": USERNAME, "password": PASSWORD}
    
    try:
        login_response = session.post(LOGIN_URL, data=login_data, timeout=10)
        if login_response.status_code not in [200, 302]:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Auth failed (HTTP {login_response.status_code})")
            return None
        
        cust_res = session.get(CUSTOMER_EDIT_URL, timeout=10)
        if cust_res.status_code == 200:
            soup = BeautifulSoup(cust_res.text, 'html.parser')
            balance_input = soup.find('input', {'name': 'balance'}) or soup.find('input', {'id': 'balance'})
            
            if balance_input:
                return float(balance_input.get('value', '0'))
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Could not fetch profile page (HTTP {cust_res.status_code})")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection error: {e}")
        
    return None

def main():
    print("=" * 60)
    print(f"Starting Instacall balance tracking loop (Interval: {CHECK_INTERVAL_SECONDS // 60}m)...")
    print(f"Target Alert Threshold: Less than {ALERT_THRESHOLD}")
    print("Press Ctrl+C to safely exit the monitor at any time.")
    print("=" * 60)

    try:
        while True:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            balance = fetch_balance()
            
            if balance is not None:
                print(f"[{timestamp}] Current Balance: {balance}")
                if balance < ALERT_THRESHOLD:
                    print(f"🚨 ALERT TRIGGERED: Balance {balance} is below threshold {ALERT_THRESHOLD}!")
                    trigger_alert(balance)
            else:
                print(f"[{timestamp}] Skipping cycle due to an endpoint error.")
                
            time.sleep(CHECK_INTERVAL_SECONDS)
            
    except KeyboardInterrupt:
        print("\n\n[-] Intercepted Ctrl+C. Cleaning up background session...")
        print("[+] Balance monitor stopped gracefully. Have a great day!")
        sys.exit(0)

if __name__ == "__main__":
    main()