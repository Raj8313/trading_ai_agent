"""Performance metrics calculation for backtest trade records.

Pure functions calculating win rates, profit factor, expectancy,
drawdown, streaks, and benchmark baseline comparisons.
"""

from typing import Optional
from pydantic import BaseModel, Field

from trading_agent.domain.models import TradeBand, TradeRecord


class BandMetrics(BaseModel):
    """Performance metrics aggregated for a specific trade band."""

    band: TradeBand = Field(..., description="Trade band evaluated")
    total_trades: int = Field(default=0, description="Total completed trades in this band")
    winning_trades: int = Field(default=0, description="Winning trades (net_pnl > 0)")
    losing_trades: int = Field(default=0, description="Losing trades (net_pnl < 0)")
    win_rate_pct: float = Field(default=0.0, description="Win rate percentage")
    net_pnl: float = Field(default=0.0, description="Total net P&L in currency")


class BacktestMetrics(BaseModel):
    """Aggregate backtest performance analytics."""

    total_trades: int = Field(..., description="Total executed and resolved trades")
    winning_trades: int = Field(..., description="Number of profitable trades")
    losing_trades: int = Field(..., description="Number of unprofitable trades")
    break_even_trades: int = Field(default=0, description="Number of zero P&L trades")
    win_rate_pct: float = Field(..., description="Percentage of winning trades")
    gross_pnl: float = Field(..., description="Gross profit or loss")
    total_fees_and_slippage: float = Field(..., description="Total costs and slippage deducted")
    net_pnl: float = Field(..., description="Net profit or loss after all costs")
    avg_win: float = Field(default=0.0, description="Average net profit on winning trades")
    avg_loss: float = Field(default=0.0, description="Average net loss on losing trades (negative)")
    profit_factor: float = Field(default=0.0, description="Gross gains / gross losses ratio")
    expectancy_per_trade: float = Field(
        default=0.0, description="Expected average net P&L per trade in currency"
    )
    max_drawdown_amount: float = Field(
        default=0.0, description="Maximum peak-to-trough drop in cumulative net P&L"
    )
    max_consecutive_losses: int = Field(default=0, description="Longest losing streak")
    max_consecutive_wins: int = Field(default=0, description="Longest winning streak")
    band_breakdown: dict[str, BandMetrics] = Field(
        default_factory=dict, description="Metrics broken down by TradeBand"
    )
    # Benchmark comparison
    baseline_symbol: str = Field(default="^NSEI", description="Benchmark index ticker")
    baseline_return_amount: float = Field(
        default=0.0, description="Virtual P&L if capital was held in benchmark"
    )
    baseline_return_pct: float = Field(
        default=0.0, description="Benchmark buy-and-hold percentage return"
    )


