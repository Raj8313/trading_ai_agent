"""Console Notifier Adapter.

Default notifier printing alerts and messages directly to stdout.
"""

from trading_agent.ports.notifier import NotifierPort


class ConsoleNotifierAdapter(NotifierPort):
    """Console implementation of NotifierPort."""

    def send_notification(self, message: str) -> bool:
        """Print the notification message to standard output."""
        print(f"\n📢 [NOTIFICATION]\n{message}\n")
        return True
