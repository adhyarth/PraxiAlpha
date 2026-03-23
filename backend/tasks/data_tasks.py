"""
PraxiAlpha — Data Pipeline Celery Tasks

Async tasks for fetching, validating, and storing market data.
These tasks are executed by Celery workers.
"""

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.config import get_settings
from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Batch size for DB upserts (1000 × 8 cols = 8K params, well under PG ~32K limit)
DB_BATCH_SIZE = 1000


# ---------------------------------------------------------------------------
# Helpers (extracted for testability)
# ---------------------------------------------------------------------------


def _candidate_dates(last_known: date, today: date) -> list[date]:
    """
    Return weekday dates from ``last_known + 1`` through ``today`` inclusive.

    Weekends are skipped as a cheap heuristic — holidays are harmless
    because the EODHD bulk endpoint simply returns an empty frame for
    non-trading days.
    """
    return [
        last_known + timedelta(days=d)
        for d in range(1, (today - last_known).days + 1)
        if (last_known + timedelta(days=d)).weekday() < 5  # Mon-Fri
    ]


async def _fetch_and_upsert_date(
    fetcher,  # type: ignore[no-untyped-def]
    target_date: date,
    ticker_to_id: dict[str, int],
    async_session_factory,  # type: ignore[no-untyped-def]
) -> dict:
    """
    Fetch bulk EOD for *one* date, upsert records, and update ``latest_date``.

    Returns a dict with ``upserted`` and ``skipped`` counts.
    """
    from backend.models.ohlcv import DailyOHLCV
    from backend.models.stock import Stock

    bulk_df = await fetcher.fetch_bulk_eod(exchange="US", date_str=target_date.isoformat())

    if bulk_df.empty:
        logger.info(f"  {target_date}: no data (holiday/weekend)")
        return {"upserted": 0, "skipped": 0}

    # Build OHLCV records, matching against known tickers
    records: list[dict] = []
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

        # Bulk-update latest_date for affected stocks.
        # Use target_date (the date we requested) rather than a date parsed
        # from the response, to guard against provider data anomalies.
        affected_ids = list({r["stock_id"] for r in records})
        async with async_session_factory() as session:
            await session.execute(
                update(Stock)
                .where(
                    Stock.id.in_(affected_ids),
                    (Stock.latest_date.is_(None)) | (Stock.latest_date < target_date),
                )
                .values(latest_date=target_date)
            )
            await session.commit()

    logger.info(f"  {target_date}: {len(records)} upserted, {skipped} skipped")
    return {"upserted": len(records), "skipped": skipped}


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="backend.tasks.data_tasks.daily_ohlcv_update",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_ohlcv_update(self):
    """
    Daily task: Fetch OHLCV data for **all missing dates** since the last
    successful update.

    Runs at 6 PM ET daily via Celery Beat.

    **Gap-fill logic:**
    1. Query ``MAX(latest_date)`` across all active stocks.
    2. Build a list of weekday candidate dates from that anchor to today.
    3. For each candidate date, call the EODHD bulk endpoint (1 API call
       per date) and upsert the results.
    4. If the gap exceeds ``OHLCV_MAX_GAP_DAYS`` (default 60), the task
       caps the fill window and logs a warning.

    On a normal day (worker running daily) this is **1 API call** — the
    same cost as the old single-day implementation.  If the worker was
    down for 5 days, it self-heals with ~3-4 calls (weekdays only).
    """
    logger.info("🔄 Starting daily OHLCV update (gap-fill)...")

    async def _run():
        from backend.database import async_session_factory
        from backend.models.stock import Stock
        from backend.services.data_pipeline.eodhd_fetcher import EODHDFetcher

        settings = get_settings()
        max_gap = settings.ohlcv_max_gap_days
        fetcher = EODHDFetcher()

        try:
            # ---- 1. Determine the anchor date ----
            async with async_session_factory() as session:
                row = await session.execute(
                    select(func.max(Stock.latest_date)).where(Stock.is_active.is_(True))
                )
                last_known = row.scalar()

            today = date.today()

            if last_known is None:
                # No data at all — target the most recent weekday
                logger.warning(
                    "⚠️ No latest_date found for any stock. "
                    "Falling back to single-day fetch. "
                    "Run the initial backfill script to populate history."
                )
                # Ensure we target the most recent weekday on or before "today"
                effective_today = today
                while effective_today.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                    effective_today -= timedelta(days=1)
                # Set last_known to the day before the effective trading day so that
                # the subsequent gap/candidate-date logic yields exactly one date.
                last_known = effective_today - timedelta(days=1)
                today = effective_today

            gap = (today - last_known).days
            if gap <= 0:
                logger.info("✅ Already up to date — nothing to fetch")
                return {"upserted": 0, "dates_filled": 0, "dates_skipped": 0}

            if gap > max_gap:
                logger.warning(
                    f"⚠️ Gap of {gap} days exceeds OHLCV_MAX_GAP_DAYS ({max_gap}). "
                    f"Capping to last {max_gap} days. "
                    f"Run the backfill script for the remainder."
                )
                last_known = today - timedelta(days=max_gap)

            # ---- 2. Build candidate dates (weekdays only) ----
            candidates = _candidate_dates(last_known, today)

            if not candidates:
                logger.info("✅ No weekday gaps to fill — already up to date")
                return {"upserted": 0, "dates_filled": 0, "dates_skipped": 0}

            logger.info(
                f"Filling {len(candidates)} candidate date(s): {candidates[0]} → {candidates[-1]}"
            )

            # ---- 3. Ticker → stock_id lookup (once) ----
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Stock.id, Stock.ticker).where(Stock.is_active.is_(True))
                )
                ticker_to_id = {r.ticker: r.id for r in result}

            # ---- 4. Fetch & upsert each date ----
            total_upserted = 0
            dates_filled = 0
            dates_skipped = 0

            for target_date in candidates:
                try:
                    day_result = await _fetch_and_upsert_date(
                        fetcher, target_date, ticker_to_id, async_session_factory
                    )
                    total_upserted += day_result["upserted"]
                    if day_result["upserted"] > 0:
                        dates_filled += 1
                    else:
                        dates_skipped += 1
                except Exception as e:
                    logger.warning(f"  {target_date}: fetch failed — {e}")
                    dates_skipped += 1

            logger.info(
                f"✅ Daily OHLCV gap-fill complete: "
                f"{total_upserted} records upserted across "
                f"{dates_filled} trading day(s), "
                f"{dates_skipped} date(s) skipped"
            )
            return {
                "upserted": total_upserted,
                "dates_filled": dates_filled,
                "dates_skipped": dates_skipped,
            }

        finally:
            await fetcher.close()

    try:
        result = asyncio.run(_run())
        # Chain: refresh candle aggregates after successful OHLCV update
        refresh_candle_aggregates.delay()
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


