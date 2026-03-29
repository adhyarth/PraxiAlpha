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
        """Weekly candles (raw/unadjusted) should include trading_days field."""
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

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.WEEKLY, adjusted=False, limit=10
        )

        assert len(candles) == 1
        assert candles[0]["trading_days"] == 5
        assert candles[0]["close"] == 155.0

    @pytest.mark.asyncio
    async def test_get_candles_quarterly(self, service, mock_session):
        """Quarterly candles (raw/unadjusted) should work and include trading_days."""
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

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.QUARTERLY, adjusted=False, limit=10
        )

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
# Split-Adjustment Tests
# ============================================================
class TestSplitAdjustment:
    """Tests for the split-adjusted candle feature."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        return CandleService(mock_session)

    @pytest.mark.asyncio
    async def test_adjusted_applies_factor_to_ohlc(self, service, mock_session):
        """When adjusted=True, OHLC prices should be scaled by adjusted_close/close."""
        # Simulate a pre-split candle: raw close=800, adjusted_close=80 (10:1 split)
        rows = [
            _make_mock_row(
                date(2024, 6, 7),
                open_=790.0,
                high=810.0,
                low=785.0,
                close=800.0,
                adj_close=80.0,
                volume=50_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=True, limit=10)

        assert len(candles) == 1
        c = candles[0]
        # factor = 80 / 800 = 0.1
        assert c["close"] == 80.0
        assert c["open"] == round(790.0 * 0.1, 4)  # 79.0
        assert c["high"] == round(810.0 * 0.1, 4)  # 81.0
        assert c["low"] == round(785.0 * 0.1, 4)  # 78.5
        # Volume should be scaled inversely: 50M / 0.1 = 500M
        assert c["volume"] == int(50_000_000 / 0.1)

    @pytest.mark.asyncio
    async def test_unadjusted_returns_raw_prices(self, service, mock_session):
        """When adjusted=False, raw prices should be returned unchanged."""
        rows = [
            _make_mock_row(
                date(2024, 6, 7),
                open_=790.0,
                high=810.0,
                low=785.0,
                close=800.0,
                adj_close=80.0,
                volume=50_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=False, limit=10)

        assert len(candles) == 1
        c = candles[0]
        assert c["open"] == 790.0
        assert c["high"] == 810.0
        assert c["low"] == 785.0
        assert c["close"] == 800.0
        assert c["adjusted_close"] == 80.0
        assert c["volume"] == 50_000_000

    @pytest.mark.asyncio
    async def test_no_split_no_change(self, service, mock_session):
        """When close == adjusted_close, adjustment factor is 1.0 — no change."""
        rows = [
            _make_mock_row(
                date(2026, 3, 20),
                open_=150.0,
                high=155.0,
                low=148.0,
                close=153.0,
                adj_close=153.0,
                volume=40_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=True, limit=10)

        c = candles[0]
        assert c["open"] == 150.0
        assert c["high"] == 155.0
        assert c["low"] == 148.0
        assert c["close"] == 153.0
        assert c["volume"] == 40_000_000

    @pytest.mark.asyncio
    async def test_adjusted_series_is_continuous(self, service, mock_session):
        """Adjusted prices across a split boundary should be continuous."""
        # Pre-split: close=800, adj=80 (factor=0.1)
        # Post-split: close=82, adj=82 (factor=1.0)
        rows = [
            _make_mock_row(
                date(2024, 6, 7),
                open_=790.0,
                high=810.0,
                low=785.0,
                close=800.0,
                adj_close=80.0,
                volume=50_000_000,
            ),
            _make_mock_row(
                date(2024, 6, 10),
                open_=81.0,
                high=84.0,
                low=79.0,
                close=82.0,
                adj_close=82.0,
                volume=300_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=True, limit=10)

        pre_split = candles[0]
        post_split = candles[1]
        # Pre-split close (adjusted) should be in the same range as post-split
        assert pre_split["close"] == 80.0
        assert post_split["close"] == 82.0
        # No massive gap — difference should be small, not 800 vs 82
        assert abs(post_split["close"] - pre_split["close"]) < 10

    @pytest.mark.asyncio
    async def test_adjusted_default_is_true(self, service, mock_session):
        """The default value of adjusted should be True."""
        rows = [
            _make_mock_row(
                date(2024, 6, 7),
                open_=800.0,
                high=810.0,
                low=790.0,
                close=800.0,
                adj_close=80.0,
                volume=50_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        # Call without specifying adjusted — should default to True
        candles = await service.get_candles(stock_id=1, limit=10)

        c = candles[0]
        # Should be adjusted (factor 0.1)
        assert c["close"] == 80.0
        assert c["open"] == round(800.0 * 0.1, 4)

    @pytest.mark.asyncio
    async def test_zero_close_skips_adjustment(self, service, mock_session):
        """If raw close is 0, skip adjustment to avoid division by zero."""
        rows = [
            _make_mock_row(
                date(2024, 1, 1),
                open_=0.0,
                high=0.0,
                low=0.0,
                close=0.0,
                adj_close=0.0,
                volume=0,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=True, limit=10)

        c = candles[0]
        assert c["close"] == 0.0
        assert c["open"] == 0.0
        assert c["volume"] == 0

    @pytest.mark.asyncio
    async def test_dividend_adjustment(self, service, mock_session):
        """Dividend-only adjustments (small factor < 1) should adjust OHLC but NOT volume.

        Dividends don't change share count, so volume should remain unadjusted.
        Only splits (factor deviating >5% from 1.0) trigger volume scaling.
        """
        # Post-dividend: close=100, adj_close=98 (factor=0.98 due to dividend)
        rows = [
            _make_mock_row(
                date(2025, 11, 1),
                open_=99.0,
                high=101.0,
                low=98.0,
                close=100.0,
                adj_close=98.0,
                volume=10_000_000,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(stock_id=1, adjusted=True, limit=10)

        c = candles[0]
        factor = 98.0 / 100.0  # 0.98
        assert c["open"] == round(99.0 * factor, 4)
        assert c["high"] == round(101.0 * factor, 4)
        assert c["low"] == round(98.0 * factor, 4)
        assert c["close"] == round(98.0, 4)
        # Volume should NOT be scaled for dividend-only adjustments
        assert c["volume"] == 10_000_000

    @pytest.mark.asyncio
    async def test_weekly_adjusted_rebuilds_from_daily(self, service, mock_session):
        """Weekly candles with adjusted=True should be rebuilt from adjusted daily data.

        Previously, weekly candles skipped adjustment and returned the raw SQL
        aggregate.  Now they fetch adjusted daily candles and re-aggregate in
        Python so that splits mid-week produce correct bars.
        """
        # Simulate 10 adjusted daily candles spanning 2 weeks.
        # Week 1: Mon 2024-06-03 through Fri 2024-06-07
        # Week 2: Mon 2024-06-10 through Fri 2024-06-14
        # W-SUN resample groups Mon-Fri into a bucket labelled by the Sunday.
        daily_rows = [
            # Week 1 (5 trading days) — post-split prices, adj_close == close
            _make_mock_row(date(2024, 6, 3), open_=80.0, high=82.0, low=79.0, close=81.0, adj_close=81.0, volume=10_000_000),
            _make_mock_row(date(2024, 6, 4), open_=81.0, high=83.0, low=80.0, close=82.0, adj_close=82.0, volume=11_000_000),
            _make_mock_row(date(2024, 6, 5), open_=82.0, high=85.0, low=81.0, close=84.0, adj_close=84.0, volume=12_000_000),
            _make_mock_row(date(2024, 6, 6), open_=84.0, high=86.0, low=83.0, close=85.0, adj_close=85.0, volume=13_000_000),
            _make_mock_row(date(2024, 6, 7), open_=85.0, high=87.0, low=84.0, close=86.0, adj_close=86.0, volume=14_000_000),
            # Week 2 (5 trading days)
            _make_mock_row(date(2024, 6, 10), open_=86.0, high=88.0, low=85.0, close=87.0, adj_close=87.0, volume=15_000_000),
            _make_mock_row(date(2024, 6, 11), open_=87.0, high=90.0, low=86.0, close=89.0, adj_close=89.0, volume=16_000_000),
            _make_mock_row(date(2024, 6, 12), open_=89.0, high=91.0, low=88.0, close=90.0, adj_close=90.0, volume=17_000_000),
            _make_mock_row(date(2024, 6, 13), open_=90.0, high=92.0, low=89.0, close=91.0, adj_close=91.0, volume=18_000_000),
            _make_mock_row(date(2024, 6, 14), open_=91.0, high=93.0, low=90.0, close=92.0, adj_close=92.0, volume=19_000_000),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = daily_rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.WEEKLY, adjusted=True, limit=10
        )

        # Should produce 2 weekly candles, rebuilt from daily data
        assert len(candles) == 2
        w1, w2 = candles[0], candles[1]

        # Week 1: open from Monday, close from Friday, high/low from the week
        assert w1["open"] == 80.0
        assert w1["high"] == 87.0
        assert w1["low"] == 79.0
        assert w1["close"] == 86.0
        assert w1["volume"] == 60_000_000  # sum of 10+11+12+13+14
        assert w1["trading_days"] == 5

        # Week 2
        assert w2["open"] == 86.0
        assert w2["high"] == 93.0
        assert w2["low"] == 85.0
        assert w2["close"] == 92.0
        assert w2["volume"] == 85_000_000  # sum of 15+16+17+18+19
        assert w2["trading_days"] == 5

    @pytest.mark.asyncio
    async def test_weekly_unadjusted_uses_sql_aggregate(self, service, mock_session):
        """Weekly candles with adjusted=False should use the SQL aggregate as-is."""
        rows = [
            _make_mock_row(
                date(2024, 6, 3),
                open_=790.0,
                high=810.0,
                low=78.0,
                close=82.0,
                adj_close=82.0,
                volume=350_000_000,
                trading_days=5,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.WEEKLY, adjusted=False, limit=10
        )

        c = candles[0]
        # Should return raw prices from the SQL aggregate
        assert c["open"] == 790.0
        assert c["high"] == 810.0
        assert c["low"] == 78.0
        assert c["close"] == 82.0
        assert c["volume"] == 350_000_000
        assert c["trading_days"] == 5

    @pytest.mark.asyncio
    async def test_monthly_adjusted_rebuilds_from_daily(self, service, mock_session):
        """Monthly candles with adjusted=True should be rebuilt from adjusted daily data."""
        # 3 daily candles in June 2024 (simplified — just enough to test aggregation)
        daily_rows = [
            _make_mock_row(date(2024, 6, 3), open_=80.0, high=85.0, low=79.0, close=84.0, adj_close=84.0, volume=10_000_000),
            _make_mock_row(date(2024, 6, 4), open_=84.0, high=90.0, low=83.0, close=88.0, adj_close=88.0, volume=12_000_000),
            _make_mock_row(date(2024, 6, 5), open_=88.0, high=92.0, low=86.0, close=90.0, adj_close=90.0, volume=14_000_000),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = daily_rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.MONTHLY, adjusted=True, limit=10
        )

        assert len(candles) == 1
        c = candles[0]
        assert c["open"] == 80.0
        assert c["high"] == 92.0
        assert c["low"] == 79.0
        assert c["close"] == 90.0
        assert c["volume"] == 36_000_000
        assert c["trading_days"] == 3

    @pytest.mark.asyncio
    async def test_monthly_unadjusted_uses_sql_aggregate(self, service, mock_session):
        """Monthly candles with adjusted=False should use the SQL aggregate as-is."""
        rows = [
            _make_mock_row(
                date(2024, 6, 1),
                open_=800.0,
                high=900.0,
                low=75.0,
                close=85.0,
                adj_close=85.0,
                volume=1_000_000_000,
                trading_days=21,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.MONTHLY, adjusted=False, limit=10
        )

        c = candles[0]
        assert c["open"] == 800.0
        assert c["high"] == 900.0
        assert c["close"] == 85.0
        assert c["trading_days"] == 21

    @pytest.mark.asyncio
    async def test_weekly_adjusted_split_boundary(self, service, mock_session):
        """A 2:1 split mid-week should produce a correct adjusted weekly candle.

        This is the key regression test — previously, the SQL aggregate would
        mix pre-split open ($248) with post-split close ($124), producing
        a nonsensical bar.  With the fix, adjusted daily prices are used:
        pre-split days are halved, post-split days are unchanged, and the
        weekly aggregate is self-consistent.

        SMH 2:1 split on 2023-05-05 (Friday).
        Week: Mon 2023-05-01 through Fri 2023-05-05.
        Pre-split days (Mon-Thu): raw close ~248, adj_close ~122 (factor≈0.49)
        Post-split day (Fri): raw close=124.38, adj_close=122.71 (factor≈0.99)
        All adjusted prices should be in the ~120 range.
        """
        daily_rows = [
            _make_mock_row(date(2023, 5, 1), open_=247.97, high=249.92, low=247.33, close=249.14, adj_close=122.89, volume=5_202_000),
            _make_mock_row(date(2023, 5, 2), open_=249.06, high=250.36, low=245.00, close=246.98, adj_close=121.83, volume=6_717_600),
            _make_mock_row(date(2023, 5, 3), open_=245.70, high=248.60, low=244.15, close=244.43, adj_close=120.57, volume=8_223_000),
            _make_mock_row(date(2023, 5, 4), open_=243.29, high=245.64, low=241.87, close=243.61, adj_close=120.17, volume=5_889_200),
            _make_mock_row(date(2023, 5, 5), open_=122.16, high=124.97, low=121.59, close=124.38, adj_close=122.71, volume=5_553_000),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = daily_rows
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.WEEKLY, adjusted=True, limit=10
        )

        # All 5 days (Mon-Fri) fall in the same W-SUN bucket
        assert len(candles) == 1
        c = candles[0]
        # All prices should be in the ~120 range (adjusted), NOT mixing $248 and $124
        assert c["close"] == round(122.71, 4)
        assert c["open"] < 130  # adjusted open from Monday
        assert c["high"] < 130  # adjusted high, not $250!
        assert c["low"] > 100   # adjusted low, not $241!
        assert c["trading_days"] == 5

    @pytest.mark.asyncio
    async def test_adjusted_aggregate_empty(self, service, mock_session):
        """If no daily data exists, adjusted aggregate should return empty list."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        candles = await service.get_candles(
            stock_id=1, timeframe=Timeframe.WEEKLY, adjusted=True, limit=10
        )
        assert candles == []


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
