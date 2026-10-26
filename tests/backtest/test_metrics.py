"""Unit tests and known-answer tests for Backtest Metrics."""

import datetime as dt
from trading_agent.backtest.metrics import calculate_metrics
from trading_agent.domain.models import ExitReason, TradeBand, TradeRecord


def make_trade(
    exit_day: int,
    gross_pnl: float,
    net_pnl: float,
    band: TradeBand = TradeBand.HALF,
) -> TradeRecord:
    """Helper to generate a TradeRecord with specified PnL."""
    base_date = dt.date(2024, 1, 15)
    exit_date = base_date + dt.timedelta(days=exit_day)
    entry_date = exit_date - dt.timedelta(days=1)
    signal_date = entry_date - dt.timedelta(days=1)
    return TradeRecord(
        symbol="TEST.NS",
        signal_date=signal_date,
        entry_date=entry_date,
        entry_price=100.0,
        exit_date=exit_date,
        exit_price=100.0 + (gross_pnl / 100.0),
        exit_reason=ExitReason.TARGET if gross_pnl > 0 else ExitReason.STOP,
        band=band,
        position_size=50000.0,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        rule_followed=True,
    )


def test_metrics_empty_trades():
    """Verify metrics on empty trade list returns clean zeroed object."""
    metrics = calculate_metrics([])
    assert metrics.total_trades == 0
    assert metrics.win_rate_pct == 0.0
    assert metrics.net_pnl == 0.0


def test_metrics_known_answer_hand_calculation():
    """Exit Criterion 9: Known-answer test on synthetic trade list with hand-verified math."""
    # 4 Hand-calculated trades:
    # 1: +1900 net (HALF)
    # 2: -1100 net (HALF)
    # 3: +3800 net (FULL)
    # 4: -2100 net (HALF)
    trades = [
        make_trade(exit_day=5, gross_pnl=2000.0, net_pnl=1900.0, band=TradeBand.HALF),
        make_trade(exit_day=10, gross_pnl=-1000.0, net_pnl=-1100.0, band=TradeBand.HALF),
        make_trade(exit_day=15, gross_pnl=4000.0, net_pnl=3800.0, band=TradeBand.FULL),
        make_trade(exit_day=20, gross_pnl=-2000.0, net_pnl=-2100.0, band=TradeBand.HALF),
    ]

    metrics = calculate_metrics(
        trades=trades,
        baseline_symbol="^NSEI",
        baseline_initial_price=20000.0,
        baseline_final_price=22000.0,  # +10%
        portfolio_initial_capital=300000.0,
    )

    # 1. Counts & Win Rate
    assert metrics.total_trades == 4
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 2
    assert metrics.win_rate_pct == 50.0

    # 2. P&L & Costs
    assert metrics.gross_pnl == 3000.0
    assert metrics.net_pnl == 2500.0
    assert metrics.total_fees_and_slippage == 500.0

    # 3. Averages & Ratios
    assert metrics.avg_win == 2850.0  # (1900 + 3800) / 2
    assert metrics.avg_loss == -1600.0  # (-1100 + -2100) / 2
    assert metrics.profit_factor == 1.78  # 5700 / 3200 = 1.78125
    assert metrics.expectancy_per_trade == 625.0  # (0.5 * 2850) + (0.5 * -1600)

    # 4. Drawdown & Streaks
    assert metrics.max_drawdown_amount == 2100.0
    assert metrics.max_consecutive_losses == 1
    assert metrics.max_consecutive_wins == 1

    # 5. Band breakdown
    half_stats = metrics.band_breakdown["HALF"]
    assert half_stats.total_trades == 3
    assert half_stats.winning_trades == 1
    assert half_stats.losing_trades == 2
    assert half_stats.net_pnl == -1300.0

    full_stats = metrics.band_breakdown["FULL"]
    assert full_stats.total_trades == 1
    assert full_stats.winning_trades == 1
    assert full_stats.losing_trades == 0
    assert full_stats.net_pnl == 3800.0

    # 6. Baseline comparison (NIFTY +10% on 300,000 = +30,000)
    assert metrics.baseline_return_pct == 10.0
    assert metrics.baseline_return_amount == 30000.0


def test_consecutive_streaks_calculation():
    """Verify losing and winning streak calculations."""
    trades = [
        make_trade(exit_day=1, gross_pnl=-500.0, net_pnl=-550.0),
        make_trade(exit_day=2, gross_pnl=-500.0, net_pnl=-550.0),
        make_trade(exit_day=3, gross_pnl=-500.0, net_pnl=-550.0),  # 3 losses
        make_trade(exit_day=4, gross_pnl=1000.0, net_pnl=950.0),
        make_trade(exit_day=5, gross_pnl=1000.0, net_pnl=950.0),   # 2 wins
    ]
    metrics = calculate_metrics(trades)
    assert metrics.max_consecutive_losses == 3
    assert metrics.max_consecutive_wins == 2
