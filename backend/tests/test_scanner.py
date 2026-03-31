"""
PraxiAlpha — Scanner Service Tests

Comprehensive unit tests for the Strategy Lab scanner engine.
All tests use small, deterministic datasets — no database required.
Mock the DB layer (CandleService + universe queries) so tests run
in milliseconds.

Test categories:
1. Data classes & validation
2. Universe resolution
3. Per-ticker enrichment (derived columns)
4. Condition filtering
5. Forward return computation
6. Summary aggregation
7. Full run_scan integration
8. Edge cases
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.services.scanner_service import (
    _OPERATORS,
    _VALID_FIELDS,
    ForwardReturn,
    ScanCondition,
    ScannerService,
    ScanRequest,
    ScanResult,
    SignalResult,
    WindowSummary,
)

# ============================================================
# Helpers — build synthetic candle data
# ============================================================


def _make_quarterly_candles(
    n: int = 20,
    *,
    base_close: float = 100.0,
    trend: float = 1.0,
    start_year: int = 2020,
) -> list[dict]:
    """
    Generate ``n`` synthetic quarterly candles.

    Each candle is a dict matching the CandleService.get_candles() output.
    Prices trend up by ``trend`` per quarter from ``base_close``.
    """
    candles = []
    quarters = ["01-01", "04-01", "07-01", "10-01"]
    for i in range(n):
        year = start_year + i // 4
        q = i % 4
        date_str = f"{year}-{quarters[q]}"
        c = base_close + i * trend
        candles.append(
            {
                "date": date_str,
                "open": round(c + 2, 4),
                "high": round(c + 15, 4),
                "low": round(c - 3, 4),
                "close": round(c, 4),
                "adjusted_close": round(c, 4),
                "volume": 1_000_000 + i * 100_000,
                "trading_days": 63,
            }
        )
    return candles


def _make_bearish_reversal_candle(
    date_str: str = "2024-07-01",
    *,
    open_: float = 100.5,
    close: float = 100.0,
    high: float = 115.0,
    low: float = 99.5,
    volume: int = 5_000_000,
) -> dict:
    """Create a single candle that looks like a bearish reversal (doji + huge wick)."""
    return {
        "date": date_str,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "adjusted_close": close,
        "volume": volume,
        "trading_days": 63,
    }


def _make_universe_result(tickers: list[tuple[int, str]]) -> MagicMock:
    """Mock the universe query result."""
    rows = []
    for stock_id, ticker in tickers:
        row = MagicMock()
        row.id = stock_id
        row.ticker = ticker
        rows.append(row)
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


# ============================================================
# 1. Data Classes & Operators
# ============================================================


class TestDataClasses:
    """Sanity checks on data classes and constants."""

    def test_scan_condition_defaults(self):
        cond = ScanCondition(field="body_pct", operator="<=", value=0.02)
        assert cond.extra is None

    def test_scan_condition_with_extra(self):
        cond = ScanCondition(field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": 3})
        assert cond.extra == {"lookback": 3}

    def test_scan_request_defaults(self):
        req = ScanRequest()
        assert req.timeframe == "quarterly"
        assert req.universe == "etf"
        assert req.candle_color == "red"
        assert req.forward_windows == [1, 2, 3, 4, 5]
        assert req.conditions == []

    def test_forward_return_null(self):
        fr = ForwardReturn(window=3, window_label="Q+3")
        assert fr.return_pct is None
        assert fr.close_price is None

    def test_operators_complete(self):
        assert set(_OPERATORS.keys()) == {"<=", ">=", "<", ">", "=="}

    def test_valid_fields(self):
        expected = {
            "body_pct",
            "upper_wick_pct",
            "lower_wick_pct",
            "volume_vs_avg",
            "rsi_14",
            "full_range_pct",
        }
        assert expected == _VALID_FIELDS

    def test_scan_result_defaults(self):
        result = ScanResult()
        assert result.signals == []
        assert result.scan_duration_seconds == 0.0

    def test_window_summary_defaults(self):
        ws = WindowSummary(window=1, window_label="Q+1")
        assert ws.signal_count == 0
        assert ws.mean_return_pct is None


# ============================================================
# 2. Request Validation
# ============================================================


class TestValidation:
    """Test ScannerService._validate_request."""

    def test_valid_request(self):
        req = ScanRequest()
        ScannerService._validate_request(req)  # should not raise

    def test_invalid_timeframe(self):
        req = ScanRequest(timeframe="daily")
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            ScannerService._validate_request(req)

    def test_invalid_universe(self):
        req = ScanRequest(universe="all")
        with pytest.raises(ValueError, match="Unsupported universe"):
            ScannerService._validate_request(req)

    def test_invalid_candle_color(self):
        req = ScanRequest(candle_color="blue")
        with pytest.raises(ValueError, match="Invalid candle_color"):
            ScannerService._validate_request(req)

    def test_empty_forward_windows(self):
        req = ScanRequest(forward_windows=[])
        with pytest.raises(ValueError, match="forward_windows must not be empty"):
            ScannerService._validate_request(req)

    def test_negative_forward_window(self):
        req = ScanRequest(forward_windows=[1, -1])
        with pytest.raises(ValueError, match="Forward window must be >= 1"):
            ScannerService._validate_request(req)


# ============================================================
# 3. Universe Resolution
# ============================================================


class TestUniverseResolution:
    """Test ScannerService.resolve_universe."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        return ScannerService(mock_session)

    @pytest.mark.asyncio
    async def test_etf_universe(self, service, mock_session):
        mock_session.execute.return_value = _make_universe_result(
            [(1, "SPY"), (2, "QQQ"), (3, "IWM")]
        )
        result = await service.resolve_universe("etf")
        assert result == [(1, "SPY"), (2, "QQQ"), (3, "IWM")]

    @pytest.mark.asyncio
    async def test_etf_universe_empty(self, service, mock_session):
        mock_session.execute.return_value = _make_universe_result([])
        result = await service.resolve_universe("etf")
        assert result == []

    @pytest.mark.asyncio
    async def test_unsupported_universe_raises(self, service):
        with pytest.raises(ValueError, match="Unsupported universe"):
            await service.resolve_universe("all")


