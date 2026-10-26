"""Backtest Engine for simulating trading performance over historical bars.

Walks historical daily bars chronologically, applies entry/exit policies,
enforces concurrent position limits, and computes conservative net P&L.
"""

from dataclasses import dataclass, field
import datetime as dt
import logging
from typing import Optional

from trading_agent.backtest.policies.exit_policy import (
    ExitPolicyPort,
    FixedTargetStopExitPolicy,
)
from trading_agent.domain.models import (
    Bar,
    DataQualityIssue,
    ExitReason,
    Score,
    TradeBand,
    TradeRecord,
)
from trading_agent.ports.market_data import MarketDataPort
from trading_agent.ports.storage import StoragePort

logger = logging.getLogger(__name__)


@dataclass
class OpenPosition:
    """Represents an active, unresolved open position."""

    symbol: str
    signal_date: dt.date
    entry_date: dt.date
    entry_price: float  # Includes entry slippage
    band: TradeBand
    position_size: float
    shares: float
    days_held: int = 0


@dataclass
class BacktestLogEvent:
    """Record of an edge-case or operational event during backtest."""

    date: dt.date
    symbol: str
    event_type: str  # e.g., SIGNAL_UNRESOLVED, SKIPPED_NO_CAPACITY, MISSING_PRICE_DATA
    details: str


