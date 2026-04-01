"""
PraxiAlpha — Strategy Lab Scanner UI Tests

Tests for:
- scanner.py — helper functions (_fmt_pct, _parse_sortable, _build_conditions)
- ScanCondition building from form state
- Display formatting and sort key extraction

All tests mock Streamlit and DB — no real backend or browser needed in CI.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Provide a real Streamlit import if available; otherwise, install a
# lightweight stub so these tests can run in CI without the full
# Streamlit dependency.
try:
    import streamlit as st  # type: ignore[import-not-found]
except ImportError:

    class _StopError(Exception):
        """Raised by st.stop() to halt page-level code during import."""

    class _StreamlitStub(types.ModuleType):
        """Minimal Streamlit stub for CI.

        Widget APIs return safe defaults so that page-level code
        (which runs at import time) can execute without crashing:
        - ``columns(n)`` → list of *n* MagicMock context managers
        - ``button(...)`` → ``False`` (never pressed)
        - ``checkbox(...)`` → the *value* kwarg if given, else ``False``
        - ``selectbox(...)`` → first item of *options* if given
        - ``slider(...)`` → the *value* kwarg if given, else ``0``
        - ``number_input(...)`` → the *value* kwarg if given, else ``0``
        - ``multiselect(...)`` → the *default* kwarg if given, else ``[]``
        - ``stop()`` → raises ``_StopStub``
        - ``cache_resource`` → identity decorator
        - Everything else → ``MagicMock``
        """

        def __getattr__(self, name: str):  # type: ignore[override]
            # Widget helpers that must return specific types
            if name == "columns":
                return self._columns
            if name == "button":
                return lambda *a, **kw: False
            if name == "checkbox":
                return lambda *a, **kw: kw.get("value", False)
            if name == "selectbox":
                return self._selectbox
            if name == "slider":
                return lambda *a, **kw: kw.get("value", 0)
            if name == "number_input":
                return lambda *a, **kw: kw.get("value", 0)
            if name == "multiselect":
                return lambda *a, **kw: kw.get("default", [])
            if name == "stop":
                return self._stop
            if name == "cache_resource":
                return lambda fn: fn  # identity decorator
            if name == "expander":
                return self._expander
            return MagicMock(name=f"st.{name}")

        @staticmethod
        def _columns(n, **kw):  # type: ignore[no-untyped-def]
            """Return a list of n MagicMock context managers."""
            cols = []
            for _ in range(n if isinstance(n, int) else len(n)):
                m = MagicMock()
                m.__enter__ = MagicMock(return_value=m)
                m.__exit__ = MagicMock(return_value=False)
                # Widgets inside a column should also return safe defaults
                m.selectbox = lambda *a, **kw: (  # noqa: E731
                    kw["options"][kw.get("index", 0)]
                    if "options" in kw and kw["options"]
                    else MagicMock()
                )
                m.checkbox = lambda *a, **kw: kw.get("value", False)  # noqa: E731
                m.slider = lambda *a, **kw: kw.get("value", 0)  # noqa: E731
                m.number_input = lambda *a, **kw: kw.get("value", 0)  # noqa: E731
                cols.append(m)
            return cols

        @staticmethod
        def _selectbox(*args, **kwargs):  # type: ignore[no-untyped-def]
            options = kwargs.get("options", [])
            index = kwargs.get("index", 0)
            if options and 0 <= index < len(options):
                return options[index]
            return MagicMock()

        @staticmethod
        def _stop():  # type: ignore[no-untyped-def]
            raise _StopError("st.stop()")

        @staticmethod
        def _expander(*args, **kwargs):  # type: ignore[no-untyped-def]
            m = MagicMock()
            m.__enter__ = MagicMock(return_value=m)
            m.__exit__ = MagicMock(return_value=False)
            return m

    st = _StreamlitStub("streamlit")  # type: ignore[assignment]
    sys.modules["streamlit"] = st


# ============================================================
# Helpers — import the formatting functions directly
# ============================================================


def _get_fmt_pct():
    """Import _fmt_pct from the scanner page module."""
    from streamlit_app.pages.scanner import _fmt_pct

    return _fmt_pct


def _get_parse_sortable():
    """Import _parse_sortable from the scanner page module."""
    from streamlit_app.pages.scanner import _parse_sortable

    return _parse_sortable


def _get_sort_key():
    """Import _sort_key from the scanner page module."""
    from streamlit_app.pages.scanner import _sort_key

    return _sort_key


# ============================================================
# Test: _fmt_pct
# ============================================================


class TestFmtPct:
    """Test percentage formatting helper."""

    def test_positive_value(self):
        fmt = _get_fmt_pct()
        assert fmt(5.25) == "+5.25%"

    def test_negative_value(self):
        fmt = _get_fmt_pct()
        assert fmt(-3.14) == "-3.14%"

    def test_zero_value(self):
        fmt = _get_fmt_pct()
        assert fmt(0.0) == "0.00%"

    def test_none_value(self):
        fmt = _get_fmt_pct()
        assert fmt(None) == "—"

    def test_large_positive(self):
        fmt = _get_fmt_pct()
        assert fmt(123.45) == "+123.45%"

    def test_small_negative(self):
        fmt = _get_fmt_pct()
        assert fmt(-0.01) == "-0.01%"

    def test_exact_zero(self):
        fmt = _get_fmt_pct()
        # 0.0 should not get a "+" prefix
        result = fmt(0.0)
        assert result.startswith("0") or result.startswith("-")
        assert "+" not in result


# ============================================================
# Test: _parse_sortable
# ============================================================


class TestParseSortable:
    """Test sort key extraction from formatted display strings."""

    def test_dollar_value(self):
        parse = _get_parse_sortable()
        assert parse("$248.12") == 248.12

    def test_dollar_with_comma(self):
        parse = _get_parse_sortable()
        assert parse("$1,234.56") == 1234.56

    def test_percentage_positive(self):
        parse = _get_parse_sortable()
        assert parse("+5.25%") == 5.25

    def test_percentage_negative(self):
        parse = _get_parse_sortable()
        assert parse("-3.14%") == -3.14

    def test_multiplier(self):
        parse = _get_parse_sortable()
        assert parse("2.5x") == 2.5

    def test_dash(self):
        parse = _get_parse_sortable()
        import math

        assert math.isnan(parse("—"))

    def test_empty_string(self):
        parse = _get_parse_sortable()
        import math

        assert math.isnan(parse(""))

    def test_numeric_int(self):
        parse = _get_parse_sortable()
        assert parse(42) == 42

    def test_numeric_float(self):
        parse = _get_parse_sortable()
        assert parse(3.14) == 3.14

    def test_non_numeric_string(self):
        parse = _get_parse_sortable()
        assert parse("SMH") == 0

    def test_none_value(self):
        parse = _get_parse_sortable()
        assert parse(None) == 0


# ============================================================
# Test: _sort_key
# ============================================================


class TestSortKey:
    """Test the pandas Series sort key function."""

    def test_sort_key_series(self):
        sort_key = _get_sort_key()
        series = pd.Series(["$100.00", "$50.00", "$200.00"])
        result = sort_key(series)
        assert result.tolist() == [100.0, 50.0, 200.0]

    def test_sort_key_with_dashes(self):
        sort_key = _get_sort_key()
        series = pd.Series(["+5.25%", "—", "-3.14%"])
        result = sort_key(series)
        assert result.iloc[0] == 5.25
        assert result.iloc[2] == -3.14
        # Dash → NaN
        import math

        assert math.isnan(result.iloc[1])


# ============================================================
# Test: ScanCondition building
# ============================================================


class TestBuildConditions:
    """Test that the _build_conditions function correctly translates UI state."""

    def test_all_conditions_enabled(self):
        """When all checkboxes are on, all 5 conditions are created."""

        # Simulate the UI state by importing and calling _build_conditions
        # with mocked module-level variables
        import streamlit_app.pages.scanner as scanner_mod

        # Save originals
        orig = {}
        fields = [
            "body_pct_enabled",
            "body_pct_op",
            "body_pct_val",
            "upper_wick_enabled",
            "upper_wick_op",
            "upper_wick_val",
            "lower_wick_enabled",
            "lower_wick_op",
            "lower_wick_val",
            "volume_enabled",
            "volume_multiplier",
            "volume_lookback",
            "rsi_enabled",
            "rsi_op",
            "rsi_val",
        ]
        for f in fields:
            orig[f] = getattr(scanner_mod, f, None)

        try:
            # Set all enabled
            scanner_mod.body_pct_enabled = True
            scanner_mod.body_pct_op = "<="
            scanner_mod.body_pct_val = 2.0
            scanner_mod.upper_wick_enabled = True
            scanner_mod.upper_wick_op = ">="
            scanner_mod.upper_wick_val = 10.0
            scanner_mod.lower_wick_enabled = True
            scanner_mod.lower_wick_op = "<="
            scanner_mod.lower_wick_val = 2.0
            scanner_mod.volume_enabled = True
            scanner_mod.volume_multiplier = 1.0
            scanner_mod.volume_lookback = 2
            scanner_mod.rsi_enabled = True
            scanner_mod.rsi_op = ">="
            scanner_mod.rsi_val = 70

            conditions = scanner_mod._build_conditions()
            assert len(conditions) == 5

            # Verify fields
            field_names = [c.field for c in conditions]
            assert "body_pct" in field_names
            assert "upper_wick_pct" in field_names
            assert "lower_wick_pct" in field_names
            assert "volume_vs_avg" in field_names
            assert "rsi_14" in field_names

            # Body pct should be converted from percentage to fraction
            body_cond = next(c for c in conditions if c.field == "body_pct")
            assert body_cond.value == pytest.approx(0.02)
            assert body_cond.operator == "<="

            # Volume should have lookback in extra
            vol_cond = next(c for c in conditions if c.field == "volume_vs_avg")
            assert vol_cond.extra == {"lookback": 2}
            assert vol_cond.operator == ">"

            # RSI should be raw value (not divided)
            rsi_cond = next(c for c in conditions if c.field == "rsi_14")
            assert rsi_cond.value == 70.0
        finally:
            # Restore originals
            for f, v in orig.items():
                if v is not None:
                    setattr(scanner_mod, f, v)

    def test_no_conditions_enabled(self):
        """When all checkboxes are off, no conditions are created."""
        import streamlit_app.pages.scanner as scanner_mod

        orig = {}
        fields = [
            "body_pct_enabled",
            "upper_wick_enabled",
            "lower_wick_enabled",
            "volume_enabled",
            "rsi_enabled",
        ]
        for f in fields:
            orig[f] = getattr(scanner_mod, f, None)

        try:
            scanner_mod.body_pct_enabled = False
            scanner_mod.upper_wick_enabled = False
            scanner_mod.lower_wick_enabled = False
            scanner_mod.volume_enabled = False
            scanner_mod.rsi_enabled = False

            conditions = scanner_mod._build_conditions()
            assert len(conditions) == 0
        finally:
            for f, v in orig.items():
                if v is not None:
                    setattr(scanner_mod, f, v)

    def test_partial_conditions(self):
        """Only enabled conditions are included."""
        import streamlit_app.pages.scanner as scanner_mod

        orig = {}
        fields = [
            "body_pct_enabled",
            "body_pct_op",
            "body_pct_val",
            "upper_wick_enabled",
            "lower_wick_enabled",
            "volume_enabled",
            "rsi_enabled",
            "rsi_op",
            "rsi_val",
        ]
        for f in fields:
            orig[f] = getattr(scanner_mod, f, None)

        try:
            scanner_mod.body_pct_enabled = True
            scanner_mod.body_pct_op = "<="
            scanner_mod.body_pct_val = 5.0
            scanner_mod.upper_wick_enabled = False
            scanner_mod.lower_wick_enabled = False
            scanner_mod.volume_enabled = False
            scanner_mod.rsi_enabled = True
            scanner_mod.rsi_op = ">="
            scanner_mod.rsi_val = 65

            conditions = scanner_mod._build_conditions()
            assert len(conditions) == 2
            assert conditions[0].field == "body_pct"
            assert conditions[0].value == pytest.approx(0.05)
            assert conditions[1].field == "rsi_14"
            assert conditions[1].value == 65.0
        finally:
            for f, v in orig.items():
                if v is not None:
                    setattr(scanner_mod, f, v)

    def test_wick_percentage_conversion(self):
        """Wick values are converted from display % to fractional."""
        import streamlit_app.pages.scanner as scanner_mod

        orig = {}
        fields = [
            "body_pct_enabled",
            "upper_wick_enabled",
            "upper_wick_op",
            "upper_wick_val",
            "lower_wick_enabled",
            "lower_wick_op",
            "lower_wick_val",
            "volume_enabled",
            "rsi_enabled",
        ]
        for f in fields:
            orig[f] = getattr(scanner_mod, f, None)

        try:
            scanner_mod.body_pct_enabled = False
            scanner_mod.upper_wick_enabled = True
            scanner_mod.upper_wick_op = ">="
            scanner_mod.upper_wick_val = 15.0  # 15% in UI
            scanner_mod.lower_wick_enabled = True
            scanner_mod.lower_wick_op = "<="
            scanner_mod.lower_wick_val = 3.0  # 3% in UI
            scanner_mod.volume_enabled = False
            scanner_mod.rsi_enabled = False

            conditions = scanner_mod._build_conditions()
            assert len(conditions) == 2

            upper = next(c for c in conditions if c.field == "upper_wick_pct")
            assert upper.value == pytest.approx(0.15)

            lower = next(c for c in conditions if c.field == "lower_wick_pct")
            assert lower.value == pytest.approx(0.03)
        finally:
            for f, v in orig.items():
                if v is not None:
                    setattr(scanner_mod, f, v)


# ============================================================
# Test: _render_signal_detail (doesn't crash with valid data)
# ============================================================


class TestRenderSignalDetail:
    """Test that signal detail rendering doesn't crash."""

    @patch("streamlit_app.pages.scanner.st")
    def test_render_with_forward_returns(self, mock_st):
        """Rendering a signal with forward returns doesn't raise."""
        from backend.services.scanner_service import ForwardReturn, SignalResult
        from streamlit_app.pages.scanner import _render_signal_detail

        # Mock st.columns to return context managers
        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        sig = SignalResult(
            ticker="SMH",
            signal_date="2024-09-30",
            open=248.0,
            high=260.0,
            low=245.0,
            close=248.12,
            volume=5000000,
            rsi_14=79.7,
            body_pct=5.0,
            upper_wick_pct=4.8,
            lower_wick_pct=1.2,
            volume_vs_avg=1.5,
            forward_returns=[
                ForwardReturn(
                    window=1,
                    window_label="Q+1",
                    close_price=233.0,
                    return_pct=-6.1,
                    max_drawdown_pct=-8.2,
                    max_surge_pct=2.1,
                ),
                ForwardReturn(
                    window=2,
                    window_label="Q+2",
                    close_price=220.0,
                    return_pct=-11.3,
                    max_drawdown_pct=-14.5,
                    max_surge_pct=3.0,
                ),
            ],
        )

        # Should not raise
        _render_signal_detail(sig)

    @patch("streamlit_app.pages.scanner.st")
    def test_render_with_null_forward_returns(self, mock_st):
        """Rendering a signal with null forward return values doesn't raise."""
        from backend.services.scanner_service import ForwardReturn, SignalResult
        from streamlit_app.pages.scanner import _render_signal_detail

        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        sig = SignalResult(
            ticker="QQQ",
            signal_date="2025-12-31",
            open=400.0,
            high=410.0,
            low=395.0,
            close=398.0,
            volume=3000000,
            rsi_14=None,
            body_pct=50.0,
            upper_wick_pct=3.0,
            lower_wick_pct=0.75,
            volume_vs_avg=None,
            forward_returns=[
                ForwardReturn(window=1, window_label="Q+1"),  # all None
            ],
        )

        _render_signal_detail(sig)

    @patch("streamlit_app.pages.scanner.st")
    def test_render_with_no_forward_returns(self, mock_st):
        """Rendering a signal with empty forward returns list doesn't raise."""
        from backend.services.scanner_service import SignalResult
        from streamlit_app.pages.scanner import _render_signal_detail

        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        sig = SignalResult(
            ticker="XBI",
            signal_date="2021-03-31",
            open=142.0,
            high=148.0,
            low=140.0,
            close=142.3,
            volume=2000000,
            rsi_14=71.2,
            body_pct=20.0,
            upper_wick_pct=4.0,
            lower_wick_pct=1.4,
            volume_vs_avg=1.8,
            forward_returns=[],
        )

        _render_signal_detail(sig)


