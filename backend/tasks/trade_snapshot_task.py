"""
PraxiAlpha — Trade Snapshot Celery Task

Periodic task that generates post-close "what-if" snapshots for closed trades.

For each eligible closed trade:
1. Fetch the ticker's closing price from daily_ohlcv for the snapshot date
2. Compute direction-aware hypothetical PnL (full position hold)
3. Insert a TradeSnapshot row

Snapshot frequency by timeframe:
  - daily trades   → every trading day for 30 calendar days
  - weekly trades  → weekly for 16 weeks (112 days)
  - monthly trades → monthly for 18 months (540 days)
"""

import asyncio
import logging
from datetime import date

from backend.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.tasks.trade_snapshot_task.generate_snapshots",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_snapshots(self, snapshot_date_str: str | None = None):
    """
    Generate post-close snapshots for all eligible trades.

    Args:
        snapshot_date_str: ISO date string (YYYY-MM-DD). Defaults to today.
    """
    logger.info("📸 Starting trade snapshot generation...")

    snapshot_dt = date.fromisoformat(snapshot_date_str) if snapshot_date_str else date.today()

    async def _run():
        from sqlalchemy import select

        from backend.database import async_session_factory
        from backend.models.ohlcv import DailyOHLCV
        from backend.services.trade_snapshot_service import (
            compute_hypothetical_pnl,
            create_snapshot,
            get_closed_trades_needing_snapshots,
        )

        async with async_session_factory() as db:
            # 1. Find closed trades that need snapshots
            eligible = await get_closed_trades_needing_snapshots(db, snapshot_dt)
            logger.info(f"Found {len(eligible)} trades needing snapshots")

            if not eligible:
                return {"created": 0, "skipped": 0, "errors": 0}

            # 2. Gather unique tickers to batch-fetch prices
            tickers = {t["ticker"] for t in eligible}

            # 3. Fetch closing prices from daily_ohlcv
            stmt = select(DailyOHLCV.ticker, DailyOHLCV.close).where(
                DailyOHLCV.ticker.in_(tickers),
                DailyOHLCV.date == snapshot_dt,
            )
            result = await db.execute(stmt)
            price_map = {row.ticker: float(row.close) for row in result.all()}

            logger.info(
                f"Fetched prices for {len(price_map)}/{len(tickers)} tickers on {snapshot_dt}"
            )

            created = 0
            skipped = 0
            errors = 0

            for trade_info in eligible:
                ticker = trade_info["ticker"]
                if ticker not in price_map:
                    logger.warning(f"No price data for {ticker} on {snapshot_dt}, skipping")
                    skipped += 1
                    continue

                close_price = price_map[ticker]
                pnl, pnl_pct = compute_hypothetical_pnl(
                    entry_price=trade_info["entry_price"],
                    close_price=close_price,
                    total_quantity=trade_info["total_quantity"],
                    direction=trade_info["direction"],
                )

                try:
                    await create_snapshot(
                        db,
                        trade_id=trade_info["trade_id"],
                        snapshot_date=snapshot_dt,
                        close_price=close_price,
                        hypothetical_pnl=pnl,
                        hypothetical_pnl_pct=pnl_pct,
                    )
                    created += 1
                except Exception:
                    logger.exception(
                        f"Failed to create snapshot for trade {trade_info['trade_id']} ({ticker})"
                    )
                    errors += 1

            await db.commit()

            logger.info(
                f"📸 Snapshot generation complete: "
                f"{created} created, {skipped} skipped, {errors} errors"
            )
            return {"created": created, "skipped": skipped, "errors": errors}

    return asyncio.run(_run())
