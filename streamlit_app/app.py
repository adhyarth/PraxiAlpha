"""
PraxiAlpha — Streamlit MVP Dashboard

This is the main entry point for the Streamlit MVP dashboard.
Used for Phases 2-7 before migrating to React.
"""

import streamlit as st

st.set_page_config(
    page_title="PraxiAlpha",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🎯 PraxiAlpha")
st.markdown("*Disciplined action that generates alpha.*")

st.divider()

st.success(
    "**Phase 2 in progress** — Charting & dashboard features are coming online. "
    "Use the sidebar to navigate to Charts or Dashboard."
)

# Sidebar
with st.sidebar:
    st.header("Navigation")
    st.markdown("""
    - 📊 [Dashboard](/Dashboard)
    - 📈 [Charts](/Charts) ✨ *New*
    - 📋 Reports *(Phase 3)*
    - 🔍 Screener *(Phase 3)*
    - 🧪 Backtesting *(Phase 4)*
    - 🎓 Education *(Phase 5)*
    - 📝 Journal *(Phase 7)*
    - 📉 Performance *(Phase 7)*
    - ⚡ Trading *(Phase 7)*
    - 🛡️ Risk *(Phase 7)*
    """)

    st.divider()
    st.caption("PraxiAlpha v0.2.0 — Phase 2")
