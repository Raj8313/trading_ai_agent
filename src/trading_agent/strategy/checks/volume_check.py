"""Volume Check (+20 points).

Evaluates whether the latest bar's volume is greater than 1.5x its
preceding 20-period average volume.
"""

import datetime as dt
from typing import Optional

from trading_agent.domain.models import Bar, CheckResult
from trading_agent.ports.confidence_check import ConfidenceCheckPort


class VolumeCheck(ConfidenceCheckPort):
    """Volume check: Latest volume > 1.5x 20-period average volume."""

    CHECK_NAME = "Volume Check"
    POINTS = 20
    PERIOD = 20
    MULTIPLIER = 1.5

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
        """Evaluate if latest volume is > 1.5x its 20-period average."""
        relevant_bars = [b for b in bars if b.date <= target_date]

        if len(relevant_bars) < (self.PERIOD + 1):
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"INSUFFICIENT_DATA: Need at least {self.PERIOD + 1} daily bars (20 baseline + latest) "
                    f"to evaluate volume; found {len(relevant_bars)}."
                ),
            )

        # Baseline: 20 bars prior to the latest bar
        baseline_bars = relevant_bars[-(self.PERIOD + 1) : -1]
        baseline_volumes = [b.volume for b in baseline_bars]
        avg_volume = sum(baseline_volumes) / len(baseline_volumes)

        if avg_volume == 0:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale="INSUFFICIENT_DATA: 20-period baseline volume average is 0.",
            )

        latest_bar = relevant_bars[-1]
        latest_volume = latest_bar.volume
        threshold = self.MULTIPLIER * avg_volume

        if latest_volume > threshold:
            ratio = latest_volume / avg_volume
            return CheckResult(
                check_name=self.name,
                passed=True,
                points_awarded=self.max_points,
                max_points=self.max_points,
                rationale=(
                    f"PASS: Latest volume ({latest_volume:,}) is {ratio:.2f}x "
                    f"20-period avg ({avg_volume:,.1f}), crossing 1.5x threshold ({threshold:,.1f})."
                ),
            )

        ratio = latest_volume / avg_volume
        return CheckResult(
            check_name=self.name,
            passed=False,
            points_awarded=0,
            max_points=self.max_points,
            rationale=(
                f"FAIL: Latest volume ({latest_volume:,}) is {ratio:.2f}x "
                f"20-period avg ({avg_volume:,.1f}), below 1.5x threshold ({threshold:,.1f})."
            ),
        )
