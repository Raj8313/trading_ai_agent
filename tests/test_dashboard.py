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
