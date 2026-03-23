"""
PraxiAlpha — Journal Trade Detail Component

Renders a detailed view of a single trade, including:
- Trade info card (ticker, direction, status, dates, prices)
- Exits table
- Option legs table
- What-if snapshot summary
"""

from typing import Any

import streamlit as st

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "open": "🟢",
    "partial": "🟡",
    "closed": "🔴",
}

_DIRECTION_ICONS = {
    "long": "📈",
    "short": "📉",
}


def _fmt_pnl(value: float | None) -> str:
    """Format a PnL value with color indicator."""
    if value is None:
        return "—"
    if value > 0:
        return f"+${value:,.2f}"
    elif value < 0:
        return f"-${abs(value):,.2f}"
    return "$0.00"


def _fmt_pct(value: float | None) -> str:
    """Format a percentage value."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_price(value: float | None) -> str:
    """Format a price."""
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _fmt_r(value: float | None) -> str:
    """Format R-multiple."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}R"


# ---------------------------------------------------------------------------
# Trade Info Card
# ---------------------------------------------------------------------------


def render_trade_info(trade: dict[str, Any]) -> None:
    """Render the trade info card with key metrics."""
    status = trade.get("status", "open")
    status_icon = _STATUS_COLORS.get(status, "⚪")
    direction = trade.get("direction", "long")
    dir_icon = _DIRECTION_ICONS.get(direction, "")

    # Header
    st.markdown(
        f"### {dir_icon} {trade['ticker']} — "
        f"{direction.upper()} {trade.get('asset_type', 'shares').upper()} "
        f"{status_icon} {status.upper()}"
    )

    # Key metrics row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        pnl = trade.get("realized_pnl", 0)
        delta_color: str = "normal" if pnl != 0 else "off"
        st.metric(
            "Realized PnL",
            _fmt_pnl(pnl),
            delta=_fmt_pct(trade.get("return_pct")),
            delta_color=delta_color,  # type: ignore[arg-type]
        )
    with col2:
        st.metric("R-Multiple", _fmt_r(trade.get("r_multiple")))
    with col3:
        st.metric("Entry Price", _fmt_price(trade.get("entry_price")))
    with col4:
        st.metric("Avg Exit", _fmt_price(trade.get("avg_exit_price")))

    # Details grid
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.markdown(f"**Entry Date:** {trade.get('entry_date', '—')}")
        st.markdown(f"**Quantity:** {trade.get('total_quantity', 0):,.2f}")
    with col_b:
        st.markdown(f"**Remaining:** {trade.get('remaining_quantity', 0):,.2f}")
        st.markdown(f"**Timeframe:** {trade.get('timeframe', '—').capitalize()}")
    with col_c:
        st.markdown(f"**Stop Loss:** {_fmt_price(trade.get('stop_loss'))}")
        st.markdown(f"**Take Profit:** {_fmt_price(trade.get('take_profit'))}")
    with col_d:
        st.markdown(f"**Trade Type:** {trade.get('trade_type', '—').replace('_', ' ').title()}")
        tags = trade.get("tags") or []
        if tags:
            tag_str = " ".join(f"`{t}`" for t in tags)
            st.markdown(f"**Tags:** {tag_str}")
        else:
            st.markdown("**Tags:** —")

    if trade.get("comments"):
        st.markdown(f"**Notes:** {trade['comments']}")


# ---------------------------------------------------------------------------
# Exits Table
# ---------------------------------------------------------------------------


