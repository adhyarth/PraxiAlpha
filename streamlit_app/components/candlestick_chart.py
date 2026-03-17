"""
PraxiAlpha — Candlestick Chart Component

Builds interactive Plotly candlestick charts with:
- Volume subplot (bar chart below the candles)
- Technical indicator overlays (SMA, EMA, RSI, MACD, Bollinger Bands)
- Timeframe label in the chart title (selection is handled by the Streamlit page)
- Responsive layout with dark theme

This module produces a ``plotly.graph_objects.Figure`` and has NO Streamlit
dependency — it can be used from any Python context (Streamlit, Jupyter,
FastAPI response, etc.).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.services.analysis.technical_indicators import (
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)

# ============================================================
# Color palette
# ============================================================

COLORS = {
    "bull": "#26a69a",  # green candle
    "bear": "#ef5350",  # red candle
    "volume_bull": "rgba(38, 166, 154, 0.4)",
    "volume_bear": "rgba(239, 83, 80, 0.4)",
    "sma": "#ff9800",  # orange
    "ema": "#2196f3",  # blue
    "bb_middle": "#9c27b0",  # purple
    "bb_band": "rgba(156, 39, 176, 0.15)",  # purple fill
    "bb_line": "rgba(156, 39, 176, 0.4)",  # purple line
    "macd_line": "#2196f3",  # blue
    "macd_signal": "#ff9800",  # orange
    "macd_hist_pos": "rgba(38, 166, 154, 0.6)",
    "macd_hist_neg": "rgba(239, 83, 80, 0.6)",
    "rsi_line": "#7c4dff",  # deep purple
    "rsi_overbought": "rgba(239, 83, 80, 0.3)",
    "rsi_oversold": "rgba(38, 166, 154, 0.3)",
    "bg": "#131722",  # TradingView dark bg
    "grid": "#1e222d",
    "text": "#d1d4dc",
}


# ============================================================
# Data preparation
# ============================================================


def candles_to_dataframe(candles: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Convert the candle list from the API/service into a DataFrame.

    Expects each dict to have: date, open, high, low, close, volume.
    Returns a DataFrame with a DatetimeIndex.
    """
    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


# ============================================================
# Figure builders
# ============================================================


def build_candlestick_figure(
    df: pd.DataFrame,
    ticker: str = "",
    timeframe: str = "daily",
    *,
    show_volume: bool = True,
    indicators: dict[str, Any] | None = None,
) -> go.Figure:
    """
    Build an interactive Plotly candlestick chart.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame with DatetimeIndex and columns:
        open, high, low, close, volume (and optionally adjusted_close).
    ticker : str
        Stock ticker symbol for the title.
    timeframe : str
        Timeframe label (daily, weekly, monthly, quarterly).
    show_volume : bool
        Whether to include a volume subplot (default True).
    indicators : dict
        Which indicators to overlay. Keys and expected values:

        - ``"sma"`` → list of periods, e.g. ``[20, 50, 200]``
        - ``"ema"`` → list of periods, e.g. ``[12, 26]``
        - ``"bollinger"`` → dict with ``"period"`` and ``"std"``
          e.g. ``{"period": 20, "std": 2.0}``
        - ``"rsi"`` → dict with ``"period"``, e.g. ``{"period": 14}``
        - ``"macd"`` → dict with ``"fast"``, ``"slow"``, ``"signal"``
          e.g. ``{"fast": 12, "slow": 26, "signal": 9}``

    Returns
    -------
    go.Figure
        A fully configured Plotly figure ready for display.
    """
    if df.empty:
        return _empty_figure(ticker)

    indicators = indicators or {}

    # Determine subplot layout
    has_rsi = "rsi" in indicators
    has_macd = "macd" in indicators

    n_rows = 1
    row_heights = [0.6]
    subplot_titles: list[str] = [""]

    if show_volume:
        n_rows += 1
        row_heights.append(0.15)
        subplot_titles.append("Volume")

    if has_rsi:
        n_rows += 1
        row_heights.append(0.12)
        subplot_titles.append("RSI")

    if has_macd:
        n_rows += 1
        row_heights.append(0.13)
        subplot_titles.append("MACD")

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # --- Row 1: Candlestick ---
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            increasing_line_color=COLORS["bull"],
            decreasing_line_color=COLORS["bear"],
            increasing_fillcolor=COLORS["bull"],
            decreasing_fillcolor=COLORS["bear"],
            name="OHLC",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # --- Indicator overlays on row 1 ---
    _add_ma_overlays(fig, df, indicators)
    _add_bollinger_overlay(fig, df, indicators)

    # Track which row we're on for bottom panels
    current_row = 2

    # --- Volume subplot ---
    if show_volume:
        _add_volume_bars(fig, df, current_row)
        current_row += 1

    # --- RSI subplot ---
    if has_rsi:
        rsi_config = indicators["rsi"]
        period = rsi_config.get("period", 14) if isinstance(rsi_config, dict) else 14
        _add_rsi_panel(fig, df, period, current_row)
        current_row += 1

    # --- MACD subplot ---
    if has_macd:
        macd_config = indicators["macd"]
        if isinstance(macd_config, dict):
            fast = macd_config.get("fast", 12)
            slow = macd_config.get("slow", 26)
            signal = macd_config.get("signal", 9)
        else:
            fast, slow, signal = 12, 26, 9
        _add_macd_panel(fig, df, fast, slow, signal, current_row)
        current_row += 1

    # --- Layout ---
    title = f"{ticker.upper()} — {timeframe.capitalize()}" if ticker else timeframe.capitalize()
    _apply_layout(fig, title, n_rows)

    return fig


