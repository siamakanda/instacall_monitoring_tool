import logging
import threading
import winsound
from plyer import notification

_siren_lock = threading.Lock()
_siren_playing = False


def _play_rising_falling(settings):
    for _ in range(settings["siren_loops"]):
        for freq in range(settings["siren_min_freq"], settings["siren_max_freq"], settings["siren_step_freq"]):
            winsound.Beep(freq, settings["siren_tone_duration"])
        for freq in range(settings["siren_max_freq"], settings["siren_min_freq"], -settings["siren_step_freq"]):
            winsound.Beep(freq, settings["siren_tone_duration"])


def _play_alternating(settings):
    tone = max(settings["siren_tone_duration"], 100)
    for _ in range(settings["siren_loops"] * 2):
        winsound.Beep(settings["siren_min_freq"], tone)
        winsound.Beep(settings["siren_max_freq"], tone)


def _play_in_background(play_fn, settings):
    global _siren_playing
    try:
        _siren_playing = True
        play_fn(settings)
    finally:
        _siren_playing = False


def trigger_balance_alert(customer_id, current_balance, customer_name, settings):
    notification.notify(
        title="BALANCE CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) balance dropped to {current_balance:.4f}!",
        app_name="Instacall Monitoring Tool",
        timeout=10
    )
    logging.warning(f"ALERT TRIGGERED for {customer_name} (ID: {customer_id}): Balance {current_balance:.4f} < {settings['balance_threshold']}")
    if settings.get("audio_enabled", True):
        with _siren_lock:
            if _siren_playing:
                print(f"Siren skipped (already playing) - BALANCE for {customer_name} (ID: {customer_id})")
                return
        print(f"Siren for {customer_name} (ID: {customer_id}) - BALANCE...")
        threading.Thread(target=_play_in_background, args=(_play_rising_falling, settings), daemon=True).start()


def trigger_margin_alert(customer_id, margin, billed_min, customer_name, settings):
    notification.notify(
        title="MARGIN CRITICAL ALERT",
        message=f"{customer_name} (ID: {customer_id}) Margin dropped to {margin:.1f}%! (Billed: {billed_min:.1f} min)",
        app_name="Instacall Monitoring Tool",
        timeout=10
    )
    logging.warning(
        f"MARGIN ALERT for {customer_name} (ID: {customer_id}): "
        f"Margin {margin:.1f}% < {settings['margin_threshold']}%, "
        f"Billed {billed_min:.1f} > {settings['billed_min_threshold']}"
    )
    if settings.get("audio_enabled", True):
        with _siren_lock:
            if _siren_playing:
                print(f"Siren skipped (already playing) - MARGIN for {customer_name} (ID: {customer_id})")
                return
        print(f"Siren for {customer_name} (ID: {customer_id}) - MARGIN...")
        threading.Thread(target=_play_in_background, args=(_play_alternating, settings), daemon=True).start()