def render_exits_table(trade: dict[str, Any]) -> None:
    """Render the exits table for a trade."""
    exits = trade.get("exits") or []

    st.markdown("#### 📤 Exits")
    if not exits:
        st.caption("No exits recorded yet.")
        return

    # Build table data
    rows = []
    for ex in exits:
        rows.append(
            {
                "Date": ex.get("exit_date", "—"),
                "Price": _fmt_price(ex.get("exit_price")),
                "Quantity": f"{ex.get('quantity', 0):,.2f}",
                "Comments": ex.get("comments") or "—",
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Legs Table
# ---------------------------------------------------------------------------


def render_legs_table(trade: dict[str, Any]) -> None:
    """Render the option legs table for a trade."""
    legs = trade.get("legs") or []

    st.markdown("#### 🦵 Option Legs")
    if not legs:
        st.caption("No option legs recorded.")
        return

    rows = []
    for lg in legs:
        leg_type_display = (lg.get("leg_type") or "—").replace("_", " ").title()
        rows.append(
            {
                "Type": leg_type_display,
                "Strike": _fmt_price(lg.get("strike")),
                "Expiry": lg.get("expiry", "—"),
                "Contracts": f"{lg.get('quantity', 0):,.2f}",
                "Premium": _fmt_price(lg.get("premium")),
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# What-If Summary
# ---------------------------------------------------------------------------


def render_whatif_summary(summary: dict[str, Any] | None) -> None:
    """
    Render the what-if analysis card.

    Shows actual PnL vs best/worst hypothetical holding PnL.
    """
    st.markdown("#### 🔮 What-If Analysis")

    if summary is None:
        st.caption("What-if analysis is only available for closed trades with snapshots.")
        return

    total_snapshots = summary.get("total_snapshots", 0)
    if total_snapshots == 0:
        st.caption(
            "No post-close snapshots yet. Snapshots are collected automatically after a trade closes."
        )
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Actual Exit**")
        actual_pnl = summary.get("actual_pnl")
        actual_pct = summary.get("actual_pnl_pct")
        st.markdown(f"PnL: **{_fmt_pnl(actual_pnl)}** ({_fmt_pct(actual_pct)})")

    best = summary.get("best_hypothetical")
    if best:
        with col2:
            st.markdown("**Best If Held**")
            st.markdown(
                f"PnL: **{_fmt_pnl(best.get('hypothetical_pnl'))}** "
                f"({_fmt_pct(best.get('hypothetical_pnl_pct'))})"
            )
            st.caption(
                f"Date: {best.get('snapshot_date', '—')} — "
                f"Close: {_fmt_price(best.get('close_price'))}"
            )

    worst = summary.get("worst_hypothetical")
    if worst:
        with col3:
            st.markdown("**Worst If Held**")
            st.markdown(
                f"PnL: **{_fmt_pnl(worst.get('hypothetical_pnl'))}** "
                f"({_fmt_pct(worst.get('hypothetical_pnl_pct'))})"
            )
            st.caption(
                f"Date: {worst.get('snapshot_date', '—')} — "
                f"Close: {_fmt_price(worst.get('close_price'))}"
            )

    latest = summary.get("latest_snapshot")
    if latest:
        st.markdown(
            f"**Latest Snapshot:** {latest.get('snapshot_date', '—')} — "
            f"Close: {_fmt_price(latest.get('close_price'))} — "
            f"Hypothetical PnL: {_fmt_pnl(latest.get('hypothetical_pnl'))}"
        )

    st.caption(f"Total snapshots: {total_snapshots}")


# ---------------------------------------------------------------------------
# Snapshot History Table
# ---------------------------------------------------------------------------


def render_snapshot_table(snapshots_data: dict[str, Any] | None) -> None:
    """Render the full snapshot history table."""
    st.markdown("#### 📊 Snapshot History")

    if snapshots_data is None:
        st.caption("Could not load snapshot data.")
        return

    snapshots = snapshots_data.get("snapshots") or []
    if not snapshots:
        st.caption("No snapshots recorded.")
        return

    rows = []
    for s in snapshots:
        rows.append(
            {
                "Date": s.get("snapshot_date", "—"),
                "Close Price": _fmt_price(s.get("close_price")),
                "Hypothetical PnL": _fmt_pnl(s.get("hypothetical_pnl")),
                "Hypothetical PnL %": _fmt_pct(s.get("hypothetical_pnl_pct")),
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)
