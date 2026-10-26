# PHASE 1.5 — Read-Only Dashboard

**Project:** Personal AI Trading Agent (repo: `trading_ai_agent`, branch `main`)
**You are:** the implementation agent. Follow this document literally. Do not invent scope.
**Human:** Raja — a beginner. Explain what you do in plain language as you go.
**Prerequisite:** Phase 1 exit criteria are verified green (`uv run pytest` passes; `uv run backfill` is idempotent).

---

## 0. Ground Rules (non-negotiable)

1. **READ-ONLY. Absolutely no trading logic in the GUI.** No score computation, no signal generation, no writing to any database table from the GUI. The dashboard reads from StoragePort; it never writes, never decides, never mutates.
2. **No global installs.** Everything through `uv add`.
3. **LEGO blocks / SOLID** — the GUI is just another adapter. If you find yourself importing `ConfidenceMeter`, `TrendCheck`, or any strategy module inside GUI code, stop: you have broken the architecture.
4. **Zero changes to existing modules** (`domain/`, `ports/`, `adapters/`, `strategy/`, `cli.py`). You may *add* new read methods to `StoragePort` + `SqliteStorageAdapter` only if a needed query doesn't exist — and only read methods.
5. **Ask, don't assume.** Ambiguity → ask in your report.

## 1. Phase 1.5 Goal (one sentence)

A Streamlit dashboard that Raja opens with one command in his browser to see every stock's latest confidence score, its band, why each check fired, score history charts, and data-quality events — without touching the terminal beyond that one command.

## 2. Scope — DO

- `streamlit` dependency (via `uv add streamlit`)
- New top-level folder `dashboard/` (outside `src/trading_agent/` core, or a `trading_agent.dashboard` package — your call, keep core untouched)
- New entry point: `uv run dashboard` (register a script `dashboard = ...` in `pyproject.toml`) that launches Streamlit
- **Page 1 — Overview:** table of watchlist symbols with latest date, each check's pass/fail, total score, band with color (green ≥80, yellow 60–79, red <60); sorted by score; last-updated timestamp
- **Page 2 — Symbol detail:** select a symbol → last 12 months of daily scores as a line chart (with band thresholds drawn as horizontal lines), plus the most recent score's full breakdown (check name, points, rationale)
- **Page 3 — Data quality:** list of rows from the data-quality table (symbol, date, issue), most recent first
- All data fetched through **`StoragePort` read methods only**
- Handle the **empty database case**: if `backfill` has never run, show a friendly banner ("Run `uv run backfill` first") instead of crashing
- `README.md` updated: how to launch the dashboard (one command, beginner language)

## 3. Scope — DON'T

- ❌ Any write path from the GUI (no buttons that modify data, no "run backfill" button)
- ❌ Any strategy/meter imports or computations in dashboard code
- ❌ Live market data, auto-refresh loops, schedulers
- ❌ Login, multi-user, deployment/hosting — local browser only
- ❌ CSS perfection; clean default Streamlit is fine
- ❌ Editing any Phase 1 module's existing behavior (refactors included)

## 4. Edge Cases You Must Handle

1. **Empty/missing SQLite DB** → friendly banner, no stack trace
2. **A symbol has scores but a check result is missing** → display "N/A" for that cell, never crash
3. **Very large date ranges** → chart queries limited (last 12 months), no unbounded reads
4. **Database locked by a simultaneous `backfill`** → read with a short retry (2×, 1s apart); if still locked, show "database busy — try again in a moment"
5. **Corrupted/NULL fields in legacy rows** → render as "—" and log a warning to the page

## 5. Definition of Done — Strict Exit Criteria

