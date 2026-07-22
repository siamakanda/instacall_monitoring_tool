from __future__ import annotations

import logging
import re
import traceback
from datetime import date
from typing import Optional, Union

import requests
from bs4 import BeautifulSoup

from auth import ensure_authenticated, perform_login
from config import BASE_EDIT_URL, SUMMARY_REPORT_URL, Settings
from retry import retry_with_backoff

BalanceResult = tuple[Optional[str], Optional[float], Optional[float], Optional[str]]
SummaryResult = tuple[dict[str, dict[str, object]], Optional[str]]


def _extract_balance_error(result: BalanceResult) -> Optional[str]:
    return result[3] if result and len(result) == 4 else None


def _extract_summary_error(result: SummaryResult) -> Optional[str]:
    return result[1] if result and len(result) == 2 else None


def fetch_balance(session: requests.Session, customer_id: str, timeout: int = 10) -> BalanceResult:
    return retry_with_backoff(_do_fetch_balance, _extract_balance_error, session, customer_id, timeout)


def _do_fetch_balance(session: requests.Session, customer_id: str, timeout: int = 10) -> BalanceResult:
    edit_url = f"{BASE_EDIT_URL}{customer_id}"

    try:
        resp = session.get(edit_url, timeout=timeout, allow_redirects=True)

        if not ensure_authenticated(session, resp, timeout):
            return None, None, None, "re-login failed"

        if "login" in resp.url.lower():
            resp = session.get(edit_url, timeout=timeout, allow_redirects=True)

        if resp.status_code != 200:
            return None, None, None, f"HTTP {resp.status_code}"

        soup = BeautifulSoup(resp.text, 'html.parser')

        name_input = (
            soup.find('input', {'name': 'name'})
            or soup.find('input', {'id': 'name'})
            or soup.find('input', {'name': 'customer_name'})
            or soup.find('input', {'name': 'company'})
            or soup.find('input', {'id': 'customer_name'})
        )
        customer_name = name_input.get('value', 'N/A').strip() if name_input else 'N/A'

        balance_input = soup.find('input', {'name': 'balance'}) or soup.find('input', {'id': 'balance'})
        balance: Optional[float] = None
        if balance_input and balance_input.get('value'):
            try:
                balance = float(balance_input['value'])
            except ValueError:
                return None, None, None, f"non-numeric balance: '{balance_input['value']}'"
        else:
            return None, None, None, "balance field not found"

        credit_input = (
            soup.find('input', {'name': 'credit_limit'})
            or soup.find('input', {'id': 'credit_limit'})
            or soup.find('input', {'name': 'credit'})
            or soup.find('input', {'id': 'credit'})
        )
        credit_limit: Optional[float] = None
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


def fetch_summary_report(session: requests.Session, settings: Settings) -> dict[str, dict[str, object]]:
    result = retry_with_backoff(_do_fetch_summary, _extract_summary_error, session, settings)
    return result[0]


def _do_fetch_summary(session: requests.Session, settings: Settings) -> SummaryResult:
    today = date.today().isoformat()
    timeout = settings.request_timeout
    direction = settings.summary_direction
    interval = settings.summary_interval
    params = {
        "direction": direction,
        "interval": interval,
        "date_from": today,
        "date_to": today,
    }
    results: dict[str, dict[str, object]] = {}
    error: Optional[str] = None

    try:
        resp = session.get(SUMMARY_REPORT_URL, params=params, timeout=timeout, allow_redirects=True)
    except requests.exceptions.Timeout:
        error = f"timeout ({timeout}s)"
        logging.error(f"Summary report - {error}")
        return results, error
    except requests.exceptions.ConnectionError:
        error = "connection error"
        logging.error(f"Summary report - {error}")
        return results, error
    except Exception as e:
        error = str(e)
        logging.error(f"Summary report - unexpected error: {e}\n{traceback.format_exc()}")
        return results, error

    if not ensure_authenticated(session, resp, timeout):
        error = "re-login failed"
        return results, error

    if "login" in resp.url.lower():
        try:
            resp = session.get(SUMMARY_REPORT_URL, params=params, timeout=timeout, allow_redirects=True)
        except requests.exceptions.Timeout:
            error = f"timeout after re-login ({timeout}s)"
            return results, error
        except requests.exceptions.ConnectionError:
            error = "connection error after re-login"
            return results, error

    if resp.status_code != 200:
        error = f"HTTP {resp.status_code}"
        logging.error(f"Summary report returned {error}")
        return results, error

    try:
        soup = BeautifulSoup(resp.text, 'html.parser')
    except Exception as e:
        error = str(e)
        logging.error(f"Summary report - parse error: {e}")
        return results, error

    cust_panel = soup.find('div', id='panel-cust')
    if not cust_panel:
        error = "#panel-cust not found"
        logging.error(f"Summary report - {error}")
        return results, error

    tbody = cust_panel.find('tbody')
    if not tbody:
        error = "Customer table tbody not found"
        logging.error(f"Summary report - {error}")
        return results, error

    for row in tbody.find_all('tr', recursive=False):
        classes = row.get('class', [])
        if 'sr-trunk-row' in classes:
            continue

        cells = row.find_all('td')
        if len(cells) < 13:
            continue

        vol_name = cells[1].find('span', class_='sr-vol-name')
        customer_name = vol_name.get_text(strip=True) if vol_name else 'N/A'

        billed_min: Optional[float] = None
        billed_span = cells[7].find('span', class_='rpt-num')
        if billed_span:
            try:
                billed_min = float(billed_span.get_text(strip=True).replace(',', ''))
            except ValueError:
                pass

        margin: Optional[float] = None
        margin_span = cells[12].find('span', class_='rpt-asr-pill')
        if margin_span:
            text = margin_span.get_text(strip=True).replace('%', '')
            try:
                margin = float(text)
            except ValueError:
                pass

        expand_btn = cells[0].find('button', class_='sr-expand-btn')
        cust_id_from_html: Optional[str] = None
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
    return results, None
