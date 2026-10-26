"""Stop-Distance Check (+15 points).

Evaluates whether the planned stop-loss distance (e.g. 2%) is sensible relative
to the stock's natural price volatility (noise).
Passes if: 2 * ATR(14) / price >= planned_stop_pct.
Fails if: stop is tighter than normal noise (stop will likely get choked).
Reads stop_loss_pct directly from config to avoid parameter drift.
"""

import datetime as dt
from typing import Optional

import trading_agent.config as config
from trading_agent.domain.models import Bar, CheckResult
from trading_agent.ports.confidence_check import ConfidenceCheckPort


class StopDistanceCheck(ConfidenceCheckPort):
    """Stop-distance check: 2 * ATR(14) / price >= stop_loss_pct."""

    CHECK_NAME = "Stop-Distance Check"
    POINTS = 15
    ATR_PERIOD = 14
    MIN_REQUIRED_BARS = 35  # 20 warmup + 15 bars for ATR calculation

    def __init__(self, stop_loss_pct: Optional[float] = None) -> None:
        """Initialize with optional stop_loss_pct override (defaults to config)."""
        settings = config.get_settings()
        self.stop_loss_pct = stop_loss_pct if stop_loss_pct is not None else settings.stop_loss_pct

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
        """Evaluate if 2x ATR(14) / price >= stop_loss_pct."""
        relevant_bars = [b for b in bars if b.date <= target_date]

        if len(relevant_bars) < self.MIN_REQUIRED_BARS:
            return CheckResult(
                check_name=self.name,
                passed=False,
                points_awarded=0,
                max_points=self.max_points,
                rationale=(
                    f"INSUFFICIENT_DATA: Need at least {self.MIN_REQUIRED_BARS} daily bars "
                    f"to compute ATR(14) volatility buffer; found {len(relevant_bars)}."
                ),
            )

        # Compute True Range over the last 14 bars
        # For bar i in last 14 bars, need prior bar i-1
        eval_window = relevant_bars[-(self.ATR_PERIOD + 1) :]
        tr_values = []
        for i in range(1, len(eval_window)):
            curr = eval_window[i]
            prev = eval_window[i - 1]
            tr = max(
                curr.high - curr.low,
                abs(curr.high - prev.close),
                abs(curr.low - prev.close),
            )
            tr_values.append(tr)

        atr = sum(tr_values) / len(tr_values) if tr_values else 0.0
        latest_close = relevant_bars[-1].close
        noise_buffer_pct = (2.0 * atr) / latest_close if latest_close > 0 else 0.0

        # Boundary condition: noise_buffer_pct >= stop_loss_pct passes (Edge Case 5)
        passed = noise_buffer_pct >= self.stop_loss_pct
        points = self.max_points if passed else 0

        verdict_str = "PASS" if passed else "FAIL"
        operator_str = ">=" if passed else "<"

        rationale = (
            f"{verdict_str}: 2x ATR(14) volatility buffer ({noise_buffer_pct * 100.0:.2f}%) "
            f"{operator_str} planned stop ({self.stop_loss_pct * 100.0:.2f}%). "
            + (
                "Stop is sensible vs volatility."
                if passed
                else "Planned stop distance is tighter than normal stock noise."
            )
        )

        return CheckResult(
            check_name=self.name,
            passed=passed,
            points_awarded=points,
            max_points=self.max_points,
            rationale=rationale,
        )
