"""
PraxiAlpha — Technical Indicators Tests

Comprehensive unit tests for the pure-Python/pandas indicator functions:
SMA, EMA, RSI, MACD, and Bollinger Bands.

All tests use small, deterministic datasets so they run without a database
and complete in milliseconds.
"""

import numpy as np
import pandas as pd
import pytest

from backend.services.analysis.technical_indicators import (
    _validate_inputs,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)

# ============================================================
# Fixtures — reusable price series
# ============================================================


@pytest.fixture
def simple_series() -> pd.Series:
    """Ten ascending prices: 1.0 … 10.0."""
    return pd.Series([float(i) for i in range(1, 11)])


@pytest.fixture
def constant_series() -> pd.Series:
    """Twenty identical prices — useful for zero-variance tests."""
    return pd.Series([50.0] * 20)


@pytest.fixture
def alternating_series() -> pd.Series:
    """Alternating up/down prices to exercise RSI."""
    return pd.Series(
        [
            100.0,
            102.0,
            99.0,
            103.0,
            98.0,
            104.0,
            97.0,
            105.0,
            96.0,
            106.0,
            95.0,
            107.0,
            94.0,
            108.0,
            93.0,
            109.0,
        ]
    )


@pytest.fixture
def realistic_series() -> pd.Series:
    """30 semi-realistic daily closes for integration-style checks."""
    np.random.seed(42)
    return pd.Series(np.cumsum(np.random.randn(30)) + 200)


# ============================================================
# Shared validation tests
# ============================================================


class TestValidation:
    """Tests for the shared _validate_inputs helper."""

    def test_rejects_non_series(self):
        with pytest.raises(TypeError, match="Expected pd.Series"):
            _validate_inputs([1, 2, 3], 5)

    def test_rejects_empty_series(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _validate_inputs(pd.Series(dtype=float), 5)

    def test_rejects_zero_period(self):
        with pytest.raises(ValueError, match="Period must be"):
            _validate_inputs(pd.Series([1.0]), 0)

    def test_rejects_negative_period(self):
        with pytest.raises(ValueError, match="Period must be"):
            _validate_inputs(pd.Series([1.0]), -3)

    def test_accepts_valid_inputs(self):
        """Should not raise for valid inputs."""
        _validate_inputs(pd.Series([1.0, 2.0]), 1)


# ============================================================
# SMA Tests
# ============================================================


class TestSMA:
    """Tests for Simple Moving Average."""

    def test_sma_basic(self, simple_series):
        result = sma(simple_series, period=3)
        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_series)
        # First 2 values should be NaN (period=3, min_periods=3)
        assert result.iloc[:2].isna().all()
        # sma of [1,2,3] = 2.0
        assert result.iloc[2] == pytest.approx(2.0)
        # sma of [2,3,4] = 3.0
        assert result.iloc[3] == pytest.approx(3.0)

    def test_sma_period_equals_length(self, simple_series):
        result = sma(simple_series, period=len(simple_series))
        assert result.iloc[:-1].isna().all()
        assert result.iloc[-1] == pytest.approx(simple_series.mean())

    def test_sma_period_1(self, simple_series):
        """Period=1 SMA should equal the original series."""
        result = sma(simple_series, period=1)
        pd.testing.assert_series_equal(result, simple_series, check_names=False)

    def test_sma_constant_series(self, constant_series):
        """SMA of constant values should equal that constant."""
        result = sma(constant_series, period=5)
        non_nan = result.dropna()
        assert (non_nan == 50.0).all()

    def test_sma_default_period(self, constant_series):
        """Default period is 20."""
        result = sma(constant_series)
        # 20 values, period 20 → only last value is non-NaN
        assert result.iloc[-1] == pytest.approx(50.0)
        assert result.iloc[:-1].isna().all()

    def test_sma_rejects_invalid_period(self, simple_series):
        with pytest.raises(ValueError):
            sma(simple_series, period=0)

    def test_sma_rejects_empty_series(self):
        with pytest.raises(ValueError):
            sma(pd.Series(dtype=float), period=5)


# ============================================================
# EMA Tests
# ============================================================


