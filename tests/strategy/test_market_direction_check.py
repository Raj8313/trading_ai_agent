"""Unit tests for MarketDirectionCheck."""

import datetime as dt
from trading_agent.domain.models import Bar
from trading_agent.strategy.checks.market_direction_check import MarketDirectionCheck


def make_market_bar(date_val: dt.date, close_price: float) -> Bar:
    """Helper to generate a market bar."""
    return Bar(
        date=date_val,
        open=close_price,
        high=close_price + 50.0,
        low=close_price - 50.0,
        close=close_price,
        volume=5000000,
    )


def test_market_direction_none_market_bars():
    """Verify MarketDirectionCheck handles None market_bars."""
    check = MarketDirectionCheck()
    result = check.evaluate("TEST.NS", dt.date(2024, 1, 15), [], None)
    assert not result.passed
    assert result.points_awarded == 0
    assert "INSUFFICIENT_DATA" in result.rationale


def test_market_direction_insufficient_bars():
    """Verify MarketDirectionCheck handles < 20 market bars."""
    check = MarketDirectionCheck()
    start_date = dt.date(2024, 1, 1)
    market_bars = [
        make_market_bar(start_date + dt.timedelta(days=i), 21000.0)
        for i in range(10)
    ]
    result = check.evaluate("TEST.NS", dt.date(2024, 1, 10), [], market_bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "INSUFFICIENT_DATA" in result.rationale


def test_market_direction_pass():
    """Verify MarketDirectionCheck passes when NIFTY is above 20 EMA."""
    check = MarketDirectionCheck()
    start_date = dt.date(2024, 1, 1)
    # Steadily rising market: 20000, 20050, 20100...
    market_bars = [
        make_market_bar(start_date + dt.timedelta(days=i), 20000.0 + i * 50.0)
        for i in range(25)
    ]
    target_date = market_bars[-1].date

    result = check.evaluate("TEST.NS", target_date, [], market_bars)
    assert result.passed
    assert result.points_awarded == 20
    assert "PASS" in result.rationale


def test_market_direction_fail():
    """Verify MarketDirectionCheck fails when NIFTY is below 20 EMA."""
    check = MarketDirectionCheck()
    start_date = dt.date(2024, 1, 1)
    # Steadily falling market: 22000, 21950, ...
    market_bars = [
        make_market_bar(start_date + dt.timedelta(days=i), 22000.0 - i * 50.0)
        for i in range(25)
    ]
    target_date = market_bars[-1].date

    result = check.evaluate("TEST.NS", target_date, [], market_bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "FAIL" in result.rationale
