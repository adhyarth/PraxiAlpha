"""
PraxiAlpha — Create TimescaleDB Continuous Aggregates for Candle Data

Creates materialized views for weekly, monthly, and quarterly OHLCV candles
from the daily_ohlcv hypertable using TimescaleDB continuous aggregates.

These aggregates:
  - Auto-refresh incrementally (only recompute changed time buckets)
  - Are orders of magnitude faster than raw SQL GROUP BY on 58M rows
  - Maintain consistency with the underlying daily data

Usage:
    python scripts/create_candle_aggregates.py
    python scripts/create_candle_aggregates.py --drop   # Drop and recreate
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is importable
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sqlalchemy import text

from backend.database import engine

# ---- Continuous Aggregate Definitions ----
# Weekly: ISO week (Monday–Friday trading week)
WEEKLY_AGG_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS weekly_ohlcv
WITH (timescaledb.continuous) AS
SELECT
    stock_id,
    time_bucket('7 days'::interval, date) AS bucket,
    first(open, date)       AS open,
    max(high)               AS high,
    min(low)                AS low,
    last(close, date)       AS close,
    last(adjusted_close, date) AS adjusted_close,
    sum(volume)             AS volume,
    count(*)                AS trading_days
FROM daily_ohlcv
GROUP BY stock_id, time_bucket('7 days'::interval, date)
WITH NO DATA;
"""

# Monthly: calendar month
MONTHLY_AGG_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS monthly_ohlcv
WITH (timescaledb.continuous) AS
SELECT
    stock_id,
    time_bucket('1 month'::interval, date) AS bucket,
    first(open, date)       AS open,
    max(high)               AS high,
    min(low)                AS low,
    last(close, date)       AS close,
    last(adjusted_close, date) AS adjusted_close,
    sum(volume)             AS volume,
    count(*)                AS trading_days
FROM daily_ohlcv
GROUP BY stock_id, time_bucket('1 month'::interval, date)
WITH NO DATA;
"""

# Quarterly: 3-month buckets
QUARTERLY_AGG_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS quarterly_ohlcv
WITH (timescaledb.continuous) AS
SELECT
    stock_id,
    time_bucket('3 months'::interval, date) AS bucket,
    first(open, date)       AS open,
    max(high)               AS high,
    min(low)                AS low,
    last(close, date)       AS close,
    last(adjusted_close, date) AS adjusted_close,
    sum(volume)             AS volume,
    count(*)                AS trading_days
FROM daily_ohlcv
GROUP BY stock_id, time_bucket('3 months'::interval, date)
WITH NO DATA;
"""

# Refresh policies: auto-refresh on a schedule
# - start_offset: how far back to look for changes
# - end_offset: how close to "now" to aggregate (NULL = up to now)
# - schedule_interval: how often to run the refresh
REFRESH_POLICIES = [
    {
        "view": "weekly_ohlcv",
        "start_offset": "4 weeks",
        "end_offset": None,
        "schedule_interval": "1 hour",
    },
    {
        "view": "monthly_ohlcv",
        "start_offset": "3 months",
        "end_offset": None,
        "schedule_interval": "1 hour",
    },
    {
        "view": "quarterly_ohlcv",
        "start_offset": "6 months",
        "end_offset": None,
        "schedule_interval": "1 hour",
    },
]

# Indexes for fast lookups
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_weekly_ohlcv_stock_bucket ON weekly_ohlcv (stock_id, bucket DESC);",
    "CREATE INDEX IF NOT EXISTS idx_monthly_ohlcv_stock_bucket ON monthly_ohlcv (stock_id, bucket DESC);",
    "CREATE INDEX IF NOT EXISTS idx_quarterly_ohlcv_stock_bucket ON quarterly_ohlcv (stock_id, bucket DESC);",
]


async def drop_aggregates() -> None:
    """Drop existing continuous aggregates (for recreation)."""
    print("🗑️  Dropping existing continuous aggregates...")
    async with engine.begin() as conn:
        for view in ["quarterly_ohlcv", "monthly_ohlcv", "weekly_ohlcv"]:
            try:
                await conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {view} CASCADE;"))
                print(f"   ✅ Dropped {view}")
            except Exception as e:
                print(f"   ⚠️  Error dropping {view}: {e}")


