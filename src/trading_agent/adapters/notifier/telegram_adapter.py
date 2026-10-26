"""Telegram Notifier Adapter.

Sends messages via the official Telegram Bot HTTP API.
Gracefully falls back to ConsoleNotifier if unconfigured or on failure.
"""

import logging
from typing import Optional
import requests

from trading_agent.adapters.notifier.console_adapter import ConsoleNotifierAdapter
from trading_agent.ports.notifier import NotifierPort

logger = logging.getLogger(__name__)


class TelegramNotifierAdapter(NotifierPort):
    """Telegram implementation of NotifierPort with Console fallback."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        fallback_notifier: Optional[NotifierPort] = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the Telegram adapter.

        If bot_token or chat_id is missing, falls back to fallback_notifier (Console).
        """
        self.bot_token = bot_token.strip() if bot_token else None
        self.chat_id = chat_id.strip() if chat_id else None
        self.fallback = fallback_notifier or ConsoleNotifierAdapter()
        self.timeout = timeout_seconds
        self._warned_unconfigured = False

    @property
    def is_configured(self) -> bool:
        """Check if both token and chat_id are present."""
        return bool(self.bot_token and self.chat_id)

    def send_notification(self, message: str) -> bool:
        """Send notification via Telegram API or fallback to console."""
        if not self.is_configured:
            if not self._warned_unconfigured:
                logger.warning(
                    "Telegram notifier is not configured (missing token or chat_id). "
                    "Falling back to ConsoleNotifier."
                )
                self._warned_unconfigured = True
            return self.fallback.send_notification(message)

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                return True
            logger.error(
                "Telegram API returned status %s: %s",
                response.status_code,
                response.text,
            )
        except Exception as e:
            logger.error("Failed to send Telegram notification: %s", e)

        # Fall back to console upon transmission error so alert is never lost
        self.fallback.send_notification(message)
        return False
