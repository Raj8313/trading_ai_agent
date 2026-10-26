"""CLI command for running backtesting and validation simulations.

Parses arguments, enforces score coverage checks (>=95%), simulates trades
chronologically using BacktestEngine, calculates metrics, saves run results,
and outputs a beginner-friendly terminal report with optional CSV export.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Optional

from trading_agent.adapters.market_data.yfinance_adapter import YFinanceMarketDataAdapter
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.backtest.engine import BacktestEngine
from trading_agent.backtest.metrics import calculate_metrics
from trading_agent.backtest.policies.exit_policy import FixedTargetStopExitPolicy
from trading_agent.backtest.report import print_backtest_report
from trading_agent.config import get_settings
from trading_agent.domain.models import Bar, Score

logger = logging.getLogger("trading_agent.backtest.cli")


def run_backtest_simulation(
    start_date: dt.date,
    end_date: dt.date,
    db_path: Optional[str] = None,
    export_csv: Optional[str] = None,
    watchlist: Optional[list[str]] = None,
    benchmark_symbol: Optional[str] = None,
    meter_version: Optional[str] = None,
) -> int:
    """Execute backtest simulation workflow with validation and reporting."""
    settings = get_settings()
    target_db = db_path or settings.database_path
    symbols = watchlist or settings.watchlist
    bench_symbol = benchmark_symbol or settings.benchmark_symbol
    active_meter_version = meter_version or settings.meter_version or "v2"

    if start_date >= end_date:
        print(f"❌ Error: Start date ({start_date}) must be earlier than end date ({end_date}).")
        return 1

    storage = SqliteStorageAdapter(db_path=target_db)
    market_data = YFinanceMarketDataAdapter(storage_adapter=storage)

    print(f"\n=======================================================")
    print(f"🔬 RUNNING BACKTEST VALIDATION")
    print(f"   Period:    {start_date} to {end_date}")
    print(f"   Database:  {target_db}")
    print(f"   Meter Ver: {active_meter_version}")
    print(f"   Symbols:   {', '.join(symbols)}")
    print(f"   Benchmark: {bench_symbol}")
    print(f"=======================================================\n")

    # 1. Fetch benchmark bars for calendar & baseline
    fetch_start = start_date - dt.timedelta(days=35)
    fetch_end = end_date + dt.timedelta(days=25)
    print(f"Fetching market bars for benchmark {bench_symbol}...")
    try:
        bench_bars = market_data.fetch_daily_bars(bench_symbol, fetch_start, fetch_end)
    except Exception as e:
        logger.warning("Could not fetch benchmark bars: %s", e)
        bench_bars = []

    bench_in_range = [b for b in bench_bars if start_date <= b.date <= end_date]
    if bench_in_range:
        expected_trading_days = len(bench_in_range)
    else:
        curr, weekdays = start_date, 0
        while curr <= end_date:
            if curr.weekday() < 5:
                weekdays += 1
            curr += dt.timedelta(days=1)
        expected_trading_days = max(1, int(weekdays * 0.95))

    # 2. Check score version integrity and coverage (>= 95% required)
    offending_symbols = []
    for sym in symbols:
        all_scores = storage.get_scores_for_symbol_in_range(sym, start_date, end_date, meter_version=None)
        v2_scores = [s for s in all_scores if s.meter_version == active_meter_version]
        v1_scores = [s for s in all_scores if s.meter_version == "v1"]

        if len(v2_scores) == 0 and len(v1_scores) > 0:
            print(f"❌ Error: Symbol {sym} has only v1 scores. Please run backfill with {active_meter_version} meter first.")
            return 1

        v1_dates, v2_dates = {s.date for s in v1_scores}, {s.date for s in v2_scores}
        if (v1_dates - v2_dates) and len(v2_scores) > 0:
            print(f"❌ Error: Mixed meter version data for {sym}. Missing {active_meter_version} scores on {len(v1_dates - v2_dates)} dates.")
            return 1

        coverage_pct = (len(v2_scores) / expected_trading_days) * 100.0 if expected_trading_days > 0 else 0.0
        if coverage_pct < 95.0:
            offending_symbols.append((sym, len(v2_scores), expected_trading_days, coverage_pct))

    if offending_symbols:
        print(f"❌ Error: Insufficient score coverage for date range {start_date} to {end_date} (meter {active_meter_version}).")
        print("The following symbols have < 95% scored trading days:")
        for sym, actual, expected, pct in offending_symbols:
            print(f"  • {sym:<15}: {actual:>3} / {expected} days ({pct:.1f}%)")
        print(f"\nPlease run backfill first to compute scores for this range:")
        print(f"  uv run backfill --years {settings.backfill_years}\n")
        return 1

    # 3. Configure Exit Policy & Engine
    exit_policy = FixedTargetStopExitPolicy(
        stop_loss_pct=settings.stop_loss_pct,
        profit_target_pct=settings.profit_target_pct,
        max_hold_days=settings.max_hold_days,
    )
    engine = BacktestEngine(
        storage=storage,
        market_data=market_data,
        exit_policy=exit_policy,
        capital_per_full=100000.0,
        capital_per_half=50000.0,
        max_concurrent_positions=3,
        round_trip_cost_rate=0.001,
        slippage_rate=0.0005,
        meter_version=active_meter_version,
    )

    print("\nExecuting backtest simulation across historical timeline...")
    trades = engine.run(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )
    print(f"✓ Simulation completed: {len(trades)} trades executed.")

    # 5. Baseline price calculations
    bench_initial_price = bench_in_range[0].close if bench_in_range else None
    bench_final_price = bench_in_range[-1].close if bench_in_range else None

    # 6. Performance metrics calculation
    metrics = calculate_metrics(
        trades=trades,
        baseline_symbol=bench_symbol,
        baseline_initial_price=bench_initial_price,
        baseline_final_price=bench_final_price,
        portfolio_initial_capital=300000.0,
    )

    # 7. Persistence & Versioning (Edge Case 7)
    config_dict = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "symbols": sorted(symbols),
        "benchmark": bench_symbol,
        "meter_version": active_meter_version,
        "stop_loss_pct": settings.stop_loss_pct,
        "profit_target_pct": settings.profit_target_pct,
        "max_holding_days": settings.max_hold_days,
        "max_concurrent": 3,
        "round_trip_cost_pct": 0.001,
        "slippage_pct": 0.0005,
    }
    config_hash = hashlib.sha256(json.dumps(config_dict, sort_keys=True).encode()).hexdigest()[:12]
    existing_runs_count = storage.get_backtest_run_count(config_hash)
    version = existing_runs_count + 1
    run_id = f"run_{config_hash}_v{version}"

    storage.save_backtest_run(
        run_id=run_id,
        started_at=dt.datetime.now(dt.timezone.utc),
        params=config_dict,
        config_hash=config_hash,
        metrics=metrics.model_dump(),
        trades=trades,
        version=version,
    )

    # 8. Print beginner-friendly report
    print_backtest_report(
        metrics=metrics,
        start_date=start_date,
        end_date=end_date,
        initial_capital=300000.0,
        run_id=run_id,
        meter_version=active_meter_version,
    )

    # 9. Export CSV if requested
    if export_csv:
        export_path = Path(export_csv)
        try:
            with open(export_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "symbol", "signal_date", "entry_date", "entry_price",
                    "exit_date", "exit_price", "exit_reason", "band",
                    "position_size", "gross_pnl", "net_pnl", "rule_followed",
                ])
                for t in trades:
                    writer.writerow([
                        t.symbol,
                        t.signal_date.isoformat(),
                        t.entry_date.isoformat(),
                        f"{t.entry_price:.2f}",
                        t.exit_date.isoformat(),
                        f"{t.exit_price:.2f}",
                        t.exit_reason.value,
                        t.band.value,
                        f"{t.position_size:.2f}",
                        f"{t.gross_pnl:.2f}",
                        f"{t.net_pnl:.2f}",
                        1 if t.rule_followed else 0,
                    ])
            print(f"✓ Trade records successfully exported to {export_path}")
        except Exception as e:
            print(f"❌ Failed to export CSV to {export_path}: {e}")
            return 1

    return 0


def backtest_cli() -> None:
    """CLI entry point for running backtests."""
    parser = argparse.ArgumentParser(
        description="Run historical backtesting and validation on confidence scores."
    )
    today = dt.date.today()
    one_year_ago = today - dt.timedelta(days=365)

    parser.add_argument(
        "--start",
        type=str,
        default=one_year_ago.isoformat(),
        help=f"Start date (YYYY-MM-DD), default: {one_year_ago.isoformat()}",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=today.isoformat(),
        help=f"End date (YYYY-MM-DD), default: {today.isoformat()}",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database file (defaults to config)",
    )
    parser.add_argument(
        "--export",
        type=str,
        default=None,
        help="Path to export executed trades CSV (optional)",
    )
    parser.add_argument(
        "--meter-version",
        type=str,
        default=None,
        help="Meter version to simulate on (default: v2)",
    )

    args = parser.parse_args()

    try:
        start_date = dt.date.fromisoformat(args.start)
    except ValueError:
        print(f"❌ Error: Invalid start date format '{args.start}'. Expected YYYY-MM-DD.")
        sys.exit(1)

    try:
        end_date = dt.date.fromisoformat(args.end)
    except ValueError:
        print(f"❌ Error: Invalid end date format '{args.end}'. Expected YYYY-MM-DD.")
        sys.exit(1)

    exit_code = run_backtest_simulation(
        start_date=start_date,
        end_date=end_date,
        db_path=args.db,
        export_csv=args.export,
        meter_version=args.meter_version,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    backtest_cli()
