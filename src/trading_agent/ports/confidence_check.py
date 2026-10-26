"""Confidence check port interface."""

from abc import ABC, abstractmethod
import datetime as dt
from typing import Optional
from trading_agent.domain.models import Bar, CheckResult


class ConfidenceCheckPort(ABC):
    """Abstract interface for a single, isolated confidence rule/check.

    Adheres strictly to the Open-Closed Principle: new checks are added
    by implementing this port, without altering the Confidence Meter or other checks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable identifier for this check."""
        pass

    @property
    @abstractmethod
    def max_points(self) -> int:
        """Maximum points this check can award when passing."""
        pass

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        target_date: dt.date,
        bars: list[Bar],
        market_bars: Optional[list[Bar]] = None,
    ) -> CheckResult:
        """Evaluate the check against historical price and market bars up to target_date.

        Args:
            symbol: Symbol being evaluated.
            target_date: Date to evaluate.
            bars: Symbol's historical bars up to and including target_date.
            market_bars: Benchmark (e.g. NIFTY 50) bars up to target_date if needed.

        Returns:
            CheckResult with points awarded and human-readable rationale.
        """
        pass
