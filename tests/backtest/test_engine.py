"""Unit tests for BacktestEngine including Lookahead Guard and edge cases."""

import datetime as dt
from unittest.mock import MagicMock
import pytest

from trading_agent.backtest.engine import BacktestEngine
from trading_agent.backtest.policies.exit_policy import FixedTargetStopExitPolicy
from trading_agent.domain.models import (
    Bar,
    CheckResult,
    ExitReason,
    Score,
    TradeBand,
)


def make_bar(date_val: dt.date, open_p: float, high_p: float, low_p: float, close_p: float) -> Bar:
    """Helper to create a valid Bar."""
    return Bar(
        date=date_val,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=100000,
    )


def make_score(symbol: str, date_val: dt.date, band: TradeBand = TradeBand.HALF, pts: int = 65) -> Score:
    """Helper to create a Score."""
    return Score(
        symbol=symbol,
        date=date_val,
        check_results=[],
        total_points=pts,
        band=band,
    )


def test_lookahead_guard_and_crash_day():
    """Exit Criterion 2: Lookahead Guard test.

    Proves entry executes strictly on Day D+1 Open, and catastrophic crash on Day D+1
    cannot influence Day D signal/entry decision.
    """
    mock_storage = MagicMock()
    mock_market = MagicMock()

    day_d = dt.date(2024, 1, 10)
    day_d1 = dt.date(2024, 1, 11)
    day_d2 = dt.date(2024, 1, 12)

    # Signal on Day D
    mock_storage.get_score.side_effect = lambda sym, d: make_score(sym, d, TradeBand.HALF, 65) if d == day_d else None

    # Bars: On Day D+1, opens at 100.0, then crashes massively to 50.0!
    bars = [
        make_bar(day_d, 98.0, 100.0, 97.0, 99.0),
        make_bar(day_d1, 100.0, 100.5, 50.0, 52.0),  # Huge crash
        make_bar(day_d2, 51.0, 53.0, 49.0, 50.0),
    ]
    mock_market.fetch_daily_bars.return_value = bars

    engine = BacktestEngine(storage=mock_storage, market_data=mock_market)
    trades = engine.run(["CRASH.NS"], start_date=day_d, end_date=day_d1)

    assert len(trades) == 1
    trade = trades[0]

    # 1. Entry must be STRICTLY after signal date (entry_date > signal_date)
    assert trade.signal_date == day_d
    assert trade.entry_date == day_d1
    assert trade.entry_date > trade.signal_date

    # 2. Entry price must be based on Day D+1 Open (+ slippage), not Day D Close
    assert abs(trade.entry_price - 100.0 * 1.0005) < 0.01

    # 3. Crash on Day D+1 hits the stop-loss on Day D+1
    assert trade.exit_date == day_d1
    assert trade.exit_reason == ExitReason.STOP


def test_capacity_limit_and_skipped_logging():
    """Exit Criterion 8: Capacity limit enforces max 3 concurrent positions and logs SKIPPED_NO_CAPACITY."""
    mock_storage = MagicMock()
    mock_market = MagicMock()

    day_d = dt.date(2024, 1, 10)
    day_d1 = dt.date(2024, 1, 11)
    day_d2 = dt.date(2024, 1, 12)

    symbols = ["SYM1.NS", "SYM2.NS", "SYM3.NS", "SYM4.NS"]

    # All 4 symbols fire signals on Day D
    def get_score_mock(sym, d):
        if d == day_d:
            pts = 65 if sym != "SYM4.NS" else 60
            return make_score(sym, d, TradeBand.HALF, pts)
        return None

    mock_storage.get_score.side_effect = get_score_mock

    # Bar data for all symbols
    bars = [
        make_bar(day_d, 100.0, 101.0, 99.0, 100.0),
        make_bar(day_d1, 100.0, 101.0, 99.0, 100.0),
        make_bar(day_d2, 100.0, 101.0, 99.0, 100.0),
    ]
    mock_market.fetch_daily_bars.return_value = bars

    engine = BacktestEngine(
        storage=mock_storage,
        market_data=mock_market,
        max_concurrent_positions=3,
    )
    engine.run(symbols, start_date=day_d, end_date=day_d1)

    # 4th symbol must be skipped due to capacity limit
    skipped_events = [e for e in engine.events if e.event_type == "SKIPPED_NO_CAPACITY"]
    assert len(skipped_events) == 1
    assert skipped_events[0].symbol == "SYM4.NS"


