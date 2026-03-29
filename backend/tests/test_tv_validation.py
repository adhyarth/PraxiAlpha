"""
Tests for TradingView data validation comparison logic.

These tests exercise the compare_candles() function and data structures
WITHOUT requiring a TradingView connection or tvdatafeed library.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.validate_tradingview import (
    CandleMismatch,
    ValidationResult,
    compare_candles,
)

# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame matching the expected format (date, OHLCV)."""
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ------------------------------------------------------------------ #
#  CandleMismatch tests                                                #
# ------------------------------------------------------------------ #


class TestCandleMismatch:
    def test_significant_price_above_tolerance(self):
        m = CandleMismatch(
            ticker="AAPL",
            timeframe="daily",
            date="2026-01-15",
            field="close",
            our_value=150.0,
            tv_value=148.0,
            pct_diff=1.35,
        )
        assert m.is_significant  # 1.35% > 1% default tolerance

    def test_not_significant_price_within_tolerance(self):
        m = CandleMismatch(
            ticker="AAPL",
            timeframe="daily",
            date="2026-01-15",
            field="close",
            our_value=150.0,
            tv_value=149.90,
            pct_diff=0.07,
        )
        assert not m.is_significant  # 0.07% < 1%

    def test_volume_uses_volume_tolerance(self):
        m = CandleMismatch(
            ticker="AAPL",
            timeframe="daily",
            date="2026-01-15",
            field="volume",
            our_value=50_000_000,
            tv_value=48_000_000,
            pct_diff=4.0,
        )
        # 4% < 5% volume tolerance → not significant
        assert not m.is_significant

    def test_volume_above_tolerance(self):
        m = CandleMismatch(
            ticker="AAPL",
            timeframe="daily",
            date="2026-01-15",
            field="volume",
            our_value=50_000_000,
            tv_value=45_000_000,
            pct_diff=11.1,
        )
        assert m.is_significant  # 11.1% > 5%


# ------------------------------------------------------------------ #
#  ValidationResult tests                                              #
# ------------------------------------------------------------------ #


class TestValidationResult:
    def test_perfect_match(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
        )
        assert r.mismatch_count == 0
        assert r.match_pct == 100.0

    def test_with_mismatches(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
            mismatches=[
                CandleMismatch(
                    "AAPL", "daily", "2026-01-15", "close", 150.0, 148.0, 1.35
                ),  # significant
                CandleMismatch(
                    "AAPL", "daily", "2026-01-15", "open", 149.0, 148.95, 0.03
                ),  # NOT significant
            ],
        )
        assert r.mismatch_count == 1  # only 1 significant
        # 100 bars × 5 fields = 500 checks, 1 mismatch → 99.8%
        assert r.match_pct == pytest.approx(99.8, abs=0.01)

    def test_no_overlap(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=0,
        )
        assert r.match_pct == 0.0


# ------------------------------------------------------------------ #
#  compare_candles() tests                                             #
# ------------------------------------------------------------------ #


