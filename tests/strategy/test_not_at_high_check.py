"""Unit tests for NotAtHighCheck (+20 points).

Includes hand-computed known answers, insufficient data handling,
and strict boundary condition verification (exactly 5% distance).
"""

import datetime as dt
import pytest

from trading_agent.domain.models import Bar
from trading_agent.strategy.checks.not_at_high_check import NotAtHighCheck


def make_constant_bars(count: int, high_val: float, close_val: float) -> list[Bar]:
    """Helper to generate synthetic bars."""
    start_date = dt.date(2023, 1, 1)
    bars = []
    for i in range(count):
        d = start_date + dt.timedelta(days=i)
        bars.append(
            Bar(
                date=d,
                open=close_val,
                high=high_val,
                low=close_val - 10.0,
                close=close_val,
                volume=100000,
            )
        )
    return bars


def test_not_at_high_insufficient_data():
    """Verify check returns INSUFFICIENT_DATA when bars < 250."""
    check = NotAtHighCheck()
    bars = make_constant_bars(count=249, high_val=1000.0, close_val=900.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert result.max_points == 20
    assert "INSUFFICIENT_DATA" in result.rationale


def test_not_at_high_fail_within_5_percent():
    """Hand-computed known answer test:
    - 52-week high = 1000.0
    - Latest close = 970.0
    - Distance = (1000 - 970) / 1000 = 30 / 1000 = 0.03 (3.0%)
    - Since 3.0% < 5.0%, the check MUST FAIL (avoid buying tops).
    """
    check = NotAtHighCheck()
    bars = make_constant_bars(count=250, high_val=1000.0, close_val=970.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "FAIL" in result.rationale
    assert "3.00% < 5.0%" in result.rationale


def test_not_at_high_pass_beyond_5_percent():
    """Hand-computed known answer test:
    - 52-week high = 1000.0
    - Latest close = 900.0
    - Distance = (1000 - 900) / 1000 = 100 / 1000 = 0.10 (10.0%)
    - Since 10.0% >= 5.0%, the check MUST PASS (+20 points).
    """
    check = NotAtHighCheck()
    bars = make_constant_bars(count=250, high_val=1000.0, close_val=900.0)
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert result.passed
    assert result.points_awarded == 20
    assert "PASS" in result.rationale
    assert "10.00% below 52-week high" in result.rationale


def test_not_at_high_exact_boundary():
    """Edge Case 5 boundary test:
    - 52-week high = 1000.0
    - Case A: Close = 950.0 -> Distance = (1000 - 950) / 1000 = 0.0500 (Exactly 5.00%).
      Specification rule: 'within means strictly less than 5%'. Exactly 5.0% MUST PASS.
    - Case B: Close = 950.01 -> Distance = (1000 - 950.01) / 1000 = 0.04999 (4.999% < 5%).
      MUST FAIL.
    """
    check = NotAtHighCheck()

    # Case A: Exactly 5.0% distance -> PASS
    bars_boundary = make_constant_bars(count=250, high_val=1000.0, close_val=950.0)
    res_a = check.evaluate("TEST.NS", bars_boundary[-1].date, bars_boundary)
    assert res_a.passed
    assert res_a.points_awarded == 20

    # Case B: Just inside 5.0% (4.999%) -> FAIL
    bars_inside = make_constant_bars(count=250, high_val=1000.0, close_val=950.10)
    res_b = check.evaluate("TEST.NS", bars_inside[-1].date, bars_inside)
    assert not res_b.passed
    assert res_b.points_awarded == 0