# ============================================================
# Test: Edge cases for display
# ============================================================


class TestDisplayEdgeCases:
    """Test edge cases in display formatting."""

    def test_fmt_pct_very_small_positive(self):
        """Very small positive value gets + prefix."""
        fmt = _get_fmt_pct()
        assert fmt(0.001) == "+0.00%"

    def test_fmt_pct_very_small_negative(self):
        """Very small negative value gets - prefix."""
        fmt = _get_fmt_pct()
        assert fmt(-0.001) == "-0.00%"

    def test_parse_sortable_percentage_no_sign(self):
        """Percentage without sign parses correctly."""
        parse = _get_parse_sortable()
        assert parse("0.00%") == 0.0

    def test_parse_sortable_just_dollar(self):
        """Edge case: just $ with nothing."""
        parse = _get_parse_sortable()
        import math

        assert math.isnan(parse("$"))


# ============================================================
# Test: ScanRequest construction
# ============================================================


class TestScanRequestConstruction:
    """Test that ScanRequest objects are built correctly for the UI flow."""

    def test_default_request(self):
        """Default bearish reversal request has correct structure."""
        from backend.services.scanner_service import ScanCondition, ScanRequest

        conditions = [
            ScanCondition(field="body_pct", operator="<=", value=0.02),
            ScanCondition(field="upper_wick_pct", operator=">=", value=0.10),
            ScanCondition(field="lower_wick_pct", operator="<=", value=0.02),
            ScanCondition(field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": 2}),
            ScanCondition(field="rsi_14", operator=">=", value=70.0),
        ]

        request = ScanRequest(
            timeframe="quarterly",
            conditions=conditions,
            universe="etf",
            forward_windows=[1, 2, 3, 4, 5],
            candle_color="red",
        )

        assert request.timeframe == "quarterly"
        assert request.universe == "etf"
        assert request.candle_color == "red"
        assert len(request.conditions) == 5
        assert request.forward_windows == [1, 2, 3, 4, 5]

    def test_green_candle_request(self):
        """Green (bullish) candle request is valid."""
        from backend.services.scanner_service import ScanRequest

        request = ScanRequest(
            timeframe="quarterly",
            conditions=[],
            universe="etf",
            forward_windows=[1, 2, 3],
            candle_color="green",
        )
        assert request.candle_color == "green"
        assert request.forward_windows == [1, 2, 3]

    def test_any_color_request(self):
        """Any-color request is valid."""
        from backend.services.scanner_service import ScanRequest

        request = ScanRequest(
            timeframe="quarterly",
            conditions=[],
            universe="etf",
            forward_windows=[1],
            candle_color="any",
        )
        assert request.candle_color == "any"


# ============================================================
# Test: WindowSummary display formatting
# ============================================================


class TestWindowSummaryDisplay:
    """Test that WindowSummary data formats correctly for the UI."""

    def test_summary_row_formatting(self):
        """Summary rows are built correctly from WindowSummary objects."""
        from backend.services.scanner_service import WindowSummary

        fmt = _get_fmt_pct()

        ws = WindowSummary(
            window=1,
            window_label="Q+1",
            mean_return_pct=-4.2,
            median_return_pct=-3.8,
            win_rate_pct=62.0,
            mean_max_drawdown_pct=-8.1,
            mean_max_surge_pct=3.5,
            signal_count=47,
        )

        row = {
            "Window": ws.window_label,
            "Mean Return %": fmt(ws.mean_return_pct),
            "Median Return %": fmt(ws.median_return_pct),
            "Win Rate %": fmt(ws.win_rate_pct),
            "Avg Drawdown %": fmt(ws.mean_max_drawdown_pct),
            "Avg Surge %": fmt(ws.mean_max_surge_pct),
            "Signals": ws.signal_count,
        }

        assert row["Window"] == "Q+1"
        assert row["Mean Return %"] == "-4.20%"
        assert row["Median Return %"] == "-3.80%"
        assert row["Win Rate %"] == "+62.00%"
        assert row["Avg Drawdown %"] == "-8.10%"
        assert row["Avg Surge %"] == "+3.50%"
        assert row["Signals"] == 47

    def test_summary_row_with_nulls(self):
        """Summary rows handle None values gracefully."""
        from backend.services.scanner_service import WindowSummary

        fmt = _get_fmt_pct()

        ws = WindowSummary(
            window=5,
            window_label="Q+5",
            mean_return_pct=None,
            median_return_pct=None,
            win_rate_pct=None,
            mean_max_drawdown_pct=None,
            mean_max_surge_pct=None,
            signal_count=0,
        )

        assert fmt(ws.mean_return_pct) == "—"
        assert fmt(ws.win_rate_pct) == "—"
        assert ws.signal_count == 0


# ============================================================
# Test: SignalResult display formatting
# ============================================================


class TestSignalResultDisplay:
    """Test that SignalResult data formats correctly for the detail table."""

    def test_signal_row_formatting(self):
        """Detail row is built correctly from a SignalResult."""
        from backend.services.scanner_service import ForwardReturn, SignalResult

        fmt = _get_fmt_pct()

        sig = SignalResult(
            ticker="SMH",
            signal_date="2024-09-30",
            open=248.0,
            high=260.0,
            low=245.0,
            close=248.12,
            volume=5000000,
            rsi_14=79.7,
            body_pct=5.0,
            upper_wick_pct=4.8,
            lower_wick_pct=1.2,
            volume_vs_avg=1.5,
            forward_returns=[
                ForwardReturn(
                    window=1,
                    window_label="Q+1",
                    close_price=233.0,
                    return_pct=-6.1,
                    max_drawdown_pct=-8.2,
                    max_surge_pct=2.1,
                ),
            ],
        )

        row = {
            "Ticker": sig.ticker,
            "Date": sig.signal_date,
            "Close": f"${sig.close:,.2f}",
            "RSI(14)": f"{sig.rsi_14:.1f}",
            "Body %": f"{sig.body_pct:.1f}%",
        }

        assert row["Ticker"] == "SMH"
        assert row["Date"] == "2024-09-30"
        assert row["Close"] == "$248.12"
        assert row["RSI(14)"] == "79.7"
        assert row["Body %"] == "5.0%"

        # Forward return column
        assert fmt(sig.forward_returns[0].return_pct) == "-6.10%"

    def test_signal_with_none_rsi(self):
        """Signal with None RSI formats as dash."""
        from backend.services.scanner_service import SignalResult

        sig = SignalResult(
            ticker="TEST",
            signal_date="2024-01-01",
            open=100.0,
            high=105.0,
            low=95.0,
            close=98.0,
            volume=1000000,
            rsi_14=None,
            body_pct=2.0,
            upper_wick_pct=5.0,
            lower_wick_pct=3.0,
            volume_vs_avg=None,
        )

        rsi_display = f"{sig.rsi_14:.1f}" if sig.rsi_14 is not None else "—"
        vol_display = f"{sig.volume_vs_avg:.1f}x" if sig.volume_vs_avg is not None else "—"

        assert rsi_display == "—"
        assert vol_display == "—"