class TestCompareCandles:
    def test_perfect_match_returns_no_mismatches(self):
        """Identical data should produce zero mismatches."""
        data = [
            {
                "date": "2026-01-13",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
            {
                "date": "2026-01-14",
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 1_200_000,
            },
            {
                "date": "2026-01-15",
                "open": 107,
                "high": 110,
                "low": 105,
                "close": 109,
                "volume": 900_000,
            },
        ]
        our_df = _make_df(data)
        tv_df = _make_df(data)

        result = compare_candles("TEST", "daily", our_df, tv_df)

        assert result.overlapping_bars == 3
        assert result.mismatch_count == 0
        assert result.match_pct == 100.0
        assert result.error is None

    def test_price_mismatch_detected(self):
        """A 5% close price difference should be flagged."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 98,
                "volume": 1_000_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))

        assert result.mismatch_count == 1
        assert result.mismatches[0].field == "close"
        assert result.mismatches[0].pct_diff > 1.0

    def test_within_tolerance_not_flagged(self):
        """A 0.5% difference should NOT be flagged (within 1% tolerance)."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100.0,
                "high": 105,
                "low": 99,
                "close": 100.50,
                "volume": 1_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100.0,
                "high": 105,
                "low": 99,
                "close": 100.00,
                "volume": 1_000_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.mismatch_count == 0

    def test_volume_tolerance_applied(self):
        """Volume uses 5% tolerance, not 1%."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_040_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        # 4% volume diff — within 5% tolerance
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.mismatch_count == 0

    def test_volume_mismatch_detected(self):
        """A 15% volume difference should be flagged."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_150_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.mismatch_count == 1
        assert result.mismatches[0].field == "volume"

    def test_no_overlapping_dates(self):
        """Non-overlapping date ranges should produce an error."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-02-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.overlapping_bars == 0
        assert result.error == "No overlapping dates found"

    def test_partial_overlap(self):
        """When we have 3 bars and TV has 2, only overlapping bars are compared."""
        our_data = [
            {
                "date": "2026-01-13",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
            {
                "date": "2026-01-14",
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 1_200_000,
            },
            {
                "date": "2026-01-15",
                "open": 107,
                "high": 110,
                "low": 105,
                "close": 109,
                "volume": 900_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-14",
                "open": 103,
                "high": 108,
                "low": 102,
                "close": 107,
                "volume": 1_200_000,
            },
            {
                "date": "2026-01-15",
                "open": 107,
                "high": 110,
                "low": 105,
                "close": 109,
                "volume": 900_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.our_bar_count == 3
        assert result.tv_bar_count == 2
        assert result.overlapping_bars == 2
        assert result.mismatch_count == 0

    def test_custom_tolerance(self):
        """Custom price tolerance should override the default."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 100.50,
                "volume": 1_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 100.00,
                "volume": 1_000_000,
            },
        ]
        # With default 1% tolerance → 0.5% diff is fine
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.mismatch_count == 0

        # With stricter 0.1% tolerance → 0.5% diff is flagged
        result = compare_candles(
            "TEST",
            "daily",
            _make_df(our_data),
            _make_df(tv_data),
            price_tolerance=0.001,
        )
        assert result.mismatch_count == 1

    def test_multiple_field_mismatches(self):
        """Multiple fields can mismatch on the same bar."""
        our_data = [
            {
                "date": "2026-01-15",
                "open": 110,
                "high": 120,
                "low": 90,
                "close": 115,
                "volume": 2_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2026-01-15",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 103,
                "volume": 1_000_000,
            },
        ]
        result = compare_candles("TEST", "daily", _make_df(our_data), _make_df(tv_data))
        # All 5 fields should differ significantly
        assert result.mismatch_count == 5

    def test_split_adjusted_comparison(self):
        """
        Simulate a stock that had a 4:1 split.
        Our data (correctly adjusted) should match TV (also adjusted).
        Pre-split prices divided by 4.
        """
        # Both sources show the split-adjusted prices (pre-split bar)
        our_data = [
            {
                "date": "2020-08-28",
                "open": 125.0,
                "high": 126.0,
                "low": 124.0,
                "close": 125.50,
                "volume": 200_000_000,
            },
        ]
        tv_data = [
            {
                "date": "2020-08-28",
                "open": 125.0,
                "high": 126.0,
                "low": 124.0,
                "close": 125.50,
                "volume": 200_000_000,
            },
        ]
        result = compare_candles("AAPL", "daily", _make_df(our_data), _make_df(tv_data))
        assert result.mismatch_count == 0


# ------------------------------------------------------------------ #
#  CSV / report tests (no file I/O, just structure)                    #
# ------------------------------------------------------------------ #


class TestReportStructure:
    def test_validation_result_error_state(self):
        r = ValidationResult(
            ticker="XYZ",
            timeframe="daily",
            our_bar_count=0,
            tv_bar_count=0,
            overlapping_bars=0,
            error="Ticker not found",
        )
        assert r.error is not None
        assert r.mismatch_count == 0
        assert r.match_pct == 0.0

    def test_mismatch_pct_diff_is_percentage(self):
        m = CandleMismatch(
            ticker="AAPL",
            timeframe="daily",
            date="2026-01-15",
            field="close",
            our_value=102.0,
            tv_value=100.0,
            pct_diff=2.0,
        )
        # pct_diff is stored as a percentage (2.0 means 2%)
        assert m.pct_diff == 2.0
        assert m.is_significant  # 2% > 1% tolerance
