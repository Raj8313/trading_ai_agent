"""Notifier port interface."""

from abc import ABC, abstractmethod


class NotifierPort(ABC):
    """Abstract port for dispatching user notifications (e.g., Console, Telegram)."""

    @abstractmethod
    def send_notification(self, message: str) -> bool:
        """Send a notification message.

        Args:
            message: Formatted text message to send.

        Returns:
            True if sent successfully, False otherwise.
        """
        pass