class BacktestEngine:
    """Conservative backtest simulation engine."""

    def __init__(
        self,
        storage: StoragePort,
        market_data: MarketDataPort,
        exit_policy: Optional[ExitPolicyPort] = None,
        capital_per_full: float = 100000.0,
        capital_per_half: float = 50000.0,
        max_concurrent_positions: int = 3,
        round_trip_cost_rate: float = 0.001,  # 0.1% round-trip statutory costs
        slippage_rate: float = 0.0005,  # 0.05% per side
    ) -> None:
        """Initialize engine with ports, exit policy, and conservative cost parameters."""
        self.storage = storage
        self.market_data = market_data
        self.exit_policy = exit_policy or FixedTargetStopExitPolicy()
        self.capital_per_full = capital_per_full
        self.capital_per_half = capital_per_half
        self.max_concurrent_positions = max_concurrent_positions
        self.cost_rate = round_trip_cost_rate
        self.slippage_rate = slippage_rate

        self.events: list[BacktestLogEvent] = []

    def run(
        self,
        symbols: list[str],
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[TradeRecord]:
        """Execute backtest over historical window for given symbols.

        Args:
            symbols: List of stock symbols to simulate.
            start_date: Start date for signal evaluation.
            end_date: End date for signal evaluation.

        Returns:
            List of completed, resolved TradeRecord objects.
        """
        self.events = []
        # 1. Fetch bars and stored scores for all symbols
        bars_by_symbol: dict[str, dict[dt.date, Bar]] = {}
        calendar_dates: set[dt.date] = set()

        for sym in symbols:
            # Fetch bars with generous buffer around range for entries/exits
            bars = self.market_data.fetch_daily_bars(
                sym, start_date - dt.timedelta(days=40), end_date + dt.timedelta(days=40)
            )
            bars_by_symbol[sym] = {b.date: b for b in bars}
            calendar_dates.update(b.date for b in bars if start_date <= b.date <= end_date)

        sorted_trading_days = sorted(calendar_dates)
        if not sorted_trading_days:
            logger.warning("No trading days found in backtest range %s to %s", start_date, end_date)
            return []

        open_positions: dict[str, OpenPosition] = {}
        completed_trades: list[TradeRecord] = []

        # 2. Iterate day by day chronologically
        for current_day in sorted_trading_days:
            # A. Evaluate exits for existing open positions on current_day
            closed_symbols = []
            for sym, pos in open_positions.items():
                day_bar = bars_by_symbol.get(sym, {}).get(current_day)
                if not day_bar:
                    # Stock halted / missing bar
                    self.events.append(
                        BacktestLogEvent(
                            date=current_day,
                            symbol=sym,
                            event_type="MISSING_PRICE_DATA",
                            details="No bar found for active position; hold day extended",
                        )
                    )
                    continue

                pos.days_held += 1
                decision = self.exit_policy.evaluate_bar(
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    current_bar=day_bar,
                    days_held=pos.days_held,
                )

                if decision.should_exit:
                    # Apply exit slippage (adverse: sell lower)
                    exit_price_with_slippage = decision.exit_price * (1.0 - self.slippage_rate)
                    gross_pnl = (pos.shares * exit_price_with_slippage) - pos.position_size
                    # Deduct round-trip statutory costs
                    net_pnl = gross_pnl - (pos.position_size * self.cost_rate)

                    trade = TradeRecord(
                        symbol=sym,
                        signal_date=pos.signal_date,
                        entry_date=pos.entry_date,
                        entry_price=round(pos.entry_price, 2),
                        exit_date=decision.exit_date,
                        exit_price=round(exit_price_with_slippage, 2),
                        exit_reason=decision.exit_reason or ExitReason.STOP,
                        band=pos.band,
                        position_size=pos.position_size,
                        gross_pnl=round(gross_pnl, 2),
                        net_pnl=round(net_pnl, 2),
                        rule_followed=True,
                    )
                    completed_trades.append(trade)
                    closed_symbols.append(sym)

            for sym in closed_symbols:
                del open_positions[sym]

            # B. Check signals generated on current_day for potential entry on next trading day
            day_signals: list[Score] = []
            for sym in symbols:
                if sym in open_positions:
                    # One position per symbol at a time (no pyramiding)
                    continue

                score = self.storage.get_score(sym, current_day)
                if score and score.band in (TradeBand.FULL, TradeBand.HALF):
                    day_signals.append(score)

            if not day_signals:
                continue

            # Deterministic resolution: sort signals by (total_points DESC, symbol ASC)
            day_signals.sort(key=lambda s: (-s.total_points, s.symbol))

            # Find next trading day for execution
            next_days = [d for d in sorted_trading_days if d > current_day]
            if not next_days:
                # Signal on last day of data -> cannot resolve entry on D+1
                for s in day_signals:
                    self.events.append(
                        BacktestLogEvent(
                            date=current_day,
                            symbol=s.symbol,
                            event_type="SIGNAL_UNRESOLVED",
                            details="Signal occurred on final day of backtest; no D+1 bar exists",
                        )
                    )
                continue

            next_day = next_days[0]

            for score in day_signals:
                # Capacity limit check
                if len(open_positions) >= self.max_concurrent_positions:
                    self.events.append(
                        BacktestLogEvent(
                            date=current_day,
                            symbol=score.symbol,
                            event_type="SKIPPED_NO_CAPACITY",
                            details=f"Concurrent positions reached maximum limit ({self.max_concurrent_positions})",
                        )
                    )
                    continue

                # Entry bar is on next_day
                next_bar = bars_by_symbol.get(score.symbol, {}).get(next_day)
                if not next_bar:
                    self.events.append(
                        BacktestLogEvent(
                            date=current_day,
                            symbol=score.symbol,
                            event_type="MISSING_PRICE_DATA",
                            details=f"Missing bar data on entry date {next_day}",
                        )
                    )
                    continue

                # Apply entry slippage (adverse: buy higher)
                entry_price_with_slippage = next_bar.open * (1.0 + self.slippage_rate)
                pos_capital = (
                    self.capital_per_full if score.band == TradeBand.FULL else self.capital_per_half
                )
                shares = pos_capital / entry_price_with_slippage

                open_positions[score.symbol] = OpenPosition(
                    symbol=score.symbol,
                    signal_date=current_day,
                    entry_date=next_day,
                    entry_price=entry_price_with_slippage,
                    band=score.band,
                    position_size=pos_capital,
                    shares=shares,
                    days_held=0,
                )

        return completed_trades
