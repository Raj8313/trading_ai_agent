"""Plain-language terminal reporting for backtest performance.

Presents performance summary tables, per-band breakdowns, baseline comparisons
against NIFTY buy-and-hold, and honest statistical caveats for beginners.
"""

import datetime as dt
from trading_agent.backtest.metrics import BacktestMetrics


def format_currency(val: float) -> str:
    """Format currency values in Indian Rupee format with positive/negative signs."""
    prefix = "+" if val > 0 else ("-" if val < 0 else " ")
    abs_val = abs(val)
    return f"{prefix}₹{abs_val:,.2f}"


def format_pct(val: float) -> str:
    """Format percentage values with sign."""
    prefix = "+" if val > 0 else ("-" if val < 0 else " ")
    return f"{prefix}{abs(val):.2f}%"


def print_backtest_report(
    metrics: BacktestMetrics,
    start_date: dt.date,
    end_date: dt.date,
    initial_capital: float = 300000.0,
    run_id: str = "",
) -> None:
    """Print an auditable, beginner-friendly backtest report to terminal."""
    strategy_return_pct = (metrics.net_pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0

    print("\n" + "=" * 65)
    print(" 📈 CONFIDENCE METER BACKTEST VALIDATION REPORT")
    print("=" * 65)
    if run_id:
        print(f" Run ID:         {run_id}")
    print(f" Period:         {start_date.isoformat()} to {end_date.isoformat()}")
    print(f" Virtual Capital: ₹{initial_capital:,.2f} (Max 3 concurrent positions)")
    print(f" Benchmark:      {metrics.baseline_symbol} Buy & Hold")
    print("-" * 65)

    print("\n1. OVERALL STRATEGY PERFORMANCE")
    print("-" * 65)
    print(f"  • Total Completed Trades:   {metrics.total_trades:>8}")
    print(f"  • Winning Trades:           {metrics.winning_trades:>8}  (Win Rate: {metrics.win_rate_pct:.1f}%)")
    print(f"  • Losing Trades:            {metrics.losing_trades:>8}")
    if metrics.break_even_trades > 0:
        print(f"  • Break-even Trades:        {metrics.break_even_trades:>8}")
    print(f"  • Gross P&L:               {format_currency(metrics.gross_pnl):>12}")
    print(f"  • Total Costs & Slippage:  {format_currency(-abs(metrics.total_fees_and_slippage)):>12}")
    print(f"  • Net P&L (After Costs):   {format_currency(metrics.net_pnl):>12}")
    print(f"  • Strategy Return:         {format_pct(strategy_return_pct):>12}")
    print(f"  • Profit Factor:           {metrics.profit_factor:>12.2f}")
    print(f"  • Expectancy / Trade:      {format_currency(metrics.expectancy_per_trade):>12}")
    print(f"  • Max Drawdown:            {format_currency(-abs(metrics.max_drawdown_amount)):>12}")
    print(f"  • Max Consecutive Losses:   {metrics.max_consecutive_losses:>8}")
    print(f"  • Max Consecutive Wins:     {metrics.max_consecutive_wins:>8}")

    print("\n2. CONFIDENCE BAND BREAKDOWN")
    print("-" * 65)
    print(f"  {'Band':<8} | {'Trades':<8} | {'Win Rate':<10} | {'Net P&L':<15}")
    print(f"  {'-'*8}-+-{'-'*8}-+-{'-'*10}-+-{'-'*15}")
    for band_key in ["FULL", "HALF"]:
        if band_key in metrics.band_breakdown:
            bm = metrics.band_breakdown[band_key]
            print(f"  {bm.band.value:<8} | {bm.total_trades:<8} | {bm.win_rate_pct:>8.1f}% | {format_currency(bm.net_pnl):>15}")
        else:
            print(f"  {band_key:<8} | {0:<8} | {'0.0%':>8} | {format_currency(0.0):>15}")

    print("\n3. BASELINE COMPARISON (Strategy vs NIFTY)")
    print("-" * 65)
    print(f"  • Strategy Net Return:     {format_pct(strategy_return_pct):>10}  ({format_currency(metrics.net_pnl)})")
    print(f"  • NIFTY Buy-and-Hold:      {format_pct(metrics.baseline_return_pct):>10}  ({format_currency(metrics.baseline_return_amount)})")

    net_edge = strategy_return_pct - metrics.baseline_return_pct
    print(f"  • Alpha / Net Edge:        {format_pct(net_edge):>10}")

    print("\n4. HONEST VERDICT")
    print("-" * 65)
    print(
        f"  \"Strategy returned {format_pct(strategy_return_pct)} vs NIFTY "
        f"{format_pct(metrics.baseline_return_pct)} over the period; "
        f"win rate {metrics.win_rate_pct:.1f}% across {metrics.total_trades} trades.\""
    )

    if metrics.total_trades < 30:
        print("\n  ⚠️ STATISTICAL HONESTY WARNING:")
        print(
            f"  Too few trades ({metrics.total_trades} < 30) to draw definitive statistical conclusions.\n"
            "  More market cycles and historical samples are required before committing real capital."
        )

    print("\n5. KNOWN LIMITATIONS (Phase 2 Simulation)")
    print("-" * 65)
    print("  1. EOD Exit Triggers: Stop/Target evaluated on daily closing prices, not tick-by-tick.")
    print("  2. Intrabar Priority: Intrabar conflict conservatively assumes Stop-loss hit.")
    print("  3. Dividends Excluded: Cash dividend distributions are omitted (conservative drag).")
    print("  4. Zero Curve-Fitting: Default fixed rules tested; no parameter optimization applied.")
    print("=" * 65 + "\n")
