# PHASE 3 — Data Expansion & Full 5-Check Meter

**Project:** Personal AI Trading Agent (repo: `trading_ai_agent`, branch `main`)
**You are:** the implementation agent. Follow this document literally. Do not invent scope.
**Human:** Raja — a beginner. Explain what you do in plain language as you go.
**Prerequisite:** Phase 2 verified green on Raja's machine (69 tests passing; `backtest` runs end-to-end).

**Context from Phase 2 (know this):** the meter v0 produced 28 HALF-band trades over 14 months and lost money net. That result is *inconclusive* because: (a) the sample was tiny, (b) only 3 of 5 checks existed so the FULL band was unreachable, and (c) the watchlist was 5 stocks. This phase fixes all three — and tunes NOTHING else. Same exits, same sizing, same costs, same entry logic.

---

## 0. Ground Rules (non-negotiable)

1. **NO TUNING.** Do not adjust stop-loss, targets, hold limits, thresholds, or band boundaries. Not "to make results better." Not "because it seems reasonable." Any change to those numbers is a ground-rule violation requiring a stop-and-explain.
2. No broker, no live data, no real trading, no ML.
3. No global installs (`uv` only).
4. LEGO blocks / SOLID — new checks are new classes + registration, zero edits to the meter.
5. Additive changes only; existing Phase 1/2 behavior must not change (scores written by the old 3-check meter must remain readable and intact).
6. Deterministic, unit-tested, offline-testable.
7. Ask, don't assume.

## 1. Phase 3 Goal (one sentence)

Re-score 5 years of history across a ~20-stock watchlist with the **full 5-check Confidence Meter** (unlocking the FULL band), then rerun the identical Phase 2 backtest configuration to get a **statistically meaningful verdict** on the complete meter.

## 2. Scope — DO

### 2.1 Watchlist expansion (config change, not code logic)
- Default watchlist grows to **20 liquid large-cap NSE stocks** (pick established, continuously-listed names — e.g., RELIANCE, TCS, HDFCBANK, ICICIBANK, INFY, SBIN, BHARTIARTL, ITC, LT, KOTAKBANK, AXISBANK, ASIANPAINT, MARUTI, TITAN, TATAMOTORS, SUNPHARMA, ULTRACEMCO, HCLTECH, WIPRO, NESTLEIND — all `.NS`; still configurable via `.env`)
- Backfill range extends to **5 years** (default `BACKFILL_YEARS=5` config; CLI override `uv run backfill --years 5`)
- Backfill must be **incremental**: symbols already scored for dates keep their rows; only missing dates are fetched (check first, fetch what's missing — don't redownload everything every run)

### 2.2 The two new checks (as new classes, registered like the others)
4. **Not-at-high check (+20):** fail if the close is within 5% of the rolling 52-week (≈250 trading days) high; pass otherwise. Rationale text must include the close, the 52w high, and the distance. Needs ≥250 bars of history, else `INSUFFICIENT_DATA`.
5. **Stop-distance check (+15):** the planned stop distance (2% — matches the backtest exit policy, reads it from config, NOT hardcoded) must be sensible vs volatility: pass if 2× ATR(14)/price ≥ 2% (i.e., the stop isn't tighter than the stock's normal noise); fail otherwise. Rationale must state ATR%, stop%, verdict. Needs ≥15 bars beyond the existing 20, else `INSUFFICIENT_DATA`.
- Max score becomes **100**; bands now fully reachable (80+ FULL).
- Both checks get the same test standard as Phase 1 checks: pass/fail/insufficient-data paths, hand-computed known-answer tests, boundary tests (exactly 5% distance, exactly equal ATR threshold).

### 2.3 Score versioning (the tricky bit — read carefully)
- New scores have 5 check results; old rows have 3. Old data must NOT be overwritten or lost.
- Add a `meter_version` concept: new scores are written/stamped `v2` (3-check rows remain `v1`). Additive schema change only.
- `backtest` reads **v2 scores** for this phase; the Phase 2 run (v1) must still be readable in the `backtest_runs` history.
- Every backtest report states which meter version produced the trades.

