"""Unit tests for SqliteStorageAdapter."""

import datetime as dt
import pytest
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.domain.models import (
    CheckResult,
    DataQualityIssue,
    ExitReason,
    Score,
    TradeBand,
    TradeRecord,
)


@pytest.fixture
def storage(tmp_path):
    """Provide a fresh SQLite adapter using a temporary database file."""
    db_file = tmp_path / "test_trading.db"
    return SqliteStorageAdapter(str(db_file))


def make_test_score(symbol: str, date_val: dt.date, points: int = 65) -> Score:
    """Helper to generate a test Score."""
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
    )


def test_sqlite_wal_mode(storage):
    """Verify database connection enables WAL journal mode."""
    with storage._get_connection() as conn:
        cursor = conn.execute("PRAGMA journal_mode;")
        mode = cursor.fetchone()[0]
        assert mode.upper() == "WAL"


def test_save_and_get_score(storage):
    """Verify persisting and reading a Score."""
    score = make_test_score("RELIANCE.NS", dt.date(2024, 1, 15), 65)
    storage.save_score(score)

    retrieved = storage.get_score("RELIANCE.NS", dt.date(2024, 1, 15))
    assert retrieved is not None
    assert retrieved.symbol == "RELIANCE.NS"
    assert retrieved.date == dt.date(2024, 1, 15)
    assert retrieved.total_points == 65
    assert retrieved.band == TradeBand.HALF
    assert len(retrieved.check_results) == 1
    assert retrieved.check_results[0].check_name == "Trend Check"


def test_score_idempotency_upsert(storage):
    """Verify saving the same (symbol, date) updates without duplicating rows."""
    date_val = dt.date(2024, 1, 15)
    score1 = make_test_score("INFY.NS", date_val, 45)
    storage.save_score(score1)

    counts_before = storage.get_score_counts_by_symbol()
    assert counts_before.get("INFY.NS") == 1

    # Update the score for the exact same date
    score2 = make_test_score("INFY.NS", date_val, 85)
    storage.save_score(score2)

    counts_after = storage.get_score_counts_by_symbol()
    # Row count must remain 1
    assert counts_after.get("INFY.NS") == 1

    retrieved = storage.get_score("INFY.NS", date_val)
    assert retrieved.total_points == 85
    assert retrieved.band == TradeBand.FULL


def test_get_all_scores_and_counts(storage):
    """Verify querying all scores and aggregation counts."""
    storage.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 10), 50))
    storage.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 11), 60))
    storage.save_score(make_test_score("WIPRO.NS", dt.date(2024, 1, 10), 70))

    tcs_scores = storage.get_all_scores_for_symbol("TCS.NS")
    assert len(tcs_scores) == 2
    assert tcs_scores[0].date == dt.date(2024, 1, 10)
    assert tcs_scores[1].date == dt.date(2024, 1, 11)

    counts = storage.get_score_counts_by_symbol()
    assert counts == {"TCS.NS": 2, "WIPRO.NS": 1}


def test_data_quality_issues_logging(storage):
    """Verify persisting and querying data quality issues."""
    issue1 = DataQualityIssue(
        symbol="TCS.NS",
        date=dt.date(2024, 1, 15),
        issue="Corrupted NaN row in High price",
    )
    issue2 = DataQualityIssue(
        symbol="INFY.NS",
        date=None,
        issue="Empty dataframe returned",
    )
    storage.save_data_quality_issue(issue1)
    storage.save_data_quality_issue(issue2)

    all_issues = storage.get_data_quality_issues()
    assert len(all_issues) == 2

    tcs_issues = storage.get_data_quality_issues("TCS.NS")
    assert len(tcs_issues) == 1
    assert tcs_issues[0].issue == "Corrupted NaN row in High price"


def test_sqlite_failure_raises_loudly(tmp_path):
    """Verify SQLite write failures raise loudly without being swallowed."""
    db_file = tmp_path / "readonly.db"
    adapter = SqliteStorageAdapter(str(db_file))

    # Drop the table so next save fails
    with adapter._get_connection() as conn:
        conn.execute("DROP TABLE scores;")

    score = make_test_score("FAIL.NS", dt.date(2024, 1, 1), 50)
    with pytest.raises(Exception):
        adapter.save_score(score)


def test_get_latest_scores(storage):
    """Verify retrieving the latest score for each symbol."""
    # TCS: 2 dates
    storage.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 10), 30))
    storage.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 15), 65))

    # INFY: 2 dates
    storage.save_score(make_test_score("INFY.NS", dt.date(2024, 1, 12), 40))
    storage.save_score(make_test_score("INFY.NS", dt.date(2024, 1, 16), 55))

    latest = storage.get_latest_scores()
    assert len(latest) == 2
    # Sorted by total_points DESC: TCS (65) then INFY (55)
    assert latest[0].symbol == "TCS.NS"
    assert latest[0].date == dt.date(2024, 1, 15)
    assert latest[0].total_points == 65

    assert latest[1].symbol == "INFY.NS"
    assert latest[1].date == dt.date(2024, 1, 16)
    assert latest[1].total_points == 55