# ============================================================
# Overlay helpers
# ============================================================

# SMA color cycle for multiple periods
_MA_COLORS = ["#ff9800", "#2196f3", "#e91e63", "#4caf50", "#ffeb3b", "#00bcd4"]


def _add_ma_overlays(
    fig: go.Figure,
    df: pd.DataFrame,
    indicators: dict[str, Any],
) -> None:
    """Add SMA and EMA lines to row 1."""
    close = df["close"]

    for i, period in enumerate(indicators.get("sma", [])):
        values = sma(close, period=period)
        color = _MA_COLORS[i % len(_MA_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=values,
                mode="lines",
                name=f"SMA {period}",
                line={"color": color, "width": 1.2},
                hovertemplate=f"SMA {period}: %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    for i, period in enumerate(indicators.get("ema", [])):
        values = ema(close, period=period)
        color = _MA_COLORS[(i + len(indicators.get("sma", []))) % len(_MA_COLORS)]
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=values,
                mode="lines",
                name=f"EMA {period}",
                line={"color": color, "width": 1.2, "dash": "dash"},
                hovertemplate=f"EMA {period}: %{{y:.2f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )


def _add_bollinger_overlay(
    fig: go.Figure,
    df: pd.DataFrame,
    indicators: dict[str, Any],
) -> None:
    """Add Bollinger Bands to row 1."""
    if "bollinger" not in indicators:
        return

    config = indicators["bollinger"]
    period = config.get("period", 20) if isinstance(config, dict) else 20
    num_std = config.get("std", 2.0) if isinstance(config, dict) else 2.0

    bb = bollinger_bands(df["close"], period=period, num_std=num_std)

    # Upper band line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=bb["upper_band"],
            mode="lines",
            name=f"BB Upper ({period}, {num_std}σ)",
            line={"color": COLORS["bb_line"], "width": 1},
            showlegend=False,
            hovertemplate="BB Upper: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Lower band line (with fill to upper)
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=bb["lower_band"],
            mode="lines",
            name=f"BB Lower ({period}, {num_std}σ)",
            line={"color": COLORS["bb_line"], "width": 1},
            fill="tonexty",
            fillcolor=COLORS["bb_band"],
            showlegend=False,
            hovertemplate="BB Lower: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Middle band
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=bb["middle_band"],
            mode="lines",
            name=f"BB ({period}, {num_std}σ)",
            line={"color": COLORS["bb_middle"], "width": 1, "dash": "dot"},
            hovertemplate="BB Middle: %{y:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _add_volume_bars(fig: go.Figure, df: pd.DataFrame, row: int) -> None:
    """Add colored volume bars."""
    colors = [
        COLORS["volume_bull"] if c >= o else COLORS["volume_bear"]
        for c, o in zip(df["close"], df["open"], strict=True)
    ]

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["volume"],
            marker_color=colors,
            name="Volume",
            showlegend=False,
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
        ),
        row=row,
        col=1,
    )


