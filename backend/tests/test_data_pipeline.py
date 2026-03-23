"""
PraxiAlpha — Data Pipeline Tests

Tests for EODHD fetcher, FRED fetcher, data validator, and OHLCV gap-fill logic.
"""

import importlib.util
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from backend.models.macro import FRED_SERIES
from backend.services.data_pipeline.data_validator import DataValidator

# Celery is not installed in the lightweight CI test environment.
# Guard the import so the rest of the test file still runs.
_has_celery = importlib.util.find_spec("celery") is not None
if _has_celery:
    from backend.tasks.data_tasks import _candidate_dates, _fetch_and_upsert_date


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


# ============================================================
# daily_ohlcv_update gap-fill logic
# ============================================================


@pytest.mark.skipif(not _has_celery, reason="celery not installed")
class TestCandidateDates:
    """Tests for the _candidate_dates helper."""

    def test_no_gap(self):
        """Same day → no candidates."""
        today = date(2026, 3, 23)
        assert _candidate_dates(today, today) == []

    def test_single_weekday_gap(self):
        """One weekday missing → one candidate."""
        # Monday → Tuesday
        last = date(2026, 3, 23)  # Monday
        today = date(2026, 3, 24)  # Tuesday
        result = _candidate_dates(last, today)
        assert result == [date(2026, 3, 24)]

    def test_weekend_skipped(self):
        """Friday → Monday should produce only Monday."""
        last = date(2026, 3, 20)  # Friday
        today = date(2026, 3, 23)  # Monday
        result = _candidate_dates(last, today)
        assert result == [date(2026, 3, 23)]

    def test_multi_day_gap(self):
        """Wednesday → next Tuesday = Thu, Fri, Mon, Tue (skip Sat/Sun)."""
        last = date(2026, 3, 18)  # Wednesday
        today = date(2026, 3, 24)  # Tuesday
        result = _candidate_dates(last, today)
        assert result == [
            date(2026, 3, 19),  # Thu
            date(2026, 3, 20),  # Fri
            date(2026, 3, 23),  # Mon
            date(2026, 3, 24),  # Tue
        ]

    def test_full_week_gap(self):
        """7-day gap should produce 5 weekdays."""
        last = date(2026, 3, 16)  # Monday
        today = date(2026, 3, 23)  # Monday (next week)
        result = _candidate_dates(last, today)
        assert len(result) == 5
        for d in result:
            assert d.weekday() < 5  # all weekdays

    def test_saturday_to_monday(self):
        """last_known on Saturday → only Monday returned."""
        last = date(2026, 3, 21)  # Saturday
        today = date(2026, 3, 23)  # Monday
        result = _candidate_dates(last, today)
        assert result == [date(2026, 3, 23)]


@pytest.mark.skipif(not _has_celery, reason="celery not installed")
class TestFetchAndUpsertDate:
    """Tests for the _fetch_and_upsert_date helper."""

    @pytest.mark.asyncio
    async def test_empty_bulk_returns_zero(self):
        """Holiday/weekend with no data → 0 upserted, 0 skipped."""
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_bulk_eod.return_value = pd.DataFrame()

        mock_session_factory = AsyncMock()

        result = await _fetch_and_upsert_date(
            mock_fetcher,
            date(2026, 3, 21),  # Saturday
            {"AAPL": 1},
            mock_session_factory,
        )
        assert result == {"upserted": 0, "skipped": 0}
        mock_fetcher.fetch_bulk_eod.assert_awaited_once_with(exchange="US", date_str="2026-03-21")

    @pytest.mark.asyncio
    async def test_upserts_known_tickers_skips_unknown(self):
        """Bulk data with 2 known + 1 unknown ticker → 2 upserted, 1 skipped."""
        bulk_df = pd.DataFrame(
            {
                "code": ["AAPL", "MSFT", "ZZZZ"],
                "date": ["2026-03-23", "2026-03-23", "2026-03-23"],
                "open": [150.0, 300.0, 10.0],
                "high": [155.0, 305.0, 11.0],
                "low": [149.0, 299.0, 9.0],
                "close": [153.0, 303.0, 10.5],
                "adjusted_close": [153.0, 303.0, 10.5],
                "volume": [1000000, 2000000, 100],
            }
        )
        mock_fetcher = AsyncMock()
        mock_fetcher.fetch_bulk_eod.return_value = bulk_df

        # Mock the async context manager for session
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session_ctx)

        ticker_to_id = {"AAPL": 1, "MSFT": 2}  # ZZZZ not in DB

        # Patch the model imports inside _fetch_and_upsert_date
        # Simpler approach: just verify the function can be called and
        # returns the right counts by mocking at a higher level
        result = await _fetch_and_upsert_date(
            mock_fetcher,
            date(2026, 3, 23),
            ticker_to_id,
            mock_factory,
        )

        assert result["upserted"] == 2
        assert result["skipped"] == 1


@pytest.mark.skipif(not _has_celery, reason="celery not installed")
class TestDailyOhlcvUpdateGapFill:
    """Integration-style tests for the gap-fill task logic."""

    def test_already_up_to_date(self):
        """When last_known == today, there should be no candidate dates."""
        today = date.today()

        candidates = _candidate_dates(today, today)
        assert candidates == []

    def test_gap_capped_at_max(self):
        """Gap > max_gap_days should be capped."""
        today = date(2026, 3, 23)
        last_known = date(2025, 1, 1)  # ~447 days ago
        max_gap = 60
        gap = (today - last_known).days
        assert gap > max_gap

        # After capping
        capped_last = today - timedelta(days=max_gap)
        candidates = _candidate_dates(capped_last, today)
        # Should be roughly 42-43 weekdays in 60 calendar days
        assert 40 <= len(candidates) <= 44
        for d in candidates:
            assert d.weekday() < 5

    def test_five_day_outage_produces_correct_candidates(self):
        """Worker down Mon–Fri: Saturday run should fill Mon–Fri (5 days)."""
        last_known = date(2026, 3, 13)  # Friday before
        today = date(2026, 3, 20)  # Friday (one week later)
        candidates = _candidate_dates(last_known, today)
        assert len(candidates) == 5
        assert candidates[0] == date(2026, 3, 16)  # Monday
        assert candidates[-1] == date(2026, 3, 20)  # Friday

    def test_holiday_in_gap_still_produces_candidate(self):
        """Holidays are weekdays, so they appear in candidates.
        The actual skip happens when fetch_bulk_eod returns empty."""
        # President's Day 2026 is Monday Feb 16
        last_known = date(2026, 2, 13)  # Friday
        today = date(2026, 2, 17)  # Tuesday
        candidates = _candidate_dates(last_known, today)
        # Mon + Tue = 2 candidates (holiday is still a weekday)
        assert len(candidates) == 2
        assert date(2026, 2, 16) in candidates  # holiday Monday — will return empty
        assert date(2026, 2, 17) in candidates
