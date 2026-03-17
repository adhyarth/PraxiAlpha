"""
PraxiAlpha — Candle Service & API Tests

Tests for the candle service layer and chart API endpoints.
These tests mock the database layer to avoid needing actual TimescaleDB
continuous aggregates in the CI environment.
"""

import importlib.util
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.candle_service import CandleService, Timeframe


# ============================================================
# Timeframe Enum Tests
# ============================================================
class TestTimeframe:
    """Tests for the Timeframe enum."""

    def test_daily_value(self):
        assert Timeframe.DAILY.value == "daily"

    def test_weekly_value(self):
        assert Timeframe.WEEKLY.value == "weekly"

    def test_monthly_value(self):
        assert Timeframe.MONTHLY.value == "monthly"

    def test_quarterly_value(self):
        assert Timeframe.QUARTERLY.value == "quarterly"

    def test_all_timeframes(self):
        assert len(Timeframe) == 4

    def test_from_string(self):
        assert Timeframe("daily") == Timeframe.DAILY
        assert Timeframe("weekly") == Timeframe.WEEKLY
        assert Timeframe("monthly") == Timeframe.MONTHLY
        assert Timeframe("quarterly") == Timeframe.QUARTERLY

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValueError):
            Timeframe("hourly")


# ============================================================
# CandleService Tests
# ============================================================
def _make_mock_row(
    dt: date,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    adj_close: float = 102.0,
    volume: int = 1_000_000,
    trading_days: int | None = None,
) -> MagicMock:
    """Create a mock row matching the SQL result shape."""
    row = MagicMock()
    row.date = dt
    row.open = open_
    row.high = high
    row.low = low
    row.close = close
    row.adjusted_close = adj_close
    row.volume = volume
    if trading_days is not None:
        row.trading_days = trading_days
    return row


