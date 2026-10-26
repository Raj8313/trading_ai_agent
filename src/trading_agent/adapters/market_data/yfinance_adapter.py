"""YFinance Market Data Adapter implementing MarketDataPort.

Fetches historical daily OHLCV bars for NSE symbols (e.g., RELIANCE.NS, ^NSEI)
using Yahoo Finance, with resilient retries, backoff, and robust data cleansing.
"""

import datetime as dt
import logging
import time
from typing import Optional
import pandas as pd
import yfinance as yf

from trading_agent.domain.models import Bar, DataQualityIssue
from trading_agent.ports.market_data import MarketDataPort
from trading_agent.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class MarketDataFetchError(Exception):
    """Raised when fetching market data fails after all retries."""

    def __init__(self, symbol: str, reason: str) -> None:
        self.symbol = symbol
        self.reason = reason
        super().__init__(f"Failed to fetch market data for {symbol}: {reason}")


class YFinanceMarketDataAdapter(MarketDataPort):
    """Yahoo Finance implementation of MarketDataPort."""

    def __init__(
        self,
        storage_adapter: Optional[StoragePort] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        """Initialize adapter with optional storage for data quality audit trail."""
        self.storage_adapter = storage_adapter
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _record_quality_issue(
        self, symbol: str, issue_date: Optional[dt.date], description: str
    ) -> None:
        """Helper to log and persist data quality anomalies."""
        logger.warning("[%s] Data quality issue: %s (date=%s)", symbol, description, issue_date)
        if self.storage_adapter:
            try:
                self.storage_adapter.save_data_quality_issue(
                    DataQualityIssue(
                        symbol=symbol,
                        date=issue_date,
                        issue=description,
                    )
                )
            except Exception as e:
                logger.error("Could not persist data quality issue: %s", e)

    def fetch_daily_bars(
        self, symbol: str, start_date: dt.date, end_date: dt.date
    ) -> list[Bar]:
        """Fetch daily bars with 3x retry and backoff, skipping corrupt bars.

        Args:
            symbol: Ticker symbol (e.g. RELIANCE.NS, ^NSEI).
            start_date: Start date.
            end_date: End date.

        Returns:
            List of clean, validated Bar objects ascending by date.

        Raises:
            MarketDataFetchError: If data fetching fails after all retries.
        """
        start_str = start_date.strftime("%Y-%m-%d")
        # yfinance end date is exclusive, so add 1 day to include end_date
        end_str = (end_date + dt.timedelta(days=1)).strftime("%Y-%m-%d")

        last_exception: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    "Fetching data for %s from %s to %s (attempt %d/%d)",
                    symbol,
                    start_str,
                    end_str,
                    attempt,
                    self.max_retries,
                )
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_str, end=end_str, auto_adjust=False)

                if df is None or df.empty:
                    self._record_quality_issue(
                        symbol,
                        None,
                        f"Empty dataframe returned by yfinance for date range {start_str} to {end_str}",
                    )
                    return []

                return self._parse_dataframe(symbol, df)

            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Attempt %d/%d failed for %s: %s",
                    attempt,
                    self.max_retries,
                    symbol,
                    exc,
                )
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        err_msg = str(last_exception) if last_exception else "Unknown fetch error"
        self._record_quality_issue(
            symbol,
            None,
            f"Network/fetch failure after {self.max_retries} retries: {err_msg}",
        )
        raise MarketDataFetchError(symbol, err_msg)

    def _parse_dataframe(self, symbol: str, df: pd.DataFrame) -> list[Bar]:
        """Clean and validate DataFrame rows into Bar models, skipping corrupted rows."""
        bars: list[Bar] = []

        # Standardize column names
        col_map = {col.lower(): col for col in df.columns}
        required = ["open", "high", "low", "close", "volume"]
        for req in required:
            if req not in col_map:
                self._record_quality_issue(
                    symbol,
                    None,
                    f"Missing required column '{req}' in dataframe columns: {list(df.columns)}",
                )
                return []

        for index_val, row in df.iterrows():
            # Extract date
            if isinstance(index_val, pd.Timestamp):
                bar_date = index_val.date()
            elif isinstance(index_val, dt.datetime):
                bar_date = index_val.date()
            elif isinstance(index_val, dt.date):
                bar_date = index_val
            else:
                try:
                    bar_date = dt.date.fromisoformat(str(index_val)[:10])
                except Exception:
                    self._record_quality_issue(
                        symbol, None, f"Could not parse index date value: {index_val}"
                    )
                    continue

            open_val = row[col_map["open"]]
            high_val = row[col_map["high"]]
            low_val = row[col_map["low"]]
            close_val = row[col_map["close"]]
            vol_val = row[col_map["volume"]]

            # Check for NaN / null
            if pd.isna(open_val) or pd.isna(high_val) or pd.isna(low_val) or pd.isna(close_val) or pd.isna(vol_val):
                self._record_quality_issue(
                    symbol,
                    bar_date,
                    f"Skipping row with NaN values: O={open_val}, H={high_val}, L={low_val}, C={close_val}, V={vol_val}",
                )
                continue

            try:
                bar = Bar(
                    date=bar_date,
                    open=float(open_val),
                    high=float(high_val),
                    low=float(low_val),
                    close=float(close_val),
                    volume=int(vol_val),
                )
                bars.append(bar)
            except Exception as val_err:
                self._record_quality_issue(
                    symbol,
                    bar_date,
                    f"Bar validation failed: {val_err}",
                )
                continue

        # Sort bars chronologically
        bars.sort(key=lambda b: b.date)
        return bars
