"""
PraxiAlpha — Candle Service

Provides unified access to OHLCV candle data across all timeframes:
daily, weekly, monthly, and quarterly.

Daily data comes from the ``daily_ohlcv`` hypertable.
Weekly/monthly/quarterly come from TimescaleDB continuous aggregates
when ``adjusted=False`` (raw prices).  When ``adjusted=True``, non-daily
candles are **rebuilt from split-adjusted daily data in Python** using pandas
``resample()`` so that split adjustments are applied correctly.
The SQL aggregates operate on raw daily prices, which means a stock split
mid-week (or mid-month) produces a bucket that mixes pre- and post-split
values — e.g. a weekly bar whose open is $248 (pre-split) and close is
$124 (post-split).  Rebuilding from adjusted dailies eliminates this.

Split adjustment (split-only, no dividend adjustment)
-----------------------------------------------------
When ``adjusted=True`` (the default), OHLC prices are retroactively adjusted
for stock splits **only** — not dividends.  This matches TradingView's
default behavior.

The adjustment factor is computed from the ``stock_splits`` table:
for each candle, we compute the cumulative product of all split ratios
that occur *after* that date.  For example, if SMH had a 2:1 split on
2023-05-05, all pre-split candles get factor = 0.5 (prices halved, volume
doubled).  Post-split candles get factor = 1.0 (no change).

This approach was chosen over the EODHD ``adjusted_close`` column because
``adjusted_close`` includes *both* split and dividend adjustments.  Dividend
adjustment pulls historical prices down by ~1-2% per year of cumulative
dividends, causing our charts to diverge from TradingView, Yahoo Finance,
and Bloomberg (which all default to split-only adjustment).

For non-daily timeframes (weekly, monthly, quarterly), when ``adjusted=True``
the service fetches enough split-adjusted daily candles, then re-aggregates
them into the requested timeframe in Python.  When ``adjusted=False``, the
pre-computed TimescaleDB continuous aggregates are returned as-is (raw prices).
"""

import logging
from datetime import date
from enum import StrEnum
from functools import reduce
from typing import Any

import pandas as pd
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

