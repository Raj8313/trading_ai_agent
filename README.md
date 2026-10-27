# 🤖 Personal AI Trading Agent

Welcome to the **Personal AI Trading Agent**! This project is an auditable, deterministic, paper-trading-first trading agent designed for Indian equity cash markets (NSE) built for ₹0 running entirely on your local machine.

---

## 📌 Capabilities & Completed Phases

- **Phase 1 — Foundation & Signal Engine**: Clean Architecture (Ports & Adapters), SQLite WAL storage, Console/Telegram notifiers, and an auditable Confidence Meter (Trend, Volume, Market Direction checks).
- **Phase 1.5 — Read-Only Dashboard**: Streamlit browser dashboard visualizing live watchlist confidence badges, 12-month historical score charts, dynamic check breakdowns, and data quality logs.
- **Phase 2 — Backtesting & Validation**: Chronological historical simulator with conservative execution physics (strict $D+1$ open entry, lookahead guard, intrabar stop-loss priority, gap-through-stop realistic losses, max 3 concurrent positions, mandatory statutory charges and slippage) and baseline comparison against NIFTY 50 buy-and-hold.
- **Phase 3 — Data Expansion & Full 5-Check Meter**: Watchlist expanded to 20 liquid large-cap NSE stocks; added `NotAtHighCheck` (+20) and `StopDistanceCheck` (+15) via Open-Closed registration reaching max 100 points and unlocking the **FULL** band ($\ge 80$); 5-year incremental backfill; score versioning (`v1` and `v2` coexistence); version mismatch guards; full 5-year backtest over 756 trades against NIFTY baseline.

---

## 🏗️ Architecture & Building Blocks

```
src/trading_agent/
├── domain/               # Core entities (Bar, Score, Signal, TradeBand, DataQualityIssue, TradeRecord)
├── ports/                # Abstract interfaces (MarketDataPort, StoragePort, NotifierPort, ConfidenceCheckPort)
├── adapters/
│   ├── market_data/      # YFinanceMarketDataAdapter with retries and data cleansing
│   ├── storage/          # SqliteStorageAdapter in WAL mode with compound keys & migrations
│   └── notifier/         # ConsoleNotifierAdapter & TelegramNotifierAdapter (graceful fallback)
├── strategy/             # ConfidenceMeter orchestrator
│   └── checks/           # 5 modular checks: Trend, Volume, Market Direction, Not-At-High, Stop-Distance
├── backtest/             # Chronological backtest engine, exit policies, metrics, reporting
├── dashboard/            # Read-only Streamlit dashboard with dynamic check columns
├── config.py             # Pydantic Settings with 20 stocks default watchlist
└── cli.py                # CLI commands: backfill, score, dashboard, backtest
```

### 📊 The Full 5-Check Confidence Meter (v2)

