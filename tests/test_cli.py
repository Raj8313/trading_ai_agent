"""Unit tests for CLI commands."""

import datetime as dt
from unittest.mock import MagicMock, patch
import pytest

from trading_agent.adapters.market_data.yfinance_adapter import MarketDataFetchError
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.cli import run_backfill, run_score
from trading_agent.domain.models import Bar, CheckResult, Score, TradeBand


def make_bar_series(symbol: str, count: int = 35) -> list[Bar]:
    """Helper to generate a series of synthetic bars."""
    start_date = dt.date(2024, 1, 1)
    bars = []
    for i in range(count):
        price = 1000.0 + i * 5.0
        bars.append(
            Bar(
                date=start_date + dt.timedelta(days=i),
                open=price,
                high=price + 10.0,
                low=price - 10.0,
                close=price + 2.0,
                volume=100000 + i * 5000,
            )
        )
    return bars


@patch("trading_agent.cli.YFinanceMarketDataAdapter")
def test_run_backfill_success(mock_mkt_adapter_cls, tmp_path):
    """Verify run_backfill successfully populates scores into SQLite."""
    db_file = tmp_path / "cli_test.db"

    mock_instance = MagicMock()
    # Return 35 bars for any symbol
    mock_instance.fetch_daily_bars.side_effect = lambda sym, s, e: make_bar_series(sym, 35)
    mock_mkt_adapter_cls.return_value = mock_instance

    exit_code = run_backfill(
        days=30,
        watchlist=["TEST1.NS", "TEST2.NS"],
        benchmark_symbol="^NSEI",
        db_path=str(db_file),
    )
    assert exit_code == 0

    storage = SqliteStorageAdapter(str(db_file))
    counts = storage.get_score_counts_by_symbol()

    # 35 bars total -> index 20 to 34 are scored -> 15 scored bars per symbol
    assert counts["TEST1.NS"] == 15
    assert counts["TEST2.NS"] == 15
    assert counts["^NSEI"] == 15


@patch("trading_agent.cli.YFinanceMarketDataAdapter")
def test_run_backfill_symbol_failure_continues(mock_mkt_adapter_cls, tmp_path):
    """Verify backfill continues if one symbol fails, and exits with 1."""
    db_file = tmp_path / "cli_fail_test.db"

    mock_instance = MagicMock()

    def side_effect(sym, s, e):
        if sym == "FAIL.NS":
            raise MarketDataFetchError(sym, "Network timeout")
        return make_bar_series(sym, 35)

    mock_instance.fetch_daily_bars.side_effect = side_effect
    mock_mkt_adapter_cls.return_value = mock_instance

    exit_code = run_backfill(
        days=30,
        watchlist=["OK.NS", "FAIL.NS"],
        benchmark_symbol="^NSEI",
        db_path=str(db_file),
    )
    assert exit_code == 1

    storage = SqliteStorageAdapter(str(db_file))
    counts = storage.get_score_counts_by_symbol()
    assert "OK.NS" in counts
    assert "FAIL.NS" not in counts


def test_run_score_success(tmp_path, capsys):
    """Verify run_score prints score details for an existing record."""
    db_file = tmp_path / "score_test.db"
    storage = SqliteStorageAdapter(str(db_file))

    check = CheckResult(
        check_name="Trend Check",
        passed=True,
        points_awarded=25,
        max_points=25,
        rationale="Price > 20 EMA and rising",
    )
    score = Score(
        symbol="RELIANCE.NS",
        date=dt.date(2024, 1, 15),
        check_results=[check],
        total_points=25,
        band=TradeBand.NONE,
    )
    storage.save_score(score)

    # Query with RELIANCE (without .NS)
    exit_code = run_score("RELIANCE", "2024-01-15", db_path=str(db_file))
    assert exit_code == 0

    captured = capsys.readouterr().out
    assert "CONFIDENCE METER SCORE BREAKDOWN" in captured
    assert "RELIANCE.NS" in captured
    assert "Trend Check" in captured
    assert "TOTAL POINTS: 25 / 25" in captured


def test_run_score_not_found(tmp_path, capsys):
    """Verify run_score returns 1 and error message if score is missing."""
    db_file = tmp_path / "score_empty.db"
    exit_code = run_score("UNKNOWN.NS", "2024-01-15", db_path=str(db_file))
    assert exit_code == 1
    captured = capsys.readouterr().out
    assert "No score record found" in captured


def test_run_score_invalid_date(tmp_path, capsys):
    """Verify run_score returns 1 if date format is invalid."""
    db_file = tmp_path / "score_invalid_date.db"
    exit_code = run_score("RELIANCE", "15-01-2024", db_path=str(db_file))
    assert exit_code == 1
    captured = capsys.readouterr().out
    assert "Invalid date format" in captured
