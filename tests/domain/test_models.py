"""Unit tests for domain models."""

from datetime import date
import pytest
from pydantic import ValidationError
from trading_agent.domain import (
    Bar,
    CheckResult,
    Score,
    Stock,
    TradeBand,
    Signal,
    DataQualityIssue,
)


def test_stock_creation():
    """Verify stock model instantiation."""
    stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", exchange="NSE")
    assert stock.symbol == "RELIANCE.NS"
    assert stock.name == "Reliance Industries"
    assert stock.exchange == "NSE"


def test_bar_valid():
    """Verify valid bar creation."""
    bar = Bar(
        date=date(2024, 1, 15),
        open=2500.0,
        high=2550.0,
        low=2490.0,
        close=2530.0,
        volume=1000000,
    )
    assert bar.close == 2530.0
    assert bar.volume == 1000000


def test_bar_invalid_high_low():
    """Ensure validation fails if high is lower than low."""
    with pytest.raises(ValidationError):
        Bar(
            date=date(2024, 1, 15),
            open=2500.0,
            high=2480.0,
            low=2490.0,
            close=2485.0,
            volume=1000,
        )


def test_score_band_calculation():
    """Verify trade band thresholds."""
    assert Score.calculate_band(85) == TradeBand.FULL
    assert Score.calculate_band(80) == TradeBand.FULL
    assert Score.calculate_band(79) == TradeBand.HALF
    assert Score.calculate_band(60) == TradeBand.HALF
    assert Score.calculate_band(59) == TradeBand.NONE
    assert Score.calculate_band(0) == TradeBand.NONE


def test_score_and_signal_models():
    """Verify score and signal instantiation."""
    check = CheckResult(
        check_name="Trend Check",
        passed=True,
        points_awarded=25,
        max_points=25,
        rationale="Price above 20 EMA and EMA rising",
    )
    score = Score(
        symbol="TCS.NS",
        date=date(2024, 1, 15),
        check_results=[check],
        total_points=25,
        band=TradeBand.NONE,
    )
    assert score.total_points == 25
    assert score.band == TradeBand.NONE

    signal = Signal(
        symbol="TCS.NS",
        date=date(2024, 1, 15),
        score=score,
        band=TradeBand.NONE,
        action="PASS",
    )
    assert signal.action == "PASS"

    issue = DataQualityIssue(
        symbol="TCS.NS",
        date=date(2024, 1, 15),
        issue="Missing volume",
    )
    assert issue.symbol == "TCS.NS"