class TestCandleService:
    """Tests for the CandleService."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        return CandleService(mock_session)

    @pytest.mark.asyncio
    async def test_get_candles_daily(self, service, mock_session):
        """Daily candles should query daily_ohlcv table."""
        rows = [
            _make_mock_row(date(2026, 3, 14), 150.0, 155.0, 148.0, 153.0, 153.0, 50_000_000),
            _make_mock_row(date(2026, 3, 15), 153.0, 158.0, 152.0, 157.0, 157.0, 45_000_000),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, timeframe=Timeframe.DAILY, limit=10)

        assert len(candles) == 2
        assert candles[0]["date"] == "2026-03-14"
        assert candles[0]["open"] == 150.0
        assert candles[0]["close"] == 153.0
        assert candles[0]["volume"] == 50_000_000
        # Daily candles should NOT have trading_days
        assert "trading_days" not in candles[0]

    @pytest.mark.asyncio
    async def test_get_candles_weekly_includes_trading_days(self, service, mock_session):
        """Weekly candles should include trading_days field."""
        rows = [
            _make_mock_row(
                date(2026, 3, 9),
                150.0,
                160.0,
                145.0,
                155.0,
                155.0,
                200_000_000,
                trading_days=5,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, timeframe=Timeframe.WEEKLY, limit=10)

        assert len(candles) == 1
        assert candles[0]["trading_days"] == 5
        assert candles[0]["close"] == 155.0

    @pytest.mark.asyncio
    async def test_get_candles_quarterly(self, service, mock_session):
        """Quarterly candles should work and include trading_days."""
        rows = [
            _make_mock_row(
                date(2026, 1, 1),
                140.0,
                165.0,
                135.0,
                160.0,
                160.0,
                3_000_000_000,
                trading_days=62,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, timeframe=Timeframe.QUARTERLY, limit=10)

        assert len(candles) == 1
        assert candles[0]["trading_days"] == 62

    @pytest.mark.asyncio
    async def test_get_candles_empty(self, service, mock_session):
        """Should return empty list when no candles exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=999, timeframe=Timeframe.DAILY)

        assert candles == []

    @pytest.mark.asyncio
    async def test_get_candles_with_date_range(self, service, mock_session):
        """Date range filters should be included in query params."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await service.get_candles(
            stock_id=1,
            timeframe=Timeframe.DAILY,
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
        )

        # Verify execute was called with proper params including start and end
        call_args = mock_session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        assert params["start"] == date(2025, 1, 1)
        assert params["end"] == date(2025, 12, 31)

    @pytest.mark.asyncio
    async def test_get_latest_candle(self, service, mock_session):
        """Should return the single most recent candle."""
        rows = [
            _make_mock_row(date(2026, 3, 16), 155.0, 160.0, 154.0, 158.0, 158.0, 60_000_000),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candle = await service.get_latest_candle(stock_id=1, timeframe=Timeframe.DAILY)

        assert candle is not None
        assert candle["date"] == "2026-03-16"
        assert candle["close"] == 158.0

    @pytest.mark.asyncio
    async def test_get_latest_candle_none(self, service, mock_session):
        """Should return None when no candles exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        candle = await service.get_latest_candle(stock_id=999)

        assert candle is None

    @pytest.mark.asyncio
    async def test_get_candle_count(self, service, mock_session):
        """Should return the row count."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 8500
        mock_session.execute.return_value = mock_result

        count = await service.get_candle_count(stock_id=1, timeframe=Timeframe.DAILY)

        assert count == 8500

    @pytest.mark.asyncio
    async def test_get_date_range(self, service, mock_session):
        """Should return earliest and latest dates."""
        mock_row = MagicMock()
        mock_row.earliest = date(1993, 2, 1)
        mock_row.latest = date(2026, 3, 16)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        dr = await service.get_date_range(stock_id=1)

        assert dr["earliest"] == "1993-02-01"
        assert dr["latest"] == "2026-03-16"

    @pytest.mark.asyncio
    async def test_get_date_range_no_data(self, service, mock_session):
        """Should return nulls when no data exists."""
        mock_row = MagicMock()
        mock_row.earliest = None
        mock_row.latest = None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        dr = await service.get_date_range(stock_id=999)

        assert dr["earliest"] is None
        assert dr["latest"] is None

    @pytest.mark.asyncio
    async def test_get_candle_summary(self, service, mock_session):
        """Should return count + date range for all timeframes in consolidated queries."""
        # 4 timeframes, 1 query each (combined count + min + max)
        mock_results = []
        for cnt, earliest, latest in [
            (8500, date(1993, 2, 1), date(2026, 3, 16)),
            (1700, date(1993, 2, 1), date(2026, 3, 10)),
            (396, date(1993, 2, 1), date(2026, 3, 1)),
            (133, date(1993, 4, 1), date(2026, 1, 1)),
        ]:
            row = MagicMock()
            row.cnt = cnt
            row.earliest = earliest
            row.latest = latest
            mr = MagicMock()
            mr.fetchone.return_value = row
            mock_results.append(mr)
        mock_session.execute.side_effect = mock_results

        summary = await service.get_candle_summary(stock_id=1)

        assert summary["daily"]["count"] == 8500
        assert summary["daily"]["earliest"] == "1993-02-01"
        assert summary["daily"]["latest"] == "2026-03-16"
        assert summary["weekly"]["count"] == 1700
        assert summary["quarterly"]["count"] == 133
        assert summary["quarterly"]["latest"] == "2026-01-01"

    @pytest.mark.asyncio
    async def test_get_candle_summary_no_data(self, service, mock_session):
        """Should return zero counts and null dates when stock has no data."""
        mock_row = MagicMock()
        mock_row.cnt = 0
        mock_row.earliest = None
        mock_row.latest = None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = mock_row
        mock_session.execute.return_value = mock_result

        summary = await service.get_candle_summary(stock_id=999)

        for tf in ["daily", "weekly", "monthly", "quarterly"]:
            assert summary[tf]["count"] == 0
            assert summary[tf]["earliest"] is None
            assert summary[tf]["latest"] is None

    @pytest.mark.asyncio
    async def test_get_aggregate_stats(self, service, mock_session):
        """Should return approximate counts and freshness for all timeframes."""
        # Each timeframe does 2 queries: pg_class approx count + max(date_col)
        mock_count_rows = [
            MagicMock(approx_count=58_000_000),
            MagicMock(approx_count=12_000_000),
            MagicMock(approx_count=3_000_000),
            MagicMock(approx_count=1_000_000),
        ]
        mock_latest_rows = [
            MagicMock(latest=date(2026, 3, 16)),
            MagicMock(latest=date(2026, 3, 10)),
            MagicMock(latest=date(2026, 3, 1)),
            MagicMock(latest=date(2026, 1, 1)),
        ]
        mock_results = []
        for count_row, latest_row in zip(mock_count_rows, mock_latest_rows, strict=True):
            # First call: pg_class query
            mr_count = MagicMock()
            mr_count.fetchone.return_value = count_row
            mock_results.append(mr_count)
            # Second call: max(date_col) query
            mr_latest = MagicMock()
            mr_latest.fetchone.return_value = latest_row
            mock_results.append(mr_latest)
        mock_session.execute.side_effect = mock_results

        stats = await service.get_aggregate_stats()

        assert stats["daily"]["approx_rows"] == 58_000_000
        assert stats["daily"]["latest"] == "2026-03-16"
        assert stats["weekly"]["approx_rows"] == 12_000_000
        assert stats["monthly"]["approx_rows"] == 3_000_000
        assert stats["quarterly"]["approx_rows"] == 1_000_000
        assert stats["quarterly"]["latest"] == "2026-01-01"


# ============================================================
# Celery Task Registration Tests
# ============================================================
class TestRefreshCandleAggregatesTask:
    """Test that the refresh_candle_aggregates Celery task is registered."""

    @pytest.mark.skipif(
        importlib.util.find_spec("celery") is None,
        reason="celery not installed in CI",
    )
    def test_task_is_registered(self):
        from backend.tasks.data_tasks import refresh_candle_aggregates

        assert callable(refresh_candle_aggregates)
