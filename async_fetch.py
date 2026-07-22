from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup

from config import BASE_EDIT_URL, SUMMARY_REPORT_URL, Settings
from display import print_balance_line, print_summary_line


async def _fetch_balance_async(
    session: aiohttp.ClientSession,
    customer_id: str,
    timeout: int = 10,
) -> tuple[Optional[str], Optional[float], Optional[float], Optional[str]]:
    edit_url = f"{BASE_EDIT_URL}{customer_id}"
    try:
        async with session.get(edit_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None, None, None, f"HTTP {resp.status}"
            html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
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
    except asyncio.TimeoutError:
        return None, None, None, f"timeout ({timeout}s)"
    except Exception as e:
        return None, None, None, str(e)


async def fetch_balances_parallel(
    session: aiohttp.ClientSession,
    customer_ids: list[str],
    timeout: int = 10,
) -> list[tuple[str, Optional[str], Optional[float], Optional[float], Optional[str]]]:
    tasks = [_fetch_balance_async(session, cid, timeout) for cid in customer_ids]
    results = await asyncio.gather(*tasks)
    return [
        (cid, name, balance, credit, error)
        for cid, (name, balance, credit, error) in zip(customer_ids, results)
    ]


async def fetch_summary_async(
    session: aiohttp.ClientSession,
    settings: Settings,
) -> Optional[dict[str, dict[str, object]]]:
    from datetime import date
    import re

    today = date.today().isoformat()
    timeout = settings.request_timeout
    params = {
        "direction": settings.summary_direction,
        "interval": settings.summary_interval,
        "date_from": today,
        "date_to": today,
    }
    try:
        async with session.get(
            SUMMARY_REPORT_URL, params=params, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                logging.error(f"Summary report HTTP {resp.status}")
                return None
            html = await resp.text()
    except Exception as e:
        logging.error(f"Summary report fetch error: {e}")
        return None

    soup = BeautifulSoup(html, 'html.parser')
    cust_panel = soup.find('div', id='panel-cust')
    if not cust_panel:
        return None
    tbody = cust_panel.find('tbody')
    if not tbody:
        return None

    results: dict[str, dict[str, object]] = {}
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
        if expand_btn and expand_btn.get('onclick'):
            match = re.search(r"ct(\d+)", expand_btn.get('onclick', ''))
            if match:
                results[match.group(1)] = {
                    'name': customer_name,
                    'margin': margin,
                    'billed_min': billed_min,
                }
    return results
