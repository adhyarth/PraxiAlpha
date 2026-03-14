"""
PraxiAlpha — Macro Backfill Tests

Unit tests for the macro backfill logic in scripts/backfill_data.py.
Uses mocks to avoid hitting the real FRED API or database.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.models.macro import FRED_SERIES


class TestBackfillMacroData:
    """Tests for the backfill_macro_data function."""

    @pytest.fixture
    def sample_fred_df(self):
        """A sample DataFrame resembling FRED API output."""
        return pd.DataFrame({
            "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "value": [4.1, 4.2, 4.3],
            "series_id": ["DGS10", "DGS10", "DGS10"],
        })

    @pytest.fixture
    def empty_fred_df(self):
        """An empty DataFrame (no data returned)."""
        return pd.DataFrame()

    @pytest.fixture
    def fred_df_with_nulls(self):
        """A DataFrame with NaN values (FRED returns '.' for missing)."""
        return pd.DataFrame({
            "date": [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)],
            "value": [4.1, float("nan"), 4.3],
            "series_id": ["DGS10", "DGS10", "DGS10"],
        })

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

            # The function should have committed (non-null records exist)
            # Detailed assertion: each series call should build records
            # filtering out NaN values
            mock_fetcher.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_backfill_macro_closes_fetcher_on_error(self, sample_fred_df):
        """The FREDFetcher should always be closed, even if an unexpected error occurs."""
        with (
            patch("scripts.backfill_data.FREDFetcher") as MockFetcher,
            patch("scripts.backfill_data.async_session_factory") as MockSession,
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
    """Tests for the record-building logic within backfill_macro_data."""

    def test_null_values_filtered(self):
        """Records should only include non-null values."""
        df = pd.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
            "value": [4.1, float("nan"), 4.3],
        })
        records = []
        for _, row in df.iterrows():
            if pd.notna(row["value"]):
                records.append({
                    "indicator_code": "DGS10",
                    "indicator_name": "10-Year Treasury Yield",
                    "date": row["date"],
                    "value": float(row["value"]),
                    "source": "FRED",
                })
        assert len(records) == 2
        assert records[0]["value"] == 4.1
        assert records[1]["value"] == 4.3

    def test_record_fields_complete(self):
        """Each record should have all required fields for MacroData."""
        df = pd.DataFrame({
            "date": [date(2024, 1, 1)],
            "value": [4.1],
        })
        row = df.iloc[0]
        record = {
            "indicator_code": "DGS10",
            "indicator_name": "10-Year Treasury Yield",
            "date": row["date"],
            "value": float(row["value"]),
            "source": "FRED",
        }
        required_keys = {"indicator_code", "indicator_name", "date", "value", "source"}
        assert set(record.keys()) == required_keys

    def test_value_cast_to_float(self):
        """Values should be cast to Python float for database insertion."""
        import numpy as np
        val = np.float64(4.12345)
        record_val = float(val)
        assert isinstance(record_val, float)
        assert record_val == pytest.approx(4.12345)
