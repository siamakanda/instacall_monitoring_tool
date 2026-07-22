import requests
import logging
from bs4 import BeautifulSoup
from config import get_credentials, HEADERS, LOGIN_URL


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


def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session
