"""
PraxiAlpha — Data Pipeline Celery Tasks

Async tasks for fetching, validating, and storing market data.
These tasks are executed by Celery workers.
"""

import asyncio
import logging

from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.tasks.data_tasks.daily_ohlcv_update")
def daily_ohlcv_update():
    """
    Daily task: Fetch today's OHLCV data for all active stocks.

    Runs at 6 PM ET daily via Celery Beat.
    Uses EODHD bulk endpoint for efficiency.
    """
    logger.info("🔄 Starting daily OHLCV update...")
    # TODO: Implement using EODHDFetcher.fetch_bulk_eod()
    # 1. Fetch bulk EOD for today
    # 2. Validate data
    # 3. Upsert into daily_ohlcv table
    # 4. Update stocks table (latest_date, total_records)
    logger.info("✅ Daily OHLCV update complete")


@celery_app.task(name="backend.tasks.data_tasks.daily_macro_update")
def daily_macro_update():
    """
    Daily task: Fetch latest macro data from FRED.

    Runs at 6:30 PM ET daily via Celery Beat.
    """
    logger.info("🔄 Starting daily macro update...")
    # TODO: Implement using FREDFetcher
    # 1. For each FRED_SERIES, fetch latest observation
    # 2. Upsert into macro_data table
    logger.info("✅ Daily macro update complete")


@celery_app.task(name="backend.tasks.data_tasks.backfill_stock")
def backfill_stock(ticker: str, start_date: str = "1990-01-01"):
    """
    Backfill historical OHLCV data for a single stock.

    Args:
        ticker: Stock ticker (e.g., "AAPL")
        start_date: Start date for backfill (YYYY-MM-DD)
    """
    logger.info(f"🔄 Backfilling {ticker} from {start_date}...")
    # TODO: Implement
    # 1. Fetch OHLCV from EODHD
    # 2. Validate data
    # 3. Insert into daily_ohlcv table
    # 4. Update stocks table metadata
    logger.info(f"✅ Backfill complete for {ticker}")


@celery_app.task(name="backend.tasks.data_tasks.backfill_all_stocks")
def backfill_all_stocks():
    """
    Backfill ALL active US stocks.

    This is the big one — ~10,000 tickers × 30+ years.
    Dispatches individual backfill_stock tasks for parallel processing.
    """
    logger.info("🔄 Starting full US market backfill...")
    # TODO: Implement
    # 1. Query all active stocks from DB
    # 2. For each, dispatch backfill_stock task
    # 3. Track progress
    logger.info("✅ All backfill tasks dispatched")


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
