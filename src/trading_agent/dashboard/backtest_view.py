"""Interactive Backtest Simulation View for Streamlit Dashboard.

Allows non-technical users to trigger historical validation runs across
custom or preset date ranges, inspect metrics, and explore executed trades.
"""

import datetime as dt
import pandas as pd
import streamlit as st

from trading_agent.backtest.metrics import BacktestMetrics
from trading_agent.backtest.runner import BacktestResult, execute_backtest
from trading_agent.config import get_settings
from trading_agent.domain.models import TradeRecord
from trading_agent.ports.storage import StoragePort


def format_inr(val: float) -> str:
    """Format Indian Rupee amount with sign."""
    prefix = "+" if val > 0 else ("-" if val < 0 else "")
    return f"{prefix}₹{abs(val):,.2f}"


def format_pct(val: float) -> str:
    """Format percentage with sign."""
    prefix = "+" if val > 0 else ("-" if val < 0 else "")
    return f"{prefix}{abs(val):.2f}%"


def render_backtest_view(storage: StoragePort) -> None:
    """Render the interactive Backtest Simulation GUI page."""
    st.title("🔬 Backtest Simulation & Trade Validation")
    st.caption("Trigger and inspect historical simulations directly from your browser—no terminal commands required.")

    settings = get_settings()
    today = dt.date.today()

    # 1. Preset & Date Range Selection
    st.markdown("### 1. Select Simulation Period")
    preset_choice = st.radio(
        "Quick Presets:",
        ["Last 7 Days", "Last 30 Days", "Last 90 Days", "Last 1 Year", "Last 5 Years", "Custom Range"],
        index=0,
        horizontal=True,
    )

    if preset_choice == "Last 7 Days":
        default_start = today - dt.timedelta(days=7)
        default_end = today
    elif preset_choice == "Last 30 Days":
        default_start = today - dt.timedelta(days=30)
        default_end = today
    elif preset_choice == "Last 90 Days":
        default_start = today - dt.timedelta(days=90)
        default_end = today
    elif preset_choice == "Last 1 Year":
        default_start = today - dt.timedelta(days=365)
        default_end = today
    elif preset_choice == "Last 5 Years":
        default_start = today - dt.timedelta(days=1825)
        default_end = today
    else:
        default_start = today - dt.timedelta(days=30)
        default_end = today

    col_start, col_end = st.columns(2)
    start_date = col_start.date_input("Start Date", value=default_start)
    end_date = col_end.date_input("End Date", value=default_end)

    # 2. Watchlist selection (in expander)
    with st.expander("⚙️ Watchlist & Parameters", expanded=False):
        all_symbols = sorted(settings.watchlist)
        selected_symbols = st.multiselect(
            "Symbols to include:",
            options=all_symbols,
            default=all_symbols,
        )
        selected_meter = st.selectbox("Meter Version:", ["v2", "v1"], index=0)

    # 3. Trigger button
    st.markdown("---")
    if st.button("🚀 Run Backtest Simulation", type="primary", use_container_width=True):
        if not selected_symbols:
            st.error("Please select at least one stock symbol to test.")
            return

        with st.spinner("Executing chronological simulation, checking exits, and deducting statutory friction..."):
            result = execute_backtest(
                start_date=start_date,
                end_date=end_date,
                storage=storage,
                watchlist=selected_symbols,
                meter_version=selected_meter,
            )
            st.session_state["latest_gui_backtest"] = result

    # 4. Display Results
    if "latest_gui_backtest" in st.session_state:
        res: BacktestResult = st.session_state["latest_gui_backtest"]

        if not res.success:
            st.error(f"❌ Simulation Error: {res.error_message}")
            return

        metrics: BacktestMetrics = res.metrics
        st.success(f"✓ Backtest completed: **{metrics.total_trades} trades** executed (Run ID: `{res.run_id}`).")

        # Key Metrics Row
        strat_ret = (metrics.net_pnl / res.initial_capital) * 100.0 if res.initial_capital > 0 else 0.0
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Net P&L", format_inr(metrics.net_pnl), delta=f"{strat_ret:+.2f}%")
        m2.metric("Win Rate", f"{metrics.win_rate_pct:.1f}%", f"{metrics.winning_trades}W / {metrics.losing_trades}L")
        m3.metric("NIFTY Benchmark", format_pct(metrics.baseline_return_pct), delta_color="off")
        alpha = strat_ret - metrics.baseline_return_pct
        m4.metric("Alpha / Edge", format_pct(alpha), delta=f"{alpha:+.2f}%")
        m5.metric("Profit Factor", f"{metrics.profit_factor:.2f}")
        m6.metric("Max Drawdown", format_inr(-abs(metrics.max_drawdown_amount)))

        # Statistical Honesty Callout
        if metrics.total_trades < 100:
            st.warning(
                f"⚠️ **Statistical Honesty Warning:** Sample size ({metrics.total_trades} trades < 100) is too small "
                "to draw definitive conclusions. More market cycles are required before committing real capital."
            )
        else:
            st.info(f"📊 **Statistically Robust Sample:** {metrics.total_trades} trades evaluated across market cycles.")

        # Band Breakdown Table
        st.subheader("🎯 Performance by Confidence Band")
        band_rows = []
        for b_name in ["FULL", "HALF"]:
            if b_name in metrics.band_breakdown:
                bm = metrics.band_breakdown[b_name]
                band_rows.append({
                    "Trade Band": bm.band.value,
                    "Total Trades": bm.total_trades,
                    "Win Rate": f"{bm.win_rate_pct:.1f}%",
                    "Net P&L": format_inr(bm.net_pnl),
                })
        st.dataframe(pd.DataFrame(band_rows), use_container_width=True, hide_index=True)

        # Executed Trades Table
        st.subheader(f"📋 Executed Trades Log ({len(res.trades)})")
        if res.trades:
            trades_data = [
                {
                    "Symbol": t.symbol,
                    "Signal Date": t.signal_date.strftime("%Y-%m-%d"),
                    "Entry Date": t.entry_date.strftime("%Y-%m-%d"),
                    "Entry (₹)": f"{t.entry_price:.2f}",
                    "Exit Date": t.exit_date.strftime("%Y-%m-%d"),
                    "Exit (₹)": f"{t.exit_price:.2f}",
                    "Exit Reason": t.exit_reason.value,
                    "Band": t.band.value,
                    "Gross (₹)": format_inr(t.gross_pnl),
                    "Net P&L (₹)": format_inr(t.net_pnl),
                }
                for t in res.trades
            ]
            df_trades = pd.DataFrame(trades_data)
            st.dataframe(df_trades, use_container_width=True, hide_index=True)

            # Download CSV
            csv_content = df_trades.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Download Trades as CSV",
                data=csv_content,
                file_name=f"trades_{res.run_id}.csv",
                mime="text/csv",
            )
        else:
            st.info("No trades were generated or completed in this date window.")
