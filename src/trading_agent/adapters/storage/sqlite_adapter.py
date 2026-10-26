"""SQLite Storage Adapter implementing StoragePort.

Uses SQLite with Write-Ahead Logging (WAL) mode, versioned schema,
and idempotent upserts for scores and data quality issues.
"""

import datetime as dt
import json
import logging
import sqlite3
import time
from typing import Callable, Optional, TypeVar

from trading_agent.adapters.storage.schema import (
    GET_ALL_SCORES_SQL,
    GET_LATEST_SCORES_SQL,
    GET_SCORE_COUNTS_SQL,
    GET_SCORE_SQL,
    GET_SCORES_IN_RANGE_SQL,
    INIT_SCHEMA_SQL,
    INSERT_DQI_SQL,
    SCHEMA_VERSION,
    UPSERT_SCORE_SQL,
)
from trading_agent.domain.models import (
    CheckResult,
    DataQualityIssue,
    Score,
    TradeBand,
)
from trading_agent.ports.storage import StoragePort

logger = logging.getLogger(__name__)
T = TypeVar("T")


class DatabaseBusyError(Exception):
    """Raised when SQLite database remains locked after retries."""

    pass


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
            conn.executescript(INIT_SCHEMA_SQL)
            cursor = conn.execute("SELECT version FROM schema_version WHERE version = ?;", (SCHEMA_VERSION,))
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                    (SCHEMA_VERSION, dt.datetime.now(dt.timezone.utc).isoformat()),
                )

    def _execute_read_query(self, query_fn: Callable[[], T]) -> T:
        """Execute a read query function with retries on database lock/busy conditions."""
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                return query_fn()
            except sqlite3.OperationalError as exc:
                err_str = str(exc).lower()
                if "locked" in err_str or "busy" in err_str:
                    logger.warning("Database locked/busy (attempt %d/%d): %s", attempt, max_attempts, exc)
                    if attempt < max_attempts:
                        time.sleep(1.0)
                        continue
                    raise DatabaseBusyError("Database busy — try again in a moment") from exc
                raise

    def save_score(self, score: Score) -> None:
        """Upsert a score record into SQLite. Raises loudly on database errors."""
        checks_payload = json.dumps([c.model_dump() for c in score.check_results])
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        date_str = score.date.isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    UPSERT_SCORE_SQL,
                    (score.symbol, date_str, score.total_points, score.band.value, checks_payload, now_iso),
                )
        except Exception as e:
            logger.error("Failed to save score for %s on %s: %s", score.symbol, score.date, e)
            raise

    def get_score(self, symbol: str, date: dt.date) -> Optional[Score]:
        """Fetch score for a symbol on a specific date."""
        def _query() -> Optional[Score]:
            with self._get_connection() as conn:
                row = conn.execute(GET_SCORE_SQL, (symbol, date.isoformat())).fetchone()
                return self._row_to_score(row) if row else None

        return self._execute_read_query(_query)

    def get_all_scores_for_symbol(self, symbol: str) -> list[Score]:
        """Fetch all scores for a symbol ordered by date ascending."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                rows = conn.execute(GET_ALL_SCORES_SQL, (symbol,)).fetchall()
                return [self._row_to_score(r) for r in rows]

        return self._execute_read_query(_query)

    def get_score_counts_by_symbol(self) -> dict[str, int]:
        """Return the count of scores grouped by symbol."""
        def _query() -> dict[str, int]:
            with self._get_connection() as conn:
                rows = conn.execute(GET_SCORE_COUNTS_SQL).fetchall()
                return {row["symbol"]: row["count"] for row in rows}

        return self._execute_read_query(_query)

    def get_latest_scores(self) -> list[Score]:
        """Fetch the most recent score for each symbol in storage, ordered by total_points DESC."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                rows = conn.execute(GET_LATEST_SCORES_SQL).fetchall()
                return [self._row_to_score(r) for r in rows]

        return self._execute_read_query(_query)

    def get_scores_for_symbol_in_range(
        self, symbol: str, start_date: dt.date, end_date: dt.date
    ) -> list[Score]:
        """Fetch scores for a symbol within a date window ascending."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                rows = conn.execute(
                    GET_SCORES_IN_RANGE_SQL, (symbol, start_date.isoformat(), end_date.isoformat())
                ).fetchall()
                return [self._row_to_score(r) for r in rows]

        return self._execute_read_query(_query)

    def save_data_quality_issue(self, issue: DataQualityIssue) -> None:
        """Persist a data quality issue record."""
        date_str = issue.date.isoformat() if issue.date else None
        try:
            with self._get_connection() as conn:
                conn.execute(INSERT_DQI_SQL, (issue.symbol, date_str, issue.issue, issue.recorded_at.isoformat()))
        except Exception as e:
            logger.error("Failed to save data quality issue for %s: %s", issue.symbol, e)
            raise

    def get_data_quality_issues(self, symbol: Optional[str] = None) -> list[DataQualityIssue]:
        """Fetch data quality issues, optionally filtered by symbol, most recent first."""
        if symbol:
            sql = "SELECT symbol, date, issue, recorded_at FROM data_quality_issues WHERE symbol = ? ORDER BY id DESC;"
            params = (symbol,)
        else:
            sql = "SELECT symbol, date, issue, recorded_at FROM data_quality_issues ORDER BY id DESC;"
            params = ()

        def _query() -> list[DataQualityIssue]:
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

        return self._execute_read_query(_query)

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
