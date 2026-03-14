"""
PraxiAlpha — Data Pipeline Tests

Tests for EODHD fetcher, FRED fetcher, and data validator.
"""

from datetime import date

import pandas as pd
import pytest

from backend.models.macro import FRED_SERIES
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
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [99.0, 100.0],
                "close": [103.0, 104.0],
                "adjusted_close": [103.0, 104.0],
                "volume": [1000000, 1100000],
            }
        )
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 2
        assert result["close"].iloc[0] == 103.0

    def test_validate_ohlcv_drops_negative_prices(self):
        """Rows with negative prices should be dropped."""
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                "open": [100.0, -1.0],
                "high": [105.0, 106.0],
                "low": [99.0, 100.0],
                "close": [103.0, 104.0],
                "adjusted_close": [103.0, 104.0],
                "volume": [1000000, 1100000],
            }
        )
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 1

    def test_validate_ohlcv_drops_duplicates(self):
        """Duplicate dates should be deduplicated (keep last)."""
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01"],
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [99.0, 100.0],
                "close": [103.0, 104.0],
                "adjusted_close": [103.0, 104.0],
                "volume": [1000000, 1100000],
            }
        )
        result = DataValidator.validate_ohlcv(df, "TEST")
        assert len(result) == 1

    def test_validate_ohlcv_swaps_high_low(self):
        """When high < low, they should be swapped."""
        df = pd.DataFrame(
            {
                "date": ["2024-01-01"],
                "open": [100.0],
                "high": [95.0],  # Lower than low!
                "low": [105.0],  # Higher than high!
                "close": [103.0],
                "adjusted_close": [103.0],
                "volume": [1000000],
            }
        )
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
        df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01"],
                "value": [4.1, 4.2],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert len(result) == 1


class TestFREDSeriesRegistry:
    """Tests for the FRED_SERIES registry configuration."""

    def test_fred_series_count(self):
        """Should have exactly 14 registered series."""
        assert len(FRED_SERIES) == 14

    def test_fred_series_all_have_name(self):
        """Every series must have a human-readable name."""
        for series_id, meta in FRED_SERIES.items():
            assert "name" in meta, f"{series_id} missing 'name'"
            assert isinstance(meta["name"], str) and len(meta["name"]) > 0

    def test_fred_series_all_have_category(self):
        """Every series must have a category."""
        for series_id, meta in FRED_SERIES.items():
            assert "category" in meta, f"{series_id} missing 'category'"

    def test_fred_series_valid_categories(self):
        """All categories should be from the expected set."""
        valid = {"bonds", "volatility", "currencies", "commodities", "liquidity", "economic"}
        for series_id, meta in FRED_SERIES.items():
            assert meta["category"] in valid, (
                f"{series_id} has unknown category '{meta['category']}'"
            )

    def test_fred_series_no_discontinued_gold(self):
        """GOLDAMGBD228NLBM was removed from FRED — it must not be in the registry."""
        assert "GOLDAMGBD228NLBM" not in FRED_SERIES

    def test_fred_series_expected_ids(self):
        """All expected FRED series IDs should be present."""
        expected = {
            "DGS10",
            "DGS2",
            "DGS30",
            "DFF",
            "T10Y2Y",
            "VIXCLS",
            "DTWEXBGS",
            "DCOILWTICO",
            "T10YIE",
            "M2SL",
            "WALCL",
            "UNRATE",
            "CPIAUCSL",
            "PCEPI",
        }
        assert set(FRED_SERIES.keys()) == expected


class TestValidateMacroExtended:
    """Extended tests for DataValidator.validate_macro."""

    def test_validate_macro_preserves_valid_data(self):
        """Valid macro data should pass through without modification."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "value": [4.1, 4.2, 4.3],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert len(result) == 3
        assert list(result["value"]) == [4.1, 4.2, 4.3]

    def test_validate_macro_sorts_by_date(self):
        """Output should be sorted by date ascending."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 3), date(2024, 1, 1), date(2024, 1, 2)],
                "value": [4.3, 4.1, 4.2],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert list(result["date"]) == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        assert list(result["value"]) == [4.1, 4.2, 4.3]

    def test_validate_macro_keeps_null_values(self):
        """Null values should be preserved (FRED uses them for holidays)."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2)],
                "value": [4.1, None],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert len(result) == 2
        assert pd.isna(result["value"].iloc[1])

    def test_validate_macro_keeps_negative_values(self):
        """Negative values are valid for some indicators (e.g., yield spread)."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2)],
                "value": [-0.5, 0.3],
            }
        )
        result = DataValidator.validate_macro(df, "T10Y2Y")
        assert len(result) == 2
        assert result["value"].iloc[0] == -0.5

    def test_validate_macro_dedup_keeps_last(self):
        """When dates are duplicated, the last occurrence should be kept."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 1)],
                "value": [4.1, 4.5],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert len(result) == 1
        assert result["value"].iloc[0] == 4.5

    def test_validate_macro_resets_index(self):
        """Result should have a clean integer index starting at 0."""
        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 3), date(2024, 1, 1)],
                "value": [4.3, 4.1],
            }
        )
        result = DataValidator.validate_macro(df, "DGS10")
        assert list(result.index) == [0, 1]
