"""Exit policies package."""

from trading_agent.backtest.policies.exit_policy import (
    ExitPolicyPort,
    FixedTargetStopExitPolicy,
)

__all__ = ["ExitPolicyPort", "FixedTargetStopExitPolicy"]
