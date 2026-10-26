"""Unit tests for meter versioning (v1 vs v2) and database schema migration."""

import datetime as dt
import sqlite3
import pytest

from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.domain.models import CheckResult, Score, TradeBand


def make_test_score(symbol: str, date_val: dt.date, points: int = 85, version: str = "v2") -> Score:
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
        meter_version=version,
    )


def test_schema_migration_preserves_v1_scores(tmp_path):
    """Verify legacy v1 scores table is migrated automatically to v2 without data loss."""
    db_file = tmp_path / "legacy.db"

    # 1. Setup legacy v1 table manually
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE scores (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            total_points INTEGER NOT NULL,
            band TEXT NOT NULL,
            check_results_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.execute("""
        INSERT INTO scores VALUES (
            'RELIANCE.NS', '2024-01-15', 65, 'HALF',
            '[{"check_name":"Trend Check","passed":true,"points_awarded":25,"max_points":25,"rationale":"OK"}]',
            '2024-01-15T10:00:00'
        );
    """)
    conn.commit()
    conn.close()

    # 2. Instantiate SqliteStorageAdapter (triggers _init_db and migration)
    adapter = SqliteStorageAdapter(str(db_file))

    # 3. Verify legacy score is preserved and stamped as 'v1'
    v1_score = adapter.get_score("RELIANCE.NS", dt.date(2024, 1, 15), meter_version="v1")
    assert v1_score is not None
    assert v1_score.total_points == 65
    assert v1_score.meter_version == "v1"

    # 4. Verify v2 does not return this score
    v2_missing = adapter.get_score("RELIANCE.NS", dt.date(2024, 1, 15), meter_version="v2")
    assert v2_missing is None


def test_coexistence_of_v1_and_v2_scores(tmp_path):
    """Verify identical (symbol, date) can hold both v1 and v2 scores independently."""
    db_file = tmp_path / "versions.db"
    adapter = SqliteStorageAdapter(str(db_file))
    target_date = dt.date(2024, 1, 15)

    # Save v1 score
    score_v1 = make_test_score("INFY.NS", target_date, points=65, version="v1")
    adapter.save_score(score_v1)

    # Save v2 score for identical symbol and date
    score_v2 = make_test_score("INFY.NS", target_date, points=85, version="v2")
    adapter.save_score(score_v2)

    # Both must coexist without overwriting
    ret_v1 = adapter.get_score("INFY.NS", target_date, meter_version="v1")
    ret_v2 = adapter.get_score("INFY.NS", target_date, meter_version="v2")

    assert ret_v1 is not None and ret_v1.total_points == 65
    assert ret_v2 is not None and ret_v2.total_points == 85

    counts_v1 = adapter.get_score_counts_by_symbol(meter_version="v1")
    counts_v2 = adapter.get_score_counts_by_symbol(meter_version="v2")
    assert counts_v1["INFY.NS"] == 1
    assert counts_v2["INFY.NS"] == 1


def test_get_scored_dates_for_symbol(tmp_path):
    """Verify querying set of already scored dates for incremental backfill."""
    db_file = tmp_path / "dates.db"
    adapter = SqliteStorageAdapter(str(db_file))

    adapter.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 10), 80, "v2"))
    adapter.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 11), 85, "v2"))
    adapter.save_score(make_test_score("TCS.NS", dt.date(2024, 1, 12), 65, "v1"))

    dates_v2 = adapter.get_scored_dates_for_symbol("TCS.NS", meter_version="v2")
    assert dates_v2 == {dt.date(2024, 1, 10), dt.date(2024, 1, 11)}

    dates_v1 = adapter.get_scored_dates_for_symbol("TCS.NS", meter_version="v1")
    assert dates_v1 == {dt.date(2024, 1, 12)}
