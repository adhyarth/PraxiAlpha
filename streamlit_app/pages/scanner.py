"""
PraxiAlpha — Strategy Lab Scanner Page

Streamlit page for the Pattern Scanner + Forward Returns Analyzer.
Provides a condition form builder (sliders, dropdowns) for candle shape,
volume, and RSI conditions. Runs the scanner engine and displays summary
statistics and per-signal detail tables.

See ``docs/STRATEGY_LAB.md`` §6 for the UI wireframe.
"""

from __future__ import annotations

import asyncio
import logging

import pandas as pd
import streamlit as st

from backend.database import async_session_factory
from backend.services.scanner_service import (
    ScanCondition,
    ScannerService,
    ScanRequest,
    ScanResult,
    SignalResult,
)

logger = logging.getLogger(__name__)


# ============================================================
# Helper functions (must be defined before Streamlit rendering)
# ============================================================


def _fmt_pct(value: float | None) -> str:
    """Format a percentage value for display."""
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _sort_key(col: pd.Series) -> pd.Series:
    """Extract numeric sort keys from formatted string columns."""
    return col.apply(_parse_sortable)


def _parse_sortable(val):  # type: ignore[no-untyped-def]
    """Parse a formatted value into a sortable number."""
    if isinstance(val, (int, float)):
        return val
    if not isinstance(val, str):
        return 0
    # Strip formatting: $, %, x, commas, +
    cleaned = (
        val.replace("$", "")
        .replace("%", "")
        .replace(",", "")
        .replace("x", "")
        .replace("+", "")
        .strip()
    )
    if cleaned == "—" or cleaned == "":
        return float("nan")
    try:
        return float(cleaned)
    except ValueError:
        return 0


