"""SQLite Storage Adapter implementing StoragePort.

Uses SQLite with Write-Ahead Logging (WAL) mode, versioned schema,
and idempotent upserts for scores and data quality issues.
"""

import datetime as dt
import json
import logging
import sqlite3
import time
from typing import Any, Callable, Optional, TypeVar

from trading_agent.adapters.storage.schema import (
    GET_ALL_SCORE_COUNTS_SQL,
    GET_ALL_SCORES_SQL,
    GET_BACKTEST_RUN_COUNT_BY_HASH_SQL,
    GET_BACKTEST_RUN_SQL,
    GET_LATEST_SCORES_ANY_VERSION_SQL,
    GET_LATEST_SCORES_SQL,
    GET_SCORE_ANY_VERSION_SQL,
    GET_SCORE_COUNTS_SQL,
    GET_SCORE_SQL,
    GET_SCORED_DATES_FOR_SYMBOL_SQL,
    GET_SCORES_IN_RANGE_ANY_VERSION_SQL,
    GET_SCORES_IN_RANGE_SQL,
    GET_TRADES_BY_RUN_ID_SQL,
    INIT_SCHEMA_SQL,
    INSERT_BACKTEST_RUN_SQL,
    INSERT_DQI_SQL,
    INSERT_TRADE_SQL,
    SCHEMA_VERSION,
    UPSERT_SCORE_SQL,
)
from trading_agent.domain.models import (
    CheckResult, DataQualityIssue, ExitReason, Score, TradeBand, TradeRecord
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
        """Create versioned tables and indices if they do not exist, and migrate schema if needed."""
        with self._get_connection() as conn:
            scores_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scores';"
            ).fetchone()
            if scores_exists:
                cols = [col["name"] for col in conn.execute("PRAGMA table_info(scores);").fetchall()]
                if "meter_version" not in cols:
                    conn.execute("ALTER TABLE scores RENAME TO scores_old;")
                    conn.executescript(INIT_SCHEMA_SQL)
                    conn.execute("""
                        INSERT INTO scores (symbol, date, total_points, band, check_results_json, created_at, meter_version)
                        SELECT symbol, date, total_points, band, check_results_json, created_at, 'v1' FROM scores_old;
                    """)
                    conn.execute("DROP TABLE scores_old;")
            conn.executescript(INIT_SCHEMA_SQL)
            cursor = conn.execute("SELECT version FROM schema_version WHERE version = ?;", (SCHEMA_VERSION,))
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
                    (SCHEMA_VERSION, dt.datetime.now(dt.timezone.utc).isoformat()),
                )

    def _execute_read_query(self, query_fn: Callable[[], T]) -> T:
        """Execute a read query function with retries on database lock/busy conditions."""
        for attempt in range(1, 4):
            try:
                return query_fn()
            except sqlite3.OperationalError as exc:
                if any(k in str(exc).lower() for k in ("locked", "busy")):
                    logger.warning("Database locked/busy (attempt %d/3): %s", attempt, exc)
                    if attempt < 3:
                        time.sleep(1.0)
                        continue
                    raise DatabaseBusyError("Database busy — try again in a moment") from exc
                raise

    def save_score(self, score: Score) -> None:
        """Upsert a score record into SQLite. Raises loudly on database errors."""
        checks_payload = json.dumps([c.model_dump() for c in score.check_results])
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    UPSERT_SCORE_SQL,
                    (score.symbol, score.date.isoformat(), score.total_points,
                     score.band.value, checks_payload, now_iso, score.meter_version),
                )
        except Exception as e:
            logger.error("Failed to save score for %s on %s: %s", score.symbol, score.date, e)
            raise

    def get_score(self, symbol: str, date: dt.date, meter_version: Optional[str] = None) -> Optional[Score]:
        """Fetch score for a symbol on a specific date."""
        def _query() -> Optional[Score]:
            with self._get_connection() as conn:
                sql = GET_SCORE_SQL if meter_version else GET_SCORE_ANY_VERSION_SQL
                params = (symbol, date.isoformat(), meter_version) if meter_version else (symbol, date.isoformat())
                row = conn.execute(sql, params).fetchone()
                return self._row_to_score(row) if row else None
        return self._execute_read_query(_query)

    def get_all_scores_for_symbol(self, symbol: str, meter_version: Optional[str] = None) -> list[Score]:
        """Fetch all scores for a symbol ordered by date ascending."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                sql = GET_ALL_SCORES_SQL if meter_version else "SELECT symbol, date, total_points, band, check_results_json, meter_version FROM scores WHERE symbol = ? ORDER BY date ASC;"
                params = (symbol, meter_version) if meter_version else (symbol,)
                return [self._row_to_score(r) for r in conn.execute(sql, params).fetchall()]
        return self._execute_read_query(_query)

    def get_score_counts_by_symbol(self, meter_version: Optional[str] = None) -> dict[str, int]:
        """Return the count of scores grouped by symbol."""
        def _query() -> dict[str, int]:
            with self._get_connection() as conn:
                sql = GET_SCORE_COUNTS_SQL if meter_version else GET_ALL_SCORE_COUNTS_SQL
                params = (meter_version,) if meter_version else ()
                return {r["symbol"]: r["count"] for r in conn.execute(sql, params).fetchall()}
        return self._execute_read_query(_query)

    def get_latest_scores(self, meter_version: Optional[str] = None) -> list[Score]:
        """Fetch the most recent score for each symbol in storage, ordered by total_points DESC."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                sql = GET_LATEST_SCORES_SQL if meter_version else GET_LATEST_SCORES_ANY_VERSION_SQL
                params = (meter_version, meter_version) if meter_version else ()
                return [self._row_to_score(r) for r in conn.execute(sql, params).fetchall()]
        return self._execute_read_query(_query)

    def get_scores_for_symbol_in_range(
        self, symbol: str, start_date: dt.date, end_date: dt.date, meter_version: Optional[str] = None
    ) -> list[Score]:
        """Fetch scores for a symbol within a date window ascending."""
        def _query() -> list[Score]:
            with self._get_connection() as conn:
                sql = GET_SCORES_IN_RANGE_SQL if meter_version else GET_SCORES_IN_RANGE_ANY_VERSION_SQL
                params = (symbol, start_date.isoformat(), end_date.isoformat(), meter_version) if meter_version else (symbol, start_date.isoformat(), end_date.isoformat())
                return [self._row_to_score(r) for r in conn.execute(sql, params).fetchall()]
        return self._execute_read_query(_query)

    def get_scored_dates_for_symbol(self, symbol: str, meter_version: str = "v1") -> set[dt.date]:
        """Fetch set of all dates already scored for a symbol and meter version."""
        def _query() -> set[dt.date]:
            with self._get_connection() as conn:
                rows = conn.execute(GET_SCORED_DATES_FOR_SYMBOL_SQL, (symbol, meter_version)).fetchall()
                return {dt.date.fromisoformat(r["date"]) for r in rows}
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
        sql = "SELECT symbol, date, issue, recorded_at FROM data_quality_issues" + (
            " WHERE symbol = ? ORDER BY id DESC;" if symbol else " ORDER BY id DESC;"
        )
        params = (symbol,) if symbol else ()
        def _query() -> list[DataQualityIssue]:
            with self._get_connection() as conn:
                rows = conn.execute(sql, params).fetchall()
                return [
                    DataQualityIssue(
                        symbol=r["symbol"],
                        date=dt.date.fromisoformat(r["date"]) if r["date"] else None,
                        issue=r["issue"],
                        recorded_at=dt.datetime.fromisoformat(r["recorded_at"]),
                    )
                    for r in rows
                ]
        return self._execute_read_query(_query)

    @staticmethod
    def _row_to_score(row: sqlite3.Row) -> Score:
        """Helper to convert a SQLite row into a domain Score object."""
        checks_data = json.loads(row["check_results_json"])
        check_results = [CheckResult(**c) for c in checks_data]
        meter_version = row["meter_version"] if "meter_version" in row.keys() else "v1"
        return Score(
            symbol=row["symbol"],
            date=dt.date.fromisoformat(row["date"]),
            check_results=check_results,
            total_points=row["total_points"],
            band=TradeBand(row["band"]),
            meter_version=meter_version,
        )

    def save_backtest_run(
        self,
        run_id: str,
        started_at: dt.datetime,
        params: dict[str, Any],
        config_hash: str,
        metrics: dict[str, Any],
        trades: list[TradeRecord],
        version: int = 1,
    ) -> str:
        """Persist a completed backtest run and its trades atomically."""
        trade_rows = [
            (
                run_id, t.symbol, t.signal_date.isoformat(), t.entry_date.isoformat(),
                t.entry_price, t.exit_date.isoformat(), t.exit_price, t.exit_reason.value,
                t.band.value, t.position_size, t.gross_pnl, t.net_pnl, 1 if t.rule_followed else 0,
            )
            for t in trades
        ]
        try:
            with self._get_connection() as conn:
                conn.execute(
                    INSERT_BACKTEST_RUN_SQL,
                    (run_id, version, started_at.isoformat(), json.dumps(params, default=str), config_hash, json.dumps(metrics, default=str)),
                )
                conn.executemany(INSERT_TRADE_SQL, trade_rows)
            return run_id
        except Exception as e:
            logger.error("Failed to save backtest run %s: %s", run_id, e)
            raise

    def get_backtest_run(self, run_id: str) -> Optional[dict[str, Any]]:
        """Fetch backtest run by id."""
        def _query() -> Optional[dict[str, Any]]:
            with self._get_connection() as conn:
                row = conn.execute(GET_BACKTEST_RUN_SQL, (run_id,)).fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "version": row["version"],
                    "started_at": dt.datetime.fromisoformat(row["started_at"]),
                    "params": json.loads(row["params_json"]),
                    "config_hash": row["config_hash"],
                    "metrics": json.loads(row["metrics_json"]),
                }

        return self._execute_read_query(_query)

    def get_backtest_trades(self, run_id: str) -> list[TradeRecord]:
        """Fetch all trades for a backtest run ordered by exit date."""
        def _query() -> list[TradeRecord]:
            with self._get_connection() as conn:
                rows = conn.execute(GET_TRADES_BY_RUN_ID_SQL, (run_id,)).fetchall()
                return [
                    TradeRecord(
                        symbol=r["symbol"], signal_date=dt.date.fromisoformat(r["signal_date"]),
                        entry_date=dt.date.fromisoformat(r["entry_date"]), entry_price=r["entry_price"],
                        exit_date=dt.date.fromisoformat(r["exit_date"]), exit_price=r["exit_price"],
                        exit_reason=ExitReason(r["exit_reason"]), band=TradeBand(r["band"]),
                        position_size=r["position_size"], gross_pnl=r["gross_pnl"],
                        net_pnl=r["net_pnl"], rule_followed=bool(r["rule_followed"]),
                    )
                    for r in rows
                ]

        return self._execute_read_query(_query)

    def get_backtest_run_count(self, config_hash: str) -> int:
        """Fetch count of existing runs for a config hash."""
        def _query() -> int:
            with self._get_connection() as conn:
                row = conn.execute(GET_BACKTEST_RUN_COUNT_BY_HASH_SQL, (config_hash,)).fetchone()
                return int(row[0]) if row else 0

        return self._execute_read_query(_query)
