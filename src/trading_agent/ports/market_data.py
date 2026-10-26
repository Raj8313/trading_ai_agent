"""Market data port interface."""

from abc import ABC, abstractmethod
import datetime as dt
from trading_agent.domain.models import Bar


class MarketDataPort(ABC):
    """Abstract port for fetching historical and market bar data."""

    @abstractmethod
    def fetch_daily_bars(
        self, symbol: str, start_date: dt.date, end_date: dt.date
    ) -> list[Bar]:
        """Fetch daily OHLCV bars for a symbol between start_date and end_date (inclusive).

        Args:
            symbol: Ticker symbol (e.g. RELIANCE.NS, ^NSEI)
            start_date: Start date for historical window
            end_date: End date for historical window

        Returns:
            List of sorted Bar objects (ascending by date)
        """
        pass
