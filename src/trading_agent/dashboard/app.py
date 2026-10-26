"""Streamlit Read-Only Dashboard for Trading Agent.

Visualizes latest confidence scores, 12-month historical score charts,
detailed check breakdowns, and data quality logs.
Strictly read-only: does not compute scores or mutate database state.
"""

import datetime as dt
import pandas as pd
import streamlit as st

from trading_agent.adapters.storage import DatabaseBusyError, SqliteStorageAdapter
from trading_agent.config import get_settings
from trading_agent.domain.models import TradeBand
from trading_agent.ports.storage import StoragePort

st.set_page_config(
    page_title="Trading Agent — Read-Only Dashboard",
    page_icon="🤖",
    layout="wide",
)


def get_storage() -> StoragePort:
    """Obtain a storage port instance configured from application settings."""
    settings = get_settings()
    return SqliteStorageAdapter(db_path=settings.database_path)


def format_band_badge(band: TradeBand) -> str:
    """Format TradeBand enum into a human-readable badge."""
    if band == TradeBand.FULL:
        return "🟢 FULL (≥80)"
    if band == TradeBand.HALF:
        return "🟡 HALF (60-79)"
    return "🔴 NONE (<60)"


def render_overview(storage: StoragePort) -> None:
    """Page 1 — Overview: Table of watchlist symbols with latest scores and bands."""
    st.title("📊 Market Overview — Latest Confidence Scores")
    st.caption("Read-only view of latest confidence meter evaluations across the watchlist.")

    try:
        latest_scores = storage.get_latest_scores()
    except DatabaseBusyError:
        st.error("⏳ Database is currently busy with a backfill operation — try again in a moment.")
        return
    except Exception as exc:
        st.error(f"❌ Error reading from database: {exc}")
        return

    if not latest_scores:
        st.warning("⚠️ No data found in database. Run `uv run backfill` in your terminal first to populate historical scores.")
        return

    # Build display table with dynamic check columns
    all_check_names: list[str] = []
    for score in latest_scores:
        for c in score.check_results:
            if c.check_name not in all_check_names:
                all_check_names.append(c.check_name)

    rows = []
    for score in latest_scores:
        check_map = {c.check_name: ("✅" if c.passed else "❌") for c in score.check_results}
        max_possible = sum(c.max_points for c in score.check_results) if score.check_results else 100

        row = {
            "Symbol": score.symbol,
            "Latest Date": score.date.strftime("%Y-%m-%d") if score.date else "—",
            "Version": getattr(score, "meter_version", "v1"),
            "Total Score": f"{score.total_points} / {max_possible}",
            "Band": format_band_badge(score.band),
        }
        for name in all_check_names:
            row[name] = check_map.get(name, "—")
        rows.append(row)

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.info(f"🕒 Last updated from database at {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Total symbols monitored: {len(latest_scores)}.")


def render_symbol_detail(storage: StoragePort) -> None:
    """Page 2 — Symbol Detail: 12-month score history chart & full latest breakdown."""
    st.title("🔍 Symbol Detail & Score History")

    try:
        counts = storage.get_score_counts_by_symbol()
    except DatabaseBusyError:
        st.error("⏳ Database is currently busy — try again in a moment.")
        return
    except Exception as exc:
        st.error(f"❌ Error reading database: {exc}")
        return

    symbols = sorted(counts.keys())
    if not symbols:
        st.warning("⚠️ No data found in database. Run `uv run backfill` first.")
        return

    selected_symbol = st.selectbox("Select Symbol:", symbols, index=0)

    # 1. Fetch 12-month score history
    today = dt.date.today()
    start_date = today - dt.timedelta(days=365)

    try:
        history = storage.get_scores_for_symbol_in_range(selected_symbol, start_date, today)
        latest_score = history[-1] if history else storage.get_score(selected_symbol, today)
    except DatabaseBusyError:
        st.error("⏳ Database is currently busy — try again in a moment.")
        return
    except Exception as exc:
        st.error(f"❌ Error retrieving symbol history: {exc}")
        return

    st.subheader(f"📈 12-Month Daily Score History for {selected_symbol}")
    if history:
        chart_data = pd.DataFrame(
            {
                "Date": [pd.to_datetime(s.date) for s in history],
                "Score": [s.total_points for s in history],
                "HALF Threshold (60)": [60 for _ in history],
                "FULL Threshold (80)": [80 for _ in history],
            }
        ).set_index("Date")

        st.line_chart(chart_data, color=["#29b5e8", "#ffbb00", "#00cc66"])
    else:
        st.info(f"No historical daily scores found for {selected_symbol} in the last 12 months.")

    # 2. Latest Score Detailed Breakdown
    if latest_score:
        st.markdown("---")
        st.subheader(f"🎯 Latest Score Breakdown ({selected_symbol} on {latest_score.date.isoformat()})")

        max_possible = sum(c.max_points for c in latest_score.check_results) if latest_score.check_results else 100
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Points", f"{latest_score.total_points} / {max_possible}")
        col2.metric("Trade Band", format_band_badge(latest_score.band))
        col3.metric("Meter Version", getattr(latest_score, "meter_version", "v1"))

        if latest_score.band == TradeBand.FULL:
            action_desc = "🟢 BUY (FULL POSITION)"
        elif latest_score.band == TradeBand.HALF:
            action_desc = "🟡 BUY (HALF POSITION)"
        else:
            action_desc = "🔴 NO TRADE (PASS)"
        col4.metric("Action Decision", action_desc)

        st.markdown("#### Individual Check Rationales")
        if latest_score.check_results:
            for check in latest_score.check_results:
                status_icon = "✅ PASS" if check.passed else "❌ FAIL"
                with st.expander(f"{check.check_name} — {status_icon} (+{check.points_awarded}/{check.max_points} pts)", expanded=True):
                    st.write(f"**Rationale:** {check.rationale or '—'}")
        else:
            st.info("No individual check records stored for this date.")


def render_data_quality(storage: StoragePort) -> None:
    """Page 3 — Data Quality: Log of recorded data anomalies, newest first."""
    st.title("🛡️ Data Quality & Anomaly Log")
    st.caption("Transparent audit trail of missing bars, corrupted rows, or feed warnings encountered during backfill.")

    try:
        issues = storage.get_data_quality_issues()
    except DatabaseBusyError:
        st.error("⏳ Database is currently busy — try again in a moment.")
        return
    except Exception as exc:
        st.error(f"❌ Error loading data quality records: {exc}")
        return

    if not issues:
        st.success("✅ Zero data quality issues recorded! Data feed and bar validations are clean.")
        return

    rows = []
    for issue in issues:
        rows.append(
            {
                "Symbol": issue.symbol or "—",
                "Date": issue.date.strftime("%Y-%m-%d") if issue.date else "—",
                "Issue Description": issue.issue or "—",
                "Recorded At": issue.recorded_at.strftime("%Y-%m-%d %H:%M:%S") if issue.recorded_at else "—",
            }
        )

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.info(f"Total anomaly events recorded: {len(issues)}")


def main() -> None:
    """Main dashboard entry point with sidebar navigation."""
    st.sidebar.title("🤖 Trading Agent")
    st.sidebar.caption("Phase 3 — 5-Check Confidence Meter")

    page = st.sidebar.radio(
        "Navigation",
        ["Overview", "Symbol Detail", "Data Quality"],
        index=0,
    )

    storage = get_storage()

    if page == "Overview":
        render_overview(storage)
    elif page == "Symbol Detail":
        render_symbol_detail(storage)
    elif page == "Data Quality":
        render_data_quality(storage)


if __name__ == "__main__":
    main()
