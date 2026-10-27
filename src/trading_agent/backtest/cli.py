"""CLI command for running backtesting and validation simulations.

Parses arguments, enforces score coverage checks (>=95%), simulates trades
chronologically using BacktestEngine, calculates metrics, saves run results,
and outputs a beginner-friendly terminal report with optional CSV export.
"""

import argparse
import csv
import datetime as dt
import logging
from pathlib import Path
import sys
from typing import Optional

from trading_agent.adapters.market_data.yfinance_adapter import YFinanceMarketDataAdapter
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.backtest.report import print_backtest_report
from trading_agent.backtest.runner import execute_backtest
from trading_agent.config import get_settings

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

    print(f"Fetching market bars for benchmark {bench_symbol}...")
    result = execute_backtest(
        start_date=start_date,
        end_date=end_date,
        storage=storage,
        market_data=market_data,
        watchlist=symbols,
        benchmark_symbol=bench_symbol,
        meter_version=active_meter_version,
    )

    if not result.success:
        print(f"❌ Error: {result.error_message}")
        if "Insufficient score coverage" in (result.error_message or ""):
            print(f"\nPlease run backfill first to compute scores for this range:")
            print(f"  uv run backfill --years {settings.backfill_years}\n")
        return 1

    print(f"✓ Simulation completed: {len(result.trades)} trades executed.")

    # Print beginner-friendly report
    print_backtest_report(
        metrics=result.metrics,
        start_date=start_date,
        end_date=end_date,
        initial_capital=result.initial_capital,
        run_id=result.run_id or "",
        meter_version=active_meter_version,
    )

    # Export CSV if requested
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
                for t in result.trades:
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
