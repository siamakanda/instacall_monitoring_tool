from __future__ import annotations

import logging
import threading

import requests

from config import Settings


def send_webhook(settings: Settings, title: str, message: str) -> None:
    if not settings.webhook_url or settings.webhook_type == "none":
        return

    def _send() -> None:
        try:
            if settings.webhook_type == "slack":
                payload = {
                    "text": f"*{title}*\n{message}",
                }
                requests.post(settings.webhook_url, json=payload, timeout=10)
            elif settings.webhook_type == "telegram":
                payload = {
                    "chat_id": settings.telegram_chat_id,
                    "text": f"<b>{title}</b>\n{message}",
                    "parse_mode": "HTML",
                }
                requests.post(settings.webhook_url, json=payload, timeout=10)
        except Exception as e:
            logging.warning(f"Webhook send failed: {e}")

    threading.Thread(target=_send, daemon=True).start()
