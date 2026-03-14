"""
PraxiAlpha — Data Backfill Script

Backfills historical OHLCV data from EODHD for the entire US stock universe.

Usage:
    # Test with a few stocks first:
    python scripts/backfill_data.py --test

    # Backfill ALL US stocks:
    python scripts/backfill_data.py --all

    # Backfill specific tickers:
    python scripts/backfill_data.py --tickers AAPL MSFT GOOGL NVDA
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import pandas as pd  # needed for dividend date parsing

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import async_session_factory
from backend.models.dividend import StockDividend
from backend.models.macro import FRED_SERIES, MacroData
from backend.models.ohlcv import DailyOHLCV
from backend.models.split import StockSplit
from backend.models.stock import Stock
from backend.services.data_pipeline.data_validator import DataValidator
from backend.services.data_pipeline.eodhd_fetcher import EODHDFetcher
from backend.services.data_pipeline.fred_fetcher import FREDFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill")

# Test tickers for initial validation
TEST_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]


async def populate_stocks_table(fetcher: EODHDFetcher):
    """
    Step 1: Fetch all US tickers from EODHD and populate the stocks table.
    """
    logger.info("=" * 60)
    logger.info("STEP 1: Populating stocks table from EODHD...")
    logger.info("=" * 60)

    tickers_data = await fetcher.fetch_us_tickers()
    logger.info(f"Fetched {len(tickers_data)} tickers from EODHD")

    inserted = 0
    updated = 0

    async with async_session_factory() as session:
        for item in tickers_data:
            ticker = item.get("Code", "").strip()
            if not ticker:
                continue

            # Check if exists
            result = await session.execute(select(Stock).where(Stock.ticker == ticker))
            existing = result.scalar_one_or_none()

            if existing:
                # Update metadata
                existing.name = item.get("Name", existing.name)
                existing.exchange = item.get("Exchange", existing.exchange)
                existing.asset_type = item.get("Type", existing.asset_type)
                existing.currency = item.get("Currency", "USD")
                existing.country = item.get("Country", "US")
                existing.isin = item.get("Isin", existing.isin)
                existing.eodhd_code = f"{ticker}.US"
                updated += 1
            else:
                stock = Stock(
                    ticker=ticker,
                    name=item.get("Name"),
                    exchange=item.get("Exchange"),
                    asset_type=item.get("Type"),
                    currency=item.get("Currency", "USD"),
                    country=item.get("Country", "US"),
                    isin=item.get("Isin"),
                    eodhd_code=f"{ticker}.US",
                    is_active=True,
                )
                session.add(stock)
                inserted += 1

        await session.commit()

    logger.info(f"✅ Stocks table: {inserted} inserted, {updated} updated")
    return len(tickers_data)


async def backfill_single_stock(
    fetcher: EODHDFetcher,
    stock: Stock,
    start_date: str = "1990-01-01",
):
    """
    Backfill OHLCV history for a single stock.
    """
    try:
        df = await fetcher.fetch_daily_ohlcv(stock.ticker, start=start_date)

        if df.empty:
            logger.warning(f"⚠️  {stock.ticker}: No data returned")
            return 0

        # Validate
        df = DataValidator.validate_ohlcv(df, stock.ticker)
        if df.empty:
            logger.warning(f"⚠️  {stock.ticker}: All data invalid after validation")
            return 0

        # Insert into database in batches
        # PostgreSQL has a limit of ~32,767 parameters per query.
        # Each row has 8 columns, so max ~4,000 rows per batch.
        BATCH_SIZE = 3000  # Conservative: 3000 × 8 = 24,000 params

        records = []
        for _, row in df.iterrows():
            records.append(
                {
                    "stock_id": stock.id,
                    "date": row["date"],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "adjusted_close": float(row["adjusted_close"]),
                    "volume": int(row["volume"]),
                }
            )

        # Upsert in batches — on conflict (stock_id, date), update prices
        if records:
            async with async_session_factory() as session:
                for batch_start in range(0, len(records), BATCH_SIZE):
                    batch = records[batch_start : batch_start + BATCH_SIZE]
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

                # Update stock metadata
                result = await session.execute(select(Stock).where(Stock.id == stock.id))
                stock_record = result.scalar_one()
                stock_record.earliest_date = df["date"].min()
                stock_record.latest_date = df["date"].max()
                stock_record.total_records = len(df)

                await session.commit()

        logger.info(
            f"✅ {stock.ticker}: {len(records)} records ({df['date'].min()} → {df['date'].max()})"
        )
        return len(records)

    except Exception as e:
        logger.error(f"❌ {stock.ticker}: {e}")
        return 0


async def backfill_splits_dividends(
    fetcher: EODHDFetcher,
    stock: Stock,
    start_date: str = "1990-01-01",
):
    """
    Backfill splits and dividends for a single stock.
    """
    splits_count = 0
    divs_count = 0

    try:
        # ---- Splits ----
        splits_df = await fetcher.fetch_splits(stock.ticker, start=start_date)
        if not splits_df.empty:
            async with async_session_factory() as session:
                for _, row in splits_df.iterrows():
                    split_str = str(row.get("split", "1/1"))
                    parts = split_str.split("/")
                    numerator = float(parts[0]) if len(parts) >= 1 else 1.0
                    denominator = float(parts[1]) if len(parts) >= 2 else 1.0

                    stmt = pg_insert(StockSplit).values(
                        stock_id=stock.id,
                        date=row["date"],
                        split_ratio=split_str,
                        numerator=numerator,
                        denominator=denominator,
                    )
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_stock_splits_stock_date")
                    await session.execute(stmt)
                    splits_count += 1
                await session.commit()

        # ---- Dividends ----
        divs_df = await fetcher.fetch_dividends(stock.ticker, start=start_date)
        if not divs_df.empty:
            async with async_session_factory() as session:
                for _, row in divs_df.iterrows():
                    decl_date = None
                    rec_date = None
                    pay_date = None
                    try:
                        if row.get("declarationDate"):
                            decl_date = pd.to_datetime(row["declarationDate"]).date()
                        if row.get("recordDate"):
                            rec_date = pd.to_datetime(row["recordDate"]).date()
                        if row.get("paymentDate"):
                            pay_date = pd.to_datetime(row["paymentDate"]).date()
                    except Exception:
                        pass

                    stmt = pg_insert(StockDividend).values(
                        stock_id=stock.id,
                        date=row["date"],
                        value=float(row.get("value", 0)),
                        unadjusted_value=float(row.get("unadjustedValue", 0))
                        if row.get("unadjustedValue")
                        else None,
                        currency=row.get("currency", "USD"),
                        period=row.get("period"),
                        declaration_date=decl_date,
                        record_date=rec_date,
                        payment_date=pay_date,
                    )
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_stock_dividends_stock_date")
                    await session.execute(stmt)
                    divs_count += 1
                await session.commit()

        if splits_count or divs_count:
            logger.info(f"   {stock.ticker}: {splits_count} splits, {divs_count} dividends")

    except Exception as e:
        logger.error(f"   {stock.ticker} splits/divs error: {e}")


async def backfill_stocks(tickers: list[str] | None = None, all_stocks: bool = False):
    """
    Backfill OHLCV data for specified tickers or all stocks.
    """
    fetcher = EODHDFetcher()

    try:
        # Get stocks from DB
        async with async_session_factory() as session:
            query = select(Stock).where(Stock.is_active.is_(True))
            if tickers and not all_stocks:
                query = query.where(Stock.ticker.in_([t.upper() for t in tickers]))
            query = query.order_by(Stock.ticker)
            result = await session.execute(query)
            stocks = result.scalars().all()

        if not stocks:
            logger.error("No stocks found in database. Run --populate first.")
            return

        logger.info("=" * 60)
        logger.info(f"BACKFILL: {len(stocks)} stocks")
        logger.info("=" * 60)

        total_records = 0
        start_time = time.time()

        for i, stock in enumerate(stocks, 1):
            logger.info(f"[{i}/{len(stocks)}] Backfilling {stock.ticker}...")
            records = await backfill_single_stock(fetcher, stock)
            total_records += records

            # Also backfill splits and dividends
            await backfill_splits_dividends(fetcher, stock)

            # Rate limiting: be nice to the API
            # EODHD allows 1000 calls/min, but we'll be conservative
            if i % 50 == 0:
                elapsed = time.time() - start_time
                rate = i / elapsed * 60
                logger.info(
                    f"   Progress: {i}/{len(stocks)} stocks, "
                    f"{total_records:,} total records, "
                    f"{rate:.0f} stocks/min"
                )
                await asyncio.sleep(1)  # Brief pause every 50 stocks

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("✅ BACKFILL COMPLETE")
        logger.info(f"   Stocks: {len(stocks)}")
        logger.info(f"   Records: {total_records:,}")
        logger.info(f"   Time: {elapsed:.1f}s ({elapsed / 60:.1f}min)")
        logger.info("=" * 60)

    finally:
        await fetcher.close()


async def backfill_macro_data(start_date: str = "1990-01-01"):
    """
    Backfill all FRED macro indicator series.

    Fetches 14 economic indicators (Treasury yields, VIX, DXY, oil,
    inflation expectations, M2, Fed balance sheet, unemployment,
    CPI, PCE) with 30+ years of history and stores them in the
    macro_data table.
    """
    fetcher = FREDFetcher()

    try:
        logger.info("=" * 60)
        logger.info("MACRO BACKFILL: Fetching FRED economic indicators")
        logger.info(f"   Series: {len(FRED_SERIES)}")
        logger.info(f"   Start date: {start_date}")
        logger.info("=" * 60)

        total_records = 0
        successful = 0
        failed = 0
        start_time = time.time()

        for series_id, meta in FRED_SERIES.items():
            try:
                logger.info(f"Fetching {series_id} ({meta['name']})...")

                df = await fetcher.fetch_series(series_id, start=start_date)
                if df.empty:
                    logger.warning(f"⚠️  {series_id}: No data returned")
                    failed += 1
                    continue

                # Validate
                df = DataValidator.validate_macro(df, series_id)

                # Build records for upsert
                BATCH_SIZE = 3000
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
                        for batch_start in range(0, len(records), BATCH_SIZE):
                            batch = records[batch_start : batch_start + BATCH_SIZE]
                            stmt = pg_insert(MacroData).values(batch)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_macro_indicator_date",
                                set_={
                                    "value": stmt.excluded.value,
                                    "indicator_name": stmt.excluded.indicator_name,
                                },
                            )
                            await session.execute(stmt)
                        await session.commit()

                logger.info(
                    f"✅ {series_id}: {len(records)} records "
                    f"({df['date'].min()} → {df['date'].max()})"
                )
                total_records += len(records)
                successful += 1

            except Exception as e:
                logger.error(f"❌ {series_id} ({meta['name']}): {e}")
                failed += 1

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("✅ MACRO BACKFILL COMPLETE")
        logger.info(f"   Series: {successful}/{len(FRED_SERIES)} successful, {failed} failed")
        logger.info(f"   Records: {total_records:,}")
        logger.info(f"   Time: {elapsed:.1f}s")
        logger.info("=" * 60)

    finally:
        await fetcher.close()


async def main():
    parser = argparse.ArgumentParser(description="PraxiAlpha Data Backfill")
    parser.add_argument(
        "--populate", action="store_true", help="Populate stocks table from EODHD (run first!)"
    )
    parser.add_argument(
        "--test", action="store_true", help="Backfill test tickers only (AAPL, MSFT, GOOGL, etc.)"
    )
    parser.add_argument("--all", action="store_true", help="Backfill ALL active US stocks")
    parser.add_argument(
        "--macro", action="store_true", help="Backfill FRED macro indicators (yields, VIX, etc.)"
    )
    parser.add_argument(
        "--tickers", nargs="+", help="Backfill specific tickers (e.g., --tickers AAPL MSFT)"
    )

    args = parser.parse_args()

    if args.populate:
        fetcher = EODHDFetcher()
        try:
            await populate_stocks_table(fetcher)
        finally:
            await fetcher.close()

    elif args.test:
        await backfill_stocks(tickers=TEST_TICKERS)

    elif args.all:
        await backfill_stocks(all_stocks=True)

    elif args.macro:
        await backfill_macro_data()

    elif args.tickers:
        await backfill_stocks(tickers=args.tickers)

    else:
        parser.print_help()
        print("\n💡 Recommended order:")
        print("   1. python scripts/backfill_data.py --populate")
        print("   2. python scripts/backfill_data.py --test")
        print("   3. python scripts/backfill_data.py --macro")
        print("   4. python scripts/backfill_data.py --all")


if __name__ == "__main__":
    asyncio.run(main())
