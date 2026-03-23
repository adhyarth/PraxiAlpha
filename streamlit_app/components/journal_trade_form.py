"""
PraxiAlpha — Journal Trade Form Component

Reusable Streamlit form for creating and editing trades.
Handles entry form, exit form, and option leg form.
"""

from datetime import date
from typing import Any

import streamlit as st


def render_trade_form(key: str = "new_trade") -> dict[str, Any] | None:
    """
    Render the new-trade entry form.

    Returns a dict with the trade fields if the form is submitted,
    or None if the user hasn't submitted yet.
    """
    with st.form(key=key, clear_on_submit=True):
        st.subheader("📝 New Trade")

        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("Ticker *", max_chars=20, placeholder="AAPL")
            direction = st.selectbox("Direction *", options=["long", "short"])
            asset_type = st.selectbox("Asset Type *", options=["shares", "options"])
            trade_type = st.selectbox("Trade Type", options=["single_leg", "multi_leg"])

        with col2:
            entry_date = st.date_input("Entry Date *", value=date.today())
            entry_price = st.number_input(
                "Entry Price *", min_value=0.01, value=100.00, step=0.01, format="%.2f"
            )
            total_quantity = st.number_input(
                "Quantity *", min_value=0.01, value=100.0, step=1.0, format="%.2f"
            )
            timeframe = st.selectbox(
                "Timeframe *", options=["daily", "weekly", "monthly", "quarterly"]
            )

        col3, col4 = st.columns(2)
        with col3:
            stop_loss = st.number_input(
                "Stop Loss",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                help="Set to 0 for no stop-loss",
            )
        with col4:
            take_profit = st.number_input(
                "Take Profit",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                help="Set to 0 for no take-profit",
            )

        tags_input = st.text_input(
            "Tags (comma-separated)", placeholder="swing, earnings, breakout"
        )
        comments = st.text_area("Comments", placeholder="Trade thesis, setup notes...")

        submitted = st.form_submit_button("➕ Create Trade", use_container_width=True)

        if submitted:
            if not ticker.strip():
                st.error("Ticker is required.")
                return None

            payload: dict[str, Any] = {
                "ticker": ticker.strip().upper(),
                "direction": direction,
                "asset_type": asset_type,
                "trade_type": trade_type,
                "timeframe": timeframe,
                "entry_date": entry_date.isoformat(),
                "entry_price": entry_price,
                "total_quantity": total_quantity,
            }

            if stop_loss and stop_loss > 0:
                payload["stop_loss"] = stop_loss
            if take_profit and take_profit > 0:
                payload["take_profit"] = take_profit

            tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
            if tags:
                payload["tags"] = tags
            if comments.strip():
                payload["comments"] = comments.strip()

            return payload

    return None


def render_edit_form(trade: dict[str, Any], key: str = "edit_trade") -> dict[str, Any] | None:
    """
    Render the trade-edit form (mutable fields only).

    Returns a dict with updated fields if submitted, or None.
    """
    with st.form(key=key, clear_on_submit=False):
        st.subheader("✏️ Edit Trade")

        col1, col2 = st.columns(2)
        with col1:
            stop_loss = st.number_input(
                "Stop Loss",
                min_value=0.0,
                value=float(trade.get("stop_loss") or 0.0),
                step=0.01,
                format="%.2f",
                help="Set to 0 to clear stop-loss",
            )
        with col2:
            take_profit = st.number_input(
                "Take Profit",
                min_value=0.0,
                value=float(trade.get("take_profit") or 0.0),
                step=0.01,
                format="%.2f",
                help="Set to 0 to clear take-profit",
            )

        timeframe = st.selectbox(
            "Timeframe",
            options=["daily", "weekly", "monthly", "quarterly"],
            index=["daily", "weekly", "monthly", "quarterly"].index(
                trade.get("timeframe", "daily")
            ),
        )

        current_tags = ", ".join(trade.get("tags") or [])
        tags_input = st.text_input("Tags (comma-separated)", value=current_tags)
        comments = st.text_area("Comments", value=trade.get("comments") or "")

        submitted = st.form_submit_button("💾 Save Changes", use_container_width=True)

        if submitted:
            payload: dict[str, Any] = {"timeframe": timeframe}

            if stop_loss and stop_loss > 0:
                payload["stop_loss"] = stop_loss
            # If was set and now is 0, pass None to clear it
            elif trade.get("stop_loss"):
                payload["stop_loss"] = None

            if take_profit and take_profit > 0:
                payload["take_profit"] = take_profit
            elif trade.get("take_profit"):
                payload["take_profit"] = None

            tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
            payload["tags"] = tags if tags else None
            payload["comments"] = comments.strip() if comments.strip() else None

            return payload

    return None


def render_exit_form(trade: dict[str, Any], key: str = "add_exit") -> dict[str, Any] | None:
    """
    Render the add-exit form.

    Returns a dict with exit fields if submitted, or None.
    """
    remaining = trade.get("remaining_quantity", 0)
    if remaining <= 0:
        st.info("This trade is fully closed — no more exits can be added.")
        return None

    with st.form(key=key, clear_on_submit=True):
        st.subheader("📤 Add Exit")
        st.caption(f"Remaining quantity: **{remaining:,.2f}**")

        col1, col2 = st.columns(2)
        with col1:
            exit_date = st.date_input("Exit Date", value=date.today())
            exit_price = st.number_input(
                "Exit Price *", min_value=0.01, value=100.00, step=0.01, format="%.2f"
            )
        with col2:
            quantity = st.number_input(
                "Quantity *",
                min_value=0.01,
                max_value=float(remaining),
                value=min(float(remaining), 100.0),
                step=1.0,
                format="%.2f",
            )
            exit_comments = st.text_input("Exit Comments", placeholder="Reason for exit...")

        submitted = st.form_submit_button("📤 Record Exit", use_container_width=True)

        if submitted:
            payload: dict[str, Any] = {
                "exit_date": exit_date.isoformat(),
                "exit_price": exit_price,
                "quantity": quantity,
            }
            if exit_comments.strip():
                payload["comments"] = exit_comments.strip()
            return payload

    return None


def render_leg_form(key: str = "add_leg") -> dict[str, Any] | None:
    """
    Render the add-option-leg form.

    Returns a dict with leg fields if submitted, or None.
    """
    with st.form(key=key, clear_on_submit=True):
        st.subheader("🦵 Add Option Leg")

        col1, col2 = st.columns(2)
        with col1:
            leg_type = st.selectbox(
                "Leg Type *",
                options=["buy_call", "sell_call", "buy_put", "sell_put"],
            )
            strike = st.number_input(
                "Strike *", min_value=0.01, value=100.00, step=0.50, format="%.2f"
            )
            expiry = st.date_input("Expiry *", value=date.today())
        with col2:
            quantity = st.number_input(
                "Contracts *", min_value=0.01, value=1.0, step=1.0, format="%.2f"
            )
            premium = st.number_input(
                "Premium per contract",
                value=0.00,
                step=0.01,
                format="%.2f",
                help="Positive = paid, negative = received (credit)",
            )

        submitted = st.form_submit_button("🦵 Add Leg", use_container_width=True)

        if submitted:
            return {
                "leg_type": leg_type,
                "strike": strike,
                "expiry": expiry.isoformat(),
                "quantity": quantity,
                "premium": premium,
            }

    return None
