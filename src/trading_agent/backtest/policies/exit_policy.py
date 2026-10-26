"""Exit policy interface and fixed target/stop implementation."""

from abc import ABC, abstractmethod
import datetime as dt
from typing import Optional

import trading_agent.config as config
from trading_agent.domain.models import Bar, ExitDecision, ExitReason


class ExitPolicyPort(ABC):
    """Abstract interface for trade exit policies.

    Evaluates whether an open position should be closed based on price action
    and duration held.
    """

    @abstractmethod
    def evaluate_bar(
        self,
        entry_date: dt.date,
        entry_price: float,
        current_bar: Bar,
        days_held: int,
    ) -> ExitDecision:
        """Evaluate if an open trade must exit on the given bar.

        Args:
            entry_date: Date trade was entered.
            entry_price: Actual execution entry price.
            current_bar: Daily bar being evaluated.
            days_held: Number of trading sessions the position has been held.

        Returns:
            ExitDecision specifying whether to exit, price, and rationale.
        """
        pass


class FixedTargetStopExitPolicy(ExitPolicyPort):
    """Conservative fixed target (+4%), stop-loss (-2%), and time-exit (max 10 days) policy.

    Conservative execution rules:
    - Intrabar conflict: If both stop and target touched on same bar -> assume STOP hit.
    - Gap-through-stop: If bar opens below stop level -> exit at open (worse loss).
    - Time exit: Exit at open on the 11th trading session (after 10 trading days held).
    """

    def __init__(
        self,
        stop_loss_pct: Optional[float] = None,
        profit_target_pct: Optional[float] = None,
        max_hold_days: Optional[int] = None,
    ) -> None:
        """Initialize exit policy thresholds from config or overrides."""
        settings = config.get_settings()
        self.stop_loss_pct = stop_loss_pct if stop_loss_pct is not None else settings.stop_loss_pct
        self.profit_target_pct = (
            profit_target_pct if profit_target_pct is not None else settings.profit_target_pct
        )
        self.max_hold_days = (
            max_hold_days if max_hold_days is not None else settings.max_hold_days
        )

    def evaluate_bar(
        self,
        entry_date: dt.date,
        entry_price: float,
        current_bar: Bar,
        days_held: int,
    ) -> ExitDecision:
        """Evaluate current daily bar against stop, target, and time rules."""
        stop_price = entry_price * (1.0 - self.stop_loss_pct)
        target_price = entry_price * (1.0 + self.profit_target_pct)

        # 1. Time exit: If position has been held for max_hold_days, exit at Day 11 open
        if days_held >= self.max_hold_days:
            return ExitDecision(
                should_exit=True,
                exit_date=current_bar.date,
                exit_price=current_bar.open,
                exit_reason=ExitReason.TIME,
            )

        # 2. Check for stop condition and target condition
        stop_hit = current_bar.low <= stop_price
        target_hit = current_bar.high >= target_price

        # 3. Intrabar conflict: if BOTH stop and target touched -> assume STOP hit
        if stop_hit and target_hit:
            # Check if opened below stop (gap down)
            if current_bar.open < stop_price:
                actual_exit = current_bar.open
            else:
                actual_exit = stop_price

            return ExitDecision(
                should_exit=True,
                exit_date=current_bar.date,
                exit_price=actual_exit,
                exit_reason=ExitReason.STOP,
            )

        # 4. Stop hit only
        if stop_hit:
            # Gap through stop: opened below stop level
            if current_bar.open < stop_price:
                actual_exit = current_bar.open
            else:
                actual_exit = stop_price

            return ExitDecision(
                should_exit=True,
                exit_date=current_bar.date,
                exit_price=actual_exit,
                exit_reason=ExitReason.STOP,
            )

        # 5. Target hit only
        if target_hit:
            # Gap above target: opened above target level
            if current_bar.open > target_price:
                actual_exit = current_bar.open
            else:
                actual_exit = target_price

            return ExitDecision(
                should_exit=True,
                exit_date=current_bar.date,
                exit_price=actual_exit,
                exit_reason=ExitReason.TARGET,
            )

        # 6. No exit condition met; hold position
        return ExitDecision(should_exit=False)