def _render_signal_detail(sig: SignalResult) -> None:
    """Render the expandable detail for a single signal."""
    # Signal candle info
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Open", f"${sig.open:,.2f}")
    with col2:
        st.metric("High", f"${sig.high:,.2f}")
    with col3:
        st.metric("Low", f"${sig.low:,.2f}")
    with col4:
        st.metric("Volume", f"{sig.volume:,}")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Body %", f"{sig.body_pct:.1f}%")
    with col6:
        st.metric("Upper Wick %", f"{sig.upper_wick_pct:.1f}%")
    with col7:
        st.metric("Lower Wick %", f"{sig.lower_wick_pct:.1f}%")
    with col8:
        st.metric("Vol vs Avg", f"{sig.volume_vs_avg:.1f}x" if sig.volume_vs_avg is not None else "—")

    # Forward returns table
    if sig.forward_returns:
        fwd_rows = []
        for fr in sig.forward_returns:
            fwd_rows.append(
                {
                    "Window": fr.window_label,
                    "Close": f"${fr.close_price:,.2f}" if fr.close_price is not None else "—",
                    "Return %": _fmt_pct(fr.return_pct),
                    "Max Drawdown %": _fmt_pct(fr.max_drawdown_pct),
                    "Max Surge %": _fmt_pct(fr.max_surge_pct),
                }
            )
        st.dataframe(
            pd.DataFrame(fwd_rows),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# Page header
# ============================================================

st.header("🔬 Strategy Lab — Pattern Scanner")
st.markdown(
    "Define candle pattern conditions, scan historical data, and analyze "
    "forward returns. Tweak thresholds and re-run for rapid strategy iteration."
)

# ============================================================
# Persistent event loop (same pattern as validation page)
# ============================================================


@st.cache_resource
def _get_persistent_loop() -> asyncio.AbstractEventLoop:
    """Return a single long-lived event loop running in a daemon thread."""
    import threading

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine on the persistent background loop."""
    loop = _get_persistent_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=300)  # 5-min timeout for large scans


# ============================================================
# Scan configuration form
# ============================================================

with st.expander("ℹ️ How it works", expanded=False):
    st.markdown("""
**1.** Configure scan conditions below (defaults = bearish reversal candle).
**2.** Click **🔍 Run Scan** to search historical quarterly candles across all ETFs.
**3.** View summary statistics and per-signal detail tables.
**4.** Tweak thresholds and re-run for rapid iteration.

**V1 scope:** Quarterly timeframe, ETF universe only.

**Note on RSI:** RSI(14) is computed on quarterly closes — each "period" is one quarter,
so 14 periods ≈ 3.5 years. This is much smoother than daily RSI(14). A quarterly RSI of 70+
signals a strong multi-year uptrend, not just a short-term overbought condition.

See [`docs/STRATEGY_LAB.md`](../docs/STRATEGY_LAB.md) for full design.
    """)

st.subheader("Scan Configuration")

# ---- Row 1: Timeframe, Universe, Candle Color ----
col_tf, col_univ, col_color = st.columns(3)

with col_tf:
    timeframe = st.selectbox(
        "Timeframe",
        options=["quarterly"],
        index=0,
        help="V1 supports quarterly only. Weekly/monthly coming in Session 33.",
    )

with col_univ:
    universe = st.selectbox(
        "Universe",
        options=["etf"],
        format_func=lambda x: "ETFs" if x == "etf" else x.upper(),
        index=0,
        help="V1 scans all active, non-delisted ETFs (~5,300 tickers).",
    )

with col_color:
    candle_color = st.selectbox(
        "Candle Color",
        options=["red", "green", "any"],
        format_func=lambda x: {
            "red": "🔴 Red (bearish)",
            "green": "🟢 Green (bullish)",
            "any": "⚪ Any",
        }[x],
        index=0,
        help="Red = close < open (bearish). Green = close > open (bullish). Any = no color filter.",
    )

st.divider()

# ---- Price Shape Conditions ----
st.markdown("**Price Shape**")
col_body, col_upper, col_lower = st.columns(3)

with col_body:
    body_pct_enabled = st.checkbox("Body % filter", value=True)
    body_pct_op = st.selectbox(
        "Body operator", options=["<=", ">=", "<", ">"], index=0, key="body_op"
    )
    body_pct_val = st.slider(
        "Body %",
        min_value=0.0,
        max_value=50.0,
        value=2.0,
        step=0.5,
        help="Body size as % of open price. Small body = indecision/reversal.",
    )

with col_upper:
    upper_wick_enabled = st.checkbox("Upper wick % filter", value=True)
    upper_wick_op = st.selectbox(
        "Upper wick operator", options=[">=", "<=", ">", "<"], index=0, key="upper_op"
    )
    upper_wick_val = st.slider(
        "Upper wick %",
        min_value=0.0,
        max_value=50.0,
        value=10.0,
        step=0.5,
        help="Upper wick as % of max(open, close). Large upper wick = rejection at highs.",
    )

with col_lower:
    lower_wick_enabled = st.checkbox("Lower wick % filter", value=True)
    lower_wick_op = st.selectbox(
        "Lower wick operator", options=["<=", ">=", "<", ">"], index=0, key="lower_op"
    )
    lower_wick_val = st.slider(
        "Lower wick %",
        min_value=0.0,
        max_value=50.0,
        value=2.0,
        step=0.5,
        help="Lower wick as % of min(open, close). Small lower wick = no buying support.",
    )

st.divider()

# ---- Volume Condition ----
st.markdown("**Volume**")
col_vol_enable, col_vol_mult, col_vol_lb = st.columns(3)

with col_vol_enable:
    volume_enabled = st.checkbox("Volume filter", value=True)

with col_vol_mult:
    volume_multiplier = st.number_input(
        "Volume > Nx avg",
        min_value=0.1,
        max_value=10.0,
        value=1.0,
        step=0.1,
        help="Volume must exceed this multiple of the rolling average.",
    )

with col_vol_lb:
    volume_lookback = st.number_input(
        "Lookback periods",
        min_value=1,
        max_value=20,
        value=2,
        step=1,
        help="Number of prior candles for the rolling volume average.",
    )

st.divider()

# ---- Indicator Conditions ----
st.markdown("**Indicators**")
col_rsi_enable, col_rsi_op, col_rsi_val = st.columns(3)

with col_rsi_enable:
    rsi_enabled = st.checkbox("RSI(14) filter", value=True)

with col_rsi_op:
    rsi_op = st.selectbox("RSI operator", options=[">=", "<=", ">", "<"], index=0, key="rsi_op")

with col_rsi_val:
    rsi_val = st.slider(
        "RSI(14) threshold",
        min_value=0,
        max_value=100,
        value=70,
        step=1,
        help="RSI(14) computed on **quarterly** closes (14 quarters ≈ 3.5 years). "
        "This is NOT daily RSI — quarterly RSI 70+ signals strong multi-year uptrend.",
    )

st.divider()

# ---- Forward Windows ----
st.markdown("**Forward Return Windows**")
forward_windows = st.multiselect(
    "Quarter offsets to compute",
    options=[1, 2, 3, 4, 5, 6, 7, 8],
    default=[1, 2, 3, 4, 5],
    help="Which future quarters to compute returns for (Q+1 through Q+8).",
)

if not forward_windows:
    st.warning("Select at least one forward window.")
    st.stop()


# ============================================================
# Build conditions list from form state
# ============================================================


def _build_conditions() -> list[ScanCondition]:
    """Convert UI form state into a list of ScanCondition objects."""
    conditions: list[ScanCondition] = []

    if body_pct_enabled:
        # Scanner uses fractional (0.02), but slider shows percentage (2.0)
        conditions.append(
            ScanCondition(field="body_pct", operator=body_pct_op, value=body_pct_val / 100)
        )

    if upper_wick_enabled:
        conditions.append(
            ScanCondition(
                field="upper_wick_pct", operator=upper_wick_op, value=upper_wick_val / 100
            )
        )

    if lower_wick_enabled:
        conditions.append(
            ScanCondition(
                field="lower_wick_pct", operator=lower_wick_op, value=lower_wick_val / 100
            )
        )

    if volume_enabled:
        conditions.append(
            ScanCondition(
                field="volume_vs_avg",
                operator=">",
                value=volume_multiplier,
                extra={"lookback": volume_lookback},
            )
        )

    if rsi_enabled:
        conditions.append(ScanCondition(field="rsi_14", operator=rsi_op, value=float(rsi_val)))

    return conditions


# ============================================================
# Run scan
# ============================================================


async def _execute_scan(
    request: ScanRequest,
    progress_callback=None,  # type: ignore[no-untyped-def]
) -> ScanResult:
    """Execute the scan using a fresh DB session."""
    async with async_session_factory() as session:
        scanner = ScannerService(session)
        return await scanner.run_scan(request, progress_callback=progress_callback)


if st.button("🔍 Run Scan", type="primary", use_container_width=True):
    conditions = _build_conditions()

    if not conditions and candle_color == "any":
        st.warning(
            "No conditions set and candle color is 'any'. Add at least one filter to avoid scanning every candle."
        )
        st.stop()

    request = ScanRequest(
        timeframe=timeframe,
        conditions=conditions,
        universe=universe,
        forward_windows=sorted(forward_windows),
        candle_color=candle_color,
    )

    # ---- Show active conditions ----
    with st.expander("📋 Active conditions", expanded=False):
        for c in conditions:
            extra_str = f" (lookback={c.extra['lookback']})" if c.extra else ""
            st.text(f"  {c.field} {c.operator} {c.value}{extra_str}")
        st.text(f"  candle_color = {candle_color}")
        st.text(f"  timeframe = {timeframe}, universe = {universe}")
        st.text(f"  forward_windows = {sorted(forward_windows)}")

    # ---- Execute with spinner ----
    # Note: progress_callback cannot update Streamlit widgets from the
    # background event-loop thread (NoSessionContext error).  We use a
    # simple st.spinner() instead — the scan runs ~5,300 ETFs sequentially.
    try:
        with st.spinner("🔍 Scanning ~5,300 ETFs… this may take 1–3 minutes."):
            result: ScanResult = _run_async(_execute_scan(request, None))
        st.success(f"✅ Scan complete in {result.scan_duration_seconds:.1f}s")
    except Exception as e:
        st.error(f"❌ Scan failed: {e}")
        logger.exception("Scanner page: scan failed")
        st.stop()

    # ============================================================
    # Display results
    # ============================================================

    st.divider()

    # ---- Summary header ----
    st.subheader("Summary")

    summary = result.summary
    col_sig, col_tick, col_range, col_time = st.columns(4)
    with col_sig:
        st.metric("Signals", summary.total_signals)
    with col_tick:
        st.metric("Unique Tickers", summary.unique_tickers)
    with col_range:
        st.metric("Date Range", summary.date_range or "—")
    with col_time:
        st.metric("Scan Time", f"{result.scan_duration_seconds:.1f}s")

    # ---- Win rate context ----
    if candle_color == "red":
        st.caption(
            "📉 Win rate = % of signals where price went **down** (bearish thesis — puts profitable)"
        )
    elif candle_color == "green":
        st.caption(
            "📈 Win rate = % of signals where price went **up** (bullish thesis — calls profitable)"
        )
    else:
        st.caption("⚪ Win rate not computed for 'any' candle color (direction ambiguous)")

    # ---- Summary table ----
    if summary.per_window:
        summary_rows = []
        for ws in summary.per_window:
            summary_rows.append(
                {
                    "Window": ws.window_label,
                    "Mean Return %": _fmt_pct(ws.mean_return_pct),
                    "Median Return %": _fmt_pct(ws.median_return_pct),
                    "Win Rate %": _fmt_pct(ws.win_rate_pct),
                    "Avg Drawdown %": _fmt_pct(ws.mean_max_drawdown_pct),
                    "Avg Surge %": _fmt_pct(ws.mean_max_surge_pct),
                    "Signals": ws.signal_count,
                }
            )
        summary_df = pd.DataFrame(summary_rows)
        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
        )
    elif summary.total_signals == 0:
        st.info(
            "No signals found. Try loosening the conditions (e.g., lower RSI threshold, increase body %)."
        )

    # ---- Signal details ----
    st.divider()
    st.subheader("Signal Details")

    if not result.signals:
        st.info("No signals to display.")
    else:
        # Build a flat detail DataFrame for the main table
        detail_rows = []
        for sig in result.signals:
            row = {
                "Ticker": sig.ticker,
                "Date": sig.signal_date,
                "Close": f"${sig.close:,.2f}",
                "RSI(14)": f"{sig.rsi_14:.1f}" if sig.rsi_14 is not None else "—",
                "Body %": f"{sig.body_pct:.1f}%",
                "Upper Wick %": f"{sig.upper_wick_pct:.1f}%",
                "Lower Wick %": f"{sig.lower_wick_pct:.1f}%",
                "Vol vs Avg": f"{sig.volume_vs_avg:.1f}x" if sig.volume_vs_avg is not None else "—",
            }
            # Add forward return columns
            for fr in sig.forward_returns:
                row[fr.window_label] = _fmt_pct(fr.return_pct)
            detail_rows.append(row)

        detail_df = pd.DataFrame(detail_rows)

        # Sort controls
        sort_col = st.selectbox(
            "Sort by",
            options=detail_df.columns.tolist(),
            index=0,
            key="sort_col",
        )
        sort_asc = st.checkbox("Ascending", value=True, key="sort_asc")

        # Sort — handle columns that are formatted strings by extracting numeric values
        # Use numeric sort key only for columns that contain numeric/formatted-numeric data;
        # fall back to normal lexicographic/date sorting for string columns like Ticker/Date.
        series = detail_df[sort_col]
        use_numeric_key = False
        if pd.api.types.is_numeric_dtype(series):
            use_numeric_key = True
        elif series.dtype == object:
            # Work with a small non-missing sample, treating display dashes as missing
            sample = (
                series.astype(str)
                .replace("—", pd.NA)
                .dropna()
                .head(10)
            )
            if not sample.empty:
                # If most sample values parse as datetimes, treat as date-like, not numeric
                parsed_dates = pd.to_datetime(sample, errors="coerce")
                date_fraction = float(parsed_dates.notna().mean())
                if date_fraction < 0.8:
                    # Not date-like: check if values look like formatted numbers ($, %, x, +/-)
                    cleaned = sample.str.replace(r"[^\d\.\+\-]", "", regex=True)
                    numeric_coerced = pd.to_numeric(cleaned, errors="coerce")
                    numeric_fraction = float(numeric_coerced.notna().mean())
                    if numeric_fraction >= 0.8:
                        use_numeric_key = True

        try:
            if use_numeric_key:
                detail_df_sorted = detail_df.sort_values(
                    by=sort_col,
                    ascending=sort_asc,
                    key=lambda col: _sort_key(col),
                )
            else:
                detail_df_sorted = detail_df.sort_values(by=sort_col, ascending=sort_asc)
        except Exception:
            detail_df_sorted = detail_df.sort_values(by=sort_col, ascending=sort_asc)

        st.dataframe(
            detail_df_sorted,
            use_container_width=True,
            hide_index=True,
            height=min(len(detail_df_sorted) * 38 + 40, 600),
        )

        # ---- Expandable per-signal detail ----
        st.divider()
        st.subheader("Per-Signal Forward Returns")
        st.caption(
            "Expand a signal to see full forward return breakdown including drawdown and surge."
        )

        for sig in result.signals:
            label = f"{sig.ticker} — {sig.signal_date} (close: ${sig.close:,.2f}, RSI: {sig.rsi_14 if sig.rsi_14 is not None else '—'})"
            with st.expander(label):
                _render_signal_detail(sig)
