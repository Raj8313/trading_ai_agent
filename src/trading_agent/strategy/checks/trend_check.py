"""Trend Check (+25 points).

Evaluates whether the stock's closing price is above its 20-period EMA
and whether the 20-period EMA is rising (ema[-1] > ema[-2]).
"""

import datetime as dt
from typing import Optional
import pandas as pd

from trading_agent.domain.models import Bar, CheckResult
from trading_agent.ports.confidence_check import ConfidenceCheckPort


class TrendCheck(ConfidenceCheckPort):
    """Trend check: Price above 20 EMA and 20 EMA rising."""

    CHECK_NAME = "Trend Check"
    POINTS = 25
    PERIOD = 20

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
        """Evaluate if price is above 20 EMA and EMA is rising as of target_date."""
        # Filter bars up to target_date
        relevant_bars = [b for b in bars if b.date <= target_date]

        # Need at least PERIOD + 1 bars to verify EMA slope (ema[-1] vs ema[-2])
        if len(relevant_bars) < (self.PERIOD + 1):
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"INSUFFICIENT_DATA: Need at least {self.PERIOD + 1} daily bars to "
                    f"calculate 20 EMA slope; found {len(relevant_bars)}."
                ),
            )

        closes = pd.Series([b.close for b in relevant_bars], dtype=float)
        ema_series = closes.ewm(span=self.PERIOD, adjust=False).mean()

        latest_close = relevant_bars[-1].close
        latest_ema = float(ema_series.iloc[-1])
        prev_ema = float(ema_series.iloc[-2])

        price_above_ema = latest_close > latest_ema
        ema_rising = latest_ema > prev_ema

        if price_above_ema and ema_rising:
            return CheckResult(
                check_name=self.name,
                passed=True,
                points_awarded=self.max_points,
                max_points=self.max_points,
                rationale=(
                    f"PASS: Close ({latest_close:.2f}) > 20 EMA ({latest_ema:.2f}) "
                    f"and 20 EMA is rising ({latest_ema:.2f} > {prev_ema:.2f})."
                ),
            )

        # Build clear diagnostic message
        reasons = []
        if not price_above_ema:
            reasons.append(f"Close ({latest_close:.2f}) <= 20 EMA ({latest_ema:.2f})")
        if not ema_rising:
            reasons.append(f"20 EMA not rising ({latest_ema:.2f} <= {prev_ema:.2f})")

        return CheckResult(
            check_name=self.name,
            passed=False,
            points_awarded=0,
            max_points=self.max_points,
            rationale=f"FAIL: {'; '.join(reasons)}.",
        )
