"""
PraxiAlpha — Trading Journal Page

Full journal UI with:
- Trade list table with filters and status/PnL columns
- New trade entry form
- Trade detail view (exits, legs, what-if snapshots)
- PDF report download
- Edit and delete actions
"""

from datetime import date, timedelta

import streamlit as st

from streamlit_app.components.journal_api import (
    add_exit,
    add_leg,
    create_trade,
    delete_trade,
    download_report,
    get_trade,
    get_whatif_summary,
    list_snapshots,
    list_trades,
    update_trade,
)
from streamlit_app.components.journal_trade_detail import (
    render_exits_table,
    render_legs_table,
    render_snapshot_table,
    render_trade_info,
    render_whatif_summary,
)
from streamlit_app.components.journal_trade_form import (
    render_edit_form,
    render_exit_form,
    render_leg_form,
    render_trade_form,
)

# ============================================================
# Page config
# ============================================================

st.header("📝 Trading Journal")

# ============================================================
# Session state initialization
# ============================================================

if "journal_view" not in st.session_state:
    st.session_state.journal_view = "list"  # "list" | "detail" | "new"
if "journal_selected_trade_id" not in st.session_state:
    st.session_state.journal_selected_trade_id = None


def _switch_to_list() -> None:
    st.session_state.journal_view = "list"
    st.session_state.journal_selected_trade_id = None


def _switch_to_detail(trade_id: str) -> None:
    st.session_state.journal_view = "detail"
    st.session_state.journal_selected_trade_id = trade_id


def _switch_to_new() -> None:
    st.session_state.journal_view = "new"


# ============================================================
# PnL formatting helpers
# ============================================================


def _pnl_display(value: float | None) -> str:
    if value is None:
        return "—"
    if value > 0:
        return f"+${value:,.2f}"
    elif value < 0:
        return f"-${abs(value):,.2f}"
    return "$0.00"


