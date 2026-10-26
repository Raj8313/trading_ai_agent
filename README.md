# 🤖 Personal AI Trading Agent

Welcome to the **Personal AI Trading Agent**! This project is an auditable, deterministic, paper-trading-first trading agent designed for Indian equity cash markets (NSE) built for ₹0 running entirely on your local machine.

---

## 📌 Capabilities & Completed Phases

- **Phase 1 — Foundation & Signal Engine**: Clean Architecture (Ports & Adapters), SQLite WAL storage, Console/Telegram notifiers, and an auditable Confidence Meter (Trend, Volume, Market Direction checks).
- **Phase 1.5 — Read-Only Dashboard**: Streamlit browser dashboard visualizing live watchlist confidence badges, 12-month historical score charts, and data quality logs.
- **Phase 2 — Backtesting & Validation**: Chronological historical simulator with conservative execution physics (strict $D+1$ open entry, lookahead guard, intrabar stop-loss priority, gap-through-stop realistic losses, max 3 concurrent positions, mandatory statutory charges and slippage) and baseline comparison against NIFTY 50 buy-and-hold.

---

## 🏗️ Architecture & Building Blocks

```
src/trading_agent/
├── domain/               # Core entities (Bar, Score, Signal, TradeBand, DataQualityIssue)
├── ports/                # Abstract interfaces (MarketDataPort, StoragePort, NotifierPort, ConfidenceCheckPort)
├── adapters/
│   ├── market_data/      # YFinanceMarketDataAdapter with retries and data cleansing
│   ├── storage/          # SqliteStorageAdapter in WAL mode with idempotent upsert
│   └── notifier/         # ConsoleNotifierAdapter & TelegramNotifierAdapter (graceful fallback)
├── strategy/             # ConfidenceMeter orchestrator
│   └── checks/           # Modular checks: TrendCheck, VolumeCheck, MarketDirectionCheck
├── config.py             # Pydantic Settings with watchlist deduplication
└── cli.py                # CLI commands: backfill, score
```

### 📊 The Confidence Meter (v0)

| Check | Points | Rule |
|---|---|---|
| **Trend Check** | +25 | Closing price > 20-period EMA AND 20-period EMA is rising (`ema[-1] > ema[-2]`). |
| **Volume Check** | +20 | Latest bar's volume > 1.5× the average of the preceding 20 periods. |
| **Market Direction Check** | +20 | NIFTY 50 (`^NSEI`) closing price > its own 20-period EMA. |

#### Trade Bands
- 🟢 **FULL** ($\ge 80$ points) $\rightarrow$ Full position size. *(Reachable in future phases when 4th/5th checks are added).*
- 🟡 **HALF** ($60\text{--}79$ points) $\rightarrow$ Half position size. *(Achieved when all 3 Phase 1 checks pass: $25 + 20 + 20 = 65$).*
- 🔴 **NONE** ($< 60$ points) $\rightarrow$ No trade / sitting on hands.

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
# Run all 42 tests
uv run pytest

# Run tests with strategy coverage report (Target: >=90%, Achieved: 100%)
uv run pytest --cov=src/trading_agent/strategy --cov-report=term-missing
```

---

## 💻 CLI Commands

### 1. Backfill Historical Data
Fetches ~1 year of daily bars for the 5 watchlist stocks (`RELIANCE.NS`, `TCS.NS`, `INFY.NS`, `HDFCBANK.NS`, `ICICIBANK.NS`) and NIFTY 50 (`^NSEI`), calculates confidence scores bar-by-bar, and saves them idempotently to SQLite:

```bash
uv run backfill
```
*(Optionally specify custom days: `uv run backfill --days 180`)*

### 2. Inspect a Symbol's Score
Inspect the transparent breakdown of every check on any past date:

```bash
uv run score RELIANCE 2025-10-17
```

**Example Output:**
```
=======================================================
🎯 CONFIDENCE METER SCORE BREAKDOWN
   Symbol: RELIANCE.NS
   Date:   2025-10-17
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

-------------------------------------------------------
TOTAL POINTS: 65 / 65
TRADE BAND:   HALF
ACTION:       🟡 BUY (HALF POSITION)
=======================================================
```

### 3. Launch Read-Only Dashboard
Launch the interactive browser dashboard with a single command to view latest watchlist scores, 12-month score charts, and data quality logs:

```bash
uv run dashboard
```

- **Page 1 (Overview)**: Watchlist table with latest scores, colored band badges (🟢 $\ge 80$, 🟡 $60\text{--}79$, 🔴 $< 60$), and individual check pass/fail indicators.
- **Page 2 (Symbol Detail)**: Interactive 12-month score history line chart with threshold lines + check rationale breakdown.
- **Page 3 (Data Quality)**: Audit log of any feed anomalies, empty bars, or skipped records.

### 4. Run Backtesting & Validation Simulation (Phase 2)
Run historical simulation over persisted confidence scores to test whether signals would have made money after all realistic statutory charges and slippage:

```bash
uv run backtest --start 2025-09-01 --end 2026-10-20 --export trades.csv
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

## 📝 Known Limitations (Phase 1)

1. **Maximum Score of 65**: Because Phase 1 strictly implements only the first 3 checks ($25 + 20 + 20 = 65$), the `FULL` band ($\ge 80$) is mathematically unreachable until Phase 2 adds subsequent checks. The `HALF` band ($60\text{--}79$) represents maximum confidence in Phase 1.
2. **Daily Candlestick Resolution**: Yahoo Finance daily bars represent end-of-day candles. Live intraday streaming is slated for future phases.
3. **Data Gaps**: Yahoo Finance occasionally has missing rows or delayed indices; the engine automatically logs these to `data_quality_issues` in SQLite without crashing.
