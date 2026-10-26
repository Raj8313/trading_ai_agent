"""Unit tests for backtest CLI simulation workflow and exports."""

import csv
import datetime as dt
import sys
from unittest.mock import MagicMock, patch
import pytest

from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.backtest.cli import backtest_cli, run_backtest_simulation
from trading_agent.domain.models import Bar, CheckResult, Score, TradeBand


def make_bar_series(start_date: dt.date, count: int = 30) -> list[Bar]:
    """Helper to generate contiguous daily bars."""
    bars = []
    for i in range(count):
        d = start_date + dt.timedelta(days=i)
        price = 1000.0 + (i * 2.0)
        bars.append(
            Bar(
                date=d,
                open=price,
                high=price + 10.0,
                low=price - 5.0,
                close=price + 4.0,
                volume=100000,
            )
        )
    return bars


def make_test_score(symbol: str, date_val: dt.date, points: int = 85, meter_version: str = "v2") -> Score:
    """Helper to create a Score model."""
    check = CheckResult(
        check_name="Trend Check",
        passed=True,
        points_awarded=25,
        max_points=25,
        rationale="Rising trend",
    )
    return Score(
        symbol=symbol,
        date=date_val,
        check_results=[check],
        total_points=points,
        band=Score.calculate_band(points),
        meter_version=meter_version,
    )


@patch("trading_agent.backtest.cli.YFinanceMarketDataAdapter")
def test_backtest_cli_coverage_check_refuses_when_incomplete(mock_mkt_cls, tmp_path):
    """Verify backtest refuses execution if any symbol has <95% score coverage."""
    db_file = tmp_path / "test_cov.db"
    storage = SqliteStorageAdapter(str(db_file))

    start_date = dt.date(2024, 1, 1)
    end_date = dt.date(2024, 1, 20)

    # Mock market data: returns 20 daily bars for benchmark
    mock_mkt = MagicMock()
    mock_mkt.fetch_daily_bars.return_value = make_bar_series(start_date, count=20)
    mock_mkt_cls.return_value = mock_mkt

    # Save only 5 scores for SYMBOL_A (5/20 = 25% < 95%)
    for i in range(5):
        storage.save_score(make_test_score("SYMBOL_A.NS", start_date + dt.timedelta(days=i), 85))

    ret = run_backtest_simulation(
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_file),
        watchlist=["SYMBOL_A.NS"],
        benchmark_symbol="^NSEI",
    )
    assert ret == 1


@patch("trading_agent.backtest.cli.YFinanceMarketDataAdapter")
def test_backtest_cli_success_and_csv_export(mock_mkt_cls, tmp_path):
    """Verify successful backtest execution, persistence, and CSV export."""
    db_file = tmp_path / "test_success.db"
    csv_file = tmp_path / "trades_export.csv"
    storage = SqliteStorageAdapter(str(db_file))

    start_date = dt.date(2024, 1, 1)
    end_date = dt.date(2024, 1, 25)

    mock_mkt = MagicMock()
    # 35 bars to allow entry and exits
    bars = make_bar_series(start_date, count=35)
    mock_mkt.fetch_daily_bars.return_value = bars
    mock_mkt_cls.return_value = mock_mkt

    # Save 25 daily scores for TEST.NS (100% coverage >= 95%)
    for i in range(25):
        d = start_date + dt.timedelta(days=i)
        storage.save_score(make_test_score("TEST.NS", d, 85))

    ret = run_backtest_simulation(
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_file),
        export_csv=str(csv_file),
        watchlist=["TEST.NS"],
        benchmark_symbol="^NSEI",
    )
    assert ret == 0

    # Verify CSV was written
    assert csv_file.exists()
    with open(csv_file, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) >= 2  # header + at least 1 trade row
        assert reader[0][0] == "symbol"
        assert reader[0][1] == "signal_date"
        assert reader[1][0] == "TEST.NS"


def test_backtest_cli_invalid_date_order(tmp_path):
    """Verify start_date >= end_date returns error code 1."""
    ret = run_backtest_simulation(
        start_date=dt.date(2024, 1, 20),
        end_date=dt.date(2024, 1, 10),
        db_path=str(tmp_path / "invalid.db"),
    )
    assert ret == 1


def test_backtest_cli_main_entry_success(monkeypatch):
    """Verify backtest_cli parses valid arguments and exits with code 0."""
    test_args = ["backtest", "--start", "2024-01-01", "--end", "2024-01-20"]
    monkeypatch.setattr(sys, "argv", test_args)

    with patch("trading_agent.backtest.cli.run_backtest_simulation", return_value=0) as mock_sim:
        with pytest.raises(SystemExit) as exc:
            backtest_cli()
        assert exc.value.code == 0
        mock_sim.assert_called_once_with(
            start_date=dt.date(2024, 1, 1),
            end_date=dt.date(2024, 1, 20),
            db_path=None,
            export_csv=None,
            meter_version=None,
        )


def test_backtest_cli_refuses_when_symbol_has_only_v1_scores(tmp_path):
    """Verify backtest refuses execution if symbol has only legacy v1 scores in range."""
    db_file = tmp_path / "test_v1_guard.db"
    storage = SqliteStorageAdapter(str(db_file))
    start_date = dt.date(2024, 1, 1)
    end_date = dt.date(2024, 1, 20)

    # Save v1 scores
    for i in range(20):
        d = start_date + dt.timedelta(days=i)
        storage.save_score(make_test_score("TEST_V1.NS", d, 85, meter_version="v1"))

    ret = run_backtest_simulation(
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_file),
        watchlist=["TEST_V1.NS"],
        meter_version="v2",
    )
    assert ret == 1


def test_backtest_cli_refuses_mixed_meter_versions(tmp_path):
    """Verify backtest refuses execution on mixed meter versions."""
    db_file = tmp_path / "test_mixed.db"
    storage = SqliteStorageAdapter(str(db_file))
    start_date = dt.date(2024, 1, 1)
    end_date = dt.date(2024, 1, 20)

    # Date 1 has only v1, Date 2 has v2
    storage.save_score(make_test_score("MIXED.NS", start_date, 85, meter_version="v1"))
    storage.save_score(make_test_score("MIXED.NS", start_date + dt.timedelta(days=1), 85, meter_version="v2"))

    ret = run_backtest_simulation(
        start_date=start_date,
        end_date=end_date,
        db_path=str(db_file),
        watchlist=["MIXED.NS"],
        meter_version="v2",
    )
    assert ret == 1


def test_backtest_cli_invalid_date_formats(monkeypatch):
    """Verify backtest_cli exits with code 1 on malformed start or end dates."""
    monkeypatch.setattr(sys, "argv", ["backtest", "--start", "invalid-date"])
    with pytest.raises(SystemExit) as exc:
        backtest_cli()
    assert exc.value.code == 1

    monkeypatch.setattr(sys, "argv", ["backtest", "--end", "invalid-date"])
    with pytest.raises(SystemExit) as exc2:
        backtest_cli()
    assert exc2.value.code == 1