### 2.4 Dashboard updates (keep the GUI truthful)
- Render **any number of checks dynamically** (from the score's own check results — no hardcoded check lists or "/65"-style constants anywhere)
- Overview and symbol-detail show meter version where relevant
- Still strictly read-only

### 2.5 Re-run and report
- Fresh 5-year backfill for all 20 symbols + NIFTY (Phase 2's incremental backfill must not lose old data)
- `uv run backtest --start <5y-ago> --end <today>` over the full range with the v2 meter
- Plain-language report: same format as Phase 2 (per-band, vs NIFTY baseline, streaks, drawdown), plus **trade count honesty**: if trades < 100, the verdict must say "sample still too small for confidence."
- The report must include a v1-vs-v2 sanity note (not a comparison of P&L — just that v1 data remains intact and readable)

## 3. Scope — DON'T

- ❌ Changing any number: stops, targets, hold days, sizing, costs, bands, thresholds
- ❌ Optimizing anything against the results
- ❌ Broker/live/ML
- ❌ New metrics beyond what's needed to display the above
- ❌ Removing or mutating v1 scores
- ❌ Expanding beyond equity cash daily bars

## 4. Edge Cases You Must Handle

1. **Stocks with < 5 years of history** (late listings): backfill from earliest available; not-at-high check returns `INSUFFICIENT_DATA` until 250 bars exist — score rows still written
2. **yfinance rate limits over 21 symbols × 5 years**: batch fetches with small delays; on repeated failure, skip symbol, log `data_quality`, continue; summary at end lists any incomplete symbols
3. **Incremental backfill boundary**: if a symbol has scores up to date X but data-quality gaps exist before X, fill the gaps, don't skip them
4. **Meter version mismatch in backtest**: if any symbol/date in range has only v1 scores, refuse that symbol for v2 backtest with a clear message (don't silently mix)
5. **New check edge values**: exactly-5%-from-high (boundary test defines it as pass — within means strictly less than 5%), ATR exactly at threshold (pass)
6. **Config drift**: stop % for the check and stop % for the exit policy must come from ONE config value; add a test that fails if they diverge
7. **Long backfill interrupted (Ctrl-C / network death)**: partial progress must be persisted (scores are upserted as they're computed); rerun continues from where it left off

## 5. Definition of Done — Strict Exit Criteria

| # | Exit criterion | Proof |
|---|---|---|
| 1 | `uv run pytest` passes; ≥90% coverage on new checks and backtest additions | coverage output |
| 2 | New checks pass known-answer + boundary tests (hand-computed values in comments) | test code + output |
| 3 | Meter extension required **zero edits** to `ConfidenceMeter` or existing checks (registration only) | `git diff` of Phase 1 files |
| 4 | 5-year incremental backfill completes for 20 symbols + NIFTY; rerun fetches little/nothing new (log shows skips) | two consecutive run logs |
| 5 | v1 scores from the Phase 2 era remain in the DB and are still readable (query proof) | query output |
| 6 | v2 scores are stamped and distinguishable; backtest refuses to run on mixed-version data | test + demo output |
| 7 | Dashboard renders 5 checks dynamically (works with 3-check legacy rows too) | screenshots |
| 8 | Full-range v2 backtest runs end-to-end and reports per-band stats vs NIFTY baseline with meter version stated | report text |
| 9 | Stop-check reads stop % from the same config as the exit policy (divergence test) | test output |
| 10 | README updated: new watchlist, incremental backfill, meter versions, beginner language | README diff |

**Report format:** exit-criteria table with proofs, the actual v2 backtest report (whatever the numbers are), known limitations, and — if the meter still loses — say so plainly. **Do not tune. The mentor wants the truth, not a pass.**

## 6. Guardrails for You (the agent)

- Small commits, beginner-readable messages; run tests after each module.
- Backfill of ~21 symbols × 5 years takes time: print per-symbol progress so Raja can see it working.
- Ground-rule conflict → stop and explain, don't improvise.
- Boring, readable code; no file over ~300 lines.

---

## 7. Phase 3 Completion & Verification Report

### 7.1 Strict Exit Criteria Verification Table

| # | Exit Criterion | Status | Concrete Proof |
|---|---|:---:|---|
| 1 | `uv run pytest` passes; $\ge 90\%$ coverage on new checks and backtest additions | **VERIFIED** | 85 passed in 4.51s. Strategy checks: `not_at_high_check.py` 100%, `stop_distance_check.py` 100%. Backtest: `backtest/cli.py` 95%, `backtest/engine.py` 96%, `backtest/report.py` 99%, `backtest/metrics.py` 98%. Storage: `sqlite_adapter.py` 97%. |
| 2 | New checks pass known-answer + boundary tests (hand-computed values in comments) | **VERIFIED** | Hand-computed known-answer & exact boundary tests in `tests/strategy/test_not_at_high_check.py` and `tests/strategy/test_stop_distance_check.py`. Boundary values verified: exactly 5% from 52w high passes; exactly equal ATR threshold passes. |
| 3 | Meter extension required **zero edits** to `ConfidenceMeter` or existing checks (OCP registration only) | **VERIFIED** | `git diff origin/main -- src/trading_agent/strategy/meter.py src/trading_agent/strategy/checks/trend_check.py src/trading_agent/strategy/checks/volume_check.py src/trading_agent/strategy/checks/market_direction_check.py` returns empty output (0 lines changed). |
| 4 | 5-year incremental backfill completes for 20 symbols + NIFTY; rerun fetches little/nothing new (log shows skips) | **VERIFIED** | Run 1 scored 32,065 bars across 20 symbols + ^NSEI. Run 2 finished in 7 seconds scoring 0 new bars (log shows `Scored 0 new bars (skipped 1527 existing)` for each stock). |
| 5 | v1 scores from Phase 2 era remain in DB and are still readable (query proof) | **VERIFIED** | SQLite query `SELECT meter_version, count(*) FROM scores GROUP BY meter_version;` returns `v1|1721` and `v2|32065`. All 1,721 legacy scores preserved intact. |
| 6 | v2 scores are stamped and distinguishable; backtest refuses to run on mixed-version data | **VERIFIED** | `run_backtest_simulation` verified with unit tests `test_backtest_cli_refuses_when_symbol_has_only_v1_scores` and `test_backtest_cli_refuses_mixed_meter_versions`. Demo run against v1-only date range printed: `❌ Error: Symbol RELIANCE.NS has only v1 scores. Please run backfill with v2 meter first.` |
| 7 | Dashboard renders 5 checks dynamically (works with 3-check legacy rows too) | **VERIFIED** | Dynamic column extraction in `src/trading_agent/dashboard/app.py`. Unit test `test_dashboard_dynamic_checks_rendering` proves mixed 3-check and 5-check rows render correctly with `Version` column. |
| 8 | Full-range v2 backtest runs end-to-end and reports per-band stats vs NIFTY baseline with meter version stated | **VERIFIED** | 5-year simulation completed: 756 trades, full per-band breakdown, NIFTY comparison, meter version `v2` explicitly printed. |
| 9 | Stop-check reads stop % from the same config as the exit policy (divergence test) | **VERIFIED** | Unit test `tests/test_config_divergence.py` proves `StopDistanceCheck` and `FixedTargetStopExitPolicy` both read `stop_loss_pct` dynamically from `Settings`. |
| 10 | README updated: new watchlist, incremental backfill, meter versions, beginner language | **VERIFIED** | `README.md` updated with 20 stocks watchlist, 5 checks reaching 100 points, incremental backfill CLI commands, and honest 5-year statistical analysis. |

---

### 7.2 Full 5-Year Backtest Simulation Output (Meter v2)

```text
=================================================================
 📈 CONFIDENCE METER BACKTEST VALIDATION REPORT
=================================================================
 Run ID:         run_d0d03a85233f_v1
 Meter Version:  v2
 Period:         2021-10-26 to 2026-10-26
 Virtual Capital: ₹300,000.00 (Max 3 concurrent positions)
 Benchmark:      ^NSEI Buy & Hold
-----------------------------------------------------------------

1. OVERALL STRATEGY PERFORMANCE
-----------------------------------------------------------------
  • Total Completed Trades:        756
  • Winning Trades:                282  (Win Rate: 37.3%)
  • Losing Trades:                 474
  • Gross P&L:                 -₹1,111.14
  • Total Costs & Slippage:   -₹62,450.00
  • Net P&L (After Costs):    -₹63,561.14
  • Strategy Return:              -21.19%
  • Profit Factor:                   0.92
  • Expectancy / Trade:           -₹84.08
  • Max Drawdown:            -₹120,635.45
  • Max Consecutive Losses:         15
  • Max Consecutive Wins:           14

2. CONFIDENCE BAND BREAKDOWN
-----------------------------------------------------------------
  Band     | Trades   | Win Rate   | Net P&L        
  ---------+----------+------------+----------------
  FULL     | 493      |     37.7% |     -₹39,519.26
  HALF     | 263      |     36.5% |     -₹24,041.88

3. BASELINE COMPARISON (Strategy vs NIFTY)
-----------------------------------------------------------------
  • Strategy Net Return:        -21.19%  (-₹63,561.14)
  • NIFTY Buy-and-Hold:         +23.65%  (+₹70,962.70)
  • Alpha / Net Edge:           -44.84%

4. HONEST VERDICT
-----------------------------------------------------------------
  "Strategy returned -21.19% vs NIFTY +23.65% over the period; win rate 37.3% across 756 trades."

5. KNOWN LIMITATIONS & DATA INTEGRITY
-----------------------------------------------------------------
  1. EOD Exit Triggers: Stop/Target evaluated on daily closing prices, not tick-by-tick.
  2. Intrabar Priority: Intrabar conflict conservatively assumes Stop-loss hit.
  3. Dividends Excluded: Cash dividend distributions are omitted (conservative drag).
  4. Zero Curve-Fitting: Default fixed rules tested; no parameter optimization applied.
  5. Version Integrity: Simulation executed exclusively on v2 scores.
     Legacy scores (v1) remain preserved and intact in database storage.
=================================================================
```

---

### 7.3 Honest Analytical Verdict (Mentor Standards)

1. **Statistical Significance**: With **756 completed trades** across 5 full market years (2021 to 2026), the sample size caveat from Phase 2 ($< 30$ trades) is completely resolved. The sample is statistically robust ($\gg 100$ trades).
2. **The Verdict**: The unmodified 5-check Confidence Meter with fixed $+4\%$ target / $-2\%$ stop-loss and 10-day time exit delivered a net loss of **-21.19%** (negative expectancy of -₹84.08 per trade), significantly lagging NIFTY's $+23.65\%$ buy-and-hold gain.
3. **Band Discrimination**: The FULL band ($\ge 80$ pts, 493 trades, win rate $37.7\%$) performed marginally better than the HALF band ($60\text{--}79$ pts, 263 trades, win rate $36.5\%$), but neither band was net profitable after friction.
4. **Frictional Drag**: Statutory charges and slippage cost ₹62,450.00 across 756 trades, turning a near-flat gross P&L (-₹1,111.14) into a substantial net drawdown.
5. **Zero Curve Fitting**: As instructed by Ground Rule 1, no parameters were tuned, no stops widened, and no rules altered to fake a passing score. This provides the exact historical benchmark required for subsequent phases.