class TestEMA:
    """Tests for Exponential Moving Average."""

    def test_ema_basic(self, simple_series):
        result = ema(simple_series, period=3)
        assert isinstance(result, pd.Series)
        assert len(result) == len(simple_series)
        # First value should be the first data point (starting seed)
        assert result.iloc[0] == pytest.approx(simple_series.iloc[0])

    def test_ema_no_nans(self, simple_series):
        """EMA (adjust=False) produces values from index 0 onward."""
        result = ema(simple_series, period=3)
        assert not result.isna().any()

    def test_ema_period_1(self, simple_series):
        """Period=1 EMA ≈ original series."""
        result = ema(simple_series, period=1)
        pd.testing.assert_series_equal(result, simple_series, check_names=False)

    def test_ema_constant_series(self, constant_series):
        """EMA of constant values should equal that constant."""
        result = ema(constant_series, period=10)
        assert np.allclose(result.values, 50.0)

    def test_ema_reacts_faster_than_sma(self, simple_series):
        """EMA should respond faster to recent changes than SMA."""
        ema_result = ema(simple_series, period=5)
        sma_result = sma(simple_series, period=5)
        # For an upward-trending series, EMA should be higher than SMA
        # at the end because it weights recent (higher) values more.
        # Compare last value where both have data.
        last = len(simple_series) - 1
        assert ema_result.iloc[last] > sma_result.iloc[last]

    def test_ema_default_period(self, constant_series):
        result = ema(constant_series)
        assert len(result) == len(constant_series)

    def test_ema_rejects_invalid_period(self, simple_series):
        with pytest.raises(ValueError):
            ema(simple_series, period=-1)


# ============================================================
# RSI Tests
# ============================================================


class TestRSI:
    """Tests for Relative Strength Index."""

    def test_rsi_basic(self, alternating_series):
        result = rsi(alternating_series, period=14)
        assert isinstance(result, pd.Series)
        assert len(result) == len(alternating_series)

    def test_rsi_range(self, alternating_series):
        """All non-NaN RSI values should be in [0, 100]."""
        result = rsi(alternating_series, period=5)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_leading_nans(self, alternating_series):
        """First *period* values should be NaN (need period diffs + 1 data point)."""
        result = rsi(alternating_series, period=5)
        # Due to .diff(), index 0 is NaN. With min_periods=5 on ewm,
        # the first 5 indices should be NaN.
        assert result.iloc[:5].isna().all()

    def test_rsi_all_gains(self):
        """Monotonically increasing prices → RSI should be 100."""
        prices = pd.Series([float(i) for i in range(1, 20)])
        result = rsi(prices, period=5)
        valid = result.dropna()
        assert np.allclose(valid.values, 100.0)

    def test_rsi_all_losses(self):
        """Monotonically decreasing prices → RSI should be 0."""
        prices = pd.Series([float(i) for i in range(20, 0, -1)])
        result = rsi(prices, period=5)
        valid = result.dropna()
        assert np.allclose(valid.values, 0.0)

    def test_rsi_constant_price(self, constant_series):
        """Constant price → RSI is NaN (0/0 division → RS is NaN)."""
        result = rsi(constant_series, period=5)
        # No gains, no losses → 0/0 → NaN
        # This is expected and correct.
        # pandas ewm with 0/0 will produce NaN; that is acceptable.
        # Some implementations return 50 for this edge case.
        # Our implementation produces NaN, which is more honest.
        assert result.dropna().empty or result.dropna().between(0, 100).all()

    def test_rsi_default_period(self, alternating_series):
        result = rsi(alternating_series)
        assert len(result) == len(alternating_series)

    def test_rsi_rejects_invalid_period(self, simple_series):
        with pytest.raises(ValueError):
            rsi(simple_series, period=0)


# ============================================================
# MACD Tests
# ============================================================


class TestMACD:
    """Tests for MACD."""

    def test_macd_returns_dataframe(self, realistic_series):
        result = macd(realistic_series)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["macd_line", "signal_line", "histogram"]

    def test_macd_length(self, realistic_series):
        result = macd(realistic_series)
        assert len(result) == len(realistic_series)

    def test_macd_histogram_is_difference(self, realistic_series):
        """histogram == macd_line − signal_line."""
        result = macd(realistic_series)
        expected = result["macd_line"] - result["signal_line"]
        pd.testing.assert_series_equal(result["histogram"], expected, check_names=False)

    def test_macd_constant_series(self, constant_series):
        """Constant prices → MACD line, signal, histogram all ≈ 0."""
        result = macd(constant_series, fast_period=3, slow_period=5, signal_period=3)
        assert np.allclose(result["macd_line"].values, 0.0, atol=1e-10)
        assert np.allclose(result["signal_line"].values, 0.0, atol=1e-10)
        assert np.allclose(result["histogram"].values, 0.0, atol=1e-10)

    def test_macd_custom_periods(self, realistic_series):
        result = macd(realistic_series, fast_period=5, slow_period=10, signal_period=3)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(realistic_series)

    def test_macd_rejects_fast_ge_slow(self, simple_series):
        with pytest.raises(ValueError, match="fast_period must be < slow_period"):
            macd(simple_series, fast_period=12, slow_period=12)

    def test_macd_rejects_fast_gt_slow(self, simple_series):
        with pytest.raises(ValueError, match="fast_period must be < slow_period"):
            macd(simple_series, fast_period=26, slow_period=12)

    def test_macd_rejects_zero_period(self, simple_series):
        with pytest.raises(ValueError, match="periods must be"):
            macd(simple_series, fast_period=0, slow_period=26)

    def test_macd_rejects_negative_period(self, simple_series):
        with pytest.raises(ValueError, match="periods must be"):
            macd(simple_series, fast_period=12, slow_period=-1)

    def test_macd_rejects_empty_series(self):
        with pytest.raises(ValueError):
            macd(pd.Series(dtype=float))