def test_get_scores_for_symbol_in_range(storage):
    """Verify querying scores within a date window."""
    storage.save_score(make_test_score("RELIANCE.NS", dt.date(2024, 1, 5), 20))
    storage.save_score(make_test_score("RELIANCE.NS", dt.date(2024, 1, 10), 40))
    storage.save_score(make_test_score("RELIANCE.NS", dt.date(2024, 1, 15), 60))
    storage.save_score(make_test_score("RELIANCE.NS", dt.date(2024, 1, 20), 80))

    # Range: 2024-01-08 to 2024-01-16
    in_range = storage.get_scores_for_symbol_in_range(
        "RELIANCE.NS", dt.date(2024, 1, 8), dt.date(2024, 1, 16)
    )
    assert len(in_range) == 2
    assert in_range[0].date == dt.date(2024, 1, 10)
    assert in_range[1].date == dt.date(2024, 1, 15)


def test_database_busy_error_raised():
    """Verify DatabaseBusyError is raised when operational error contains locked."""
    from trading_agent.adapters.storage import DatabaseBusyError
    import sqlite3

    adapter = SqliteStorageAdapter(":memory:")
    # Mock query_fn to always raise sqlite3.OperationalError: database is locked
    def mock_query():
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(DatabaseBusyError) as exc_info:
        adapter._execute_read_query(mock_query)
    assert "Database busy" in str(exc_info.value)


def test_save_and_get_backtest_run_and_trades(storage):
    """Verify persisting and querying backtest runs and associated trades."""
    trade = TradeRecord(
        symbol="RELIANCE.NS",
        signal_date=dt.date(2024, 1, 10),
        entry_date=dt.date(2024, 1, 11),
        entry_price=2500.0,
        exit_date=dt.date(2024, 1, 15),
        exit_price=2600.0,
        exit_reason=ExitReason.TARGET,
        band=TradeBand.FULL,
        position_size=100000.0,
        gross_pnl=4000.0,
        net_pnl=3750.0,
        rule_followed=True,
    )
    run_id = "test_run_123"
    params = {"start": "2024-01-01", "end": "2024-01-20"}
    metrics = {"win_rate_pct": 100.0, "net_pnl": 3750.0}

    storage.save_backtest_run(
        run_id=run_id,
        started_at=dt.datetime(2024, 1, 20, 10, 0, tzinfo=dt.timezone.utc),
        params=params,
        config_hash="abc_hash",
        metrics=metrics,
        trades=[trade],
        version=1,
    )

    run = storage.get_backtest_run(run_id)
    assert run is not None
    assert run["id"] == run_id
    assert run["version"] == 1
    assert run["config_hash"] == "abc_hash"
    assert run["params"] == params
    assert run["metrics"] == metrics

    trades = storage.get_backtest_trades(run_id)
    assert len(trades) == 1
    assert trades[0].symbol == "RELIANCE.NS"
    assert trades[0].net_pnl == 3750.0
    assert trades[0].exit_reason == ExitReason.TARGET


def test_backtest_run_versioning_and_no_duplicate_trades(storage):
    """Verify incremented run versions for identical config and refusal to overwrite existing run_id."""
    config_hash = "conf_hash_xyz"
    assert storage.get_backtest_run_count(config_hash) == 0

    trade1 = TradeRecord(
        symbol="TCS.NS",
        signal_date=dt.date(2024, 2, 1),
        entry_date=dt.date(2024, 2, 2),
        entry_price=3500.0,
        exit_date=dt.date(2024, 2, 5),
        exit_price=3570.0,
        exit_reason=ExitReason.TARGET,
        band=TradeBand.HALF,
        position_size=50000.0,
        gross_pnl=1000.0,
        net_pnl=900.0,
    )

    # First run version 1
    storage.save_backtest_run(
        run_id=f"{config_hash}_v1",
        started_at=dt.datetime.now(dt.timezone.utc),
        params={"window": "30d"},
        config_hash=config_hash,
        metrics={"total_trades": 1},
        trades=[trade1],
        version=1,
    )
    assert storage.get_backtest_run_count(config_hash) == 1

    # Second run with version 2
    count = storage.get_backtest_run_count(config_hash)
    version = count + 1
    storage.save_backtest_run(
        run_id=f"{config_hash}_v{version}",
        started_at=dt.datetime.now(dt.timezone.utc),
        params={"window": "30d"},
        config_hash=config_hash,
        metrics={"total_trades": 1},
        trades=[trade1],
        version=version,
    )
    assert storage.get_backtest_run_count(config_hash) == 2

    # Trades for v1 belong strictly to v1 (no cross-contamination or duplication)
    assert len(storage.get_backtest_trades(f"{config_hash}_v1")) == 1
    assert len(storage.get_backtest_trades(f"{config_hash}_v2")) == 1

    # Overwriting existing run_id raises error (no silent duplicate rows)
    with pytest.raises(Exception):
        storage.save_backtest_run(
            run_id=f"{config_hash}_v1",
            started_at=dt.datetime.now(dt.timezone.utc),
            params={"window": "30d"},
            config_hash=config_hash,
            metrics={},
            trades=[],
            version=1,
        )
