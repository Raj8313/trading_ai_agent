"""Unit tests for YFinanceMarketDataAdapter."""

import datetime as dt
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
import pytest

from trading_agent.adapters.market_data.yfinance_adapter import (
    MarketDataFetchError,
    YFinanceMarketDataAdapter,
)
from trading_agent.domain.models import DataQualityIssue


def test_empty_dataframe_handling():
    """Verify empty DataFrame from yfinance logs data quality issue and returns empty list."""
    mock_storage = MagicMock()
    adapter = YFinanceMarketDataAdapter(storage_adapter=mock_storage, max_retries=1)

    empty_df = pd.DataFrame()
    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.history.return_value = empty_df
        mock_ticker_cls.return_value = mock_instance

        bars = adapter.fetch_daily_bars("EMPTY.NS", dt.date(2024, 1, 1), dt.date(2024, 1, 10))

        assert bars == []
        mock_storage.save_data_quality_issue.assert_called_once()
        issue_arg = mock_storage.save_data_quality_issue.call_args[0][0]
        assert isinstance(issue_arg, DataQualityIssue)
        assert "Empty dataframe" in issue_arg.issue


def test_corrupted_data_nan_rows_skipped():
    """Verify NaN rows are skipped without crashing, valid rows preserved."""
    mock_storage = MagicMock()
    adapter = YFinanceMarketDataAdapter(storage_adapter=mock_storage, max_retries=1)

    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    data = {
        "Open": [100.0, np.nan, 102.0],
        "High": [105.0, 110.0, 106.0],
        "Low": [98.0, 95.0, 100.0],
        "Close": [103.0, 105.0, 104.0],
        "Volume": [10000, 20000, 15000],
    }
    df = pd.DataFrame(data, index=dates)

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.history.return_value = df
        mock_ticker_cls.return_value = mock_instance

        bars = adapter.fetch_daily_bars("NAN_TEST.NS", dt.date(2024, 1, 1), dt.date(2024, 1, 3))

        # Row 2 was skipped because of NaN
        assert len(bars) == 2
        assert bars[0].date == dt.date(2024, 1, 1)
        assert bars[1].date == dt.date(2024, 1, 3)

        # Issue should have been recorded for the skipped row
        assert mock_storage.save_data_quality_issue.call_count == 1
        issue = mock_storage.save_data_quality_issue.call_args[0][0]
        assert "NaN values" in issue.issue


def test_invalid_price_bounds_skipped():
    """Verify rows violating High >= Low bounds are skipped safely."""
    mock_storage = MagicMock()
    adapter = YFinanceMarketDataAdapter(storage_adapter=mock_storage, max_retries=1)

    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    # Row 1 has High (90) < Low (100) -> invalid bar
    data = {
        "Open": [95.0, 102.0],
        "High": [90.0, 106.0],
        "Low": [100.0, 100.0],
        "Close": [95.0, 104.0],
        "Volume": [10000, 15000],
    }
    df = pd.DataFrame(data, index=dates)

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.history.return_value = df
        mock_ticker_cls.return_value = mock_instance

        bars = adapter.fetch_daily_bars("INVALID.NS", dt.date(2024, 1, 1), dt.date(2024, 1, 2))

        assert len(bars) == 1
        assert bars[0].date == dt.date(2024, 1, 2)
        assert mock_storage.save_data_quality_issue.call_count == 1


def test_retry_on_network_failure():
    """Verify adapter retries 3 times and raises MarketDataFetchError when all fail."""
    mock_storage = MagicMock()
    adapter = YFinanceMarketDataAdapter(
        storage_adapter=mock_storage, max_retries=3, backoff_factor=0.01
    )

    with patch("yfinance.Ticker") as mock_ticker_cls:
        mock_instance = MagicMock()
        mock_instance.history.side_effect = ConnectionError("Network unreachable")
        mock_ticker_cls.return_value = mock_instance

        with pytest.raises(MarketDataFetchError) as exc_info:
            adapter.fetch_daily_bars("FAIL.NS", dt.date(2024, 1, 1), dt.date(2024, 1, 10))

        assert "Network unreachable" in str(exc_info.value)
        assert mock_instance.history.call_count == 3
        mock_storage.save_data_quality_issue.assert_called_once()