# ============================================================
# 4. Per-Ticker Enrichment (Derived Columns)
# ============================================================


class TestEnrichment:
    """Test _fetch_and_enrich_ticker derived column computation."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        return ScannerService(mock_session)

    @pytest.mark.asyncio
    async def test_derived_columns_exist(self, service):
        candles = _make_quarterly_candles(20)
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "SPY", "quarterly", req)

        assert df is not None
        for col in (
            "body_pct",
            "upper_wick_pct",
            "lower_wick_pct",
            "full_range_pct",
            "volume_vs_avg",
            "rsi_14",
            "ticker",
        ):
            assert col in df.columns

    @pytest.mark.asyncio
    async def test_body_pct_calculation(self, service):
        candles = [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 105.0,
                "adjusted_close": 105.0,
                "volume": 1_000_000,
                "trading_days": 63,
            },
            {
                "date": "2024-04-01",
                "open": 200.0,
                "high": 220.0,
                "low": 190.0,
                "close": 210.0,
                "adjusted_close": 210.0,
                "volume": 1_500_000,
                "trading_days": 63,
            },
        ]
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "TEST", "quarterly", req)

        assert df is not None
        # body_pct = abs(close - open) / open
        # First candle: abs(105 - 100) / 100 = 0.05
        assert abs(df.iloc[0]["body_pct"] - 0.05) < 1e-6

    @pytest.mark.asyncio
    async def test_upper_wick_pct_calculation(self, service):
        # open=100, close=101 (green), high=120
        # max(open, close) = 101, upper_wick = (120 - 101) / 101 ≈ 0.1881
        candles = [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 120.0,
                "low": 98.0,
                "close": 101.0,
                "adjusted_close": 101.0,
                "volume": 1_000_000,
                "trading_days": 63,
            },
            {
                "date": "2024-04-01",
                "open": 102.0,
                "high": 125.0,
                "low": 100.0,
                "close": 103.0,
                "adjusted_close": 103.0,
                "volume": 1_200_000,
                "trading_days": 63,
            },
        ]
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "TEST", "quarterly", req)

        assert df is not None
        expected = (120.0 - 101.0) / 101.0
        assert abs(df.iloc[0]["upper_wick_pct"] - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_lower_wick_pct_calculation(self, service):
        # open=100, close=98 (red), low=90
        # min(open, close) = 98, lower_wick = (98 - 90) / 98 ≈ 0.08163
        candles = [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 105.0,
                "low": 90.0,
                "close": 98.0,
                "adjusted_close": 98.0,
                "volume": 1_000_000,
                "trading_days": 63,
            },
            {
                "date": "2024-04-01",
                "open": 99.0,
                "high": 106.0,
                "low": 88.0,
                "close": 97.0,
                "adjusted_close": 97.0,
                "volume": 1_200_000,
                "trading_days": 63,
            },
        ]
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "TEST", "quarterly", req)

        assert df is not None
        expected = (98.0 - 90.0) / 98.0
        assert abs(df.iloc[0]["lower_wick_pct"] - expected) < 1e-6

    @pytest.mark.asyncio
    async def test_rsi_computed_for_sufficient_data(self, service):
        candles = _make_quarterly_candles(20)
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "SPY", "quarterly", req)

        assert df is not None
        # RSI should be non-NaN after period warmup
        rsi_values = df["rsi_14"].dropna()
        assert len(rsi_values) > 0
        # RSI should be 0–100
        assert rsi_values.between(0, 100).all()

    @pytest.mark.asyncio
    async def test_empty_candles_returns_none(self, service):
        with patch.object(service._candle_service, "get_candles", return_value=[]):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "EMPTY", "quarterly", req)
        assert df is None

    @pytest.mark.asyncio
    async def test_single_candle_returns_none(self, service):
        candles = _make_quarterly_candles(1)
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest()
            df = await service._fetch_and_enrich_ticker(1, "ONE", "quarterly", req)
        assert df is None

    @pytest.mark.asyncio
    async def test_volume_lookback_from_condition(self, service):
        """Volume lookback should come from condition extra if provided."""
        candles = _make_quarterly_candles(10)
        with patch.object(service._candle_service, "get_candles", return_value=candles):
            req = ScanRequest(
                conditions=[
                    ScanCondition(
                        field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": 4}
                    )
                ]
            )
            df = await service._fetch_and_enrich_ticker(1, "TEST", "quarterly", req)

        assert df is not None
        assert "volume_vs_avg" in df.columns


# ============================================================
# 5. Condition Filtering
# ============================================================


class TestConditionFiltering:
    """Test _apply_conditions."""

    @pytest.fixture
    def service(self):
        return ScannerService(AsyncMock())

    def _make_df(self) -> pd.DataFrame:
        """Create a small DataFrame simulating enriched candle data."""
        return pd.DataFrame(
            {
                "ticker": ["SPY"] * 5,
                "date": ["2024-01-01", "2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01"],
                "open": [100.0, 102.0, 99.0, 101.0, 103.0],
                "close": [99.0, 103.0, 98.0, 100.5, 104.0],  # rows 0,2 = red
                "high": [115.0, 105.0, 112.0, 108.0, 106.0],
                "low": [98.5, 100.0, 97.5, 99.0, 102.0],
                "volume": [5e6, 3e6, 4e6, 2e6, 6e6],
                "body_pct": [0.01, 0.0098, 0.0101, 0.005, 0.0097],
                "upper_wick_pct": [0.16, 0.019, 0.14, 0.075, 0.019],
                "lower_wick_pct": [0.005, 0.020, 0.005, 0.015, 0.010],
                "volume_vs_avg": [1.5, 0.8, 1.2, 0.7, 1.8],
                "rsi_14": [75.0, 55.0, 72.0, 60.0, 80.0],
                "full_range_pct": [0.17, 0.05, 0.15, 0.09, 0.04],
            }
        )

    def test_red_candle_filter(self, service):
        df = self._make_df()
        req = ScanRequest(candle_color="red", conditions=[])
        result = service._apply_conditions(df, req)
        # Rows 0 (99 < 100), 2 (98 < 99), 3 (100.5 < 101) are red
        assert len(result) == 3
        assert list(result.index) == [0, 2, 3]

    def test_green_candle_filter(self, service):
        df = self._make_df()
        req = ScanRequest(candle_color="green", conditions=[])
        result = service._apply_conditions(df, req)
        # Rows 1 (103 > 102), 3 (100.5 > 101? NO → not green), 4 (104 > 103)
        # Row 3: close=100.5 < open=101.0 → red, not green
        assert len(result) == 2
        assert list(result.index) == [1, 4]

    def test_any_color_no_filter(self, service):
        df = self._make_df()
        req = ScanRequest(candle_color="any", conditions=[])
        result = service._apply_conditions(df, req)
        assert len(result) == 5

    def test_single_condition_body_pct(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="body_pct", operator="<=", value=0.01)],
        )
        result = service._apply_conditions(df, req)
        # body_pct: [0.01, 0.0098, 0.0101, 0.005, 0.0097]
        # <= 0.01 → rows 0, 1, 3, 4
        assert len(result) == 4

    def test_multiple_conditions_and_logic(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="red",
            conditions=[
                ScanCondition(field="upper_wick_pct", operator=">=", value=0.10),
                ScanCondition(field="rsi_14", operator=">", value=70),
            ],
        )
        result = service._apply_conditions(df, req)
        # Red: rows 0, 2
        # upper_wick >= 0.10: rows 0 (0.16), 2 (0.14) → both pass
        # rsi > 70: rows 0 (75), 2 (72) → both pass
        assert len(result) == 2

    def test_volume_vs_avg_condition(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="volume_vs_avg", operator=">", value=1.0)],
        )
        result = service._apply_conditions(df, req)
        # volume_vs_avg: [1.5, 0.8, 1.2, 0.7, 1.8]
        # > 1.0 → rows 0, 2, 4
        assert len(result) == 3

    def test_invalid_field_raises(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="fake_field", operator=">=", value=1)],
        )
        with pytest.raises(ValueError, match="Unknown condition field"):
            service._apply_conditions(df, req)

    def test_invalid_operator_raises(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="body_pct", operator="!=", value=0.01)],
        )
        with pytest.raises(ValueError, match="Unknown operator"):
            service._apply_conditions(df, req)

    def test_nan_values_excluded(self, service):
        """NaN values should not pass any condition."""
        df = self._make_df()
        df.loc[0, "rsi_14"] = np.nan
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="rsi_14", operator=">", value=70)],
        )
        result = service._apply_conditions(df, req)
        # rsi > 70: rows 0 (NaN → excluded), 2 (72), 4 (80)
        assert len(result) == 2
        assert 0 not in result.index

    def test_no_conditions_returns_all_of_color(self, service):
        df = self._make_df()
        req = ScanRequest(candle_color="any", conditions=[])
        result = service._apply_conditions(df, req)
        assert len(result) == 5

    def test_eq_operator(self, service):
        df = self._make_df()
        req = ScanRequest(
            candle_color="any",
            conditions=[ScanCondition(field="body_pct", operator="==", value=0.005)],
        )
        result = service._apply_conditions(df, req)
        assert len(result) == 1
        assert result.iloc[0]["body_pct"] == 0.005


# ============================================================
# 6. Forward Return Computation
# ============================================================


class TestForwardReturns:
    """Test _compute_single_forward_return and _compute_forward_returns."""

    def test_single_forward_return_basic(self):
        """Basic forward return for Q+1."""
        # Signal at index 5 (close=105), Q+1 at index 6 (close=110)
        data = {
            "date": [f"2020-{q}-01" for q in ["01", "04", "07", "10"]] * 3,
            "close": [100, 101, 102, 103, 104, 105, 110, 108, 112, 115, 120, 118],
            "ticker": ["SPY"] * 12,
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 5, 105.0, 1)
        assert result.window == 1
        assert result.window_label == "Q+1"
        assert result.close_price == 110.0
        expected_return = (110 - 105) / 105 * 100
        assert abs(result.return_pct - expected_return) < 0.01

    def test_single_forward_return_max_drawdown(self):
        """Max drawdown should be the min close in the forward window."""
        # Signal at index 2 (close=100), looking at Q+3 (indices 3, 4, 5)
        data = {
            "date": [
                "2020-01-01",
                "2020-04-01",
                "2020-07-01",
                "2020-10-01",
                "2021-01-01",
                "2021-04-01",
            ],
            "close": [110, 105, 100, 90, 85, 95],  # drops then recovers
            "ticker": ["SPY"] * 6,
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 2, 100.0, 3)
        # Forward slice = indices 3,4,5 → closes [90, 85, 95]
        # return = (95 - 100) / 100 * 100 = -5%
        assert abs(result.return_pct - (-5.0)) < 0.01
        # max drawdown = (85 - 100) / 100 * 100 = -15%
        assert abs(result.max_drawdown_pct - (-15.0)) < 0.01
        # max surge clamped at 0% (all forward closes below signal close)
        assert abs(result.max_surge_pct - 0.0) < 0.01

    def test_single_forward_return_max_surge(self):
        """Max surge should be the max close in the forward window."""
        data = {
            "date": ["2020-01-01", "2020-04-01", "2020-07-01", "2020-10-01", "2021-01-01"],
            "close": [90, 95, 100, 120, 110],
            "ticker": ["SPY"] * 5,
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 2, 100.0, 2)
        # Forward slice = indices 3,4 → closes [120, 110]
        # max surge = (120 - 100) / 100 * 100 = 20%
        assert abs(result.max_surge_pct - 20.0) < 0.01
        # max drawdown clamped at 0% (all forward closes above signal close)
        assert abs(result.max_drawdown_pct - 0.0) < 0.01
        # return = (110 - 100) / 100 * 100 = 10%
        assert abs(result.return_pct - 10.0) < 0.01

    def test_forward_return_insufficient_data(self):
        """Not enough forward data should return null fields."""
        data = {
            "date": ["2024-01-01", "2024-04-01", "2024-07-01"],
            "close": [100, 105, 110],
            "ticker": ["SPY"] * 3,
        }
        df = pd.DataFrame(data)
        # Signal at index 2, looking Q+3 → index 5 doesn't exist
        result = ScannerService._compute_single_forward_return(df, 2, 110.0, 3)
        assert result.return_pct is None
        assert result.close_price is None
        assert result.max_drawdown_pct is None

    def test_forward_return_at_boundary(self):
        """Signal at second-to-last position, Q+1 = last candle."""
        data = {
            "date": ["2024-01-01", "2024-04-01", "2024-07-01"],
            "close": [100, 105, 102],
            "ticker": ["SPY"] * 3,
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 1, 105.0, 1)
        assert result.return_pct is not None
        expected = (102 - 105) / 105 * 100
        assert abs(result.return_pct - expected) < 0.01


# ============================================================
# 7. Summary Aggregation
# ============================================================


class TestSummaryAggregation:
    """Test _build_summary."""

    @pytest.fixture
    def service(self):
        return ScannerService(AsyncMock())

    def _make_signals(self) -> list[SignalResult]:
        """Two signals with known forward returns."""
        return [
            SignalResult(
                ticker="SPY",
                signal_date="2022-07-01",
                open=100.5,
                high=115.0,
                low=99.5,
                close=100.0,
                volume=5_000_000,
                rsi_14=75.0,
                body_pct=0.50,
                upper_wick_pct=14.93,
                lower_wick_pct=0.50,
                volume_vs_avg=1.5,
                forward_returns=[
                    ForwardReturn(1, "Q+1", 95.0, -5.0, -8.0, 2.0),
                    ForwardReturn(2, "Q+2", 90.0, -10.0, -12.0, 1.0),
                ],
            ),
            SignalResult(
                ticker="QQQ",
                signal_date="2023-01-01",
                open=300.5,
                high=330.0,
                low=298.0,
                close=300.0,
                volume=8_000_000,
                rsi_14=72.0,
                body_pct=0.17,
                upper_wick_pct=10.0,
                lower_wick_pct=0.67,
                volume_vs_avg=1.8,
                forward_returns=[
                    ForwardReturn(1, "Q+1", 310.0, 3.33, -2.0, 5.0),
                    ForwardReturn(2, "Q+2", 285.0, -5.0, -8.0, 5.0),
                ],
            ),
        ]

    def test_summary_counts(self, service):
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1, 2])
        summary = service._build_summary(signals, req)
        assert summary.total_signals == 2
        assert summary.unique_tickers == 2

    def test_summary_date_range(self, service):
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1, 2])
        summary = service._build_summary(signals, req)
        assert "2022-07-01" in summary.date_range
        assert "2023-01-01" in summary.date_range

    def test_summary_per_window(self, service):
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1, 2], candle_color="red")
        summary = service._build_summary(signals, req)
        assert len(summary.per_window) == 2

        # Q+1: returns [-5.0, 3.33] → mean = -0.835, median = -0.835
        w1 = summary.per_window[0]
        assert w1.signal_count == 2
        expected_mean = (-5.0 + 3.33) / 2
        assert abs(w1.mean_return_pct - expected_mean) < 0.01

    def test_bearish_win_rate(self, service):
        """For bearish scans, win = return < 0."""
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1], candle_color="red")
        summary = service._build_summary(signals, req)
        w1 = summary.per_window[0]
        # Q+1: [-5.0, 3.33] → 1 winner out of 2 = 50%
        assert abs(w1.win_rate_pct - 50.0) < 0.01

    def test_bullish_win_rate(self, service):
        """For bullish scans, win = return > 0."""
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1], candle_color="green")
        summary = service._build_summary(signals, req)
        w1 = summary.per_window[0]
        # Q+1: [-5.0, 3.33] → 1 winner out of 2 = 50%
        assert abs(w1.win_rate_pct - 50.0) < 0.01

    def test_any_color_win_rate_is_none(self, service):
        """For candle_color='any', win direction is undefined → win_rate_pct=None."""
        signals = self._make_signals()
        req = ScanRequest(forward_windows=[1], candle_color="any")
        summary = service._build_summary(signals, req)
        w1 = summary.per_window[0]
        assert w1.win_rate_pct is None
        # Other stats should still be computed
        assert w1.signal_count == 2
        assert w1.mean_return_pct is not None

    def test_empty_signals(self, service):
        req = ScanRequest(forward_windows=[1, 2, 3])
        summary = service._build_summary([], req)
        assert summary.total_signals == 0
        assert summary.unique_tickers == 0
        assert len(summary.per_window) == 3
        for ws in summary.per_window:
            assert ws.signal_count == 0

    def test_partial_forward_data(self, service):
        """Signals with missing forward windows should still be counted for available windows."""
        signals = [
            SignalResult(
                ticker="SPY",
                signal_date="2024-07-01",
                open=100.0,
                high=115.0,
                low=99.0,
                close=100.0,
                volume=5_000_000,
                rsi_14=75.0,
                body_pct=0.0,
                upper_wick_pct=15.0,
                lower_wick_pct=1.0,
                volume_vs_avg=1.5,
                forward_returns=[
                    ForwardReturn(1, "Q+1", 95.0, -5.0, -8.0, 2.0),
                    ForwardReturn(2, "Q+2"),  # null — no data
                ],
            ),
        ]
        req = ScanRequest(forward_windows=[1, 2], candle_color="red")
        summary = service._build_summary(signals, req)
        assert summary.per_window[0].signal_count == 1
        assert summary.per_window[1].signal_count == 0


# ============================================================
# 8. Volume Lookback Helper
# ============================================================


class TestVolumeLookback:
    """Test _get_volume_lookback."""

    def test_default_lookback(self):
        assert ScannerService._get_volume_lookback([]) == 2

    def test_lookback_from_condition(self):
        conditions = [
            ScanCondition(field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": 4}),
        ]
        assert ScannerService._get_volume_lookback(conditions) == 4

    def test_lookback_no_extra(self):
        conditions = [
            ScanCondition(field="volume_vs_avg", operator=">", value=1.0),
        ]
        assert ScannerService._get_volume_lookback(conditions) == 2

    def test_lookback_from_unrelated_condition(self):
        conditions = [
            ScanCondition(field="body_pct", operator="<=", value=0.02, extra={"lookback": 10}),
        ]
        # "lookback" on a non-volume_vs_avg field → ignored
        assert ScannerService._get_volume_lookback(conditions) == 2

    def test_lookback_invalid_value_falls_back(self):
        """Non-numeric lookback should fall back to default, not raise."""
        conditions = [
            ScanCondition(
                field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": "bad"}
            ),
        ]
        assert ScannerService._get_volume_lookback(conditions) == 2

    def test_lookback_zero_falls_back(self):
        """Lookback of 0 should fall back to default."""
        conditions = [
            ScanCondition(field="volume_vs_avg", operator=">", value=1.0, extra={"lookback": 0}),
        ]
        assert ScannerService._get_volume_lookback(conditions) == 2


# ============================================================
# 9. Full run_scan Integration
# ============================================================


class TestRunScan:
    """Integration tests for run_scan with mocked DB."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        return ScannerService(mock_session)

    def _setup_scan(
        self,
        service: ScannerService,
        mock_session: AsyncMock,
        tickers: list[tuple[int, str]],
        candle_sets: dict[str, list[dict]],
    ) -> None:
        """Wire up mocks for universe + per-ticker candle fetches."""
        # Universe query
        mock_session.execute.return_value = _make_universe_result(tickers)

        # Candle fetches go through CandleService.get_candles
        async def mock_get_candles(
            stock_id, timeframe, adjusted=True, limit=200, start=None, end=None
        ):
            for sid, ticker in tickers:
                if sid == stock_id:
                    return candle_sets.get(ticker, [])
            return []

        service._candle_service.get_candles = mock_get_candles  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_scan_finds_bearish_reversal(self, service, mock_session):
        """A classic bearish reversal candle should be detected."""
        # Build 20 normal candles, then insert a bearish reversal at index 15
        candles = _make_quarterly_candles(20, base_close=100.0, trend=2.0)
        # Make candle at index 15 a bearish reversal
        candles[15] = _make_bearish_reversal_candle(
            date_str=candles[15]["date"],
            open_=candles[15]["close"] + 0.3,  # small body, red
            close=candles[15]["close"],
            high=candles[15]["close"] + 20.0,  # huge upper wick
            low=candles[15]["close"] - 0.5,  # tiny lower wick
            volume=10_000_000,  # high volume
        )

        self._setup_scan(
            service,
            mock_session,
            [(1, "SPY")],
            {"SPY": candles},
        )

        req = ScanRequest(
            candle_color="red",
            conditions=[
                ScanCondition(field="body_pct", operator="<=", value=0.02),
                ScanCondition(field="upper_wick_pct", operator=">=", value=0.05),
                ScanCondition(field="lower_wick_pct", operator="<=", value=0.02),
            ],
            forward_windows=[1, 2, 3],
        )

        result = await service.run_scan(req)
        assert isinstance(result, ScanResult)
        assert result.scan_duration_seconds >= 0
        assert len(result.conditions_used) == 3
        # Should find at least the signal we planted
        assert result.summary.total_signals >= 1
        # The planted signal should have forward returns
        for sig in result.signals:
            assert len(sig.forward_returns) == 3

    @pytest.mark.asyncio
    async def test_scan_empty_universe(self, service, mock_session):
        """Empty universe should return empty result fast."""
        mock_session.execute.return_value = _make_universe_result([])
        req = ScanRequest()
        result = await service.run_scan(req)
        assert result.summary.total_signals == 0
        assert result.signals == []

    @pytest.mark.asyncio
    async def test_scan_no_signals(self, service, mock_session):
        """All candles fail conditions → zero signals."""
        candles = _make_quarterly_candles(20, base_close=100.0, trend=2.0)
        self._setup_scan(
            service,
            mock_session,
            [(1, "SPY")],
            {"SPY": candles},
        )
        # Impossible conditions: body must be exactly 99% AND upper wick >= 99%
        req = ScanRequest(
            candle_color="any",
            conditions=[
                ScanCondition(field="body_pct", operator=">=", value=0.99),
                ScanCondition(field="upper_wick_pct", operator=">=", value=0.99),
            ],
        )
        result = await service.run_scan(req)
        assert result.summary.total_signals == 0

    @pytest.mark.asyncio
    async def test_scan_multiple_tickers(self, service, mock_session):
        """Scan across multiple tickers should aggregate correctly."""
        spy_candles = _make_quarterly_candles(20, base_close=100, trend=2.0)
        qqq_candles = _make_quarterly_candles(20, base_close=200, trend=3.0)

        # Insert a bearish reversal in each
        for candles in [spy_candles, qqq_candles]:
            base = candles[10]["close"]
            candles[10] = _make_bearish_reversal_candle(
                date_str=candles[10]["date"],
                open_=base + 0.2,
                close=base,
                high=base + 25.0,
                low=base - 0.3,
                volume=8_000_000,
            )

        self._setup_scan(
            service,
            mock_session,
            [(1, "SPY"), (2, "QQQ")],
            {"SPY": spy_candles, "QQQ": qqq_candles},
        )

        req = ScanRequest(
            candle_color="red",
            conditions=[
                ScanCondition(field="upper_wick_pct", operator=">=", value=0.05),
            ],
            forward_windows=[1, 2],
        )

        result = await service.run_scan(req)
        assert result.summary.total_signals >= 2
        tickers_found = {s.ticker for s in result.signals}
        assert len(tickers_found) >= 1  # at least one ticker found

    @pytest.mark.asyncio
    async def test_scan_progress_callback(self, service, mock_session):
        """Progress callback should be called for each ticker."""
        candles = _make_quarterly_candles(10)
        self._setup_scan(
            service,
            mock_session,
            [(1, "SPY"), (2, "QQQ")],
            {"SPY": candles, "QQQ": candles},
        )

        progress_calls = []

        def on_progress(current, total):
            progress_calls.append((current, total))

        req = ScanRequest(candle_color="any", conditions=[])
        await service.run_scan(req, progress_callback=on_progress)
        assert len(progress_calls) == 2
        assert progress_calls[-1] == (2, 2)

    @pytest.mark.asyncio
    async def test_scan_validation_error(self, service, mock_session):
        """Invalid request should raise immediately."""
        req = ScanRequest(timeframe="daily")
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            await service.run_scan(req)

    @pytest.mark.asyncio
    async def test_scan_result_conditions_preserved(self, service, mock_session):
        """The conditions used should be preserved in the result."""
        candles = _make_quarterly_candles(10)
        self._setup_scan(
            service,
            mock_session,
            [(1, "SPY")],
            {"SPY": candles},
        )
        conditions = [
            ScanCondition(field="body_pct", operator="<=", value=0.02),
            ScanCondition(field="rsi_14", operator=">", value=70),
        ]
        req = ScanRequest(candle_color="red", conditions=conditions)
        result = await service.run_scan(req)
        assert result.conditions_used == conditions


