"""SQLite Storage Adapter implementing StoragePort.

Uses SQLite with Write-Ahead Logging (WAL) mode, versioned schema,
and idempotent upserts for scores and data quality issues.
"""

import datetime as dt
import json
import logging
import sqlite3
from typing import Optional

from trading_agent.domain.models import (
    CheckResult,
    DataQualityIssue,
    Score,
    TradeBand,
)
from trading_agent.ports.storage import StoragePort

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class SqliteStorageAdapter(StoragePort):
    """SQLite implementation of StoragePort with WAL mode and idempotent upserts."""

    def __init__(self, db_path: str = "trading_agent.db") -> None:
        """Initialize the SQLite adapter and ensure tables are created."""
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Open a new connection configured with WAL mode and foreign keys."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Create versioned tables and indices if they do not exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )

            # Record version 1 if not already applied
            cursor = conn.execute("SELECT version FROM schema_version WHERE version = ?;", (SCHEMA_VERSION,))
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                    (SCHEMA_VERSION, dt.datetime.now(dt.timezone.utc).isoformat()),
                )

            # Scores table: unique composite primary key on (symbol, date) guarantees idempotency
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scores (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    total_points INTEGER NOT NULL,
                    band TEXT NOT NULL,
                    check_results_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, date)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_symbol ON scores(symbol);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_scores_date ON scores(date);")

            # Data quality issues table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    date TEXT,
                    issue TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dqi_symbol ON data_quality_issues(symbol);")

    def save_score(self, score: Score) -> None:
        """Upsert a score record into SQLite.

        Raises loudly on database errors.
        """
        checks_payload = json.dumps([c.model_dump() for c in score.check_results])
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        date_str = score.date.isoformat()

        sql = """
            INSERT INTO scores (symbol, date, total_points, band, check_results_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
                total_points = excluded.total_points,
                band = excluded.band,
                check_results_json = excluded.check_results_json,
                created_at = excluded.created_at;
        """
        try:
            with self._get_connection() as conn:
                conn.execute(
                    sql,
                    (
                        score.symbol,
                        date_str,
                        score.total_points,
                        score.band.value,
                        checks_payload,
                        now_iso,
                    ),
                )
        except Exception as e:
            logger.error("Failed to save score for %s on %s: %s", score.symbol, score.date, e)
            raise

    def get_score(self, symbol: str, date: dt.date) -> Optional[Score]:
        """Fetch score for a symbol on a specific date."""
        sql = "SELECT symbol, date, total_points, band, check_results_json FROM scores WHERE symbol = ? AND date = ?;"
        try:
            with self._get_connection() as conn:
                row = conn.execute(sql, (symbol, date.isoformat())).fetchone()
                if not row:
                    return None
                return self._row_to_score(row)
        except Exception as e:
            logger.error("Failed to retrieve score for %s on %s: %s", symbol, date, e)
            raise

    def get_all_scores_for_symbol(self, symbol: str) -> list[Score]:
        """Fetch all scores for a symbol ordered by date ascending."""
        sql = "SELECT symbol, date, total_points, band, check_results_json FROM scores WHERE symbol = ? ORDER BY date ASC;"
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, (symbol,)).fetchall()
                return [self._row_to_score(r) for r in rows]
        except Exception as e:
            logger.error("Failed to retrieve all scores for %s: %s", symbol, e)
            raise

    def get_score_counts_by_symbol(self) -> dict[str, int]:
        """Return the count of scores grouped by symbol."""
        sql = "SELECT symbol, COUNT(*) as count FROM scores GROUP BY symbol ORDER BY symbol ASC;"
        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql).fetchall()
                return {row["symbol"]: row["count"] for row in rows}
        except Exception as e:
            logger.error("Failed to get score counts: %s", e)
            raise

    def save_data_quality_issue(self, issue: DataQualityIssue) -> None:
        """Persist a data quality issue record."""
        sql = """
            INSERT INTO data_quality_issues (symbol, date, issue, recorded_at)
            VALUES (?, ?, ?, ?);
        """
        date_str = issue.date.isoformat() if issue.date else None
        try:
            with self._get_connection() as conn:
                conn.execute(sql, (issue.symbol, date_str, issue.issue, issue.recorded_at.isoformat()))
        except Exception as e:
            logger.error("Failed to save data quality issue for %s: %s", issue.symbol, e)
            raise

    def get_data_quality_issues(self, symbol: Optional[str] = None) -> list[DataQualityIssue]:
        """Fetch data quality issues, optionally filtered by symbol."""
        if symbol:
            sql = "SELECT symbol, date, issue, recorded_at FROM data_quality_issues WHERE symbol = ? ORDER BY id ASC;"
            params = (symbol,)
        else:
            sql = "SELECT symbol, date, issue, recorded_at FROM data_quality_issues ORDER BY id ASC;"
            params = ()

        try:
            with self._get_connection() as conn:
                rows = conn.execute(sql, params).fetchall()
                results = []
                for row in rows:
                    parsed_date = dt.date.fromisoformat(row["date"]) if row["date"] else None
                    results.append(
                        DataQualityIssue(
                            symbol=row["symbol"],
                            date=parsed_date,
                            issue=row["issue"],
                            recorded_at=dt.datetime.fromisoformat(row["recorded_at"]),
                        )
                    )
                return results
        except Exception as e:
            logger.error("Failed to fetch data quality issues: %s", e)
            raise

    @staticmethod
    def _row_to_score(row: sqlite3.Row) -> Score:
        """Helper to convert a SQLite row into a domain Score object."""
        checks_data = json.loads(row["check_results_json"])
        check_results = [CheckResult(**c) for c in checks_data]
        return Score(
            symbol=row["symbol"],
            date=dt.date.fromisoformat(row["date"]),
            check_results=check_results,
            total_points=row["total_points"],
            band=TradeBand(row["band"]),
        )
