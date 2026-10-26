"""Unit tests for configuration management."""

import logging
from trading_agent.config import Settings


def test_watchlist_deduplication(caplog):
    """Verify duplicate watchlist entries are removed and logged as warnings."""
    with caplog.at_level(logging.WARNING):
        settings = Settings(watchlist="RELIANCE.NS, TCS.NS, RELIANCE.NS, INFY.NS, TCS.NS")
        assert settings.watchlist == ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
        assert "Duplicate watchlist entries detected and removed" in caplog.text


def test_watchlist_from_list():
    """Verify watchlist deduplication when passed as a list with duplicates."""
    settings = Settings(watchlist=["TCS.NS", "TCS.NS", "HDFCBANK.NS"])
    assert settings.watchlist == ["TCS.NS", "HDFCBANK.NS"]