# ============================================================
# 10. Edge Cases
# ============================================================


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_forward_return_window_1(self):
        """Q+1 should look at the very next candle."""
        data = {
            "date": ["2024-01-01", "2024-04-01"],
            "close": [100, 95],
            "ticker": ["SPY", "SPY"],
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 0, 100.0, 1)
        assert result.return_pct == -5.0

    def test_forward_return_at_last_index(self):
        """Signal at last index with any window → null returns."""
        data = {
            "date": ["2024-01-01", "2024-04-01"],
            "close": [100, 105],
            "ticker": ["SPY", "SPY"],
        }
        df = pd.DataFrame(data)
        result = ScannerService._compute_single_forward_return(df, 1, 105.0, 1)
        assert result.return_pct is None

    def test_signal_result_display_values(self):
        """SignalResult stores display-ready values (pct × 100)."""
        sig = SignalResult(
            ticker="SPY",
            signal_date="2024-07-01",
            open=100.5,
            high=115.0,
            low=99.5,
            close=100.0,
            volume=5_000_000,
            rsi_14=75.0,
            body_pct=0.50,  # 0.50%
            upper_wick_pct=14.93,  # 14.93%
            lower_wick_pct=0.50,  # 0.50%
            volume_vs_avg=1.5,
        )
        # These are already in display-ready format (×100)
        assert sig.body_pct == 0.50
        assert sig.upper_wick_pct == 14.93

    def test_operators_with_series(self):
        """All operators should work with pandas Series."""
        s = pd.Series([1, 2, 3, 4, 5])
        assert _OPERATORS["<="](s, 3).tolist() == [True, True, True, False, False]
        assert _OPERATORS[">="](s, 3).tolist() == [False, False, True, True, True]
        assert _OPERATORS["<"](s, 3).tolist() == [True, True, False, False, False]
        assert _OPERATORS[">"](s, 3).tolist() == [False, False, False, True, True]
        assert _OPERATORS["=="](s, 3).tolist() == [False, False, True, False, False]

    def test_window_summary_with_all_wins(self):
        """100% win rate scenario."""
        service = ScannerService(AsyncMock())
        signals = [
            SignalResult(
                ticker="SPY",
                signal_date="2024-01-01",
                open=100,
                high=110,
                low=95,
                close=100,
                volume=1000000,
                rsi_14=75,
                body_pct=0.0,
                upper_wick_pct=10.0,
                lower_wick_pct=5.0,
                volume_vs_avg=1.5,
                forward_returns=[ForwardReturn(1, "Q+1", 90.0, -10.0, -15.0, -2.0)],
            ),
            SignalResult(
                ticker="QQQ",
                signal_date="2024-04-01",
                open=300,
                high=320,
                low=290,
                close=300,
                volume=2000000,
                rsi_14=72,
                body_pct=0.0,
                upper_wick_pct=6.67,
                lower_wick_pct=3.33,
                volume_vs_avg=1.3,
                forward_returns=[ForwardReturn(1, "Q+1", 280.0, -6.67, -10.0, -1.0)],
            ),
        ]
        req = ScanRequest(forward_windows=[1], candle_color="red")
        summary = service._build_summary(signals, req)
        assert summary.per_window[0].win_rate_pct == 100.0

    def test_window_summary_with_zero_wins(self):
        """0% win rate scenario (all signals move against the thesis)."""
        service = ScannerService(AsyncMock())
        signals = [
            SignalResult(
                ticker="SPY",
                signal_date="2024-01-01",
                open=100,
                high=110,
                low=95,
                close=100,
                volume=1000000,
                rsi_14=75,
                body_pct=0.0,
                upper_wick_pct=10.0,
                lower_wick_pct=5.0,
                volume_vs_avg=1.5,
                forward_returns=[ForwardReturn(1, "Q+1", 110.0, 10.0, -2.0, 12.0)],
            ),
        ]
        req = ScanRequest(forward_windows=[1], candle_color="red")
        summary = service._build_summary(signals, req)
        assert summary.per_window[0].win_rate_pct == 0.0
