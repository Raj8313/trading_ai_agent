"""Not-At-High Check (+20 points).

Avoids buying tops: fails if the current closing price is within 5% of
the rolling 52-week (approx. 250 trading sessions) high price.
Passes otherwise. Requires at least 250 bars of history.
"""

import datetime as dt
from typing import Optional

from trading_agent.domain.models import Bar, CheckResult
from trading_agent.ports.confidence_check import ConfidenceCheckPort


class NotAtHighCheck(ConfidenceCheckPort):
    """Not-at-high check: fails if close is within 5% of 52-week high."""

    CHECK_NAME = "Not-At-High Check"
    POINTS = 20
    LOOKBACK_BARS = 250
    THRESHOLD_PCT = 0.05  # 5% threshold

    @property
    def name(self) -> str:
        return self.CHECK_NAME

    @property
    def max_points(self) -> int:
        return self.POINTS

    def evaluate(
        self,
        symbol: str,
        target_date: dt.date,
        bars: list[Bar],
        market_bars: Optional[list[Bar]] = None,
    ) -> CheckResult:
        """Evaluate whether current close is outside the top 5% of 52-week high."""
        relevant_bars = [b for b in bars if b.date <= target_date]

        if len(relevant_bars) < self.LOOKBACK_BARS:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"INSUFFICIENT_DATA: Need at least {self.LOOKBACK_BARS} daily bars to "
                    f"compute 52-week high; found {len(relevant_bars)}."
                ),
            )

        window_bars = relevant_bars[-self.LOOKBACK_BARS :]
        high_52w = max(b.high for b in window_bars)
        latest_close = relevant_bars[-1].close

        # Distance percentage from the 52-week high
        distance_pct = (high_52w - latest_close) / high_52w if high_52w > 0 else 0.0

        # Boundary condition: within means strictly less than 5% distance
        if distance_pct < self.THRESHOLD_PCT:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"FAIL: Close ({latest_close:.2f}) is within 5% of 52-week high ({high_52w:.2f}) "
                    f"— distance is {distance_pct * 100.0:.2f}% < {self.THRESHOLD_PCT * 100.0:.1f}%."
                ),
            )

        return CheckResult(
            check_name=self.name,
            passed=True,
            points_awarded=self.max_points,
            max_points=self.max_points,
            rationale=(
                f"PASS: Close ({latest_close:.2f}) is {distance_pct * 100.0:.2f}% below "
                f"52-week high ({high_52w:.2f}) >= {self.THRESHOLD_PCT * 100.0:.1f}% threshold."
            ),
        )
