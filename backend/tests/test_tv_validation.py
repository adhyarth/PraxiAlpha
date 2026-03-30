"""
Tests for data validation service (second-source comparison).

These tests exercise the compare_candles() function, data structures,
quarterly aggregation, failure persistence, and summary computation
WITHOUT requiring a Yahoo Finance connection or yfinance library.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.services.tv_validation_service import (
    CandleMismatch,
    ValidationResult,
    aggregate_monthly_to_quarterly,
    compare_candles,
    compute_summary,
    get_retry_tickers_from_failures,
    load_previous_failures,
    save_failures,
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


# ------------------------------------------------------------------ #
#  Quarterly aggregation tests                                         #
# ------------------------------------------------------------------ #


class TestQuarterlyAggregation:
    """Tests for aggregate_monthly_to_quarterly()."""

    def test_basic_quarterly_aggregation(self):
        """Three monthly bars should produce one quarterly bar."""
        monthly = pd.DataFrame(
            [
                {
                    "date": "2025-01-01",
                    "open": 100,
                    "high": 110,
                    "low": 95,
                    "close": 105,
                    "volume": 1_000_000,
                },
                {
                    "date": "2025-02-01",
                    "open": 105,
                    "high": 115,
                    "low": 100,
                    "close": 112,
                    "volume": 1_200_000,
                },
                {
                    "date": "2025-03-01",
                    "open": 112,
                    "high": 120,
                    "low": 108,
                    "close": 118,
                    "volume": 900_000,
                },
            ]
        )
        result = aggregate_monthly_to_quarterly(monthly)

        assert len(result) == 1
        row = result.iloc[0]
        assert row["open"] == 100  # first month's open
        assert row["high"] == 120  # max high across quarter
        assert row["low"] == 95  # min low across quarter
        assert row["close"] == 118  # last month's close
        assert row["volume"] == 3_100_000  # sum of volumes

    def test_multiple_quarters(self):
        """Six monthly bars should produce two quarterly bars."""
        monthly = pd.DataFrame(
            [
                {
                    "date": "2025-01-01",
                    "open": 100,
                    "high": 110,
                    "low": 95,
                    "close": 105,
                    "volume": 1_000_000,
                },
                {
                    "date": "2025-02-01",
                    "open": 105,
                    "high": 115,
                    "low": 100,
                    "close": 112,
                    "volume": 1_200_000,
                },
                {
                    "date": "2025-03-01",
                    "open": 112,
                    "high": 120,
                    "low": 108,
                    "close": 118,
                    "volume": 900_000,
                },
                {
                    "date": "2025-04-01",
                    "open": 118,
                    "high": 125,
                    "low": 115,
                    "close": 122,
                    "volume": 1_100_000,
                },
                {
                    "date": "2025-05-01",
                    "open": 122,
                    "high": 130,
                    "low": 119,
                    "close": 128,
                    "volume": 1_300_000,
                },
                {
                    "date": "2025-06-01",
                    "open": 128,
                    "high": 135,
                    "low": 125,
                    "close": 132,
                    "volume": 1_000_000,
                },
            ]
        )
        result = aggregate_monthly_to_quarterly(monthly)

        assert len(result) == 2
        q1 = result.iloc[0]
        q2 = result.iloc[1]
        assert q1["open"] == 100
        assert q1["close"] == 118
        assert q2["open"] == 118
        assert q2["close"] == 132

    def test_empty_input(self):
        """Empty DataFrame should return empty DataFrame."""
        result = aggregate_monthly_to_quarterly(pd.DataFrame())
        assert result.empty
        assert set(result.columns) == {"date", "open", "high", "low", "close", "volume"}

    def test_none_input(self):
        """None input should return empty DataFrame."""
        result = aggregate_monthly_to_quarterly(None)  # type: ignore[arg-type]
        assert result.empty

    def test_date_column_is_date_type(self):
        """Quarterly output dates should be date objects, not timestamps."""
        import datetime

        monthly = pd.DataFrame(
            [
                {
                    "date": "2025-01-01",
                    "open": 100,
                    "high": 110,
                    "low": 95,
                    "close": 105,
                    "volume": 1_000_000,
                },
                {
                    "date": "2025-02-01",
                    "open": 105,
                    "high": 115,
                    "low": 100,
                    "close": 112,
                    "volume": 1_200_000,
                },
                {
                    "date": "2025-03-01",
                    "open": 112,
                    "high": 120,
                    "low": 108,
                    "close": 118,
                    "volume": 900_000,
                },
            ]
        )
        result = aggregate_monthly_to_quarterly(monthly)
        assert isinstance(result.iloc[0]["date"], datetime.date)


# ------------------------------------------------------------------ #
#  Failure persistence tests                                           #
# ------------------------------------------------------------------ #


class TestFailurePersistence:
    """Tests for save_failures / load_previous_failures / get_retry_tickers."""

    def test_save_and_load_failures(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Saving failures and loading them round-trips correctly."""
        failure_path = tmp_path / "tv_validation_failures.json"
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)

        results = [
            ValidationResult(
                ticker="AAPL",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
                mismatches=[
                    CandleMismatch("AAPL", "daily", "2026-01-15", "close", 150.0, 148.0, 1.35),
                ],
            ),
            ValidationResult(
                ticker="MSFT",
                timeframe="weekly",
                our_bar_count=50,
                tv_bar_count=50,
                overlapping_bars=50,
                group="fixed",
            ),  # This one passes — no mismatches
        ]

        save_failures(results, random_tickers=["XYZ", "ABC"])

        loaded = load_previous_failures()
        assert loaded is not None
        assert len(loaded["failures"]) == 1  # Only AAPL failed
        assert loaded["failures"][0]["ticker"] == "AAPL"
        assert loaded["failures"][0]["timeframe"] == "daily"
        assert loaded["random_tickers"] == ["XYZ", "ABC"]
        assert "timestamp" in loaded

    def test_all_pass_deletes_failure_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """When all results pass, the failure file should be deleted."""
        failure_path = tmp_path / "tv_validation_failures.json"
        # Create a pre-existing failure file
        failure_path.write_text('{"failures": []}')
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)

        results = [
            ValidationResult(
                ticker="AAPL",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
            ),
        ]

        save_failures(results, random_tickers=[])
        assert not failure_path.exists()

    def test_load_nonexistent_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Loading from a non-existent path should return None."""
        failure_path = tmp_path / "does_not_exist.json"
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)
        assert load_previous_failures() is None

    def test_load_corrupt_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Loading corrupt JSON should return None, not crash."""
        failure_path = tmp_path / "bad.json"
        failure_path.write_text("NOT VALID JSON{{{")
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)
        assert load_previous_failures() is None

    def test_get_retry_tickers(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """get_retry_tickers_from_failures returns (ticker, timeframe) pairs."""
        failure_path = tmp_path / "tv_validation_failures.json"
        data = {
            "timestamp": "2025-01-01T00:00:00",
            "failures": [
                {
                    "ticker": "AAPL",
                    "timeframe": "daily",
                    "group": "fixed",
                    "error": None,
                    "mismatch_count": 1,
                    "match_pct": 99.8,
                    "worst_diff": "close: +1.35%",
                },
                {
                    "ticker": "NVDA",
                    "timeframe": "weekly",
                    "group": "fixed",
                    "error": "Not found on TV",
                    "mismatch_count": 0,
                    "match_pct": 0.0,
                    "worst_diff": "—",
                },
            ],
            "random_tickers": [],
        }
        failure_path.write_text(json.dumps(data))
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)

        retries = get_retry_tickers_from_failures()
        assert retries == [("AAPL", "daily"), ("NVDA", "weekly")]

    def test_get_retry_tickers_no_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """No failure file should return empty list."""
        failure_path = tmp_path / "none.json"
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)
        assert get_retry_tickers_from_failures() == []

    def test_save_error_results(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Error results (e.g. TV unavailable) should also be persisted."""
        failure_path = tmp_path / "tv_validation_failures.json"
        monkeypatch.setattr("backend.services.tv_validation_service.FAILURES_PATH", failure_path)

        results = [
            ValidationResult(
                ticker="XYZ",
                timeframe="daily",
                our_bar_count=0,
                tv_bar_count=0,
                overlapping_bars=0,
                group="random",
                error="Not found on Yahoo Finance",
            ),
        ]

        save_failures(results, random_tickers=["XYZ"])

        loaded = load_previous_failures()
        assert loaded is not None
        assert len(loaded["failures"]) == 1
        assert loaded["failures"][0]["error"] == "Not found on Yahoo Finance"


# ------------------------------------------------------------------ #
#  compute_summary tests                                               #
# ------------------------------------------------------------------ #


class TestComputeSummary:
    """Tests for compute_summary()."""

    def test_all_passing(self):
        results = [
            ValidationResult(
                ticker="AAPL",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
            ),
            ValidationResult(
                ticker="MSFT",
                timeframe="daily",
                our_bar_count=50,
                tv_bar_count=50,
                overlapping_bars=50,
                group="fixed",
            ),
        ]
        s = compute_summary(results)
        assert s["total_combinations"] == 2
        assert s["passed"] == 2
        assert s["failed"] == 0
        assert s["errors"] == 0
        assert s["overall_match_pct"] == 100.0

    def test_with_failures(self):
        results = [
            ValidationResult(
                ticker="AAPL",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
                mismatches=[
                    CandleMismatch("AAPL", "daily", "2026-01-15", "close", 150.0, 148.0, 1.35),
                ],
            ),
        ]
        s = compute_summary(results)
        assert s["passed"] == 0
        assert s["failed"] == 1
        assert s["total_mismatches"] == 1
        # 100 bars × 5 fields = 500 checks, 1 mismatch → 99.8%
        assert s["overall_match_pct"] == pytest.approx(99.8, abs=0.01)

    def test_with_errors(self):
        results = [
            ValidationResult(
                ticker="BAD",
                timeframe="daily",
                our_bar_count=0,
                tv_bar_count=0,
                overlapping_bars=0,
                group="fixed",
                error="Not found",
            ),
        ]
        s = compute_summary(results)
        assert s["errors"] == 1
        assert s["passed"] == 0
        assert s["failed"] == 0
        assert s["overall_match_pct"] == 0.0

    def test_mixed_results(self):
        results = [
            ValidationResult(
                ticker="AAPL",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
            ),  # pass
            ValidationResult(
                ticker="NVDA",
                timeframe="daily",
                our_bar_count=100,
                tv_bar_count=100,
                overlapping_bars=100,
                group="fixed",
                mismatches=[
                    CandleMismatch("NVDA", "daily", "2026-01-15", "close", 150.0, 140.0, 7.14),
                ],
            ),  # fail
            ValidationResult(
                ticker="XYZ",
                timeframe="daily",
                our_bar_count=0,
                tv_bar_count=0,
                overlapping_bars=0,
                group="random",
                error="Not found",
            ),  # error
        ]
        s = compute_summary(results)
        assert s["total_combinations"] == 3
        assert s["passed"] == 1
        assert s["failed"] == 1
        assert s["errors"] == 1
        assert s["total_mismatches"] == 1

    def test_empty_results(self):
        s = compute_summary([])
        assert s["total_combinations"] == 0
        assert s["overall_match_pct"] == 0.0


# ------------------------------------------------------------------ #
#  ValidationResult property tests                                     #
# ------------------------------------------------------------------ #


class TestValidationResultProperties:
    """Tests for status and worst_diff properties."""

    def test_status_pass(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
        )
        assert r.status == "✅"

    def test_status_error(self):
        r = ValidationResult(
            ticker="XYZ",
            timeframe="daily",
            our_bar_count=0,
            tv_bar_count=0,
            overlapping_bars=0,
            error="Not found",
        )
        assert r.status == "❌"

    def test_status_warning(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
            mismatches=[
                CandleMismatch("AAPL", "daily", "2026-01-15", "close", 150.0, 148.0, 1.35),
            ],
        )
        assert r.status == "⚠️"

    def test_worst_diff_no_mismatches(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
        )
        assert r.worst_diff == "—"

    def test_worst_diff_with_mismatches(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
            mismatches=[
                CandleMismatch("AAPL", "daily", "2026-01-15", "close", 150.0, 148.0, 1.35),
                CandleMismatch("AAPL", "daily", "2026-01-15", "open", 152.0, 148.0, 2.70),
            ],
        )
        assert "open" in r.worst_diff  # 2.70% > 1.35%, so open is worst
        assert "2.70" in r.worst_diff

    def test_group_default(self):
        r = ValidationResult(
            ticker="AAPL",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
        )
        assert r.group == "fixed"

    def test_group_custom(self):
        r = ValidationResult(
            ticker="XYZ",
            timeframe="daily",
            our_bar_count=100,
            tv_bar_count=100,
            overlapping_bars=100,
            group="random",
        )
        assert r.group == "random"