# pandas resample rules for each non-daily timeframe
# 'W-SUN' = week ending Sunday → groups Mon–Fri together (matches our
#           TimescaleDB origin='2026-01-05', a Monday, where each 7-day
#           bucket starts on Monday).
# 'MS'    = month start (calendar month)
# 'QS'    = quarter start (calendar quarter)
_RESAMPLE_RULE = {
    Timeframe.WEEKLY: "W-SUN",
    Timeframe.MONTHLY: "MS",
    Timeframe.QUARTERLY: "QS",
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

    # ------------------------------------------------------------------ #
    #  Split factor computation                                           #
    # ------------------------------------------------------------------ #

    async def _get_split_factors(
        self,
        stock_id: int,
    ) -> list[tuple[date, float]]:
        """
        Fetch all splits for a stock and return a list of (split_date, ratio).

        Each entry represents a split event.  The ``ratio`` is
        ``numerator / denominator`` — e.g. 2.0 for a 2:1 split (each
        pre-split share becomes 2 post-split shares, so pre-split prices
        are divided by 2).
        """
        result = await self.session.execute(
            text(
                "SELECT date, numerator, denominator "
                "FROM stock_splits "
                "WHERE stock_id = :stock_id "
                "ORDER BY date ASC"
            ),
            {"stock_id": stock_id},
        )
        splits = []
        for row in result.fetchall():
            denom = float(row.denominator) if row.denominator else 1.0
            ratio = float(row.numerator) / denom
            splits.append((row.date, ratio))
        return splits

    def _compute_cumulative_split_factor(
        self,
        candle_date: date,
        splits: list[tuple[date, float]],
    ) -> float:
        """
        Compute the cumulative split adjustment factor for a candle.

        The factor is the product of ``1 / ratio`` for every split that
        occurs **after** ``candle_date``.  For a candle on or after the
        last split, the factor is 1.0 (no adjustment).

        Example: SMH 2:1 split on 2023-05-05.
        - Candle on 2023-05-04 (pre-split): factor = 1/2 = 0.5
        - Candle on 2023-05-05 (split day, post-split): factor = 1.0
        """
        future_ratios = [ratio for split_date, ratio in splits if split_date > candle_date]
        if not future_ratios:
            return 1.0
        return reduce(lambda a, b: a * b, (1.0 / r for r in future_ratios), 1.0)

    async def get_candles(
        self,
        stock_id: int,
        timeframe: Timeframe = Timeframe.DAILY,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
        adjusted: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Fetch OHLCV candles for a stock in the specified timeframe.

        Args:
            stock_id: The stock's database ID
            timeframe: daily, weekly, monthly, or quarterly
            start: Start date filter (inclusive)
            end: End date filter (inclusive)
            limit: Maximum number of candles to return (most recent N)
            adjusted: If True (default), apply **split-only** adjustment to
                OHLC prices using the cumulative split factor computed from
                the ``stock_splits`` table.  Dividends are NOT included —
                this matches TradingView / Yahoo / Bloomberg defaults.
                For daily candles, each row is adjusted individually.  For
                non-daily timeframes, **adjusted daily candles are fetched
                and re-aggregated in Python** using pandas ``resample()``
                so that split boundaries within a bucket are handled
                correctly.  When ``adjusted=False``, non-daily timeframes
                return the pre-computed SQL aggregates (raw prices).

        Returns:
            List of candle dicts, ordered by date ascending (oldest → newest).
            Each dict has: date, open, high, low, close, adjusted_close,
            volume, and (for non-daily timeframes) trading_days.
        """
        # For non-daily timeframes with adjustment, rebuild from adjusted
        # daily data to avoid split-boundary corruption in SQL aggregates.
        if adjusted and timeframe != Timeframe.DAILY:
            return await self._get_adjusted_aggregate_candles(
                stock_id, timeframe, start=start, end=end, limit=limit
            )

        # Daily candles, or non-daily with adjusted=False → query directly
        return await self._get_candles_from_table(
            stock_id, timeframe, start=start, end=end, limit=limit, adjusted=adjusted
        )

    # ------------------------------------------------------------------ #
    #  Private: query a single table/view and optionally adjust           #
    # ------------------------------------------------------------------ #

    async def _get_candles_from_table(
        self,
        stock_id: int,
        timeframe: Timeframe,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
        adjusted: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Low-level fetch from a single table/view.

        For daily candles with ``adjusted=True``, applies split-only
        adjustment using the cumulative factor from ``stock_splits``.
        For non-daily or ``adjusted=False``, returns raw prices.
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

        # Pre-fetch splits if adjustment is needed
        splits: list[tuple[date, float]] = []
        if adjusted and timeframe == Timeframe.DAILY:
            splits = await self._get_split_factors(stock_id)

        candles = []
        for row in rows:
            raw_close = float(row.close)
            adj_close = float(row.adjusted_close)

            apply_adj = adjusted and timeframe == Timeframe.DAILY

            if apply_adj and splits:
                candle_date = (
                    row.date if isinstance(row.date, date) else date.fromisoformat(str(row.date))
                )
                factor = self._compute_cumulative_split_factor(candle_date, splits)

                adj_volume = (
                    int(round(row.volume / factor))
                    if factor != 1.0 and factor != 0
                    else int(row.volume)
                )

                candle: dict[str, Any] = {
                    "date": row.date.isoformat()
                    if hasattr(row.date, "isoformat")
                    else str(row.date),
                    "open": round(float(row.open) * factor, 4),
                    "high": round(float(row.high) * factor, 4),
                    "low": round(float(row.low) * factor, 4),
                    "close": round(raw_close * factor, 4),
                    "adjusted_close": round(adj_close, 4),
                    "volume": adj_volume,
                }
            elif apply_adj:
                # No splits for this stock — return raw prices unchanged
                candle = {
                    "date": row.date.isoformat()
                    if hasattr(row.date, "isoformat")
                    else str(row.date),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": raw_close,
                    "adjusted_close": adj_close,
                    "volume": int(row.volume),
                }
            else:
                candle = {
                    "date": row.date.isoformat()
                    if hasattr(row.date, "isoformat")
                    else str(row.date),
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": raw_close,
                    "adjusted_close": adj_close,
                    "volume": int(row.volume),
                }
            if timeframe != Timeframe.DAILY:
                candle["trading_days"] = int(row.trading_days)
            candles.append(candle)

        return candles

    # ------------------------------------------------------------------ #
    #  Private: build adjusted aggregate candles from adjusted dailies    #
    # ------------------------------------------------------------------ #

    async def _get_adjusted_aggregate_candles(
        self,
        stock_id: int,
        timeframe: Timeframe,
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Build adjusted weekly/monthly/quarterly candles by fetching adjusted
        daily data and re-aggregating in Python with pandas ``resample()``.

        The SQL continuous aggregates (``weekly_ohlcv``, etc.) operate on raw
        daily prices.  If a stock split occurs mid-bucket, the resulting bar
        mixes pre- and post-split values (e.g. weekly open=$248, close=$124).
        By adjusting at the daily level first and then aggregating, every
        field in the output bar is self-consistent.
        """
        rule = _RESAMPLE_RULE[timeframe]

        # We need enough daily candles to produce `limit` aggregate bars.
        # Rough multipliers: weekly ≈ 5 trading days, monthly ≈ 21, quarterly ≈ 63.
        daily_multiplier = {
            Timeframe.WEEKLY: 5,
            Timeframe.MONTHLY: 21,
            Timeframe.QUARTERLY: 63,
        }
        daily_limit = limit * daily_multiplier[timeframe] + 10  # small buffer

        # Fetch adjusted daily candles (adjustment applied per-row)
        daily_candles = await self._get_candles_from_table(
            stock_id,
            Timeframe.DAILY,
            start=start,
            end=end,
            limit=daily_limit,
            adjusted=True,
        )

        if not daily_candles:
            return []

        # Build DataFrame
        df = pd.DataFrame(daily_candles)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # Resample into the target timeframe
        agg = df.resample(rule).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "adjusted_close": "last",
                "volume": "sum",
            }
        )

        # Count trading days per bucket
        agg["trading_days"] = df["close"].resample(rule).count()

        # Drop any buckets with no trading data (e.g. future dates, holidays)
        agg = agg.dropna(subset=["close"])

        # Trim to the last `limit` bars
        agg = agg.tail(limit)

        # Convert back to list of dicts
        candles = []
        for dt, row in agg.iterrows():
            candles.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "open": round(float(row["open"]), 4),
                    "high": round(float(row["high"]), 4),
                    "low": round(float(row["low"]), 4),
                    "close": round(float(row["close"]), 4),
                    "adjusted_close": round(float(row["adjusted_close"]), 4),
                    "volume": int(row["volume"]),
                    "trading_days": int(row["trading_days"]),
                }
            )

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
