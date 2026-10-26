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