def calculate_metrics(
    trades: list[TradeRecord],
    baseline_symbol: str = "^NSEI",
    baseline_initial_price: Optional[float] = None,
    baseline_final_price: Optional[float] = None,
    portfolio_initial_capital: float = 300000.0,
) -> BacktestMetrics:
    """Calculate comprehensive performance metrics from a list of completed trades.

    Args:
        trades: List of completed TradeRecord instances.
        baseline_symbol: Symbol of benchmark index (default ^NSEI).
        baseline_initial_price: Benchmark price at start of backtest window.
        baseline_final_price: Benchmark price at end of backtest window.
        portfolio_initial_capital: Virtual total capital allocated to strategy.

    Returns:
        BacktestMetrics object.
    """
    if not trades:
        # Return clean empty metrics if no trades executed
        return BacktestMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            break_even_trades=0,
            win_rate_pct=0.0,
            gross_pnl=0.0,
            total_fees_and_slippage=0.0,
            net_pnl=0.0,
            baseline_symbol=baseline_symbol,
        )

    # Sort trades chronologically by exit date
    sorted_trades = sorted(trades, key=lambda t: t.exit_date)

    total_trades = len(sorted_trades)
    wins = [t for t in sorted_trades if t.net_pnl > 0]
    losses = [t for t in sorted_trades if t.net_pnl < 0]
    evens = [t for t in sorted_trades if t.net_pnl == 0]

    winning_trades = len(wins)
    losing_trades = len(losses)
    break_even_trades = len(evens)

    win_rate_pct = (winning_trades / total_trades) * 100.0

    gross_pnl = sum(t.gross_pnl for t in sorted_trades)
    net_pnl = sum(t.net_pnl for t in sorted_trades)
    total_costs = gross_pnl - net_pnl

    total_gains = sum(t.net_pnl for t in wins)
    total_loss_abs = abs(sum(t.net_pnl for t in losses))

    avg_win = (total_gains / winning_trades) if winning_trades > 0 else 0.0
    avg_loss = (-total_loss_abs / losing_trades) if losing_trades > 0 else 0.0

    if total_loss_abs > 0:
        profit_factor = total_gains / total_loss_abs
    else:
        profit_factor = float("inf") if total_gains > 0 else 0.0

    # Expectancy: (Win% * Avg Win) - (Loss% * |Avg Loss|)
    win_prob = winning_trades / total_trades
    loss_prob = losing_trades / total_trades
    expectancy = (win_prob * avg_win) + (loss_prob * avg_loss)

    # Max Drawdown & Streaks
    max_dd = 0.0
    peak = 0.0
    cum_pnl = 0.0

    current_l_streak = 0
    max_l_streak = 0
    current_w_streak = 0
    max_w_streak = 0

    for t in sorted_trades:
        cum_pnl += t.net_pnl
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd

        # Streak calculation
        if t.net_pnl < 0:
            current_l_streak += 1
            current_w_streak = 0
            if current_l_streak > max_l_streak:
                max_l_streak = current_l_streak
        elif t.net_pnl > 0:
            current_w_streak += 1
            current_l_streak = 0
            if current_w_streak > max_w_streak:
                max_w_streak = current_w_streak
        else:
            current_l_streak = 0
            current_w_streak = 0

    # Band breakdown
    band_breakdown = {}
    for band in (TradeBand.FULL, TradeBand.HALF, TradeBand.NONE):
        band_trades = [t for t in sorted_trades if t.band == band]
        if band_trades:
            b_total = len(band_trades)
            b_wins = len([t for t in band_trades if t.net_pnl > 0])
            b_losses = len([t for t in band_trades if t.net_pnl < 0])
            b_pnl = sum(t.net_pnl for t in band_trades)
            band_breakdown[band.value] = BandMetrics(
                band=band,
                total_trades=b_total,
                winning_trades=b_wins,
                losing_trades=b_losses,
                win_rate_pct=(b_wins / b_total) * 100.0,
                net_pnl=b_pnl,
            )

    # Baseline calculation
    base_ret_amt = 0.0
    base_ret_pct = 0.0
    if baseline_initial_price and baseline_final_price and baseline_initial_price > 0:
        base_ret_pct = ((baseline_final_price - baseline_initial_price) / baseline_initial_price) * 100.0
        base_ret_amt = portfolio_initial_capital * (base_ret_pct / 100.0)

    return BacktestMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        break_even_trades=break_even_trades,
        win_rate_pct=round(win_rate_pct, 2),
        gross_pnl=round(gross_pnl, 2),
        total_fees_and_slippage=round(total_costs, 2),
        net_pnl=round(net_pnl, 2),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.0,
        expectancy_per_trade=round(expectancy, 2),
        max_drawdown_amount=round(max_dd, 2),
        max_consecutive_losses=max_l_streak,
        max_consecutive_wins=max_w_streak,
        band_breakdown=band_breakdown,
        baseline_symbol=baseline_symbol,
        baseline_return_amount=round(base_ret_amt, 2),
        baseline_return_pct=round(base_ret_pct, 2),
    )
