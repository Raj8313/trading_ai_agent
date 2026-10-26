"""Unit tests for FixedTargetStopExitPolicy."""

import datetime as dt
from trading_agent.backtest.policies.exit_policy import FixedTargetStopExitPolicy
from trading_agent.domain.models import Bar, ExitReason


def make_bar(date_val: dt.date, open_p: float, high_p: float, low_p: float, close_p: float) -> Bar:
    """Helper to create a bar."""
    return Bar(
        date=date_val,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=50000,
    )


def test_no_exit_when_within_bounds():
    """Verify holding position when neither stop nor target is reached."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04)
    # Entry at 100.0 -> Stop at 98.0, Target at 104.0
    bar = make_bar(dt.date(2024, 1, 2), 100.5, 102.0, 99.0, 101.0)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=1,
    )
    assert not decision.should_exit


def test_stop_loss_hit():
    """Verify stop loss triggers at 98.0 when price dips to 97.5."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04)
    bar = make_bar(dt.date(2024, 1, 2), 99.5, 100.0, 97.5, 98.0)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=1,
    )
    assert decision.should_exit
    assert decision.exit_reason == ExitReason.STOP
    assert decision.exit_price == 98.0
    assert decision.exit_date == dt.date(2024, 1, 2)


def test_target_hit():
    """Verify target triggers at 104.0 when price reaches 104.5."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04)
    bar = make_bar(dt.date(2024, 1, 2), 101.0, 104.5, 100.5, 103.5)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=1,
    )
    assert decision.should_exit
    assert decision.exit_reason == ExitReason.TARGET
    assert decision.exit_price == 104.0


def test_intrabar_conflict_resolves_to_stop():
    """Exit Criterion 5: Intrabar conflict (both stop and target touched) must resolve to STOP."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04)
    # Day with wild volatility: High = 105.0 (>104), Low = 97.0 (<98)
    bar = make_bar(dt.date(2024, 1, 3), 101.0, 105.0, 97.0, 100.0)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=2,
    )
    assert decision.should_exit
    # Must resolve conservatively to STOP, never TARGET!
    assert decision.exit_reason == ExitReason.STOP
    assert decision.exit_price == 98.0


def test_gap_through_stop_records_worse_loss():
    """Exit Criterion 6: Gap-through-stop records the real (worse) loss at open."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04)
    # Stop is 98.0. Stock opens gap-down at 95.0 (-5%)
    bar = make_bar(dt.date(2024, 1, 3), 95.0, 96.0, 94.0, 95.5)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=2,
    )
    assert decision.should_exit
    assert decision.exit_reason == ExitReason.STOP
    # Must exit at actual open (95.0), not magical stop price (98.0)
    assert decision.exit_price == 95.0


def test_time_exit_at_open():
    """Verify position exits at Day 11 Open after 10 trading days held."""
    policy = FixedTargetStopExitPolicy(stop_loss_pct=0.02, profit_target_pct=0.04, max_hold_days=10)
    bar = make_bar(dt.date(2024, 1, 15), 101.5, 102.5, 100.5, 101.0)
    decision = policy.evaluate_bar(
        entry_date=dt.date(2024, 1, 1),
        entry_price=100.0,
        current_bar=bar,
        days_held=10,  # 10 days reached -> time exit
    )
    assert decision.should_exit
    assert decision.exit_reason == ExitReason.TIME
    assert decision.exit_price == 101.5