# ============================================================
# Bollinger Bands Tests
# ============================================================


class TestBollingerBands:
    """Tests for Bollinger Bands."""

    def test_bb_returns_dataframe(self, simple_series):
        result = bollinger_bands(simple_series, period=3)
        assert isinstance(result, pd.DataFrame)
        assert list(result.columns) == ["middle_band", "upper_band", "lower_band"]

    def test_bb_length(self, simple_series):
        result = bollinger_bands(simple_series, period=3)
        assert len(result) == len(simple_series)

    def test_bb_middle_equals_sma(self, simple_series):
        """Middle band should equal the SMA."""
        result = bollinger_bands(simple_series, period=3)
        expected = sma(simple_series, period=3)
        pd.testing.assert_series_equal(result["middle_band"], expected, check_names=False)

    def test_bb_upper_above_middle(self, simple_series):
        """Upper band ≥ middle band everywhere (for non-constant data)."""
        result = bollinger_bands(simple_series, period=3)
        valid = result.dropna()
        assert (valid["upper_band"] >= valid["middle_band"]).all()

    def test_bb_lower_below_middle(self, simple_series):
        """Lower band ≤ middle band everywhere."""
        result = bollinger_bands(simple_series, period=3)
        valid = result.dropna()
        assert (valid["lower_band"] <= valid["middle_band"]).all()

    def test_bb_symmetry(self, simple_series):
        """Upper and lower bands should be equidistant from the middle."""
        result = bollinger_bands(simple_series, period=3, num_std=2.0)
        valid = result.dropna()
        upper_diff = valid["upper_band"] - valid["middle_band"]
        lower_diff = valid["middle_band"] - valid["lower_band"]
        pd.testing.assert_series_equal(upper_diff, lower_diff, check_names=False)

    def test_bb_constant_series(self, constant_series):
        """Constant prices → bands collapse to the mean (std=0)."""
        result = bollinger_bands(constant_series, period=5)
        valid = result.dropna()
        assert np.allclose(valid["upper_band"].values, 50.0)
        assert np.allclose(valid["middle_band"].values, 50.0)
        assert np.allclose(valid["lower_band"].values, 50.0)

    def test_bb_wider_with_more_std(self, realistic_series):
        """3-sigma bands should be wider than 1-sigma bands."""
        narrow = bollinger_bands(realistic_series, period=5, num_std=1.0)
        wide = bollinger_bands(realistic_series, period=5, num_std=3.0)
        valid_idx = narrow.dropna().index
        assert (wide.loc[valid_idx, "upper_band"] >= narrow.loc[valid_idx, "upper_band"]).all()
        assert (wide.loc[valid_idx, "lower_band"] <= narrow.loc[valid_idx, "lower_band"]).all()

    def test_bb_default_params(self, constant_series):
        result = bollinger_bands(constant_series)
        assert len(result) == len(constant_series)

    def test_bb_rejects_zero_num_std(self, simple_series):
        with pytest.raises(ValueError, match="num_std must be > 0"):
            bollinger_bands(simple_series, period=3, num_std=0)

    def test_bb_rejects_negative_num_std(self, simple_series):
        with pytest.raises(ValueError, match="num_std must be > 0"):
            bollinger_bands(simple_series, period=3, num_std=-1.0)

    def test_bb_rejects_invalid_period(self, simple_series):
        with pytest.raises(ValueError):
            bollinger_bands(simple_series, period=0)


# ============================================================
# Integration: chaining indicators together
# ============================================================


class TestIntegration:
    """Cross-indicator integration checks."""

    def test_rsi_of_ema(self, realistic_series):
        """RSI can be computed on an EMA-smoothed series."""
        smoothed = ema(realistic_series, period=5)
        result = rsi(smoothed, period=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_bollinger_bands_with_ema(self, realistic_series):
        """
        We can manually construct EMA-based Bollinger Bands by combining
        our primitives; just verify shapes are consistent.
        """
        middle = ema(realistic_series, period=20)
        upper = middle + 2 * realistic_series.rolling(20).std(ddof=0)
        lower = middle - 2 * realistic_series.rolling(20).std(ddof=0)
        assert len(middle) == len(realistic_series)
        assert len(upper) == len(realistic_series)
        assert len(lower) == len(realistic_series)

    def test_all_indicators_same_length(self, realistic_series):
        """All indicators should return the same length as the input."""
        assert len(sma(realistic_series, 5)) == len(realistic_series)
        assert len(ema(realistic_series, 5)) == len(realistic_series)
        assert len(rsi(realistic_series, 5)) == len(realistic_series)
        assert len(macd(realistic_series, 5, 10, 3)) == len(realistic_series)
        assert len(bollinger_bands(realistic_series, 5)) == len(realistic_series)
