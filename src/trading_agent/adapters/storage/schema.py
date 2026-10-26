"""SQL schemas and statements for SQLite storage adapter."""

SCHEMA_VERSION = 1

INIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    total_points INTEGER NOT NULL,
    band TEXT NOT NULL,
    check_results_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_scores_symbol ON scores(symbol);
CREATE INDEX IF NOT EXISTS idx_scores_date ON scores(date);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT,
    issue TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dqi_symbol ON data_quality_issues(symbol);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL,
    params_json TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    metrics_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_btr_config_hash ON backtest_runs(config_hash);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_date TEXT NOT NULL,
    exit_price REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    band TEXT NOT NULL,
    position_size REAL NOT NULL,
    gross_pnl REAL NOT NULL,
    net_pnl REAL NOT NULL,
    rule_followed INTEGER NOT NULL,
    FOREIGN KEY(run_id) REFERENCES backtest_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trades_run_id ON trades(run_id);
"""

UPSERT_SCORE_SQL = """
INSERT INTO scores (symbol, date, total_points, band, check_results_json, created_at)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT(symbol, date) DO UPDATE SET
    total_points = excluded.total_points,
    band = excluded.band,
    check_results_json = excluded.check_results_json,
    created_at = excluded.created_at;
"""

GET_SCORE_SQL = "SELECT symbol, date, total_points, band, check_results_json FROM scores WHERE symbol = ? AND date = ?;"

GET_ALL_SCORES_SQL = "SELECT symbol, date, total_points, band, check_results_json FROM scores WHERE symbol = ? ORDER BY date ASC;"

GET_SCORE_COUNTS_SQL = "SELECT symbol, COUNT(*) as count FROM scores GROUP BY symbol ORDER BY symbol ASC;"

GET_LATEST_SCORES_SQL = """
SELECT s.symbol, s.date, s.total_points, s.band, s.check_results_json
FROM scores s
INNER JOIN (
    SELECT symbol, MAX(date) AS max_date
    FROM scores
    GROUP BY symbol
) latest ON s.symbol = latest.symbol AND s.date = latest.max_date
ORDER BY s.total_points DESC;
"""

GET_SCORES_IN_RANGE_SQL = """
SELECT symbol, date, total_points, band, check_results_json
FROM scores
WHERE symbol = ? AND date >= ? AND date <= ?
ORDER BY date ASC;
"""

INSERT_DQI_SQL = "INSERT INTO data_quality_issues (symbol, date, issue, recorded_at) VALUES (?, ?, ?, ?);"

INSERT_BACKTEST_RUN_SQL = """
INSERT INTO backtest_runs (id, version, started_at, params_json, config_hash, metrics_json)
VALUES (?, ?, ?, ?, ?, ?);
"""

INSERT_TRADE_SQL = """
INSERT INTO trades (
    run_id, symbol, signal_date, entry_date, entry_price, exit_date, exit_price,
    exit_reason, band, position_size, gross_pnl, net_pnl, rule_followed
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
"""

GET_BACKTEST_RUN_COUNT_BY_HASH_SQL = "SELECT COUNT(*) FROM backtest_runs WHERE config_hash = ?;"

GET_BACKTEST_RUN_SQL = "SELECT id, version, started_at, params_json, config_hash, metrics_json FROM backtest_runs WHERE id = ?;"

GET_TRADES_BY_RUN_ID_SQL = """
SELECT symbol, signal_date, entry_date, entry_price, exit_date, exit_price,
       exit_reason, band, position_size, gross_pnl, net_pnl, rule_followed
FROM trades
WHERE run_id = ?
ORDER BY exit_date ASC, id ASC;
"""