def _pct_display(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


_STATUS_BADGES = {
    "open": "🟢 Open",
    "partial": "🟡 Partial",
    "closed": "🔴 Closed",
}


# ============================================================
# Sidebar filters (always visible)
# ============================================================

with st.sidebar:
    st.subheader("Journal Filters")

    filter_ticker = st.text_input("Ticker", key="jf_ticker", max_chars=20, placeholder="e.g. AAPL")
    filter_status = st.selectbox(
        "Status", options=["All", "open", "partial", "closed"], key="jf_status"
    )
    filter_direction = st.selectbox(
        "Direction", options=["All", "long", "short"], key="jf_direction"
    )
    filter_timeframe = st.selectbox(
        "Timeframe",
        options=["All", "daily", "weekly", "monthly", "quarterly"],
        key="jf_timeframe",
    )
    filter_tags = st.text_input("Tags (comma-sep)", key="jf_tags", placeholder="swing, earnings")

    st.divider()
    st.subheader("Date Range")
    filter_start = st.date_input("From", value=date.today() - timedelta(days=365), key="jf_start")
    filter_end = st.date_input("To", value=date.today(), key="jf_end")

    st.divider()

    # PDF Report download section
    st.subheader("📄 PDF Report")
    report_include_charts = st.checkbox("Include Charts", value=True, key="jf_charts")
    if st.button("📥 Generate Report", key="jf_report_btn", use_container_width=True):
        with st.spinner("Generating PDF report..."):
            pdf_bytes, filename = download_report(
                start_date=filter_start if filter_start else None,
                end_date=filter_end if filter_end else None,
                status=filter_status if filter_status != "All" else None,
                ticker=filter_ticker.strip().upper() if filter_ticker.strip() else None,
                include_charts=report_include_charts,
            )
        if pdf_bytes:
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.error("Failed to generate report. Is the backend running?")


# ============================================================
# Build filter kwargs for the API call
# ============================================================


def _build_filters() -> dict:
    """Build API filter parameters from sidebar state."""
    filters: dict = {}
    if filter_ticker.strip():
        filters["ticker"] = filter_ticker.strip().upper()
    if filter_status != "All":
        filters["status"] = filter_status
    if filter_direction != "All":
        filters["direction"] = filter_direction
    if filter_timeframe != "All":
        filters["timeframe"] = filter_timeframe
    if filter_tags.strip():
        filters["tags"] = filter_tags.strip()
    if filter_start:
        filters["start_date"] = filter_start
    if filter_end:
        filters["end_date"] = filter_end
    return filters


# ============================================================
# VIEW: Trade List
# ============================================================


def _render_trade_list() -> None:
    """Render the trade list view with action buttons."""
    # Action bar
    col_new, _col_spacer = st.columns([1, 5])
    with col_new:
        if st.button("➕ New Trade", use_container_width=True):
            _switch_to_new()
            st.rerun()

    filters = _build_filters()
    data = list_trades(**filters, limit=100)

    if data is None:
        st.error("⚠️ Could not connect to the backend. Is Docker running?")
        return

    trades = data.get("trades", [])
    count = data.get("count", 0)

    st.caption(f"Showing {count} trade(s)")

    if not trades:
        st.info("No trades found. Click **➕ New Trade** to add your first entry.")
        return

    # Build a table of trades
    for trade in trades:
        status = trade.get("status", "open")
        status_badge = _STATUS_BADGES.get(status, status)
        pnl = trade.get("realized_pnl", 0)
        pnl_str = _pnl_display(pnl)
        pct_str = _pct_display(trade.get("return_pct"))
        direction_icon = "📈" if trade.get("direction") == "long" else "📉"
        tags = trade.get("tags") or []
        tag_str = " ".join(f"`{t}`" for t in tags) if tags else ""

        # Each trade is a row
        with st.container():
            col1, col2, col3, col4, col5, col6 = st.columns([2, 1.5, 1.5, 2, 2, 1.5])
            with col1:
                st.markdown(f"**{direction_icon} {trade['ticker']}**")
                st.caption(
                    f"{trade.get('entry_date', '—')} · {trade.get('timeframe', '—').capitalize()}"
                )
            with col2:
                st.markdown(f"{status_badge}")
            with col3:
                st.markdown(f"${trade.get('entry_price', 0):,.2f}")
                st.caption(f"Qty: {trade.get('total_quantity', 0):,.0f}")
            with col4:
                if pnl and pnl > 0:
                    st.markdown(f"🟩 **{pnl_str}** ({pct_str})")
                elif pnl and pnl < 0:
                    st.markdown(f"🟥 **{pnl_str}** ({pct_str})")
                else:
                    st.markdown(f"⬜ {pnl_str}")
            with col5:
                if tag_str:
                    st.markdown(tag_str)
                else:
                    st.caption("—")
            with col6:
                if st.button(
                    "View",
                    key=f"view_{trade['id']}",
                    use_container_width=True,
                ):
                    _switch_to_detail(trade["id"])
                    st.rerun()
            st.divider()


# ============================================================
# VIEW: Trade Detail
# ============================================================


def _render_trade_detail() -> None:
    """Render the full detail view for a single trade."""
    trade_id = st.session_state.journal_selected_trade_id

    # Back button
    if st.button("⬅️ Back to List"):
        _switch_to_list()
        st.rerun()

    if not trade_id:
        st.warning("No trade selected.")
        return

    trade = get_trade(trade_id)
    if trade is None:
        st.error("Could not load trade. It may have been deleted or the backend is unavailable.")
        return

    # Trade info card
    render_trade_info(trade)
    st.divider()

    # Tabs for different sections
    tab_exits, tab_legs, tab_whatif, tab_edit, tab_actions = st.tabs(
        ["📤 Exits", "🦵 Option Legs", "🔮 What-If", "✏️ Edit", "⚙️ Actions"]
    )

    with tab_exits:
        render_exits_table(trade)

        st.divider()
        # Add exit form
        exit_payload = render_exit_form(trade, key=f"exit_{trade_id}")
        if exit_payload:
            result = add_exit(trade_id, exit_payload)
            if result:
                st.success("Exit recorded successfully!")
                st.rerun()
            else:
                st.error("Failed to add exit. Check backend connection.")

    with tab_legs:
        render_legs_table(trade)

        if trade.get("asset_type") == "options":
            st.divider()
            leg_payload = render_leg_form(key=f"leg_{trade_id}")
            if leg_payload:
                result = add_leg(trade_id, leg_payload)
                if result:
                    st.success("Option leg added successfully!")
                    st.rerun()
                else:
                    st.error("Failed to add leg. Check backend connection.")
        else:
            st.caption("Option legs are only available for options trades.")

    with tab_whatif:
        status = trade.get("status", "open")
        if status == "closed":
            # Fetch what-if summary
            summary = get_whatif_summary(trade_id)
            render_whatif_summary(summary)

            st.divider()

            # Full snapshot history
            snapshots_data = list_snapshots(trade_id)
            render_snapshot_table(snapshots_data)
        else:
            st.info(
                "What-if analysis is available after a trade is fully closed. "
                "Post-close snapshots are collected automatically."
            )

    with tab_edit:
        edit_payload = render_edit_form(trade, key=f"edit_{trade_id}")
        if edit_payload:
            result = update_trade(trade_id, edit_payload)
            if result:
                st.success("Trade updated successfully!")
                st.rerun()
            else:
                st.error("Failed to update trade. Check backend connection.")

    with tab_actions:
        st.markdown("#### ⚠️ Danger Zone")
        st.warning("Deleting a trade is permanent and cannot be undone.")

        # Require confirmation
        confirm = st.checkbox(
            "I understand this action is irreversible",
            key=f"confirm_delete_{trade_id}",
        )
        if confirm and st.button(
            "🗑️ Delete Trade",
            key=f"delete_{trade_id}",
            type="primary",
            use_container_width=True,
        ):
            success = delete_trade(trade_id)
            if success:
                st.success("Trade deleted.")
                _switch_to_list()
                st.rerun()
            else:
                st.error("Failed to delete trade. Check backend connection.")


# ============================================================
# VIEW: New Trade
# ============================================================


def _render_new_trade() -> None:
    """Render the new trade creation view."""
    if st.button("⬅️ Back to List"):
        _switch_to_list()
        st.rerun()

    payload = render_trade_form(key="create_trade_form")
    if payload:
        result = create_trade(payload)
        if result:
            st.success(
                f"Trade created: **{result.get('ticker', '')}** ({result.get('direction', '')})"
            )
            _switch_to_detail(result["id"])
            st.rerun()
        else:
            st.error("Failed to create trade. Check backend connection and input values.")


# ============================================================
# Route to the correct view
# ============================================================

view = st.session_state.journal_view

if view == "detail":
    _render_trade_detail()
elif view == "new":
    _render_new_trade()
else:
    _render_trade_list()
