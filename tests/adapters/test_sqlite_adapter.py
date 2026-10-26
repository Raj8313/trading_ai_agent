"""Unit tests for SqliteStorageAdapter."""

import datetime as dt
import pytest
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.domain.models import (
    CheckResult,
    DataQualityIssue,
    Score,
    TradeBand,
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
