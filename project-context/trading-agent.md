# 🤖 AI Trading Bot — Project Draft

**Owner:** Raja Shekhar
**Stage:** Idea → Paper trading (zero real money)
**Version:** v0.1

---

## 1. The Idea (One-liner)

> A personal, fully local trading bot that never fires a trade unless a **Confidence Meter** crosses a threshold, adjusts itself using **pre-market sentiment checks**, and continuously **learns from its logged mistakes** — all built for **₹0** and validated via **paper trading** before a single rupee is risked.

**Positioning:** a *compliant execution engine for a tested strategy* — NOT a money-printing robot.

---

## 2. Core Building Blocks

### 📊 Block A — Confidence Meter (the heart)

Instead of buy/don't-buy, the bot outputs a score:

| Check | Points if ✅ |
|---|---|
| Stock clearly trending up | +25 |
| Volume higher than usual (real interest) | +20 |
| Not at an all-time crazy high (avoid buying tops) | +20 |
| Overall market green today (Nifty up) | +20 |
| Stop-loss level makes sense (small loss if wrong) | +15 |

**Bands:**
- 🟢 80–100 → take the trade
- 🟡 60–79 → half-size trade
- 🔴 Below 60 → no trade (sitting on hands is a feature)

**Starter version:** use only 3 checks (trend, volume, market direction). Add the rest once the first three prove useful.

### 📰 Block B — Pre-Market Sentiment Add-on

Checked at ~8:30 AM, before the 9:15 open. Feeds a **−10 / 0 / +10 adjustment** into the Confidence Meter.

**Stage 1 (structured data, very practical):**
1. US market close (↑/↓)
2. GIFT Nifty direction ← the single best signal
3. "Big event today?" (tiny manually maintained calendar: RBI, budget, elections, Fed)
4. Crude oil / rupee direction

**Stage 2 (later, only after Stage 1 proves itself):**
- AI reading actual news headlines and scoring sentiment. Noisy, harder to get right — not a day-one item.

**Honest truth:** by the time news is "news", the price already knows. Use this module mainly to answer *"should I be cautious today?"* — most days it should output "normal day, no adjustment".

### 🧠 Block C — Learning from Mistakes (the main engine)

The realistic version of "learning" is a **feedback loop**, not a puppy that trains itself:

```
Every trade → log WHY (confidence score + which checks fired)
        ↓
Outcome → win/loss, amount, followed rules?
        ↓
Weekly review → "when volume ✅, win rate 65%; when ❌, 40%"
        ↓
Adjust → give each check more/less points
```

**Three levels of learning — build in this order:**
1. **Level 1:** Log everything. YOU review weekly. YOU adjust the rules. (Human-in-the-loop.)
2. **Level 2:** Code auto-stats your logs — e.g., "alert: your 60–79 bucket is losing money, tighten threshold."
3. **Level 3:** ML auto-tuning. ⛔ Skip for now — it will happily learn garbage from 3 weeks of data.

**Secret ingredient:** tag every trade as **rule-followed** or **rule-broken** (bug, bad data, stale signal). Only learn from clean mistakes.

**Poker rule:** judge decisions, not outcomes. A rule-followed trade that loses is NOT a mistake; a rule-broken trade that wins is NOT a win.

---

## 3. Paper Trading (How It All Works Without Money)

- Bot watches **real prices, real timings** (9:15 AM – 3:30 PM IST)
- When confidence > threshold → it logs "**WOULD have bought**" instead of buying
- You track would-be profit/loss in a Google Sheet / SQLite
- After 3–6 months of consistent paper profits → only then consider real money

**Catch to remember:** paper money = fake emotions. Real losses hit different. It's the right *first* step, not the whole journey.

---

## 4. Tool Stack (₹0 — Runs Entirely on Your Laptop)

| Tool | Purpose | Cost |
|---|---|---|
| Python + VS Code | The whole brain | Free |
| pandas | Data crunching | Free |
| yfinance | Historical + live-ish Indian stock data | Free |
| SQLite (built into Python) | Trade logs, scores, outcomes ("one Excel file code reads") | Free |
| Telegram bot | Alerts to you ("confidence 85%, would buy RELIANCE") | Free |
| Google Sheets | Weekly human review journal | Free |

**Zero-rupee workflow:** laptop on during market hours → bot watches prices → logs paper signals → Telegram pings → weekend review → tweak meter.

### Costs that come LATER (only after paper-trading success)

| Item | Cost | Trigger |
|---|---|---|
| Broker API (Zerodha Kite Connect ~₹500/mo; Angel One SmartAPI free) | ₹0–500/mo | Going live |
| VPS with static IP (~₹400/mo, e.g., AWS Mumbai) | ~₹400/mo | Bot must run unattended 9:15–3:30 |
| Real capital (start ₹5–10k) | You decide | 3+ months of profitable paper trading |

