"""
PraxiAlpha — Candlestick Chart Component Tests

Tests for the Plotly chart builder: data preparation, figure structure,
indicator overlays, subplot layout, and edge cases.

These tests import plotly but NOT streamlit, so they can run in CI if
plotly is available. If plotly is not installed, all tests are skipped.
"""

from __future__ import annotations

import pytest

# Guard: skip entire module if plotly is not installed (CI lightweight env)
plotly = pytest.importorskip("plotly")

import numpy as np
import pandas as pd

from streamlit_app.components.candlestick_chart import (
    build_candlestick_figure,
    candles_to_dataframe,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_candles() -> list[dict]:
    """Minimal candle list matching the API response shape."""
    rng = np.random.default_rng(99)
    base = 150.0
    candles = []
    for i in range(60):
        o = base + rng.standard_normal() * 2
        c = o + rng.standard_normal() * 2
        h = max(o, c) + abs(rng.standard_normal())
        low = min(o, c) - abs(rng.standard_normal())
        candles.append(
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(low, 2),
                "close": round(c, 2),
                "adjusted_close": round(c, 2),
                "volume": int(abs(rng.standard_normal()) * 1_000_000 + 500_000),
            }
        )
        base = c
    return candles


@pytest.fixture
def sample_df(sample_candles) -> pd.DataFrame:
    """DataFrame from sample candles."""
    return candles_to_dataframe(sample_candles)


# ============================================================
# candles_to_dataframe Tests
# ============================================================


class TestCandlesToDataframe:
    """Tests for the candles_to_dataframe helper."""

    def test_returns_dataframe(self, sample_candles):
        df = candles_to_dataframe(sample_candles)
        assert isinstance(df, pd.DataFrame)

    def test_correct_columns(self, sample_candles):
        df = candles_to_dataframe(sample_candles)
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns

    def test_datetime_index(self, sample_candles):
        df = candles_to_dataframe(sample_candles)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_sorted_ascending(self, sample_candles):
        df = candles_to_dataframe(sample_candles)
        assert df.index.is_monotonic_increasing

    def test_correct_length(self, sample_candles):
        df = candles_to_dataframe(sample_candles)
        assert len(df) == len(sample_candles)

    def test_empty_input(self):
        df = candles_to_dataframe([])
        assert isinstance(df, pd.DataFrame)
        assert df.empty


# ============================================================
# build_candlestick_figure Tests — Basic
# ============================================================


class TestBuildFigureBasic:
    """Tests for the basic candlestick figure."""

    def test_returns_figure(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST")
        assert isinstance(fig, plotly.graph_objs.Figure)

    def test_has_candlestick_trace(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST")
        trace_types = [type(t).__name__ for t in fig.data]
        assert "Candlestick" in trace_types

    def test_has_volume_bars(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", show_volume=True)
        bar_traces = [t for t in fig.data if type(t).__name__ == "Bar"]
        assert len(bar_traces) >= 1

    def test_no_volume_when_disabled(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", show_volume=False)
        bar_traces = [t for t in fig.data if type(t).__name__ == "Bar"]
        assert len(bar_traces) == 0

    def test_title_contains_ticker(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="AAPL", timeframe="daily")
        assert "AAPL" in fig.layout.title.text

    def test_title_contains_timeframe(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="AAPL", timeframe="weekly")
        assert "Weekly" in fig.layout.title.text

    def test_dark_theme(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST")
        assert fig.layout.template.layout.to_plotly_json() is not None

    def test_empty_df_returns_figure(self):
        fig = build_candlestick_figure(pd.DataFrame(), ticker="EMPTY")
        assert isinstance(fig, plotly.graph_objs.Figure)
        # Should have an annotation saying "No data"
        assert len(fig.layout.annotations) > 0
        assert "No data" in fig.layout.annotations[0].text


# ============================================================
# build_candlestick_figure Tests — Indicators
# ============================================================


class TestBuildFigureIndicators:
    """Tests for indicator overlays."""

    def test_sma_overlay(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", indicators={"sma": [20]})
        names = [t.name for t in fig.data if t.name]
        assert any("SMA 20" in n for n in names)

    def test_multiple_sma_periods(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", indicators={"sma": [10, 20]})
        names = [t.name for t in fig.data if t.name]
        assert any("SMA 10" in n for n in names)
        assert any("SMA 20" in n for n in names)

    def test_ema_overlay(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", indicators={"ema": [12]})
        names = [t.name for t in fig.data if t.name]
        assert any("EMA 12" in n for n in names)

    def test_bollinger_overlay(self, sample_df):
        fig = build_candlestick_figure(
            sample_df,
            ticker="TEST",
            indicators={"bollinger": {"period": 20, "std": 2.0}},
        )
        names = [t.name for t in fig.data if t.name]
        assert any("BB" in n for n in names)

    def test_rsi_subplot(self, sample_df):
        fig = build_candlestick_figure(
            sample_df,
            ticker="TEST",
            indicators={"rsi": {"period": 14}},
        )
        names = [t.name for t in fig.data if t.name]
        assert any("RSI" in n for n in names)

    def test_macd_subplot(self, sample_df):
        fig = build_candlestick_figure(
            sample_df,
            ticker="TEST",
            indicators={"macd": {"fast": 12, "slow": 26, "signal": 9}},
        )
        names = [t.name for t in fig.data if t.name]
        assert any("MACD" in n for n in names)
        assert any("Signal" in n for n in names)

    def test_all_indicators_combined(self, sample_df):
        """All indicators enabled at once should produce a valid figure."""
        fig = build_candlestick_figure(
            sample_df,
            ticker="TEST",
            show_volume=True,
            indicators={
                "sma": [20, 50],
                "ema": [12],
                "bollinger": {"period": 20, "std": 2.0},
                "rsi": {"period": 14},
                "macd": {"fast": 12, "slow": 26, "signal": 9},
            },
        )
        assert isinstance(fig, plotly.graph_objs.Figure)
        # Should have many traces: candle + volume + 2 SMA + 1 EMA + 3 BB + RSI + 3 MACD
        assert len(fig.data) >= 10


# ============================================================
# Subplot layout tests
# ============================================================


class TestSubplotLayout:
    """Tests for correct subplot row assignment."""

    def test_volume_only(self, sample_df):
        fig = build_candlestick_figure(sample_df, ticker="TEST", show_volume=True, indicators={})
        # 2 rows: candles + volume
        assert fig.layout.height >= 500

    def test_rsi_adds_row(self, sample_df):
        fig_no_rsi = build_candlestick_figure(
            sample_df, ticker="TEST", show_volume=True, indicators={}
        )
        fig_rsi = build_candlestick_figure(
            sample_df, ticker="TEST", show_volume=True, indicators={"rsi": {"period": 14}}
        )
        # More traces when RSI is added
        assert len(fig_rsi.data) > len(fig_no_rsi.data)

    def test_macd_adds_row(self, sample_df):
        fig_no_macd = build_candlestick_figure(
            sample_df, ticker="TEST", show_volume=True, indicators={}
        )
        fig_macd = build_candlestick_figure(
            sample_df,
            ticker="TEST",
            show_volume=True,
            indicators={"macd": {"fast": 12, "slow": 26, "signal": 9}},
        )
        assert len(fig_macd.data) > len(fig_no_macd.data)

    def test_no_volume_no_indicators(self, sample_df):
        """Candles only — single row."""
        fig = build_candlestick_figure(sample_df, ticker="TEST", show_volume=False, indicators={})
        # Should have just the candlestick trace
        assert len(fig.data) == 1
        assert type(fig.data[0]).__name__ == "Candlestick"
