"""
PraxiAlpha — Charts Page

Interactive candlestick charting with technical indicator overlays.
Fetches candle data from the FastAPI backend and renders via Plotly.
"""

import os
from typing import Any

import streamlit as st

from streamlit_app.components.candlestick_chart import (
    build_candlestick_figure,
    candles_to_dataframe,
)

# ============================================================
# Helper functions (defined before use in the Streamlit script)
# ============================================================


def _parse_periods(text: str) -> list[int]:
    """Parse a comma-separated list of integers."""
    periods = []
    for part in text.split(","):
        part = part.strip()
        if part.isdigit() and int(part) >= 1:
            periods.append(int(part))
    return periods


def _fetch_candles(tk: str, tf: str, lim: int) -> dict[str, Any] | None:
    """Fetch candle data from the FastAPI backend."""
    try:
        import httpx

        base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
        url = f"{base_url}/api/v1/charts/{tk}/candles"
        params: dict[str, str | int] = {"timeframe": tf, "limit": lim}

        response = httpx.get(url, params=params, timeout=10)
        if response.status_code == 200:
            result: dict[str, Any] = response.json()
            return result
        elif response.status_code == 404:
            st.error(f"Ticker **{tk}** not found in the database.")
        else:
            st.error(f"API error: {response.status_code}")
    except Exception as e:
        st.error(f"Could not connect to the backend: {e}")
    return None


# ============================================================
# Page header
# ============================================================

st.header("📈 Charts")

# ============================================================
# Sidebar controls
# ============================================================

with st.sidebar:
    st.subheader("Chart Settings")

    ticker = (
        st.text_input(
            "Ticker",
            value="AAPL",
            max_chars=10,
            help="Enter a stock ticker symbol (e.g. AAPL, MSFT, TSLA)",
        )
        .strip()
        .upper()
    )

    timeframe = st.selectbox(
        "Timeframe",
        options=["daily", "weekly", "monthly", "quarterly"],
        index=0,
    )

    limit = st.slider(
        "Number of candles",
        min_value=50,
        max_value=2000,
        value=252,
        step=50,
        help="Number of most recent candles to display",
    )

    show_volume = st.checkbox("Show Volume", value=True)

    st.divider()
    st.subheader("Indicators")

    # --- Moving Averages ---
    show_sma = st.checkbox("SMA (Simple Moving Average)", value=False)
    sma_periods: list[int] = []
    if show_sma:
        sma_input = st.text_input("SMA Periods (comma-separated)", value="20, 50, 200")
        sma_periods = _parse_periods(sma_input)

    show_ema = st.checkbox("EMA (Exponential Moving Average)", value=False)
    ema_periods: list[int] = []
    if show_ema:
        ema_input = st.text_input("EMA Periods (comma-separated)", value="12, 26")
        ema_periods = _parse_periods(ema_input)

    # --- Bollinger Bands ---
    show_bb = st.checkbox("Bollinger Bands", value=False)
    bb_period = 20
    bb_std = 2.0
    if show_bb:
        bb_period = st.number_input("BB Period", min_value=2, max_value=200, value=20)
        bb_std = st.number_input("BB Std Dev", min_value=0.5, max_value=5.0, value=2.0, step=0.5)

    # --- RSI ---
    show_rsi = st.checkbox("RSI", value=False)
    rsi_period = 14
    if show_rsi:
        rsi_period = st.number_input("RSI Period", min_value=2, max_value=100, value=14)

    # --- MACD ---
    show_macd = st.checkbox("MACD", value=False)
    macd_fast, macd_slow, macd_signal = 12, 26, 9
    if show_macd:
        macd_fast = st.number_input("MACD Fast", min_value=2, max_value=100, value=12)
        macd_slow = st.number_input("MACD Slow", min_value=2, max_value=200, value=26)
        macd_signal = st.number_input("MACD Signal", min_value=2, max_value=100, value=9)


# ============================================================
# Build indicator config from sidebar selections
# ============================================================


def _build_indicators() -> dict[str, Any]:
    """Build the indicator config dict from sidebar state."""
    indicators: dict[str, Any] = {}

    if show_sma and sma_periods:
        indicators["sma"] = sma_periods
    if show_ema and ema_periods:
        indicators["ema"] = ema_periods
    if show_bb:
        indicators["bollinger"] = {"period": bb_period, "std": bb_std}
    if show_rsi:
        indicators["rsi"] = {"period": rsi_period}
    if show_macd:
        indicators["macd"] = {"fast": macd_fast, "slow": macd_slow, "signal": macd_signal}

    return indicators


# ============================================================
# Main chart rendering
# ============================================================

if not ticker:
    st.info("Enter a ticker symbol in the sidebar to get started.")
else:
    with st.spinner(f"Loading {ticker} {timeframe} data..."):
        data = _fetch_candles(ticker, timeframe, limit)

    if data and data.get("candles"):
        # Info bar
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Ticker", data["ticker"])
        with col2:
            st.metric("Timeframe", data["timeframe"].capitalize())
        with col3:
            st.metric("Candles", f"{data['count']:,}")

        # Build chart
        df = candles_to_dataframe(data["candles"])
        indicators = _build_indicators()

        fig = build_candlestick_figure(
            df,
            ticker=data.get("ticker", ticker),
            timeframe=data.get("timeframe", timeframe),
            show_volume=show_volume,
            indicators=indicators,
        )

        st.plotly_chart(fig, use_container_width=True)

        # Price summary
        if not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            change = latest["close"] - prev["close"]
            pct = (change / prev["close"]) * 100 if prev["close"] != 0 else 0

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Close", f"${latest['close']:.2f}", f"{change:+.2f} ({pct:+.2f}%)")
            with c2:
                st.metric("Open", f"${latest['open']:.2f}")
            with c3:
                st.metric("High", f"${latest['high']:.2f}")
            with c4:
                st.metric("Low", f"${latest['low']:.2f}")

    elif data and not data.get("candles"):
        st.warning(f"No candle data found for **{ticker}** in the **{timeframe}** timeframe.")
