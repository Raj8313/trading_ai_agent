"""Unit tests for VolumeCheck."""

import datetime as dt
from trading_agent.domain.models import Bar
from trading_agent.strategy.checks.volume_check import VolumeCheck


def make_bar_with_volume(date_val: dt.date, volume: int) -> Bar:
    """Helper to generate a Bar with specified volume."""
    return Bar(
        date=date_val,
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=volume,
    )


def test_volume_check_insufficient_data():
    """Verify VolumeCheck returns INSUFFICIENT_DATA if < 21 bars."""
    check = VolumeCheck()
    start_date = dt.date(2024, 1, 1)
    bars = [
        make_bar_with_volume(start_date + dt.timedelta(days=i), 10000)
        for i in range(10)
    ]
    result = check.evaluate("TEST.NS", dt.date(2024, 1, 10), bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "INSUFFICIENT_DATA" in result.rationale


def test_volume_check_zero_average_volume():
    """Verify VolumeCheck handles zero average volume edge case cleanly."""
    check = VolumeCheck()
    start_date = dt.date(2024, 1, 1)
    # 20 bars with 0 volume + 1 latest bar with 100 volume
    bars = [
        make_bar_with_volume(start_date + dt.timedelta(days=i), 0)
        for i in range(20)
    ]
    bars.append(make_bar_with_volume(start_date + dt.timedelta(days=20), 100))
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "INSUFFICIENT_DATA" in result.rationale


def test_volume_check_pass():
    """Verify VolumeCheck passes when latest volume > 1.5x 20-period average."""
    check = VolumeCheck()
    start_date = dt.date(2024, 1, 1)
    # 20 bars with volume = 100,000 (average = 100,000)
    bars = [
        make_bar_with_volume(start_date + dt.timedelta(days=i), 100000)
        for i in range(20)
    ]
    # 21st bar with volume = 160,000 (> 1.5 * 100,000 = 150,000)
    bars.append(make_bar_with_volume(start_date + dt.timedelta(days=20), 160000))
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert result.passed
    assert result.points_awarded == 20
    assert "PASS" in result.rationale


def test_volume_check_fail():
    """Verify VolumeCheck fails when latest volume <= 1.5x average."""
    check = VolumeCheck()
    start_date = dt.date(2024, 1, 1)
    bars = [
        make_bar_with_volume(start_date + dt.timedelta(days=i), 100000)
        for i in range(20)
    ]
    # 21st bar with volume = 120,000 (<= 150,000)
    bars.append(make_bar_with_volume(start_date + dt.timedelta(days=20), 120000))
    target_date = bars[-1].date

    result = check.evaluate("TEST.NS", target_date, bars)
    assert not result.passed
    assert result.points_awarded == 0
    assert "FAIL" in result.rationale
