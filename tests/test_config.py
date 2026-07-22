from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Settings, validate_settings


class TestSettings:
    def test_default_settings(self) -> None:
        s = Settings()
        assert s.customer_ids == ["18"]
        assert s.check_interval_seconds == 600
        assert s.balance_threshold == -365.0
        assert s.alert_cooldown_seconds == 300
        assert s.webhook_type == "none"

    def test_from_dict_partial(self) -> None:
        s = Settings.from_dict({"customer_ids": ["42", "99"], "check_interval_seconds": 120})
        assert s.customer_ids == ["42", "99"]
        assert s.check_interval_seconds == 120
        assert s.balance_threshold == -365.0  # default

    def test_from_dict_ignores_unknown(self) -> None:
        s = Settings.from_dict({"customer_ids": ["1"], "unknown_field": "foo"})
        assert s.customer_ids == ["1"]
        assert not hasattr(s, "unknown_field")

    def test_to_dict_roundtrip(self) -> None:
        s = Settings(customer_ids=["5", "10"], balance_threshold=-200.0)
        d = s.to_dict()
        s2 = Settings.from_dict(d)
        assert s2.customer_ids == s.customer_ids
        assert s2.balance_threshold == s.balance_threshold

    def test_validate_valid(self) -> None:
        errors = validate_settings(Settings())
        assert len(errors) == 0

    def test_validate_empty_ids(self) -> None:
        errors = validate_settings(Settings(customer_ids=[]))
        assert any("customer_ids" in e for e in errors)

    def test_validate_bad_direction(self) -> None:
        errors = validate_settings(Settings(summary_direction="invalid"))
        assert any("summary_direction" in e for e in errors)

    def test_validate_bad_webhook_type(self) -> None:
        errors = validate_settings(Settings(webhook_type="discord"))
        assert any("webhook_type" in e for e in errors)

    def test_validate_negative_cooldown(self) -> None:
        errors = validate_settings(Settings(alert_cooldown_seconds=-1))
        assert any("alert_cooldown_seconds" in e for e in errors)
