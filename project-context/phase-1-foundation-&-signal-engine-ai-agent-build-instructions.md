# PHASE 1 — Foundation & Signal Engine

**Project:** Personal AI Trading Agent (paper-trading first, India/NSE, equity intraday cash)
**You are:** the implementation agent. Follow this document literally. Do not invent scope.
**Human:** Raja — a beginner. Explain what you do in plain language as you go.

---

## 0. Ground Rules (non-negotiable)

1. **No real trading. No broker integration. No real money.** Nothing in this phase places orders or simulates placing them to a broker. This phase produces *signals and logs only*.
2. **No global installs.** Use `uv`. Every command runs inside the project's virtual environment. If a package can't be installed via `uv add`, stop and report instead of using `pip install --user` or `sudo`.
3. **LEGO blocks architecture.** Every capability is a small module behind an interface (a "port"). Adapters plug into ports. No module reaches into another module's internals.
4. **SOLID.** Especially: single responsibility per module; dependencies point at abstractions; new behavior = new class, not an edited `if` chain.
5. **Everything logged.** Every signal — taken or not — is persisted. Silent failures are bugs. A missing log row is a bug.
6. **Deterministic and testable.** All business logic must be unit-testable with fake adapters, without network access.
7. **Ask, don't assume.** If a requirement is ambiguous, stop and ask in your report rather than guessing.

---

## 1. Phase 1 Goal (one sentence)

Build the skeleton of the trading agent — environment, domain model, ports, and a working **Confidence Meter with 3 checks** — that scores historical NSE data, logs every score to SQLite, and can notify via Telegram, with the architecture ready for future phases to plug into *without modifying existing modules*.

## 2. Phase 1 Scope — DO

- Python project scaffold with `uv` (`pyproject.toml`, lockfile, `.venv`)
- Domain model: `Stock`, `Bar` (OHLCV), `Score`, `Signal`, enum `TradeBand` — typed with Pydantic
- Ports (abstract base classes or `typing.Protocol`):
  - `MarketDataPort` — fetch historical bars for a symbol/date range
  - `StoragePort` — persist/read signals & scores
  - `NotifierPort` — send a message
  - `ConfidenceCheckPort` — one check = one class; returns points + rationale
- Adapters (Phase 1 implementations):
  - `YFinanceMarketDataAdapter` (historical daily data, NSE symbols like `RELIANCE.NS`)
  - `SqliteStorageAdapter` (WAL mode, one writer, simple versioned schema)
  - `TelegramNotifierAdapter` (token/chat-id from `.env`; fall back to `ConsoleNotifier` if unconfigured)
  - `ConsoleNotifierAdapter` (default)
- **Confidence Meter v0** with exactly **3 checks**:
  1. Trend check (+25): price above 20-period EMA and EMA rising
  2. Volume check (+20): latest volume above 1.5× its 20-period average
  3. Market direction check (+20): NIFTY 50 above its own 20-period EMA
  - Bands: `>=80` FULL, `60–79` HALF, `<60` NONE. (With 3 checks max score is 65 — expected and fine for Phase 1; the meter still logs the raw score.)
- `backfill` command: fetch ~1 year of daily data for a configurable watchlist (default: 5 large-cap NSE stocks + NIFTY 50) and compute scores bar-by-bar
- `score <SYMBOL> <DATE>` command: print the score breakdown for one symbol/date
- Every score persisted: date, symbol, each check's pass/fail + points + rationale, total, band
- Unit tests (pytest) for every check, the meter, bands, and storage — using **fake adapters and synthetic data only**, no network in tests
- A `README.md` a beginner can follow: setup, commands, how to run tests

## 3. Phase 1 Scope — DON'T

- ❌ Broker APIs (Dhan/Kite/Angel), tokens, webhooks
- ❌ Live/websocket data, schedulers, market-hours loops
- ❌ Stop-loss, position sizing, exits, portfolio logic
- ❌ Pre-market sentiment module
- ❌ ML/AI/LLM anywhere in the decision path — plain, auditable rules only
- ❌ Web UI, dashboards, charts
- ❌ Premature optimization: no async plumbing, no multiprocessing, no plugin frameworks

## 4. Suggested Layout (refine names if needed, keep the structure)

```
trading-agent/
├── pyproject.toml            # uv-managed
├── .env.example              # TELEGRAM_BOT_TOKEN=, TELEGRAM_CHAT_ID=
├── README.md
├── src/trading_agent/
│   ├── domain/               # models: Bar, Score, Signal, enums
│   ├── ports/                # abstract interfaces ONLY
│   ├── adapters/
│   │   ├── market_data/      # yfinance adapter
│   │   ├── storage/          # sqlite adapter
│   │   └── notifier/         # telegram + console
│   ├── strategy/             # confidence meter
│   │   └── checks/           # one file per check
│   ├── cli.py                # backfill / score commands
│   └── config.py             # pydantic-settings, .env loading
└── tests/                    # unit tests, synthetic data only
```

## 5. Edge Cases You Must Handle

1. **Bad/missing data from yfinance** (empty df, NaN rows, missing dates): skip the bar, log a `data_quality` record, never crash the backfill.
2. **Zero-volume or insufficient history** (a check needs 20 periods): check returns 0 points with rationale `INSUFFICIENT_DATA`, not an error.
3. **SQLite write failure**: raise loudly; never swallow and continue.
4. **Missing `.env` / Telegram unconfigured**: fall back to `ConsoleNotifier`, log a warning once.
5. **Network failure during backfill**: retry 3× with backoff per symbol; if still failing, record it and continue with other symbols; non-zero exit if any symbol failed.
6. **Same bar scored twice** (backfill rerun): upsert — one row per (symbol, date). Idempotency is required.
7. **Duplicate watchlist entries**: dedupe at config load with a warning.

## 6. Definition of Done — Strict Exit Criteria

The phase is complete ONLY when all of these are demonstrably true:

| # | Exit criterion | Proof |
|---|---|---|
| 1 | `uv sync` on a clean checkout creates the env; `uv run pytest` passes with **≥90% coverage** on `strategy/` | test run output |
| 2 | All tests pass **without network access** (fakes only) | shown command + output |
| 3 | `backfill` completes on 5 stocks + NIFTY, 1 year of daily bars, with score rows per symbol in SQLite | row counts per symbol |
| 4 | Rerunning `backfill` produces **zero duplicate rows** (idempotent) | before/after row counts equal |
| 5 | `score RELIANCE <date>` prints full breakdown: each check, points, rationale, total, band | terminal output |
| 6 | Corrupted data (empty df / NaNs) handled per §5.1–5.2 without crash | a test case for each |
| 7 | Adding a hypothetical 4th check requires **zero edits** to the meter or existing checks — only a new class + registration | show the diff |
| 8 | Every module has a docstring; every check returns a human-readable rationale | code review |
| 9 | `README.md` lets a beginner set up and run everything in < 15 minutes | fresh-clone walkthrough |

**Report format:** when done, produce a report listing each exit criterion with its proof, plus an honest "known limitations" section (e.g., yfinance data gaps, FULL band unreachable with 3 checks).

## 7. Guardrails for You (the agent)

- Work in small commits with messages a beginner understands.
- After each major module, run the tests and say what they cover.
- If you're about to break a ground rule, stop and explain the conflict instead.
- No file over ~300 lines; split when larger.
- Prefer boring, readable code over clever code. The human must be able to read it.