"""
PraxiAlpha — Dashboard Page

Main trading dashboard with market overview and economic calendar.
"""

import streamlit as st

from streamlit_app.components.economic_calendar import render_economic_calendar_widget

st.header("📊 Dashboard")

# ---- Economic Calendar Widget ----
with st.expander("📅 Economic Calendar — Upcoming Events", expanded=True):
    tab_high, tab_all = st.tabs(["🔴 High Impact", "All Events"])

    with tab_high:
        render_economic_calendar_widget(
            days=7, importance=3, title="High-Impact Events (Next 7 Days)"
        )

    with tab_all:
        render_economic_calendar_widget(days=7, importance=None, title="All Events (Next 7 Days)")

st.divider()

# ---- Placeholder sections for future Phase 2 work ----
st.info("📈 **Market overview, charts, and portfolio widgets** are coming in Phase 2.")
