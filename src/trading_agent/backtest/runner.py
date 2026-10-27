"""Backtest execution runner for coordinating simulation, metrics, and persistence.

Encapsulates chronological backtest simulation logic so both the CLI
and interactive web dashboard can execute runs deterministically.
"""

from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
import logging
from typing import Optional

from trading_agent.adapters.market_data.yfinance_adapter import YFinanceMarketDataAdapter
from trading_agent.adapters.storage.sqlite_adapter import SqliteStorageAdapter
from trading_agent.backtest.engine import BacktestEngine
from trading_agent.backtest.metrics import BacktestMetrics, calculate_metrics
from trading_agent.backtest.policies.exit_policy import FixedTargetStopExitPolicy
from trading_agent.config import get_settings
from trading_agent.domain.models import TradeRecord
from trading_agent.ports.market_data import MarketDataPort
from trading_agent.ports.storage import StoragePort

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Encapsulates output and execution state of a backtest run."""

    success: bool
    error_message: Optional[str] = None
    run_id: Optional[str] = None
    metrics: Optional[BacktestMetrics] = None
    trades: list[TradeRecord] = field(default_factory=list)
    start_date: Optional[dt.date] = None
    end_date: Optional[dt.date] = None
    initial_capital: float = 300000.0


def execute_backtest(
    start_date: dt.date,
    end_date: dt.date,
    storage: Optional[StoragePort] = None,
    market_data: Optional[MarketDataPort] = None,
    db_path: Optional[str] = None,
    watchlist: Optional[list[str]] = None,
    benchmark_symbol: Optional[str] = None,
    meter_version: Optional[str] = None,
    initial_capital: float = 300000.0,
) -> BacktestResult:
    """Execute complete historical backtest workflow deterministically."""
    settings = get_settings()
    target_db = db_path or settings.database_path
    symbols = watchlist or settings.watchlist
    bench_symbol = benchmark_symbol or settings.benchmark_symbol
    active_meter_version = meter_version or settings.meter_version or "v2"

    if start_date >= end_date:
        return BacktestResult(
            success=False,
            error_message=f"Start date ({start_date}) must be earlier than end date ({end_date}).",
        )

    store = storage or SqliteStorageAdapter(db_path=target_db)
    mkt = market_data or YFinanceMarketDataAdapter(storage_adapter=store)

    # Auto-clamp end_date if requested end_date is today or later and today's session has not closed
    try:
        latest_scores = store.get_latest_scores(meter_version=active_meter_version)
        latest_scored_date = max((s.date for s in latest_scores), default=None)
        if latest_scored_date and end_date > latest_scored_date and end_date >= dt.date.today():
            logger.info("Clamping end_date from %s to latest completed trading day %s", end_date, latest_scored_date)
            end_date = latest_scored_date
    except Exception as exc:
        logger.warning("Could not determine latest scored date for clamping: %s", exc)

    # 1. Fetch benchmark bars for calendar & baseline
    fetch_start = start_date - dt.timedelta(days=35)
    fetch_end = end_date + dt.timedelta(days=25)
    try:
        bench_bars = mkt.fetch_daily_bars(bench_symbol, fetch_start, fetch_end)
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

    # 2. Check score version integrity and coverage
    offending_symbols = []
    for sym in symbols:
        all_scores = store.get_scores_for_symbol_in_range(sym, start_date, end_date, meter_version=None)
        v2_scores = [s for s in all_scores if s.meter_version == active_meter_version]
        v1_scores = [s for s in all_scores if s.meter_version == "v1"]

        if len(v2_scores) == 0 and len(v1_scores) > 0:
            return BacktestResult(
                success=False,
                error_message=f"Symbol {sym} has only v1 scores. Please run backfill with {active_meter_version} meter first.",
            )

        v1_dates, v2_dates = {s.date for s in v1_scores}, {s.date for s in v2_scores}
        if (v1_dates - v2_dates) and len(v2_scores) > 0:
            return BacktestResult(
                success=False,
                error_message=f"Mixed meter version data for {sym}. Missing {active_meter_version} scores on {len(v1_dates - v2_dates)} dates.",
            )

        coverage_pct = (len(v2_scores) / expected_trading_days) * 100.0 if expected_trading_days > 0 else 0.0
        if coverage_pct < 95.0:
            offending_symbols.append((sym, len(v2_scores), expected_trading_days, coverage_pct))

    if offending_symbols:
        summary_lines = [f"• {s}: {act}/{exp} days ({pct:.1f}%)" for s, act, exp, pct in offending_symbols]
        return BacktestResult(
            success=False,
            error_message=(
                f"Insufficient score coverage for date range {start_date} to {end_date} (meter {active_meter_version}).\n"
                + "\n".join(summary_lines)
            ),
        )

    # 3. Configure Exit Policy & Engine
    exit_policy = FixedTargetStopExitPolicy(
        stop_loss_pct=settings.stop_loss_pct,
        profit_target_pct=settings.profit_target_pct,
        max_hold_days=settings.max_hold_days,
    )
    engine = BacktestEngine(
        storage=store,
        market_data=mkt,
        exit_policy=exit_policy,
        capital_per_full=100000.0,
        capital_per_half=50000.0,
        max_concurrent_positions=3,
        round_trip_cost_rate=0.001,
        slippage_rate=0.0005,
        meter_version=active_meter_version,
    )
    trades = engine.run(symbols=symbols, start_date=start_date, end_date=end_date)

    # 4. Baseline & Metrics
    bench_initial_price = bench_in_range[0].close if bench_in_range else None
    bench_final_price = bench_in_range[-1].close if bench_in_range else None

    metrics = calculate_metrics(
        trades=trades,
        baseline_symbol=bench_symbol,
        baseline_initial_price=bench_initial_price,
        baseline_final_price=bench_final_price,
        portfolio_initial_capital=initial_capital,
    )

    # 5. Persistence & Versioning
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
    existing_runs_count = store.get_backtest_run_count(config_hash)
    version = existing_runs_count + 1
    run_id = f"run_{config_hash}_v{version}"

    store.save_backtest_run(
        run_id=run_id,
        started_at=dt.datetime.now(dt.timezone.utc),
        params=config_dict,
        config_hash=config_hash,
        metrics=metrics.model_dump(),
        trades=trades,
        version=version,
    )

    return BacktestResult(
        success=True,
        run_id=run_id,
        metrics=metrics,
        trades=trades,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
