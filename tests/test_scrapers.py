from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers import _do_fetch_balance, _do_fetch_summary
from config import Settings

BALANCE_HTML = """<html><body>
<input name="name" value="TestCo"/>
<input name="balance" value="-150.5000"/>
<input name="credit_limit" value="600"/>
</body></html>"""

BALANCE_HTML_NO_CREDIT = """<html><body>
<input name="name" value="MinimalCo"/>
<input name="balance" value="-50.0000"/>
</body></html>"""

SUMMARY_HTML = """<html><body>
<div id="panel-cust">
<table><tbody>
<tr>
<td><button class="sr-expand-btn" onclick="someJs('ct18')"></button></td>
<td><span class="sr-vol-name">TestCo</span></td>
<td></td><td></td><td></td><td></td><td></td>
<td><span class="rpt-num">1,234.5</span></td>
<td></td><td></td><td></td><td></td>
<td><span class="rpt-asr-pill">52.9%</span></td>
</tr>
<tr>
<td><button class="sr-expand-btn" onclick="foo('ct99')"></button></td>
<td><span class="sr-vol-name">OtherCo</span></td>
<td></td><td></td><td></td><td></td><td></td>
<td><span class="rpt-num">500</span></td>
<td></td><td></td><td></td><td></td>
<td><span class="rpt-asr-pill">28.3%</span></td>
</tr>
</tbody></table>
</div>
</body></html>"""


class TestScrapers:
    def test_fetch_balance_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/customers?edit=18"
        mock_resp.status_code = 200
        mock_resp.text = BALANCE_HTML

        session = MagicMock()
        session.get.return_value = mock_resp

        name, balance, credit, error = _do_fetch_balance(session, "18", 10)
        assert name == "TestCo"
        assert balance == -150.5
        assert credit == 600.0
        assert error is None

    def test_fetch_balance_no_credit(self) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/customers?edit=18"
        mock_resp.status_code = 200
        mock_resp.text = BALANCE_HTML_NO_CREDIT

        session = MagicMock()
        session.get.return_value = mock_resp

        name, balance, credit, error = _do_fetch_balance(session, "18", 10)
        assert name == "MinimalCo"
        assert balance == -50.0
        assert credit is None
        assert error is None

    def test_fetch_balance_http_error(self) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/customers?edit=18"
        mock_resp.status_code = 404

        session = MagicMock()
        session.get.return_value = mock_resp

        name, balance, credit, error = _do_fetch_balance(session, "18", 10)
        assert balance is None
        assert "HTTP 404" in (error or "")

    def test_fetch_summary_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/summary_report"
        mock_resp.status_code = 200
        mock_resp.text = SUMMARY_HTML

        session = MagicMock()
        session.get.return_value = mock_resp

        settings = Settings()
        results, error = _do_fetch_summary(session, settings)

        assert error is None
        assert "18" in results
        assert results["18"]["name"] == "TestCo"
        assert results["18"]["margin"] == 52.9
        assert results["18"]["billed_min"] == 1234.5
        assert "99" in results
        assert results["99"]["margin"] == 28.3
        assert results["99"]["billed_min"] == 500.0

    def test_fetch_summary_no_panel(self) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/summary_report"
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><div id='wrong'></div></body></html>"

        session = MagicMock()
        session.get.return_value = mock_resp

        settings = Settings()
        results, error = _do_fetch_summary(session, settings)

        assert error is not None
        assert "panel-cust" in (error or "")