@celery_app.task(name="backend.tasks.data_tasks.refresh_candle_aggregates")
def refresh_candle_aggregates():
    """
    Refresh TimescaleDB continuous aggregates for weekly/monthly/quarterly candles.

    Called after the daily OHLCV update to ensure aggregates include the latest data.
    TimescaleDB also auto-refreshes via its own policy (every 1 hour), but this
    task provides an immediate refresh after new data lands.
    """
    logger.info("🔄 Refreshing candle aggregates...")

    async def _refresh():
        # refresh_continuous_aggregate() cannot run inside a transaction block,
        # so we use a raw asyncpg connection
        import asyncpg

        from backend.config import get_settings

        settings = get_settings()
        raw_url = settings.async_database_url.replace("+asyncpg", "")
        conn = await asyncpg.connect(raw_url)
        refreshed = {}
        try:
            for view, lookback in [
                ("weekly_ohlcv", "4 weeks"),
                ("monthly_ohlcv", "3 months"),
                ("quarterly_ohlcv", "6 months"),
            ]:
                try:
                    await conn.execute(
                        f"CALL refresh_continuous_aggregate('{view}', "
                        f"now() - '{lookback}'::interval, now()::date);"
                    )
                    # Use max(bucket) as a cheap freshness signal instead of count(*)
                    latest = await conn.fetchval(f"SELECT max(bucket) FROM {view}")
                    refreshed[view] = str(latest) if latest else "empty"
                    logger.info(f"   ✅ {view}: refreshed (latest bucket: {refreshed[view]})")
                except Exception as e:
                    logger.warning(f"   ❌ {view}: {e}")
                    refreshed[view] = f"error: {e}"
        finally:
            await conn.close()
        return refreshed

    result = asyncio.run(_refresh())
    logger.info(f"✅ Candle aggregate refresh complete: {result}")
    return result