def test_signal_unresolved_on_final_day():
    """Exit Criterion 8: Signal on final day of data logs SIGNAL_UNRESOLVED."""
    mock_storage = MagicMock()
    mock_market = MagicMock()

    final_day = dt.date(2024, 1, 10)
    mock_storage.get_score.return_value = make_score("LAST.NS", final_day, TradeBand.HALF, 65)

    bars = [make_bar(final_day, 100.0, 102.0, 99.0, 101.0)]
    mock_market.fetch_daily_bars.return_value = bars

    engine = BacktestEngine(storage=mock_storage, market_data=mock_market)
    trades = engine.run(["LAST.NS"], start_date=final_day, end_date=final_day)

    assert len(trades) == 0
    unresolved_events = [e for e in engine.events if e.event_type == "SIGNAL_UNRESOLVED"]
    assert len(unresolved_events) == 1
    assert unresolved_events[0].symbol == "LAST.NS"


def test_missing_price_data_logged():
    """Exit Criterion 8: Missing D+1 bar data logs MISSING_PRICE_DATA."""
    mock_storage = MagicMock()
    mock_market = MagicMock()

    day_d = dt.date(2024, 1, 10)
    day_d1 = dt.date(2024, 1, 11)

    mock_storage.get_score.side_effect = lambda sym, d: make_score(sym, d, TradeBand.HALF, 65) if d == day_d and sym == "SYM_GAP.NS" else None

    # SYM_OK has both days (so day_d1 is an established trading day on the calendar)
    # but SYM_GAP is missing its bar on day_d1
    def mock_fetch(sym, s, e):
        if sym == "SYM_GAP.NS":
            return [make_bar(day_d, 100.0, 102.0, 99.0, 101.0)]
        return [
            make_bar(day_d, 100.0, 102.0, 99.0, 101.0),
            make_bar(day_d1, 101.0, 103.0, 100.0, 102.0),
        ]

    mock_market.fetch_daily_bars.side_effect = mock_fetch

    engine = BacktestEngine(storage=mock_storage, market_data=mock_market)
    trades = engine.run(["SYM_GAP.NS", "SYM_OK.NS"], start_date=day_d, end_date=day_d1)

    assert len(trades) == 0
    missing_events = [e for e in engine.events if e.event_type == "MISSING_PRICE_DATA"]
    assert len(missing_events) == 1
    assert missing_events[0].symbol == "SYM_GAP.NS"


def test_successful_target_trade_full_lifecycle():
    """Verify clean full lifecycle of a trade reaching target with cost deduction."""
    mock_storage = MagicMock()
    mock_market = MagicMock()

    day_d = dt.date(2024, 1, 1)
    day_d1 = dt.date(2024, 1, 2)
    day_d2 = dt.date(2024, 1, 3)

    mock_storage.get_score.side_effect = lambda sym, d: make_score(sym, d, TradeBand.FULL, 85) if d == day_d else None

    # Day D+1 enters at 100.0. Day D+2 hits target (+4% = 104.0)
    bars = [
        make_bar(day_d, 99.0, 100.0, 98.0, 99.5),
        make_bar(day_d1, 100.0, 101.0, 99.0, 100.5),  # Entry at 100.0 (+slippage)
        make_bar(day_d2, 102.0, 104.5, 101.5, 104.0),  # Target hit at 104.0
    ]
    mock_market.fetch_daily_bars.return_value = bars

    engine = BacktestEngine(
        storage=mock_storage,
        market_data=mock_market,
        capital_per_full=100000.0,
        round_trip_cost_rate=0.001,  # 0.1% = ₹100
        slippage_rate=0.0005,        # 0.05%
    )
    trades = engine.run(["WIN.NS"], start_date=day_d, end_date=day_d2)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.band == TradeBand.FULL
    assert trade.exit_reason == ExitReason.TARGET
    assert trade.position_size == 100000.0
    assert trade.gross_pnl > 3800.0  # Approx +4% minus slippage
    assert trade.net_pnl < trade.gross_pnl  # Costs deducted
    # Cost deduction should be ₹100 (0.1% of 100,000)
    assert round(trade.gross_pnl - trade.net_pnl, 2) == 100.0
