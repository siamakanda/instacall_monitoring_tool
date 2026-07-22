from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable

from plyer import notification

from config import Settings
from notifications import send_webhook


class SirenManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playing = False
        self._last_alert_time: dict[str, float] = {}
        self._last_margin_alert_time: dict[str, float] = {}

    @property
    def is_playing(self) -> bool:
        return self._playing

    def can_alert(self, customer_id: str, cooldown: float) -> bool:
        now = time.time()
        last = self._last_alert_time.get(customer_id, 0)
        if now - last < cooldown:
            return False
        self._last_alert_time[customer_id] = now
        return True

    def can_margin_alert(self, customer_id: str, cooldown: float) -> bool:
        now = time.time()
        last = self._last_margin_alert_time.get(customer_id, 0)
        if now - last < cooldown:
            return False
        self._last_margin_alert_time[customer_id] = now
        return True

    def play_rising_falling(self, settings: Settings) -> None:
        if not self._acquire():
            return
        try:
            for _ in range(settings.siren_loops):
                for freq in range(settings.siren_min_freq, settings.siren_max_freq, settings.siren_step_freq):
                    _beep(freq, settings.siren_tone_duration)
                for freq in range(settings.siren_max_freq, settings.siren_min_freq, -settings.siren_step_freq):
                    _beep(freq, settings.siren_tone_duration)
        finally:
            self._release()

    def play_alternating(self, settings: Settings) -> None:
        if not self._acquire():
            return
        try:
            tone = max(settings.siren_tone_duration, 100)
            for _ in range(settings.siren_loops * 2):
                _beep(settings.siren_min_freq, tone)
                _beep(settings.siren_max_freq, tone)
        finally:
            self._release()

    def _acquire(self) -> bool:
        with self._lock:
            if self._playing:
                return False
            self._playing = True
            return True

    def _release(self) -> None:
        with self._lock:
            self._playing = False


def _beep(freq: int, duration: int) -> None:
    if sys.platform == "win32":
        import winsound
        winsound.Beep(freq, duration)
    else:
        pass


def play_siren(
    manager: SirenManager,
    play_fn: Callable[[], None],
    customer_name: str,
    customer_id: str,
    alert_type: str,
) -> None:
    """Play siren in background thread, or skip if already playing."""
    if manager.is_playing:
        print(f"Siren skipped (already playing) - {alert_type} for {customer_name} (ID: {customer_id})")
        return
    print(f"Siren for {customer_name} (ID: {customer_id}) - {alert_type}...")
    threading.Thread(target=play_fn, daemon=True).start()


_siren_manager = SirenManager()


def trigger_balance_alert(
    customer_id: str,
    current_balance: float,
    customer_name: str,
    settings: Settings,
    manager: SirenManager = _siren_manager,
) -> None:
    notification.notify(
        title="BALANCE CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) balance dropped to {current_balance:.4f}!",
        app_name="Instacall Monitoring Tool",
        timeout=10,
    )
    logging.warning(
        f"ALERT TRIGGERED for {customer_name} (ID: {customer_id}): "
        f"Balance {current_balance:.4f} < {settings.balance_threshold}"
    )
    send_webhook(settings, "BALANCE CRITICAL ALERT",
                 f"{customer_name} (ID: {customer_id}) balance dropped to {current_balance:.4f}")

    if settings.audio_enabled:
        play_siren(
            manager,
            lambda: manager.play_rising_falling(settings),
            customer_name,
            customer_id,
            "BALANCE",
        )


def trigger_margin_alert(
    customer_id: str,
    margin: float,
    billed_min: float,
    customer_name: str,
    settings: Settings,
    manager: SirenManager = _siren_manager,
) -> None:
    notification.notify(
        title="MARGIN CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) Margin dropped to {margin:.1f}%! (Billed: {billed_min:.1f} min)",
        app_name="Instacall Monitoring Tool",
        timeout=10,
    )
    logging.warning(
        f"MARGIN ALERT for {customer_name} (ID: {customer_id}): "
        f"Margin {margin:.1f}% < {settings.margin_threshold}%, "
        f"Billed {billed_min:.1f} > {settings.billed_min_threshold}"
    )
    send_webhook(settings, "MARGIN CRITICAL ALERT",
                 f"{customer_name} (ID: {customer_id}) Margin: {margin:.1f}% (Billed: {billed_min:.1f} min)")

    if settings.audio_enabled:
        play_siren(
            manager,
            lambda: manager.play_alternating(settings),
            customer_name,
            customer_id,
            "MARGIN",
        )
