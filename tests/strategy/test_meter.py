"""Unit tests for ConfidenceMeter and extensibility (OCP)."""

import datetime as dt
from typing import Optional
from trading_agent.domain.models import Bar, CheckResult, Score, TradeBand
from trading_agent.ports.confidence_check import ConfidenceCheckPort
from trading_agent.strategy.meter import ConfidenceMeter


def make_bar(date_val: dt.date, close_price: float, volume: int = 100000) -> Bar:
    """Helper to generate a Bar."""
    return Bar(
        date=date_val,
        open=close_price,
        high=close_price + 5.0,
        low=close_price - 5.0,
        close=close_price,
        volume=volume,
    )


class HypotheticalFourthCheck(ConfidenceCheckPort):
    """Hypothetical 4th check (+20 points) used to prove Open-Closed Principle."""

    @property
    def name(self) -> str:
        return "Hypothetical Fourth Check"

    @property
    def max_points(self) -> int:
        return 20

    def evaluate(
        self,
        symbol: str,
        target_date: dt.date,
        bars: list[Bar],
        market_bars: Optional[list[Bar]] = None,
    ) -> CheckResult:
        return CheckResult(
            check_name=self.name,
            passed=True,
            points_awarded=20,
            max_points=20,
            rationale="PASS: Fourth check condition satisfied.",
        )


def test_confidence_meter_defaults():
    """Verify default ConfidenceMeter initializes with exactly 3 checks."""
    meter = ConfidenceMeter()
    assert len(meter.checks) == 3
    check_names = [c.name for c in meter.checks]
    assert "Trend Check" in check_names
    assert "Volume Check" in check_names
    assert "Market Direction Check" in check_names


def test_confidence_meter_custom_checks_and_pass_signal():
    """Verify initializing meter with explicit checks and PASS signal generation."""
    meter = ConfidenceMeter(checks=[HypotheticalFourthCheck()])
    assert len(meter.checks) == 1
    assert meter.checks[0].name == "Hypothetical Fourth Check"

    # Score with 0 points -> NONE band -> PASS signal
    score = Score(
        symbol="TEST.NS",
        date=dt.date(2024, 1, 1),
        check_results=[],
        total_points=0,
        band=TradeBand.NONE,
    )
    signal = meter.generate_signal(score)
    assert signal.action == "PASS"
    assert signal.band == TradeBand.NONE


def test_confidence_meter_evaluation_all_pass():
    """Verify ConfidenceMeter aggregates scores correctly when all default checks pass."""
    meter = ConfidenceMeter()
    start_date = dt.date(2024, 1, 1)

    # 30 bars of rising stock prices and baseline volume 100k, last volume 200k
    stock_bars = [
        make_bar(start_date + dt.timedelta(days=i), 100.0 + i * 2.0, 100000)
        for i in range(29)
    ]
    stock_bars.append(make_bar(start_date + dt.timedelta(days=29), 200.0, 200000))

    # Rising market bars
    market_bars = [
        make_bar(start_date + dt.timedelta(days=i), 20000.0 + i * 50.0, 1000000)
        for i in range(30)
    ]
    target_date = stock_bars[-1].date

    score = meter.calculate_score("RELIANCE.NS", target_date, stock_bars, market_bars)
    # 25 (Trend) + 20 (Volume) + 20 (Market) = 65 -> HALF band
    assert score.total_points == 65
    assert score.band == TradeBand.HALF
    assert len(score.check_results) == 3

    signal = meter.generate_signal(score)
    assert signal.action == "BUY_HALF"
    assert signal.band == TradeBand.HALF


def test_confidence_meter_ocp_extensibility():
    """Verify adding a 4th check reaches FULL band without touching meter or existing checks."""
    meter = ConfidenceMeter()
    # Register 4th check (+20 points)
    meter.register_check(HypotheticalFourthCheck())
    assert len(meter.checks) == 4

    start_date = dt.date(2024, 1, 1)
    stock_bars = [
        make_bar(start_date + dt.timedelta(days=i), 100.0 + i * 2.0, 100000)
        for i in range(29)
    ]
    stock_bars.append(make_bar(start_date + dt.timedelta(days=29), 200.0, 200000))

    market_bars = [
        make_bar(start_date + dt.timedelta(days=i), 20000.0 + i * 50.0, 1000000)
        for i in range(30)
    ]
    target_date = stock_bars[-1].date

    score = meter.calculate_score("RELIANCE.NS", target_date, stock_bars, market_bars)
    # 25 + 20 + 20 + 20 = 85 -> FULL band!
    assert score.total_points == 85
    assert score.band == TradeBand.FULL

    signal = meter.generate_signal(score)
    assert signal.action == "BUY_FULL"
