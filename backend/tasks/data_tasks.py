"""
PraxiAlpha — Data Pipeline Celery Tasks

Async tasks for fetching, validating, and storing market data.
These tasks are executed by Celery workers.
"""

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Batch size for DB upserts (1000 × 8 cols = 8K params, well under PG ~32K limit)
DB_BATCH_SIZE = 1000


@celery_app.task(
    name="backend.tasks.data_tasks.daily_ohlcv_update",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_ohlcv_update(self):
    """
    Daily task: Fetch today's OHLCV data for all active stocks.

    Runs at 6 PM ET daily via Celery Beat.
    Uses EODHD bulk endpoint for efficiency — a single API call
    returns all tickers' EOD data for a given date.

    Updates each stock's latest_date metadata
    so future runs know where to pick up.
    """
    logger.info("🔄 Starting daily OHLCV update...")

    async def _run():
        from backend.database import async_session_factory
        from backend.models.ohlcv import DailyOHLCV
        from backend.models.stock import Stock
        from backend.services.data_pipeline.eodhd_fetcher import EODHDFetcher

        fetcher = EODHDFetcher()
        try:
            # Fetch bulk EOD for today (EODHD returns latest trading day)
            bulk_df = await fetcher.fetch_bulk_eod(exchange="US")

            if bulk_df.empty:
                logger.warning("⚠️ Bulk EOD returned no data (market closed?)")
                return {"upserted": 0, "skipped": 0}

            logger.info(f"Bulk EOD: {len(bulk_df)} tickers returned")

            # Build a ticker → stock_id lookup from DB
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Stock.id, Stock.ticker).where(Stock.is_active.is_(True))
                )
                ticker_to_id = {row.ticker: row.id for row in result}

            # Build OHLCV records, matching against known tickers
            records = []
            skipped = 0
            for _, row in bulk_df.iterrows():
                ticker = str(row.get("code", "")).strip()
                stock_id = ticker_to_id.get(ticker)
                if not stock_id:
                    skipped += 1
                    continue

                try:
                    record_date = pd.to_datetime(row.get("date")).date()
                    records.append(
                        {
                            "stock_id": stock_id,
                            "date": record_date,
                            "open": float(row.get("open", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "close": float(row.get("close", 0)),
                            "adjusted_close": float(row.get("adjusted_close", row.get("close", 0))),
                            "volume": int(row.get("volume", 0)),
                        }
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skipping {ticker}: bad data — {e}")
                    skipped += 1

            # Upsert in batches
            if records:
                async with async_session_factory() as session:
                    for batch_start in range(0, len(records), DB_BATCH_SIZE):
                        batch = records[batch_start : batch_start + DB_BATCH_SIZE]
                        stmt = pg_insert(DailyOHLCV).values(batch)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["stock_id", "date"],
                            set_={
                                "open": stmt.excluded.open,
                                "high": stmt.excluded.high,
                                "low": stmt.excluded.low,
                                "close": stmt.excluded.close,
                                "adjusted_close": stmt.excluded.adjusted_close,
                                "volume": stmt.excluded.volume,
                            },
                        )
                        await session.execute(stmt)
                    await session.commit()

                # Bulk-update latest_date for all affected stocks in one statement
                if records:
                    from sqlalchemy import update

                    record_date = records[0]["date"]
                    affected_ids = list({r["stock_id"] for r in records})
                    async with async_session_factory() as session:
                        await session.execute(
                            update(Stock)
                            .where(
                                Stock.id.in_(affected_ids),
                                (Stock.latest_date.is_(None)) | (Stock.latest_date < record_date),
                            )
                            .values(latest_date=record_date)
                        )
                        await session.commit()

            logger.info(f"✅ Daily OHLCV update: {len(records)} upserted, {skipped} skipped")
            return {"upserted": len(records), "skipped": skipped}

        finally:
            await fetcher.close()

    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.error(f"❌ Daily OHLCV update failed: {exc}")
        raise self.retry(exc=exc) from exc


@celery_app.task(
    name="backend.tasks.data_tasks.daily_macro_update",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_macro_update(self):
    """
    Daily task: Fetch latest macro data from FRED.

    Runs at 6:30 PM ET daily via Celery Beat.
    Fetches only the last 7 days of observations for each series
    to keep API calls minimal. The upsert handles deduplication.
    """
    logger.info("🔄 Starting daily macro update...")

    async def _run():
        from backend.database import async_session_factory
        from backend.models.macro import FRED_SERIES, MacroData
        from backend.services.data_pipeline.data_validator import DataValidator
        from backend.services.data_pipeline.fred_fetcher import FREDFetcher

        fetcher = FREDFetcher()
        try:
            # Only fetch last 7 days — daily incremental update
            start = (date.today() - timedelta(days=7)).isoformat()
            total_records = 0
            successful = 0
            failed = 0

            for series_id, meta in FRED_SERIES.items():
                try:
                    df = await fetcher.fetch_series(series_id, start=start)
                    if df.empty:
                        logger.debug(f"{series_id}: no new data")
                        continue

                    df = DataValidator.validate_macro(df, series_id)

                    # Build records (filter NaN)
                    records = []
                    for _, row in df.iterrows():
                        if pd.notna(row["value"]):
                            records.append(
                                {
                                    "indicator_code": series_id,
                                    "indicator_name": meta["name"],
                                    "date": row["date"],
                                    "value": float(row["value"]),
                                    "source": "FRED",
                                }
                            )

                    if records:
                        async with async_session_factory() as session:
                            stmt = pg_insert(MacroData).values(records)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_macro_indicator_date",
                                set_={
                                    "value": stmt.excluded.value,
                                    "indicator_name": stmt.excluded.indicator_name,
                                },
                            )
                            await session.execute(stmt)
                            await session.commit()

                    total_records += len(records)
                    successful += 1

                except Exception as e:
                    logger.warning(f"❌ {series_id}: {e}")
                    failed += 1

            logger.info(
                f"✅ Daily macro update: {successful}/{len(FRED_SERIES)} series, "
                f"{total_records} records upserted, {failed} failed"
            )
            return {
                "successful": successful,
                "failed": failed,
                "records": total_records,
            }

        finally:
            await fetcher.close()

    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.error(f"❌ Daily macro update failed: {exc}")
        raise self.retry(exc=exc) from exc


@celery_app.task(name="backend.tasks.data_tasks.backfill_stock")
def backfill_stock(ticker: str, start_date: str = "1990-01-01"):
    """
    Backfill historical OHLCV data for a single stock.

    Args:
        ticker: Stock ticker (e.g., "AAPL")
        start_date: Start date for backfill (YYYY-MM-DD)
    """
    logger.info(f"🔄 Backfilling {ticker} from {start_date}...")

    async def _run():
        from backend.database import async_session_factory
        from backend.models.stock import Stock
        from backend.services.data_pipeline.eodhd_fetcher import EODHDFetcher

        # Import from the full backfill script for shared logic
        from scripts.backfill_full import backfill_single_stock

        fetcher = EODHDFetcher()
        try:
            async with async_session_factory() as session:
                result = await session.execute(select(Stock).where(Stock.ticker == ticker.upper()))
                stock = result.scalar_one_or_none()

            if not stock:
                logger.error(f"Stock {ticker} not found in database")
                return {"error": f"Stock {ticker} not found"}

            backfill_result = await backfill_single_stock(fetcher, stock, start_date=start_date)

            if backfill_result["error"]:
                logger.error(f"❌ Backfill {ticker}: {backfill_result['error']}")
            else:
                logger.info(
                    f"✅ Backfill {ticker}: {backfill_result['records']} records "
                    f"({backfill_result['date_range']})"
                )
            return backfill_result

        finally:
            await fetcher.close()

    return asyncio.run(_run())


@celery_app.task(name="backend.tasks.data_tasks.backfill_all_stocks")
def backfill_all_stocks():
    """
    Backfill ALL active US stocks.

    This is the big one — ~23,714 tickers × 30+ years.
    Dispatches individual backfill_stock tasks in batches of 500
    with brief pauses between batches to avoid overwhelming the
    Celery broker/worker pool.
    """
    import time

    logger.info("🔄 Starting full US market backfill...")

    async def _get_tickers():
        from backend.database import async_session_factory
        from backend.models.stock import Stock
        from scripts.backfill_full import ALLOWED_ASSET_TYPES, filter_backfill_tickers

        async with async_session_factory() as session:
            query = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.ticker)
            result = await session.execute(query)
            all_stocks = list(result.scalars().all())

        filtered = filter_backfill_tickers(all_stocks, allowed_types=ALLOWED_ASSET_TYPES)
        return [s.ticker for s in filtered]

    tickers = asyncio.run(_get_tickers())
    total = len(tickers)
    logger.info(f"Dispatching backfill tasks for {total} tickers...")

    # Dispatch in batches to avoid overwhelming the broker/worker pool
    batch_size = 500
    pause_seconds = 0.5
    dispatched = 0

    for start in range(0, total, batch_size):
        batch = tickers[start : start + batch_size]
        for ticker in batch:
            backfill_stock.delay(ticker)
            dispatched += 1

        logger.info(
            "Dispatched backfill tasks for tickers %d–%d of %d",
            start + 1,
            min(start + len(batch), total),
            total,
        )
        # Brief pause between batches to reduce burst load on the broker
        if start + batch_size < total:
            time.sleep(pause_seconds)

    logger.info(f"✅ {dispatched} backfill tasks dispatched")
    return {"dispatched": dispatched}


@celery_app.task(name="backend.tasks.data_tasks.daily_economic_calendar_sync")
def daily_economic_calendar_sync():
    """
    Daily task: Sync economic calendar events from TradingEconomics.

    Runs at 7 AM ET daily (before market open) via Celery Beat.
    Fetches high & medium importance events for the next 14 days,
    upserts them into the DB, and prunes old records.
    """
    logger.info("🔄 Starting economic calendar sync...")

    async def _sync():
        from backend.database import async_session_factory
        from backend.services.data_pipeline.economic_calendar_service import (
            EconomicCalendarService,
        )

        async with async_session_factory() as session:
            svc = EconomicCalendarService(session)
            # Sync all importance levels (1, 2, 3) for the next 14 days
            count = await svc.sync_upcoming_events(days=14, importance=None)
            # Prune events older than 90 days
            pruned = await svc.prune_old_events()
            await session.commit()
        return count, pruned

    count, pruned = asyncio.run(_sync())
    logger.info(f"✅ Economic calendar sync complete: {count} upserted, {pruned} pruned")
    return {"upserted": count, "pruned": pruned}