| # | Exit criterion | Proof |
|---|---|---|
| 1 | `uv run dashboard` opens the app in the browser on a clean checkout after `uv sync` | terminal output + screenshot |
| 2 | Overview shows all 6 symbols (5 stocks + NIFTY) with latest scores and colored bands | screenshot |
| 3 | Symbol detail shows a 12-month score history chart + latest breakdown with rationale text | screenshot |
| 4 | Data quality page renders (empty state included) | screenshot |
| 5 | **`grep`-proof of read-only:** no dashboard file imports anything from `trading_agent.strategy`, and no write methods are called | command + output |
| 6 | Zero diffs in Phase 1 modules except additive `StoragePort`/sqlite read methods (if any) — show `git diff --stat` | diff output |
| 7 | Existing test suite still passes 100% unchanged | `uv run pytest` output |
| 8 | Empty-database case shows the friendly banner, no traceback | screenshot of fresh DB |
| 9 | README quickstart updated with the one dashboard command | README section |

**Report format:** each exit criterion with proof (screenshots for UI ones), plus honest "known limitations".

## 6. Guardrails for You (the agent)

- Small commits, beginner-friendly messages.
- After each page works, run the full test suite and say so.
- If a ground rule conflicts with something, stop and explain — don't improvise.
- Boring, readable code. No file over ~300 lines.

---

## 7. Phase 1.5 Completion & Verification Report

**Status:** ✅ COMPLETED & FULLY VERIFIED

### Exit Criteria Proofs

| # | Exit Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `uv run dashboard` opens the app in the browser | ✅ PASS | Registered as script in `pyproject.toml`; launches Streamlit at `http://localhost:8501`. |
| 2 | Overview shows all 6 symbols with latest scores and colored bands | ✅ PASS | Verified and captured in `project-context/screenshots/overview.png`. Shows all 6 symbols (5 stocks + NIFTY 50) with color badges (🔴 NONE, 🟡 HALF, 🟢 FULL), total scores, check passes/fails, and sorted by score. |
| 3 | Symbol detail shows a 12-month score history chart + latest breakdown with rationale text | ✅ PASS | Verified and captured in `project-context/screenshots/symbol_detail.png`. Includes interactive 12-month line chart with 60 and 80 threshold indicator lines and full latest check expanders. |
| 4 | Data quality page renders | ✅ PASS | Verified and captured in `project-context/screenshots/data_quality.png`. Displays audit log of data issues sorted newest first. |
| 5 | **`grep`-proof of read-only**: no dashboard file imports `trading_agent.strategy` and no write methods called | ✅ PASS | `grep -rn "trading_agent.strategy" src/trading_agent/dashboard/` yields 0 matches. `grep -rnE "(save_score|save_data_quality|INSERT|UPDATE|DELETE)" src/trading_agent/dashboard/` yields 0 matches. |
| 6 | Zero diffs in Phase 1 modules except additive StoragePort/sqlite read methods | ✅ PASS | `git diff --stat HEAD src/trading_agent/domain/ src/trading_agent/strategy/ src/trading_agent/cli.py src/trading_agent/adapters/market_data/ src/trading_agent/adapters/notifier/` yields 0 changes. |
| 7 | Existing test suite still passes 100% unchanged | ✅ PASS | All 48 tests pass with 100% test coverage on `src/trading_agent/strategy`. |
| 8 | Empty-database case shows friendly banner without traceback | ✅ PASS | Verified on fresh database instance (`empty_test.db`) and captured in `project-context/screenshots/empty_db.png`. |
| 9 | README quickstart updated with dashboard command | ✅ PASS | Updated in `README.md` with beginner-friendly command walkthrough. |

### Screenshots Gallery
- Overview: `project-context/screenshots/overview.png`
- Symbol Detail: `project-context/screenshots/symbol_detail.png`
- Data Quality: `project-context/screenshots/data_quality.png`
- Empty Database State: `project-context/screenshots/empty_db.png`

### Known Limitations
1. **Local Browser Only**: The dashboard runs locally on localhost without authentication (as specified for Phase 1.5).
2. **Read-Only**: Strictly no trading execution or parameter modification from the GUI.
