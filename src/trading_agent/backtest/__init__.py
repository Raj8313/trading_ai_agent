"""Backtesting package for trading agent."""

from trading_agent.backtest.engine import BacktestEngine, BacktestLogEvent
from trading_agent.backtest.metrics import BacktestMetrics, calculate_metrics
from trading_agent.backtest.policies.exit_policy import (
    ExitPolicyPort,
    FixedTargetStopExitPolicy,
)

__all__ = [
    "BacktestEngine",
    "BacktestLogEvent",
    "BacktestMetrics",
    "ExitPolicyPort",
    "FixedTargetStopExitPolicy",
    "calculate_metrics",
]