---

## 5. Edge Cases to Design For

1. **Bot crashes at 2 PM, position open** → mandatory auto square-off at 3:15 PM
2. **API token expires mid-day** (they expire daily!) → detect and alert; never die silently
3. **Overnight gap-up** (stock opens +8%) → re-check at open; never act on yesterday's signal
4. **Circuit / halted stocks** → can't buy what's frozen; skip gracefully
5. **Confidence meter says 90% every day** → it's broken (or too lenient) — recalibrate
6. **Internet dies** → broker-side stop-loss as backup when live
7. **Rule-broken trades** → tag them; exclude from learning stats
8. **Order spam** (later, live) → rate-limit well below 10 orders/sec (SEBI threshold); mind order-to-trade ratio penalties

---

## 6. Do's ✅ and Don'ts ❌

### ✅ Do's
- Start with **3 checks max** in the confidence meter
- Log **every** signal — including the trades you *didn't* take
- Review weekly; adjust one thing at a time so you know what worked
- Judge decisions, not outcomes
- Paper trade for **3–6 months** minimum before real money
- When going live: start with ₹5–10k you can fully afford to lose
- Keep a kill switch from day one
- Confirm current SEBI/exchange rules on official sources on the day you go live
- Host on an India-region server (e.g., AWS Mumbai) with a **static IP** when live

### ❌ Don'ts
- Don't use offshore forex/CFD/crypto "AI bot" platforms (RBI Alert List — FEMA violation)
- Don't sell signals or run the bot for others without SEBI registration (RIA/PMS) — personal + immediate family only
- Don't trust "guaranteed returns" — in algo land that phrase is a red flag SEBI actively punishes
- Don't add ML auto-learning at Stage 1
- Don't judge a strategy on < 30 trades
- Don't let the bot trade through lunch while unmonitored, before it has a proven track record
- Don't over-trade — most beginner losses come from too many trades, not bad ones
- Don't add a new indicator every losing week (strategy hopping = the real killer)

---

## 7. Regulatory Notes (India)

- Retail algo trading via broker APIs is **legal**, governed by SEBI's 4 Feb 2025 circular ("Safer participation of retail investors in Algorithmic trading"), fully applicable to all brokers since 1 April 2026.
- **Below 10 orders/second per exchange** → ordinary API user; no exchange registration needed, orders get a generic algo ID for audit.
- **Above the threshold** → strategy must be exchange-approved with a unique Algo ID.
- Technical mandates: static IP whitelisting, OAuth/2FA only, 5-year audit trail, kill-switch controls.
- The **broker is legally responsible (principal)** for algo orders; algo providers act as their agents.
- Reality check (SEBI's own study): 93% of individual F&O traders lost money FY22–24 (₹1.8 lakh crore aggregate). A bot executes faster — it does not fix a bad edge.

---

## 8. Build Roadmap

- [x] **Phase 1:** Foundation & Signal Engine — Ports & Adapters, Confidence Meter v0 (3 checks), SQLite in WAL mode, Telegram alerts, CLI `backfill` & `score`
- [x] **Phase 1.5:** Read-Only Dashboard — Streamlit browser UI (Overview, Symbol Detail charts, Data Quality logs)
- [x] **Phase 2:** Backtesting & Validation — Historical backtest engine, lookahead guard, conservative execution physics, metrics & NIFTY benchmark baseline comparison, CLI `backtest`
- [x] **Phase 3:** Data Expansion & Full 5-Check Meter — 20 liquid NSE large-caps, 5-year incremental backfill, 5-check Confidence Meter reaching 100 pts (`NotAtHighCheck` + `StopDistanceCheck`), score versioning (`v1` and `v2`), 756-trade 5-year backtest against NIFTY baseline
- [ ] **Phase 4:** Pre-market sentiment module (GIFT Nifty + US close + event calendar)
- [ ] **Phase 5:** Paper trading execution loop (9:15 AM – 3:30 PM real-time shadow trading)
- [ ] **Phase 6:** Feedback & Continuous Learning loop (auto-stats, rule-followed vs broken tags, threshold adjustment)
- [ ] **Phase 7:** Broker API integration (under SEBI algorithmic trading guidelines)

---

## 9. Success Criteria

| Milestone | Proof |
|---|---|
| Meter works | 80–100 band trades clearly outperform 60–79 band in paper logs |
| Learning works | Weekly review changes points/thresholds with evidence from ≥30 trades |
| Ready for real money | 3+ months paper profitability + zero rule-broken trades in the last month |

---

*Draft v0.1 — everything here is educational planning, not financial or legal advice.*