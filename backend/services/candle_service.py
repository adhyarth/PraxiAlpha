"""
PraxiAlpha — Candle Service

Provides unified access to OHLCV candle data across all timeframes:
daily, weekly, monthly, and quarterly.

Daily data comes from the `daily_ohlcv` hypertable.
Weekly/monthly/quarterly come from TimescaleDB continuous aggregates.
"""

import logging
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class Timeframe(StrEnum):
    """Supported candle timeframes."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


# Map timeframe to the table/view name
_TIMEFRAME_TABLE = {
    Timeframe.DAILY: "daily_ohlcv",
    Timeframe.WEEKLY: "weekly_ohlcv",
    Timeframe.MONTHLY: "monthly_ohlcv",
    Timeframe.QUARTERLY: "quarterly_ohlcv",
}

# The date column name differs: daily uses "date", aggregates use "bucket"
_DATE_COLUMN = {
    Timeframe.DAILY: "date",
    Timeframe.WEEKLY: "bucket",
    Timeframe.MONTHLY: "bucket",
    Timeframe.QUARTERLY: "bucket",
}


class CandleService:
    """
    Service for querying OHLCV candle data across timeframes.

    All queries go through raw SQL against the hypertable or continuous
    aggregates for maximum performance. No ORM overhead for read-heavy
    charting queries.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_candles(
        self,
        stock_id: int,
        timeframe: Timeframe = Timeframe.DAILY,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Fetch OHLCV candles for a stock in the specified timeframe.

        Args:
            stock_id: The stock's database ID
            timeframe: daily, weekly, monthly, or quarterly
            start: Start date filter (inclusive)
            end: End date filter (inclusive)
            limit: Maximum number of candles to return (most recent N)

        Returns:
            List of candle dicts, ordered by date ascending (oldest → newest).
            Internally selects the last `limit` rows by date DESC, then
            re-sorts ascending for charting libraries.
            Each dict has: date, open, high, low, close, adjusted_close,
            volume, and (for aggregates) trading_days.
        """
        table = _TIMEFRAME_TABLE[timeframe]
        date_col = _DATE_COLUMN[timeframe]

        # Build query
        extra_cols = ", trading_days" if timeframe != Timeframe.DAILY else ""
        where_clauses = ["stock_id = :stock_id"]
        params: dict[str, Any] = {"stock_id": stock_id, "limit": limit}

        if start:
            where_clauses.append(f"{date_col} >= :start")
            params["start"] = start
        if end:
            where_clauses.append(f"{date_col} <= :end")
            params["end"] = end

        where_sql = " AND ".join(where_clauses)

        # Use a subquery to get the last N rows, then re-sort ascending
        query = text(f"""
            SELECT * FROM (
                SELECT
                    {date_col} AS date,
                    open, high, low, close, adjusted_close, volume
                    {extra_cols}
                FROM {table}
                WHERE {where_sql}
                ORDER BY {date_col} DESC
                LIMIT :limit
            ) sub
            ORDER BY date ASC
        """)

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        candles = []
        for row in rows:
            candle: dict[str, Any] = {
                "date": row.date.isoformat() if hasattr(row.date, "isoformat") else str(row.date),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "adjusted_close": float(row.adjusted_close),
                "volume": int(row.volume),
            }
            if timeframe != Timeframe.DAILY:
                candle["trading_days"] = int(row.trading_days)
            candles.append(candle)

        return candles

    async def get_latest_candle(
        self,
        stock_id: int,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> dict[str, Any] | None:
        """Get the most recent candle for a stock in the given timeframe."""
        candles = await self.get_candles(stock_id, timeframe, limit=1)
        return candles[0] if candles else None

    async def get_candle_summary(
        self,
        stock_id: int,
    ) -> dict[str, dict[str, Any]]:
        """
        Get count + date range for all timeframes in one query per timeframe.

        Combines count, min, and max into a single query per timeframe to
        reduce DB round-trips (was 2 queries × 4 timeframes = 8, now 4 total).
        """
        summary: dict[str, dict[str, Any]] = {}
        for tf in Timeframe:
            table = _TIMEFRAME_TABLE[tf]
            date_col = _DATE_COLUMN[tf]
            result = await self.session.execute(
                text(
                    f"SELECT count(*) AS cnt, "
                    f"min({date_col}) AS earliest, "
                    f"max({date_col}) AS latest "
                    f"FROM {table} WHERE stock_id = :stock_id"
                ),
                {"stock_id": stock_id},
            )
            row = result.fetchone()
            if row and row.earliest is not None:
                summary[tf.value] = {
                    "count": row.cnt,
                    "earliest": row.earliest.isoformat(),
                    "latest": row.latest.isoformat(),
                }
            else:
                summary[tf.value] = {
                    "count": 0,
                    "earliest": None,
                    "latest": None,
                }
        return summary

    async def get_candle_count(
        self,
        stock_id: int,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> int:
        """Count the number of candles for a stock in the given timeframe."""
        table = _TIMEFRAME_TABLE[timeframe]
        result = await self.session.execute(
            text(f"SELECT count(*) FROM {table} WHERE stock_id = :stock_id"),
            {"stock_id": stock_id},
        )
        return result.scalar() or 0

    async def get_date_range(
        self,
        stock_id: int,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> dict[str, str | None]:
        """Get the earliest and latest date for a stock's candle data."""
        table = _TIMEFRAME_TABLE[timeframe]
        date_col = _DATE_COLUMN[timeframe]
        result = await self.session.execute(
            text(
                f"SELECT min({date_col}) AS earliest, max({date_col}) AS latest "
                f"FROM {table} WHERE stock_id = :stock_id"
            ),
            {"stock_id": stock_id},
        )
        row = result.fetchone()
        if not row or row.earliest is None:
            return {"earliest": None, "latest": None}
        return {
            "earliest": row.earliest.isoformat(),
            "latest": row.latest.isoformat(),
        }

    async def get_aggregate_stats(self) -> dict[str, Any]:
        """
        Get approximate row counts and freshness for all candle views.

        Uses pg_class.reltuples for O(1) approximate counts instead of
        exact count(*) which would scan millions of rows.
        Also returns the latest bucket/date per view as a freshness signal.
        """
        stats: dict[str, Any] = {}
        for tf in Timeframe:
            table = _TIMEFRAME_TABLE[tf]
            date_col = _DATE_COLUMN[tf]

            # Approximate row count from pg_class (updated by ANALYZE/autovacuum)
            count_result = await self.session.execute(
                text(
                    "SELECT reltuples::bigint AS approx_count FROM pg_class WHERE relname = :table"
                ),
                {"table": table},
            )
            count_row = count_result.fetchone()
            approx_count = int(count_row.approx_count) if count_row else 0

            # Latest date as freshness signal (cheap — hits the index)
            latest_result = await self.session.execute(
                text(f"SELECT max({date_col}) AS latest FROM {table}")
            )
            latest_row = latest_result.fetchone()
            latest = latest_row.latest.isoformat() if latest_row and latest_row.latest else None

            stats[tf.value] = {
                "approx_rows": max(approx_count, 0),
                "latest": latest,
            }
        return stats