| Check | Points | Rule |
|---|---|---|
| **Trend Check** | +25 | Closing price > 20-period EMA AND 20-period EMA is rising (`ema[-1] > ema[-2]`). |
| **Volume Check** | +20 | Latest bar's volume > 1.5× the average of the preceding 20 periods. |
| **Market Direction Check** | +20 | NIFTY 50 (`^NSEI`) closing price > its own 20-period EMA. |
| **Not-At-High Check** | +20 | Closing price is at least 5% below its 52-week (250-bar) rolling high (avoids chasing parabolic tops). |
| **Stop-Distance Check** | +15 | Volatility check: $2 \times \text{ATR}(14) / \text{Price} \ge \text{Stop Loss \%}$ (stop isn't tighter than normal daily noise). |

#### Trade Bands (Max Score: 100)
- 🟢 **FULL** ($\ge 80$ points) $\rightarrow$ Full position size (e.g. ₹100,000). *(Requires passing $\ge 4$ checks).*
- 🟡 **HALF** ($60\text{--}79$ points) $\rightarrow$ Half position size (e.g. ₹50,000).
- 🔴 **NONE** ($< 60$ points) $\rightarrow$ No trade / sitting on hands.

#### Score Versioning & Data Safety
- Legacy Phase 1/2 scores (3 checks, max 65 pts) are permanently preserved with `meter_version = 'v1'`.
- Phase 3 scores (5 checks, max 100 pts) are stamped with `meter_version = 'v2'`.
- Both versions coexist in SQLite under compound key `(symbol, date, meter_version)`. Backtest runs exclusively on `v2` and refuses mixed or unmigrated data.

---

## ⚡ Quickstart Setup (< 5 Minutes)

### 1. Requirements
- Python 3.11 or higher
- `uv` package manager ([installation instructions](https://docs.astral.sh/uv/))

### 2. Environment Setup
Clone the repository and install all dependencies (including test tools):
```bash
uv sync --extra dev
```

### 3. (Optional) Configure Telegram Notifications
Copy the sample environment file:
```bash
cp .env.example .env
```
Open `.env` and fill in your Telegram bot token and chat ID if desired. If left empty, the agent logs alerts to the console with zero warnings.

---

## 🧪 Running Tests

All unit tests use **synthetic in-memory data and fake adapters**. Zero network access is required during testing:

```bash
# Run all 85 tests
uv run pytest

# Run tests with full coverage report (Target: >=90% on strategy & backtest)
uv run pytest --cov=src/trading_agent --cov-report=term-missing
```

---

## 💻 CLI Commands

### 1. Incremental Historical Backfill (5 Years)
Fetches historical daily bars for all 20 large-cap watchlist stocks and NIFTY 50 (`^NSEI`), calculates full 5-check confidence scores bar-by-bar, and saves them idempotently to SQLite stamped as `v2`. Backfills are **strictly incremental**—dates already scored are automatically skipped:

```bash
uv run backfill --years 5
```
*(Optionally specify custom days: `uv run backfill --days 180`)*

### 2. Inspect a Symbol's Score
Inspect the transparent breakdown of all 5 checks on any past date:

```bash
uv run score RELIANCE 2025-10-17
```

**Example Output:**
```
=======================================================
🎯 CONFIDENCE METER SCORE BREAKDOWN
   Symbol: RELIANCE.NS
   Date:   2025-10-17
   Meter:  v2
=======================================================

• Trend Check [✅ PASS]
  Points:    +25 / 25
  Rationale: PASS: Close (1416.80) > 20 EMA (1383.91) and 20 EMA is rising (1383.91 > 1380.45).

• Volume Check [✅ PASS]
  Points:    +20 / 20
  Rationale: PASS: Latest volume (19,335,561) is 1.81x 20-period avg (10,671,879.7), crossing 1.5x threshold (16,007,819.5).

• Market Direction Check [✅ PASS]
  Points:    +20 / 20
  Rationale: PASS: NIFTY 50 close (25709.85) > 20 EMA (25170.82). Market is green/bullish.

• Not-At-High Check [✅ PASS]
  Points:    +20 / 20
  Rationale: PASS: Close (1416.80) is 9.42% below 52-week high (1564.20). Safe distance >= 5.0%.

• Stop-Distance Check [✅ PASS]
  Points:    +15 / 15
  Rationale: PASS: Volatility buffer (2x ATR(14)/price = 2.85%) >= planned stop (2.00%). Stop is outside normal noise.

-------------------------------------------------------
TOTAL POINTS: 100 / 100
TRADE BAND:   FULL
ACTION:       🟢 BUY (FULL POSITION)
=======================================================
```

### 3. Launch Web Dashboard (GUI)
Launch the interactive browser dashboard with a single command to view latest watchlist scores, 12-month score charts, trigger historical backtests with one click, and inspect data quality logs:

```bash
uv run dashboard
```

- **Page 1 (Overview)**: Watchlist table with latest scores, meter versions (`v1` or `v2`), colored band badges (🟢 $\ge 80$, 🟡 $60\text{--}79$, 🔴 $< 60$), and dynamic check pass/fail indicators.
- **Page 2 (Symbol Detail)**: Interactive 12-month score history line chart with threshold lines + check rationale breakdown and meter version display.
- **Page 3 (Backtest)**: Interactive simulation GUI! Pick quick presets ("Last 7 Days", "Last 30 Days", "Last 1 Year", "Last 5 Years") or custom calendar dates, click **"🚀 Run Backtest Simulation"**, view performance metrics, explore the executed trades log, and download them as CSV with one click.
- **Page 4 (Data Quality)**: Audit log of any feed anomalies, empty bars, or skipped records.

### 4. Run Backtesting & Validation Simulation (5-Year Historical Test)
Run historical simulation over persisted `v2` confidence scores across 5 years to test whether signals would have made money after all realistic statutory charges and slippage:

```bash
uv run backtest --start 2021-10-26 --end 2026-10-26 --export trades.csv
```

#### Understanding the Backtest Report (Beginner's Guide)

Trading beginners often fixate on **Win Rate**, but in systematic trading, win rate alone can be deceiving:
1. **Expectancy (Expected Value per Trade)**:
   - *Formula*: $(\text{Win Rate} \times \text{Avg Win}) - (\text{Loss Rate} \times \text{Avg Loss})$
   - Tells you how many rupees you make or lose on average every time you enter a trade.
   - A 90% win rate strategy that wins ₹100 but loses ₹2,000 on the 10th trade has negative expectancy and will eventually lose capital. Conversely, a 35% win rate strategy with ₹3,000 avg win and ₹1,000 avg loss is consistently profitable.
2. **Maximum Drawdown (Peak-to-Trough Drop)**:
   - Measures the deepest painful dip your account experiences before recovering.
   - Even a profitable strategy cannot be traded if its drawdown exceeds what you can psychologically or financially endure.
3. **Mandatory Realistic Costs**:
   - The engine automatically deducts **0.1% round-trip statutory costs** (STT, stamp duty, exchange turnover charges) + **0.05% slippage per side** (~0.2% round-trip total drag).
4. **Baseline Comparison (NIFTY 50)**:
   - Compares the strategy's return against passively holding NIFTY 50 over the exact same period to evaluate whether active trading provided real value (alpha).
5. **Sample Size & Statistical Honesty**:
   - The report automatically alerts you if total completed trades are $< 30$: small sample sizes cannot provide statistically definitive proof.
6. **No Silent Duplication**:
   - Every backtest execution computes a configuration hash and saves versioned records (`v1`, `v2`, ...) in SQLite without corrupting or duplicating trade logs.

---

## 🧩 Adding a New Check (Open-Closed Principle)

To add a 4th check, you **never need to modify** `ConfidenceMeter` or existing checks. Simply create a class implementing `ConfidenceCheckPort` and register it:

```python
from trading_agent.ports.confidence_check import ConfidenceCheckPort
from trading_agent.domain.models import CheckResult, Bar

class RsiCheck(ConfidenceCheckPort):
    @property
    def name(self) -> str:
        return "RSI Check"

    @property
    def max_points(self) -> int:
        return 20

    def evaluate(self, symbol, target_date, bars, market_bars=None) -> CheckResult:
        # compute 14-period RSI...
        return CheckResult(
            check_name=self.name,
            passed=True,
            points_awarded=20,
            max_points=20,
            rationale="PASS: RSI is 55 (healthy bullish momentum).",
        )

# Register into the meter:
meter = ConfidenceMeter()
meter.register_check(RsiCheck())
```

---

## 📝 Known Limitations & Honest Phase 3 Insights

1. **The 5-Year Statistical Truth**: Across 5 years of daily bars and 756 executed trades with the complete 5-check meter, the strategy returned **-21.19%** net of statutory costs and slippage (vs NIFTY +23.65% buy-and-hold). We strictly refuse to curve-fit parameters or adjust stop-loss/target levels to fake profitability.
2. **Daily Candlestick Resolution**: Yahoo Finance daily bars represent end-of-day candles. Exit stops and targets are evaluated on daily closing prices rather than intraday tick data.
3. **Data Gaps**: Yahoo Finance occasionally has missing rows or delayed index bars; the engine automatically logs these to `data_quality_issues` in SQLite without interrupting execution.
4. **Dividends Excluded**: Cash dividend distributions are omitted, providing a conservative drag on portfolio cash balance.