async def create_aggregates() -> None:
    """Create continuous aggregates for weekly, monthly, and quarterly candles."""
    print("📊 Creating continuous aggregates...")

    async with engine.begin() as conn:
        # 1. Create the continuous aggregates
        for name, sql in [
            ("weekly_ohlcv", WEEKLY_AGG_SQL),
            ("monthly_ohlcv", MONTHLY_AGG_SQL),
            ("quarterly_ohlcv", QUARTERLY_AGG_SQL),
        ]:
            try:
                await conn.execute(text(sql))
                print(f"   ✅ Created {name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"   ℹ️  {name} already exists")
                else:
                    print(f"   ❌ Error creating {name}: {e}")
                    raise

        # 2. Create indexes for fast lookups
        print("\n📇 Creating indexes...")
        for idx_sql in INDEXES:
            try:
                await conn.execute(text(idx_sql))
            except Exception as e:
                print(f"   ⚠️  Index warning: {e}")
        print("   ✅ Indexes created")

        # 3. Add refresh policies
        print("\n⏰ Adding refresh policies...")
        for policy in REFRESH_POLICIES:
            try:
                end_offset = (
                    f"'{policy['end_offset']}'::interval" if policy["end_offset"] else "NULL"
                )
                await conn.execute(
                    text(
                        f"SELECT add_continuous_aggregate_policy('{policy['view']}', "
                        f"start_offset => '{policy['start_offset']}'::interval, "
                        f"end_offset => {end_offset}, "
                        f"schedule_interval => '{policy['schedule_interval']}'::interval, "
                        f"if_not_exists => TRUE);"
                    )
                )
                print(
                    f"   ✅ {policy['view']}: refresh every {policy['schedule_interval']}, "
                    f"lookback {policy['start_offset']}"
                )
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"   ℹ️  {policy['view']} policy already exists")
                else:
                    print(f"   ⚠️  Policy warning for {policy['view']}: {e}")


async def initial_refresh() -> None:
    """Perform initial full refresh of all aggregates (fills historical data)."""
    print("\n🔄 Running initial data refresh (this may take a few minutes for 58M rows)...")

    # refresh_continuous_aggregate() cannot run inside a transaction block,
    # so we need a raw asyncpg connection with autocommit
    import asyncpg

    from backend.config import get_settings

    settings = get_settings()
    raw_url = settings.async_database_url.replace("+asyncpg", "")
    conn = await asyncpg.connect(raw_url)
    try:
        for view in ["weekly_ohlcv", "monthly_ohlcv", "quarterly_ohlcv"]:
            print(f"   Refreshing {view}...", end=" ", flush=True)
            try:
                await conn.execute(
                    f"CALL refresh_continuous_aggregate('{view}', '1990-01-01'::date, now()::date);"
                )
                count = await conn.fetchval(f"SELECT count(*) FROM {view};")
                print(f"✅ {count:,} rows")
            except Exception as e:
                print(f"❌ {e}")
                raise
    finally:
        await conn.close()


async def verify_aggregates() -> None:
    """Verify the aggregates are working correctly with a sample query."""
    print("\n🔍 Verification — AAPL candle samples:")

    import asyncpg

    from backend.config import get_settings

    settings = get_settings()
    raw_url = settings.async_database_url.replace("+asyncpg", "")
    conn = await asyncpg.connect(raw_url)
    try:
        stock_id = await conn.fetchval("SELECT id FROM stocks WHERE ticker = 'AAPL' LIMIT 1;")
        if not stock_id:
            print("   ⚠️  AAPL not found, skipping verification")
            return

        for view, label in [
            ("weekly_ohlcv", "Weekly"),
            ("monthly_ohlcv", "Monthly"),
            ("quarterly_ohlcv", "Quarterly"),
        ]:
            rows = await conn.fetch(
                f"SELECT bucket, open, high, low, close, volume, trading_days "
                f"FROM {view} "
                f"WHERE stock_id = $1 "
                f"ORDER BY bucket DESC LIMIT 3;",
                stock_id,
            )
            print(f"\n   {label} (last 3):")
            for row in rows:
                print(
                    f"     {row['bucket']} | O:{float(row['open']):.2f} "
                    f"H:{float(row['high']):.2f} "
                    f"L:{float(row['low']):.2f} C:{float(row['close']):.2f} "
                    f"V:{int(row['volume']):,} "
                    f"({row['trading_days']} days)"
                )
    finally:
        await conn.close()


async def main(drop: bool = False) -> None:
    """Main entry point."""
    print("=" * 60)
    print("PraxiAlpha — Candle Aggregate Setup")
    print("=" * 60)
    print()

    if drop:
        await drop_aggregates()
        print()

    await create_aggregates()
    await initial_refresh()
    await verify_aggregates()

    print("\n" + "=" * 60)
    print("✅ Candle aggregates ready!")
    print("   Views: weekly_ohlcv, monthly_ohlcv, quarterly_ohlcv")
    print("   Auto-refresh: every 1 hour via TimescaleDB policy")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create TimescaleDB candle aggregates")
    parser.add_argument("--drop", action="store_true", help="Drop and recreate existing aggregates")
    args = parser.parse_args()
    asyncio.run(main(drop=args.drop))
