"""Market Direction Check (+20 points).

Evaluates whether the broader market benchmark (NIFTY 50) is trading
above its own 20-period EMA on the target date.
"""

import datetime as dt
from typing import Optional
import pandas as pd

from trading_agent.domain.models import Bar, CheckResult
from trading_agent.ports.confidence_check import ConfidenceCheckPort


class MarketDirectionCheck(ConfidenceCheckPort):
    """Market direction check: NIFTY 50 above its own 20-period EMA."""

    CHECK_NAME = "Market Direction Check"
    POINTS = 20
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
        """Evaluate if market index close is above its 20-period EMA."""
        if market_bars is None:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale="INSUFFICIENT_DATA: No market benchmark (NIFTY 50) bars provided.",
            )

        relevant_bars = [b for b in market_bars if b.date <= target_date]
        if len(relevant_bars) < self.PERIOD:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"INSUFFICIENT_DATA: Need at least {self.PERIOD} market bars for "
                    f"20-period EMA; found {len(relevant_bars)}."
                ),
            )

        closes = pd.Series([b.close for b in relevant_bars], dtype=float)
        ema_series = closes.ewm(span=self.PERIOD, adjust=False).mean()

        latest_close = relevant_bars[-1].close
        latest_ema = float(ema_series.iloc[-1])

        if latest_close > latest_ema:
            return CheckResult(
                check_name=self.name,
                passed=True,
                points_awarded=self.max_points,
                max_points=self.max_points,
                rationale=(
                    f"PASS: NIFTY 50 close ({latest_close:.2f}) > "
                    f"20 EMA ({latest_ema:.2f}). Market is green/bullish."
                ),
            )

        return CheckResult(
            check_name=self.name,
            passed=False,
            points_awarded=0,
            max_points=self.max_points,
            rationale=(
                f"FAIL: NIFTY 50 close ({latest_close:.2f}) <= "
                f"20 EMA ({latest_ema:.2f}). Market is flat or bearish."
            ),
        )
