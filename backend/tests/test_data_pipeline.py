"""
PraxiAlpha — Data Pipeline Tests

Tests for EODHD fetcher, FRED fetcher, and data validator.
"""

import pytest
import pandas as pd

from backend.services.data_pipeline.data_validator import DataValidator


class TestDataValidator:
    """Tests for the DataValidator class."""

    def test_validate_ohlcv_empty_df(self):
        """Empty DataFrame should pass through."""
        df = pd.DataFrame()
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert result.empty

    def test_validate_ohlcv_missing_columns(self):
        """Should raise ValueError if required columns are missing."""
        df = pd.DataFrame({"date": ["2024-01-01"], "open": [100]})
        with pytest.raises(ValueError, match="Missing columns"):
            DataValidator.validate_ohlcv(df, "TEST")

    def test_validate_ohlcv_valid_data(self):
        """Valid OHLCV data should pass through cleanly."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "adjusted_close": [103.0, 104.0],
            "volume": [1000000, 1100000],
        })
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 2
        assert result["close"].iloc[0] == 103.0

    def test_validate_ohlcv_drops_negative_prices(self):
        """Rows with negative prices should be dropped."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "open": [100.0, -1.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "adjusted_close": [103.0, 104.0],
            "volume": [1000000, 1100000],
        })
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 1

    def test_validate_ohlcv_drops_duplicates(self):
        """Duplicate dates should be deduplicated (keep last)."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01"],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [99.0, 100.0],
            "close": [103.0, 104.0],
            "adjusted_close": [103.0, 104.0],
            "volume": [1000000, 1100000],
        })
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 1

    def test_validate_ohlcv_swaps_high_low(self):
        """When high < low, they should be swapped."""
        df = pd.DataFrame({
            "date": ["2024-01-01"],
            "open": [100.0],
            "high": [95.0],   # Lower than low!
            "low": [105.0],   # Higher than high!
            "close": [103.0],
            "adjusted_close": [103.0],
            "volume": [1000000],
        })
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert result["high"].iloc[0] == 105.0
        assert result["low"].iloc[0] == 95.0

    def test_validate_macro_empty_df(self):
        """Empty DataFrame should pass through."""
        df = pd.DataFrame()
        result = DataValidator.validate_macro(df, "DGS10")
        assert result.empty

    def test_validate_macro_drops_duplicates(self):
        """Duplicate dates should be deduplicated."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01"],
            "value": [4.1, 4.2],
        })
        result = DataValidator.validate_macro(df, "DGS10")
        assert len(result) == 1
