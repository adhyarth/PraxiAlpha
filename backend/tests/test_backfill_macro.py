"""
PraxiAlpha — Macro Backfill Tests

Unit tests for the macro backfill logic in scripts/backfill_data.py.
Uses mocks to avoid hitting the real FRED API or database.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from backend.models.macro import FRED_SERIES


class TestBackfillMacroData:
    """Tests for the backfill_macro_data function."""

    @pytest.fixture
    def sample_fred_df(self):
        """A sample DataFrame resembling FRED API output."""
        return pd.DataFrame(
            {
                "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "value": [4.1, 4.2, 4.3],
                "series_id": ["DGS10", "DGS10", "DGS10"],
            }
        )

    @pytest.fixture
    def empty_fred_df(self):
        """An empty DataFrame (no data returned)."""
        return pd.DataFrame()

    @pytest.fixture
    def fred_df_with_nulls(self):
        """A DataFrame with NaN values (FRED returns '.' for missing)."""
        return pd.DataFrame(
            {
                "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
                "value": [4.1, float("nan"), 4.3],
                "series_id": ["DGS10", "DGS10", "DGS10"],
            }
        )

    @pytest.mark.asyncio
    async def test_backfill_macro_calls_fetcher_for_all_series(self, sample_fred_df):
        """backfill_macro_data should call fetch_series for every FRED_SERIES entry."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory") as MockSession,
        ):
            mock_fetcher = AsyncMock()
            mock_fetcher.fetch_series = AsyncMock(return_value=sample_fred_df)
            mock_fetcher.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher

            # Mock the DB session to avoid real database calls
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            from scripts.backfill_data import backfill_macro_data

            await backfill_macro_data()

            assert mock_fetcher.fetch_series.call_count == len(FRED_SERIES)
            mock_fetcher.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backfill_macro_skips_empty_series(self, empty_fred_df, sample_fred_df):
        """Empty DataFrames should be skipped and counted as failed."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory") as MockSession,
        ):
            mock_fetcher = AsyncMock()
            # First call returns empty, rest return data
            mock_fetcher.fetch_series = AsyncMock(
                side_effect=[empty_fred_df] + [sample_fred_df] * (len(FRED_SERIES) - 1)
            )
            mock_fetcher.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            from scripts.backfill_data import backfill_macro_data

            await backfill_macro_data()

            # All 14 series should be attempted
            assert mock_fetcher.fetch_series.call_count == len(FRED_SERIES)

    @pytest.mark.asyncio
    async def test_backfill_macro_handles_fetch_exception(self, sample_fred_df):
        """An exception during fetch_series should be caught and logged, not crash."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory") as MockSession,
        ):
            mock_fetcher = AsyncMock()
            # First call raises, rest succeed
            mock_fetcher.fetch_series = AsyncMock(
                side_effect=[Exception("API timeout")] + [sample_fred_df] * (len(FRED_SERIES) - 1)
            )
            mock_fetcher.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            MockSession.return_value = mock_session

            from scripts.backfill_data import backfill_macro_data

            # Should NOT raise — errors are caught per-series
            await backfill_macro_data()
            mock_fetcher.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backfill_macro_filters_null_values(self, fred_df_with_nulls):
        """Records with NaN values should be filtered out before DB insert."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory") as MockSession,
        ):
            mock_fetcher = AsyncMock()
            mock_fetcher.fetch_series = AsyncMock(return_value=fred_df_with_nulls)
            mock_fetcher.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher

            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock()
            mock_session.commit = AsyncMock()
            MockSession.return_value = mock_session

            from scripts.backfill_data import backfill_macro_data

            await backfill_macro_data()

            # fred_df_with_nulls has 3 rows per series (1 NaN).
            # build_macro_records filters nulls → 2 records per series.
            # Verify execute was called (records were inserted).
            assert mock_session.execute.call_count > 0

            # Verify that build_macro_records correctly filters nulls
            # by calling it directly with the same input.
            from scripts.backfill_data import build_macro_records

            records = build_macro_records(fred_df_with_nulls, "DGS10", "test")
            assert len(records) == 2
            for r in records:
                assert r["value"] is not None

            mock_fetcher.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backfill_macro_closes_fetcher_on_error(self, sample_fred_df):
        """The FREDFetcher should always be closed, even if an unexpected error occurs."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory"),
        ):
            mock_fetcher = AsyncMock()
            mock_fetcher.fetch_series = AsyncMock(side_effect=Exception("Total failure"))
            mock_fetcher.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher

            from scripts.backfill_data import backfill_macro_data

            # The outer try/finally should ensure close is called
            # (the per-series try/except will catch individual errors,
            #  but fetch_series raising for ALL series means the
            #  function still completes and calls close)
            await backfill_macro_data()
            mock_fetcher.close.assert_called_once()


class TestBackfillMacroRecordBuilding:
    """Tests for the build_macro_records helper function."""

    def test_null_values_filtered(self):
        """Records should only include non-null values."""
        from scripts.backfill_data import build_macro_records

        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "value": [4.1, float("nan"), 4.3],
            }
        )
        records = build_macro_records(df, "DGS10", "10-Year Treasury Yield")
        assert len(records) == 2
        assert records[0]["value"] == 4.1
        assert records[1]["value"] == 4.3

    def test_record_fields_complete(self):
        """Each record should have all required fields for MacroData."""
        from scripts.backfill_data import build_macro_records

        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1)],
                "value": [4.1],
            }
        )
        records = build_macro_records(df, "DGS10", "10-Year Treasury Yield")
        required_keys = {"indicator_code", "indicator_name", "date", "value", "source"}
        assert len(records) == 1
        assert set(records[0].keys()) == required_keys
        assert records[0]["indicator_code"] == "DGS10"
        assert records[0]["indicator_name"] == "10-Year Treasury Yield"
        assert records[0]["source"] == "FRED"

    def test_value_cast_to_float(self):
        """Values should be cast to Python float for database insertion."""
        import numpy as np

        from scripts.backfill_data import build_macro_records

        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1)],
                "value": [np.float64(4.12345)],
            }
        )
        records = build_macro_records(df, "DGS10", "10-Year Treasury Yield")
        assert isinstance(records[0]["value"], float)
        assert records[0]["value"] == pytest.approx(4.12345)

    def test_all_null_returns_empty(self):
        """A DataFrame with all NaN values should produce zero records."""
        from scripts.backfill_data import build_macro_records

        df = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2)],
                "value": [float("nan"), float("nan")],
            }
        )
        records = build_macro_records(df, "DGS10", "10-Year Treasury Yield")
        assert len(records) == 0

    def test_empty_df_returns_empty(self):
        """An empty DataFrame should produce zero records."""
        from scripts.backfill_data import build_macro_records

        df = pd.DataFrame()
        records = build_macro_records(df, "DGS10", "10-Year Treasury Yield")
        assert len(records) == 0