def _add_rsi_panel(fig: go.Figure, df: pd.DataFrame, period: int, row: int) -> None:
    """Add RSI line with overbought/oversold bands."""
    rsi_values = rsi(df["close"], period=period)

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=rsi_values,
            mode="lines",
            name=f"RSI ({period})",
            line={"color": COLORS["rsi_line"], "width": 1.5},
            hovertemplate=f"RSI({period}): %{{y:.1f}}<extra></extra>",
        ),
        row=row,
        col=1,
    )

    # Overbought / oversold reference lines
    for level, color, label in [
        (70, COLORS["rsi_overbought"], "Overbought"),
        (30, COLORS["rsi_oversold"], "Oversold"),
    ]:
        fig.add_hline(
            y=level,
            line_dash="dot",
            line_color=color,
            line_width=1,
            annotation_text=label,
            annotation_position="right",
            row=row,
            col=1,
        )

    # Fix RSI y-axis range
    fig.update_yaxes(range=[0, 100], row=row, col=1)


def _add_macd_panel(
    fig: go.Figure,
    df: pd.DataFrame,
    fast: int,
    slow: int,
    signal: int,
    row: int,
) -> None:
    """Add MACD line, signal line, and histogram."""
    macd_df = macd(df["close"], fast_period=fast, slow_period=slow, signal_period=signal)

    # Histogram
    hist_colors = [
        COLORS["macd_hist_pos"] if v >= 0 else COLORS["macd_hist_neg"] for v in macd_df["histogram"]
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=macd_df["histogram"],
            marker_color=hist_colors,
            name="MACD Hist",
            showlegend=False,
            hovertemplate="Hist: %{y:.4f}<extra></extra>",
        ),
        row=row,
        col=1,
    )

    # MACD line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=macd_df["macd_line"],
            mode="lines",
            name=f"MACD ({fast},{slow})",
            line={"color": COLORS["macd_line"], "width": 1.5},
            hovertemplate=f"MACD({fast},{slow}): %{{y:.4f}}<extra></extra>",
        ),
        row=row,
        col=1,
    )

    # Signal line
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=macd_df["signal_line"],
            mode="lines",
            name=f"Signal ({signal})",
            line={"color": COLORS["macd_signal"], "width": 1.5, "dash": "dash"},
            hovertemplate=f"Signal({signal}): %{{y:.4f}}<extra></extra>",
        ),
        row=row,
        col=1,
    )

    # Zero line
    fig.add_hline(y=0, line_dash="dot", line_color="#555", line_width=0.5, row=row, col=1)


# ============================================================
# Layout
# ============================================================


def _apply_layout(fig: go.Figure, title: str, n_rows: int) -> None:
    """Apply dark theme and TradingView-style layout."""
    fig.update_layout(
        title={
            "text": title,
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 16, "color": COLORS["text"]},
        },
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font={"color": COLORS["text"], "size": 11},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 10},
        },
        margin={"l": 60, "r": 30, "t": 60, "b": 30},
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        height=max(500, 200 + n_rows * 150),
    )

    # Style all axes
    axis_style = {
        "gridcolor": COLORS["grid"],
        "zerolinecolor": COLORS["grid"],
        "showgrid": True,
    }
    fig.update_xaxes(**axis_style)
    fig.update_yaxes(**axis_style)


def _empty_figure(ticker: str) -> go.Figure:
    """Return a placeholder figure when no data is available."""
    fig = go.Figure()
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        font={"color": COLORS["text"]},
        annotations=[
            {
                "text": f"No data available for {ticker.upper()}"
                if ticker
                else "No data available",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 18, "color": COLORS["text"]},
            }
        ],
        height=400,
    )
    return fig
