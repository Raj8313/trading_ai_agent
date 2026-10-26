"""Verification test for single source of truth configuration (Exit Criterion 9).

Proves that StopDistanceCheck and FixedTargetStopExitPolicy both read
their stop-loss percentage from the shared Settings object, preventing
any parameter divergence or silent config drift.
"""

from unittest.mock import patch
import pytest

from trading_agent.backtest.policies.exit_policy import FixedTargetStopExitPolicy
from trading_agent.config import Settings, get_settings
from trading_agent.strategy.checks.stop_distance_check import StopDistanceCheck


def test_stop_loss_config_single_source_of_truth():
    """Verify default instantiation reads identical stop_loss_pct from config."""
    settings = get_settings()
    check = StopDistanceCheck()
    policy = FixedTargetStopExitPolicy()

    # Both must match the global config exactly
    assert check.stop_loss_pct == settings.stop_loss_pct
    assert policy.stop_loss_pct == settings.stop_loss_pct
    assert check.stop_loss_pct == policy.stop_loss_pct


def test_stop_loss_config_drift_prevention():
    """Verify that changing the shared config updates both check and policy synchronously."""
    custom_settings = Settings(stop_loss_pct=0.035)

    with patch("trading_agent.config.get_settings", return_value=custom_settings):
        check = StopDistanceCheck()
        policy = FixedTargetStopExitPolicy()

        assert check.stop_loss_pct == 0.035
        assert policy.stop_loss_pct == 0.035
        assert check.stop_loss_pct == policy.stop_loss_pct
