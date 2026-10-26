"""Unit tests for StopDistanceCheck (+15 points).

Includes hand-computed known answers, insufficient data handling,
and exact boundary threshold tests (2 * ATR / price == stop_loss_pct).
"""

import datetime as dt
import pytest

from trading_agent.domain.models import Bar
from trading_agent.strategy.checks.stop_distance_check import StopDistanceCheck


def make_tr_bars(count: int, tr_val: float, close_val: float = 1000.0) -> list[Bar]:
    """Helper to generate bars with a constant True Range."""
    start_date = dt.date(2023, 1, 1)
    bars = []
    half_tr = tr_val / 2.0
    for i in range(count):
        d = start_date + dt.timedelta(days=i)
        bars.append(
            Bar(
                date=d,
                open=close_val,
                high=close_val + half_tr,
                low=close_val - half_tr,
                close=close_val,
                volume=100000,
            )
        )
    return bars


def test_stop_distance_insufficient_data():
    """Verify check returns INSUFFICIENT_DATA when bars < 35."""
    check = StopDistanceCheck(stop_loss_pct=0.02)
    bars = make_tr_bars(count=34, tr_val=20.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert result.max_points == 15
    assert "INSUFFICIENT_DATA" in result.rationale


def test_stop_distance_fail_when_noise_too_small():
    """Hand-computed known answer test:
    - High = 1003.0, Low = 997.0, Close = 1000.0
    - True Range per bar = 1003.0 - 997.0 = 6.0
    - ATR(14) = 6.0
    - 2 * ATR(14) / price = (2 * 6.0) / 1000.0 = 12.0 / 1000.0 = 0.0120 (1.20%)
    - Planned stop = 0.02 (2.00%)
    - Since 1.20% < 2.00%, the check MUST FAIL (stop is tighter than volatility noise).
    """
    check = StopDistanceCheck(stop_loss_pct=0.02)
    bars = make_tr_bars(count=35, tr_val=6.0, close_val=1000.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "FAIL" in result.rationale
    assert "1.20%" in result.rationale
    assert "2.00%" in result.rationale


def test_stop_distance_pass_when_noise_sufficient():
    """Hand-computed known answer test:
    - High = 1015.0, Low = 985.0, Close = 1000.0
    - True Range per bar = 1015.0 - 985.0 = 30.0
    - ATR(14) = 30.0
    - 2 * ATR(14) / price = (2 * 30.0) / 1000.0 = 60.0 / 1000.0 = 0.0600 (6.00%)
    - Planned stop = 0.02 (2.00%)
    - Since 6.00% >= 2.00%, the check MUST PASS (+15 points).
    """
    check = StopDistanceCheck(stop_loss_pct=0.02)
    bars = make_tr_bars(count=35, tr_val=30.0, close_val=1000.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert result.passed
    assert result.points_awarded == 15
    assert "PASS" in result.rationale
    assert "6.00%" in result.rationale
    assert "2.00%" in result.rationale


def test_stop_distance_exact_boundary():
    """Edge Case 5 boundary test:
    - True Range per bar = 10.0
    - ATR(14) = 10.0
    - Price = 1000.0
    - 2 * ATR(14) / price = (2 * 10.0) / 1000.0 = 20.0 / 1000.0 = 0.0200 (Exactly 2.00%)
    - Planned stop = 0.02 (Exactly 2.00%)
    - Edge Case 5 rule: 'ATR exactly at threshold (pass)'.
    - MUST PASS (+15 points).
    """
    check = StopDistanceCheck(stop_loss_pct=0.02)
    bars = make_tr_bars(count=35, tr_val=10.0, close_val=1000.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert result.passed
    assert result.points_awarded == 15
    assert "PASS" in result.rationale
    assert "2.00%" in result.rationale
    assert ">= planned stop" in result.rationale
