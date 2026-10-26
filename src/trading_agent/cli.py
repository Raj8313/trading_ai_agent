"""Command Line Interface (CLI) for Trading Agent.

Provides commands for backfilling historical bars & confidence scores,
and inspecting score breakdowns for specific symbols and dates.
"""

import argparse
import datetime as dt
import logging
import sys
import time
from typing import Optional

from trading_agent.adapters.market_data.yfinance_adapter import (
    MarketDataFetchError,
    YFinanceMarketDataAdapter,
)
from trading_agent.adapters.notifier.telegram_adapter import TelegramNotifierAdapter
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.config import get_settings
from trading_agent.domain.models import Score
from trading_agent.strategy.checks.not_at_high_check import NotAtHighCheck
from trading_agent.strategy.checks.stop_distance_check import StopDistanceCheck
from trading_agent.strategy.meter import ConfidenceMeter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("trading_agent.cli")


def run_backfill(
    days: Optional[int] = None,
    years: Optional[int] = None,
    watchlist: Optional[list[str]] = None,
    benchmark_symbol: Optional[str] = None,
    db_path: Optional[str] = None,
    meter_version: str = "v2",
) -> int:
    """Execute historical backfill for watchlist and benchmark symbols.

    Args:
        days: Number of historical days to fetch (defaults to backfill_years * 365).
        years: Number of historical years to fetch.
        watchlist: Symbols to backfill.
        benchmark_symbol: Benchmark market symbol (default ^NSEI).
        db_path: SQLite database file path.
        meter_version: Confidence meter version (default v2).

    Returns:
        0 on success, non-zero if any symbol failed.
    """
    settings = get_settings()
    target_db = db_path or settings.database_path
    symbols = watchlist or settings.watchlist
    bench_symbol = benchmark_symbol or settings.benchmark_symbol

    if years is not None:
        total_days = int(years * 365)
    elif days is not None:
        total_days = days
    else:
        total_days = int(settings.backfill_years * 365)

    storage = SqliteStorageAdapter(db_path=target_db)
    notifier = TelegramNotifierAdapter(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    market_data = YFinanceMarketDataAdapter(storage_adapter=storage)

    # Configure meter according to requested version
    meter = ConfidenceMeter()
    if meter_version == "v2":
        meter.register_check(NotAtHighCheck())
        meter.register_check(StopDistanceCheck(stop_loss_pct=settings.stop_loss_pct))

    today = dt.date.today()
    start_date = today - dt.timedelta(days=int(total_days * 1.25))

    print(f"\n=======================================================")
    print(f"🚀 STARTING HISTORICAL BACKFILL ({total_days} days, Meter {meter_version})")
    print(f"   Database:  {target_db}")
    print(f"   Benchmark: {bench_symbol}")
    print(f"   Watchlist: {len(symbols)} symbols")
    print(f"=======================================================\n")

    failed_symbols: list[str] = []

    print(f"Fetching benchmark data for {bench_symbol}...")
    try:
        benchmark_bars = market_data.fetch_daily_bars(bench_symbol, start_date, today)
        print(f"  ✓ {bench_symbol}: Fetched {len(benchmark_bars)} bars.")
    except MarketDataFetchError as e:
        logger.error("Failed to fetch benchmark %s: %s", bench_symbol, e)
        print(f"  ✗ {bench_symbol}: Failed to fetch benchmark market data.")
        failed_symbols.append(bench_symbol)
        benchmark_bars = []

    all_targets = list(symbols)
    if bench_symbol not in all_targets:
        all_targets.append(bench_symbol)

    for symbol in all_targets:
        print(f"\nProcessing {symbol}...")
        try:
            bars = benchmark_bars if (symbol == bench_symbol and benchmark_bars) else market_data.fetch_daily_bars(symbol, start_date, today)
            if not bars:
                print(f"  ⚠ {symbol}: No bar data returned. Skipping scoring.")
                continue

            existing_dates = storage.get_scored_dates_for_symbol(symbol, meter_version=meter_version)
            scored_count, skipped_count = 0, 0

            for idx in range(20, len(bars)):
                target_date = bars[idx].date
                if target_date in existing_dates:
                    skipped_count += 1
                    continue

                stock_history = bars[: idx + 1]
                mkt_history = [b for b in benchmark_bars if b.date <= target_date]

                score = meter.calculate_score(
                    symbol=symbol,
                    target_date=target_date,
                    bars=stock_history,
                    market_bars=mkt_history,
                )
                score.meter_version = meter_version
                storage.save_score(score)
                scored_count += 1

            print(f"  ✓ {symbol}: Scored {scored_count} new bars (skipped {skipped_count} existing).")
            if scored_count > 0:
                time.sleep(0.3)

        except MarketDataFetchError as exc:
            logger.error("Error processing %s: %s", symbol, exc)
            print(f"  ✗ {symbol}: Failed after retries: {exc.reason}")
            failed_symbols.append(symbol)
        except Exception as exc:
            logger.error("Unexpected error for %s: %s", symbol, exc, exc_info=True)
            print(f"  ✗ {symbol}: Unexpected error: {exc}")
            failed_symbols.append(symbol)

    print("\n=======================================================")
    print(f"📊 BACKFILL SUMMARY ({meter_version}) — ROW COUNTS IN SQLITE")
    print("=======================================================")
    counts = storage.get_score_counts_by_symbol(meter_version=meter_version)
    total_stored = sum(counts.values())
    for sym in sorted(counts.keys()):
        print(f"  • {sym:<16} : {counts[sym]:>5} scored bars")
    print("-------------------------------------------------------")
    print(f"  Total Scored Rows: {total_stored}")
    print("=======================================================\n")

    summary_msg = f"Backfill finished: {total_stored} {meter_version} scores persisted across {len(counts)} symbols."
    if failed_symbols:
        summary_msg += f" (Failures: {', '.join(failed_symbols)})"
    notifier.send_notification(summary_msg)

    if failed_symbols:
        print(f"❌ Completed with failures for: {', '.join(failed_symbols)}")
        return 1

    print("✅ Backfill completed successfully!")
    return 0


def run_score(symbol: str, date_str: str, db_path: Optional[str] = None) -> int:
    """Print score breakdown for a specific symbol and date.

    Args:
        symbol: Stock ticker symbol (e.g. RELIANCE, RELIANCE.NS).
        date_str: Date string in YYYY-MM-DD format.
        db_path: Optional SQLite database file path.

    Returns:
        0 if score found and printed, 1 otherwise.
    """
    settings = get_settings()
    target_db = db_path or settings.database_path
    storage = SqliteStorageAdapter(db_path=target_db)

    try:
        target_date = dt.date.fromisoformat(date_str)
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Expected YYYY-MM-DD.")
        return 1

    # Candidate symbol formats (handle with or without .NS)
    candidates = [symbol]
    if not symbol.endswith(".NS") and not symbol.startswith("^"):
        candidates.append(f"{symbol}.NS")
    elif symbol.endswith(".NS"):
        candidates.append(symbol[:-3])

    score: Optional[Score] = None
    matched_symbol: str = symbol
    for cand in candidates:
        score = storage.get_score(cand, target_date, meter_version="v2")
        if not score:
            score = storage.get_score(cand, target_date, meter_version="v1")
        if score:
            matched_symbol = cand
            break

    if not score:
        print(f"\n❌ No score record found in database for '{symbol}' on {date_str}.")
        print(f"   Database: {target_db}")
        print("   Tip: Run `uv run backfill` first to populate historical scores.\n")
        return 1

    print(f"\n=======================================================")
    print(f"🎯 CONFIDENCE METER SCORE BREAKDOWN")
    print(f"   Symbol:  {matched_symbol}")
    print(f"   Date:    {score.date.isoformat()}")
    print(f"   Version: {score.meter_version}")
    print(f"=======================================================")
    for check in score.check_results:
        status = "✅ PASS" if check.passed else "❌ FAIL"
        print(f"\n• {check.check_name} [{status}]")
        print(f"  Points:    +{check.points_awarded} / {check.max_points}")
        print(f"  Rationale: {check.rationale}")

    max_pts = sum(c.max_points for c in score.check_results) if score.check_results else 100
    print("\n-------------------------------------------------------")
    print(f"TOTAL POINTS: {score.total_points} / {max_pts}")
    print(f"TRADE BAND:   {score.band.value}")
    if score.band.value == "FULL":
        action = "🟢 BUY (FULL POSITION)"
    elif score.band.value == "HALF":
        action = "🟡 BUY (HALF POSITION)"
    else:
        action = "🔴 NO TRADE (PASS)"
    print(f"ACTION:       {action}")
    print(f"=======================================================\n")
    return 0


def backfill_cli() -> None:
    """Entry point for standalone `backfill` command."""
    parser = argparse.ArgumentParser(description="Backfill historical daily scores into SQLite.")
    parser.add_argument("--days", type=int, default=None, help="Number of historical days to fetch")
    parser.add_argument("--years", type=int, default=None, help="Number of historical years to fetch (default: 5)")
    parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")
    args = parser.parse_args()
    exit_code = run_backfill(days=args.days, years=args.years, db_path=args.db)
    sys.exit(exit_code)


def score_cli() -> None:
    """Entry point for standalone `score <SYMBOL> <DATE>` command."""
    parser = argparse.ArgumentParser(description="Inspect confidence meter score breakdown.")
    parser.add_argument("symbol", type=str, help="Stock ticker symbol (e.g. RELIANCE, RELIANCE.NS, ^NSEI)")
    parser.add_argument("date", type=str, help="Evaluation date (YYYY-MM-DD)")
    parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")
    args = parser.parse_args()
    exit_code = run_score(symbol=args.symbol, date_str=args.date, db_path=args.db)
    sys.exit(exit_code)


def main_cli() -> None:
    """Entry point for combined `trading-agent` CLI."""
    parser = argparse.ArgumentParser(description="Personal AI Trading Agent CLI.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    bf_parser = subparsers.add_parser("backfill", help="Backfill historical data and calculate scores.")
    bf_parser.add_argument("--days", type=int, default=None, help="Days of history to backfill")
    bf_parser.add_argument("--years", type=int, default=None, help="Years of history to backfill (default: 5)")
    bf_parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")

    sc_parser = subparsers.add_parser("score", help="Print score breakdown for a symbol on a date.")
    sc_parser.add_argument("symbol", type=str, help="Stock ticker symbol")
    sc_parser.add_argument("date", type=str, help="Date (YYYY-MM-DD)")
    sc_parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")

    args = parser.parse_args()
    if args.subcommand == "backfill":
        sys.exit(run_backfill(days=args.days, years=args.years, db_path=args.db))
    elif args.subcommand == "score":
        sys.exit(run_score(symbol=args.symbol, date_str=args.date, db_path=args.db))
