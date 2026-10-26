# 🤖 Personal AI Trading Agent — Phase 1: Foundation & Signal Engine

Welcome to the **Personal AI Trading Agent**! This project is an auditable, deterministic, paper-trading-first trading agent designed for Indian equity cash markets (NSE) built for ₹0 running entirely on your local machine.

---

## 📌 Phase 1 Goal

Phase 1 establishes the rock-solid modular foundation:
- **Clean Architecture (Ports & Adapters)**: Business logic is decoupled from external tools, databases, and APIs.
- **Auditable Confidence Meter (v0)**: Scores daily stock price action across **3 transparent checks** (Max 65 points in Phase 1).
- **SQLite Storage in WAL mode**: Fully idempotent persistence of scores and data quality anomalies.
- **Multi-channel Notifier**: Console alerts by default with optional Telegram integration.
- **Zero Real Money**: Signals and logs only; no broker connections or order execution.

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
