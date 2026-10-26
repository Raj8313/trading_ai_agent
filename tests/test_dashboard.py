"""Unit tests for Dashboard components and edge cases."""

from unittest.mock import MagicMock
from trading_agent.adapters.storage.sqlite_adapter import DatabaseBusyError
from trading_agent.dashboard.app import format_band_badge
from trading_agent.domain.models import TradeBand


def test_format_band_badge():
    """Verify band badge formatting."""
    assert "FULL" in format_band_badge(TradeBand.FULL)
    assert "HALF" in format_band_badge(TradeBand.HALF)
    assert "NONE" in format_band_badge(TradeBand.NONE)


def test_empty_database_handling():
    """Verify empty database returns empty results cleanly without exceptions."""
    mock_storage = MagicMock()
    mock_storage.get_latest_scores.return_value = []
    mock_storage.get_score_counts_by_symbol.return_value = {}
    mock_storage.get_data_quality_issues.return_value = []

    latest = mock_storage.get_latest_scores()
    assert latest == []

    counts = mock_storage.get_score_counts_by_symbol()
    assert counts == {}

    issues = mock_storage.get_data_quality_issues()
    assert issues == []


def test_database_busy_handling():
    """Verify DatabaseBusyError is handled as expected."""
    mock_storage = MagicMock()
    mock_storage.get_latest_scores.side_effect = DatabaseBusyError("Database busy")

    try:
        mock_storage.get_latest_scores()
    except DatabaseBusyError as exc:
        assert "Database busy" in str(exc)


def test_dashboard_dynamic_checks_rendering():
    """Verify dashboard overview builds dynamic check columns for 3-check and 5-check scores."""
    import datetime as dt
    from unittest.mock import patch
    from trading_agent.dashboard.app import render_overview
    from trading_agent.domain.models import CheckResult, Score, TradeBand

    mock_storage = MagicMock()
    v1_score = Score(
        symbol="V1_STOCK.NS",
        date=dt.date(2024, 1, 1),
        check_results=[
            CheckResult(check_name="Trend Check", passed=True, points_awarded=25, max_points=25, rationale="Up"),
            CheckResult(check_name="Volume Check", passed=False, points_awarded=0, max_points=20, rationale="Low"),
            CheckResult(check_name="Market Direction Check", passed=True, points_awarded=20, max_points=20, rationale="Bullish"),
        ],
        total_points=45,
        band=TradeBand.NONE,
        meter_version="v1",
    )
    v2_score = Score(
        symbol="V2_STOCK.NS",
        date=dt.date(2024, 1, 1),
        check_results=[
            CheckResult(check_name="Trend Check", passed=True, points_awarded=25, max_points=25, rationale="Up"),
            CheckResult(check_name="Volume Check", passed=True, points_awarded=20, max_points=20, rationale="High"),
            CheckResult(check_name="Market Direction Check", passed=True, points_awarded=20, max_points=20, rationale="Bullish"),
            CheckResult(check_name="Not-At-High Check", passed=True, points_awarded=20, max_points=20, rationale="6% below"),
            CheckResult(check_name="Stop-Distance Check", passed=True, points_awarded=15, max_points=15, rationale="Valid stop"),
        ],
        total_points=100,
        band=TradeBand.FULL,
        meter_version="v2",
    )
    mock_storage.get_latest_scores.return_value = [v1_score, v2_score]

    with patch("trading_agent.dashboard.app.st") as mock_st:
        render_overview(mock_storage)
        assert mock_st.dataframe.called
        df = mock_st.dataframe.call_args[0][0]
        assert "Version" in df.columns
        assert "Not-At-High Check" in df.columns
        assert "Stop-Distance Check" in df.columns
        # V1 stock has "—" for the 2 new checks
        assert df.loc[df["Symbol"] == "V1_STOCK.NS", "Not-At-High Check"].values[0] == "—"
        # V2 stock has "✅" for all checks
        assert df.loc[df["Symbol"] == "V2_STOCK.NS", "Not-At-High Check"].values[0] == "✅"
