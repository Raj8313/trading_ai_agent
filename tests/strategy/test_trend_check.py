"""Unit tests for TrendCheck."""

import datetime as dt
from trading_agent.domain.models import Bar
from trading_agent.strategy.checks.trend_check import TrendCheck


def make_bar(date_val: dt.date, close_price: float) -> Bar:
    """Helper to generate a valid Bar with given close price."""
    return Bar(
        date=date_val,
        open=close_price,
        high=close_price + 10.0,
        low=close_price - 10.0,
        close=close_price,
        volume=100000,
    )


def test_trend_check_insufficient_data():
    """Verify TrendCheck returns INSUFFICIENT_DATA if < 21 bars."""
    check = TrendCheck()
    start_date = dt.date(2024, 1, 1)
    bars = [make_bar(start_date + dt.timedelta(days=i), 100.0) for i in range(15)]

    result = check.evaluate("TEST.NS", dt.date(2024, 1, 15), bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "INSUFFICIENT_DATA" in result.rationale


def test_trend_check_pass_condition():
    """Verify TrendCheck passes when price is above 20 EMA and EMA is rising."""
    check = TrendCheck()
    start_date = dt.date(2024, 1, 1)
    # Steadily rising prices: 100, 102, 104, ...
    bars = [
        make_bar(start_date + dt.timedelta(days=i), 100.0 + i * 2.0)
        for i in range(30)
    ]
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert result.passed
    assert result.points_awarded == 25
    assert "PASS" in result.rationale


def test_trend_check_fail_falling_ema():
    """Verify TrendCheck fails when prices and EMA are falling."""
    check = TrendCheck()
    start_date = dt.date(2024, 1, 1)
    # Steadily falling prices: 200, 198, 196, ...
    bars = [
        make_bar(start_date + dt.timedelta(days=i), 200.0 - i * 2.0)
        for i in range(30)
    ]
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "FAIL" in result.rationale


def test_trend_check_fail_price_below_rising_ema():
    """Verify TrendCheck fails when EMA is rising but current price drops below EMA."""
    check = TrendCheck()
    start_date = dt.date(2024, 1, 1)
    # Rising for 28 bars, then sudden steep crash on last bar below EMA
    bars = [
        make_bar(start_date + dt.timedelta(days=i), 100.0 + i * 5.0)
        for i in range(29)
    ]
    # Crash on the 30th bar
    bars.append(make_bar(start_date + dt.timedelta(days=29), 80.0))
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "Close" in result.rationale
