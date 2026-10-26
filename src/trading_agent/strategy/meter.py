"""Confidence Meter implementation.

Evaluates pluggable confidence checks against stock and market bars,
producing auditable scores and actionable trading signals.
"""

import datetime as dt
from typing import Optional

from trading_agent.domain.models import Bar, Score, Signal, SignalAction, TradeBand
from trading_agent.ports.confidence_check import ConfidenceCheckPort
from trading_agent.strategy.checks.market_direction_check import MarketDirectionCheck
from trading_agent.strategy.checks.trend_check import TrendCheck
from trading_agent.strategy.checks.volume_check import VolumeCheck


class ConfidenceMeter:
    """The Confidence Meter orchestrates pluggable checks to score a symbol.

    Designed according to the Open-Closed Principle (OCP):
    new checks can be registered without modifying this class.
    """

    def __init__(self, checks: Optional[list[ConfidenceCheckPort]] = None) -> None:
        """Initialize ConfidenceMeter with a list of checks or standard defaults."""
        if checks is None:
            self._checks: list[ConfidenceCheckPort] = [
                TrendCheck(),
                VolumeCheck(),
                MarketDirectionCheck(),
            ]
        else:
            self._checks = list(checks)

    @property
    def checks(self) -> list[ConfidenceCheckPort]:
        """Return the list of currently registered checks."""
        return list(self._checks)

    def register_check(self, check: ConfidenceCheckPort) -> None:
        """Register an additional check into the meter."""
        self._checks.append(check)

    def calculate_score(
        self,
        symbol: str,
        target_date: dt.date,
        bars: list[Bar],
        market_bars: Optional[list[Bar]] = None,
    ) -> Score:
        """Execute all registered checks and compute the composite Score.

        Args:
            symbol: Ticker symbol being evaluated.
            target_date: Evaluation date.
            bars: Symbol's historical bars.
            market_bars: Benchmark market bars (e.g. NIFTY 50).

        Returns:
            Score containing individual check results, total points, and band.
        """
        results = []
        total_points = 0

        for check in self._checks:
            result = check.evaluate(
                symbol=symbol,
                target_date=target_date,
                bars=bars,
                market_bars=market_bars,
            )
            results.append(result)
            total_points += result.points_awarded

        band = Score.calculate_band(total_points)

        return Score(
            symbol=symbol,
            date=target_date,
            check_results=results,
            total_points=total_points,
            band=band,
        )

    def generate_signal(self, score: Score) -> Signal:
        """Derive an actionable trading signal from a Score.

        Args:
            score: The computed Score model.

        Returns:
            Signal instance with BUY_FULL, BUY_HALF, or PASS action.
        """
        if score.band == TradeBand.FULL:
            action = SignalAction.BUY_FULL
        elif score.band == TradeBand.HALF:
            action = SignalAction.BUY_HALF
        else:
            action = SignalAction.PASS

        return Signal(
            symbol=score.symbol,
            date=score.date,
            score=score,
            band=score.band,
            action=action,
        )
