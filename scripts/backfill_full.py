"""
PraxiAlpha — Full Market Backfill Script

Production-grade backfill for ~23,714 active US stocks & ETFs.
Features:
  - Smart ticker filtering (Common Stock + ETF only)
  - Async concurrency (configurable parallelism via semaphore)
  - Checkpoint/resume from data/backfill_progress.json
  - Real-time progress file (data/backfill_live.log) for tail -f monitoring
  - Failed ticker retry queue
  - Incremental backfill (skips tickers already up-to-date)

Usage:
    # Full backfill (all active Common Stock + ETF tickers):
    python scripts/backfill_full.py

    # Resume after crash (reads checkpoint, skips completed tickers):
    python scripts/backfill_full.py --resume

    # Dry-run — show what would be fetched without calling the API:
    python scripts/backfill_full.py --dry-run

    # Custom concurrency (default 5):
    python scripts/backfill_full.py --concurrency 3

    # Only ETFs:
    python scripts/backfill_full.py --asset-type ETF

    # Skip splits/dividends to go faster:
    python scripts/backfill_full.py --skip-splits-divs
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

# Ensure project root is importable when running as a standalone script
# (only when invoked directly; avoids side effects when imported as a module)
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError

from backend.database import async_session_factory
from backend.models.dividend import StockDividend
from backend.models.ohlcv import DailyOHLCV
from backend.models.split import StockSplit
from backend.models.stock import Stock
from backend.services.data_pipeline.data_validator import DataValidator
from backend.services.data_pipeline.eodhd_fetcher import EODHDFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill_full")

# ---- Constants ----
PROJECT_ROOT = Path(__file__).parent.parent
PROGRESS_FILE = PROJECT_ROOT / "data" / "backfill_progress.json"
LIVE_LOG_FILE = PROJECT_ROOT / "data" / "backfill_live.log"
DB_BATCH_SIZE = 1000  # 1000 rows × 8 cols = 8K params (well under PG limit of ~32K)
DEFAULT_START_DATE = "1990-01-01"
DEFAULT_CONCURRENCY = 5  # parallel API requests (EODHD allows 1K/min)
REQUEST_TIMEOUT = 60.0  # seconds — longer than default for heavy historical pulls

# Asset types we care about — skip warrants, preferred, units, etc.
ALLOWED_ASSET_TYPES = {"Common Stock", "ETF"}


# ============================================================
# Progress Tracker
# ============================================================
class BackfillProgressTracker:
    """
    Tracks backfill progress in a JSON file and a live log file.

    The JSON file serves as both a progress report and a checkpoint
    for resuming after crashes. The live log file is a simple text
    file you can `tail -f` to monitor progress in real time.
    """

    def __init__(
        self,
        total_tickers: int,
        progress_file: Path = PROGRESS_FILE,
        live_log_file: Path = LIVE_LOG_FILE,
        resume_from: dict[str, Any] | None = None,
    ):
        self.progress_file = progress_file
        self.live_log_file = live_log_file
        self.total_tickers = total_tickers
        self.start_time = time.time()

        # Ensure data/ directory exists
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        if resume_from:
            # Resuming from a previous run
            self.completed: list[str] = resume_from.get("tickers_completed", [])
            self.failed: dict[str, str] = resume_from.get("tickers_failed", {})
            self.total_records: int = resume_from.get("records_inserted", 0)
            self.total_splits: int = resume_from.get("splits_inserted", 0)
            self.total_dividends: int = resume_from.get("dividends_inserted", 0)
            self.started_at: str = resume_from.get("started_at", datetime.now(UTC).isoformat())
            self._write_live_log(
                f"\n{'=' * 60}\n"
                f"RESUMED at {datetime.now(UTC).isoformat()}\n"
                f"Previously completed: {len(self.completed)}/{self.total_tickers}\n"
                f"{'=' * 60}\n"
            )
        else:
            self.completed = []
            self.failed = {}
            self.total_records = 0
            self.total_splits = 0
            self.total_dividends = 0
            self.started_at = datetime.now(UTC).isoformat()
            # Clear live log for fresh run
            self.live_log_file.write_text(
                f"{'=' * 60}\n"
                f"PraxiAlpha Full Backfill — Started {self.started_at}\n"
                f"Target: {self.total_tickers} tickers\n"
                f"{'=' * 60}\n\n",
                encoding="utf-8",
            )

        self._lock = asyncio.Lock()

    @property
    def completed_count(self) -> int:
        return len(self.completed)

    @property
    def failed_count(self) -> int:
        return len(self.failed)

    @property
    def processed_count(self) -> int:
        return self.completed_count + self.failed_count

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def eta_seconds(self) -> float:
        """Estimated time remaining in seconds."""
        if self.processed_count == 0:
            return 0.0
        rate = self.elapsed_seconds / self.processed_count
        remaining = self.total_tickers - self.completed_count - self.failed_count
        # Don't count previously completed tickers from resume
        return rate * max(remaining, 0)

    @property
    def completed_set(self) -> set[str]:
        """Set of completed tickers for O(1) lookups."""
        return set(self.completed)

    async def record_success(
        self,
        ticker: str,
        records: int,
        splits: int = 0,
        dividends: int = 0,
        date_range: str = "",
    ) -> None:
        """Record a successful ticker backfill."""
        async with self._lock:
            self.completed.append(ticker)
            # Remove from failed dict if this was a retry that succeeded
            self.failed.pop(ticker, None)
            self.total_records += records
            self.total_splits += splits
            self.total_dividends += dividends

            progress_pct = self.completed_count / self.total_tickers * 100
            eta = str(timedelta(seconds=int(self.eta_seconds)))

            line = (
                f"[{self.completed_count:>5}/{self.total_tickers}] "
                f"({progress_pct:5.1f}%) ✅ {ticker:<8} "
                f"{records:>7,} records  {date_range}  "
                f"ETA: {eta}"
            )
            self._write_live_log(line + "\n")
            self._save_progress()

    async def record_failure(self, ticker: str, error: str) -> None:
        """Record a failed ticker."""
        async with self._lock:
            self.failed[ticker] = error

            line = f"[{self.processed_count:>5}/{self.total_tickers}] ❌ {ticker:<8} ERROR: {error}"
            self._write_live_log(line + "\n")
            self._save_progress()

    def _write_live_log(self, text: str) -> None:
        """Append a line to the live log file."""
        with open(self.live_log_file, "a", encoding="utf-8") as f:
            f.write(text)

    def _save_progress(self) -> None:
        """Save progress snapshot to JSON file."""
        data = {
            "started_at": self.started_at,
            "last_updated": datetime.now(UTC).isoformat(),
            "total_tickers": self.total_tickers,
            "completed": self.completed_count,
            "failed": self.failed_count,
            "remaining": self.total_tickers - self.processed_count,
            "progress_pct": round(self.completed_count / max(self.total_tickers, 1) * 100, 1),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "estimated_remaining_seconds": round(self.eta_seconds, 1),
            "records_inserted": self.total_records,
            "splits_inserted": self.total_splits,
            "dividends_inserted": self.total_dividends,
            "tickers_completed": self.completed,
            "tickers_failed": self.failed,
        }
        # Write atomically — write to temp, then replace
        tmp = self.progress_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.progress_file)

    def write_summary(self) -> None:
        """Write a final summary to the live log."""
        elapsed = str(timedelta(seconds=int(self.elapsed_seconds)))
        summary = (
            f"\n{'=' * 60}\n"
            f"BACKFILL COMPLETE\n"
            f"{'=' * 60}\n"
            f"  Total tickers:    {self.total_tickers}\n"
            f"  Completed:        {self.completed_count}\n"
            f"  Failed:           {self.failed_count}\n"
            f"  OHLCV records:    {self.total_records:,}\n"
            f"  Splits:           {self.total_splits:,}\n"
            f"  Dividends:        {self.total_dividends:,}\n"
            f"  Elapsed:          {elapsed}\n"
            f"{'=' * 60}\n"
        )
        if self.failed:
            summary += "\nFailed tickers:\n"
            for ticker, err in self.failed.items():
                summary += f"  {ticker}: {err}\n"

        self._write_live_log(summary)
        self._save_progress()
        logger.info(summary)


# ============================================================
# Ticker Filtering
# ============================================================
def filter_backfill_tickers(
    stocks: list[Stock],
    allowed_types: set[str] | None = None,
) -> list[Stock]:
    """
    Filter stocks to only include tickers worth backfilling.

    Filters:
    - Only asset types in allowed_types (default: Common Stock, ETF)
    - Only active (not delisted) tickers
    - Skip tickers with no name (usually junk entries)

    Args:
        stocks: All stocks from DB
        allowed_types: Set of asset_type values to include

    Returns:
        Filtered list of Stock objects
    """
    if allowed_types is None:
        allowed_types = ALLOWED_ASSET_TYPES

    filtered = []
    skipped_types: dict[str, int] = {}

    for stock in stocks:
        asset_type = (stock.asset_type or "").strip()

        # Skip inactive/delisted
        if not stock.is_active or stock.is_delisted:
            continue

        # Skip tickers with no name (junk entries)
        if not stock.name or stock.name.strip() == "":
            continue

        # Filter by asset type
        if asset_type not in allowed_types:
            skipped_types[asset_type] = skipped_types.get(asset_type, 0) + 1
            continue

        filtered.append(stock)

    # Log what we skipped
    if skipped_types:
        logger.info("Skipped asset types:")
        for atype, count in sorted(skipped_types.items(), key=lambda x: -x[1]):
            logger.info(f"  {atype or '(empty)'}: {count}")

    logger.info(
        f"Filtered {len(stocks)} → {len(filtered)} tickers "
        f"(types: {', '.join(sorted(allowed_types))})"
    )
    return filtered


# ============================================================
# Single Stock Backfill (with incremental support)
# ============================================================
async def backfill_single_stock(
    fetcher: EODHDFetcher,
    stock: Stock,
    start_date: str = DEFAULT_START_DATE,
    skip_splits_divs: bool = False,
) -> dict[str, Any]:
    """
    Backfill OHLCV + splits + dividends for a single stock.

    If the stock already has data (stock.latest_date is set), fetches
    only from (latest_date - 5 days) to ensure no gaps. The upsert
    handles deduplication.

    Returns:
        Dict with keys: records, splits, dividends, date_range, error
    """
    result: dict[str, Any] = {
        "records": 0,
        "splits": 0,
        "dividends": 0,
        "date_range": "",
        "error": None,
    }

    try:
        # Determine start date — incremental if data already exists
        effective_start = start_date
        if stock.latest_date:
            # Overlap by 5 days to catch any corrections/adjustments
            overlap_start = stock.latest_date - timedelta(days=5)
            effective_start = max(overlap_start.isoformat(), start_date)

        # ---- OHLCV ----
        df = await fetcher.fetch_daily_ohlcv(stock.ticker, start=effective_start)

        if df.empty:
            result["error"] = "No OHLCV data returned"
            return result

        # Validate
        df = DataValidator.validate_ohlcv(df, stock.ticker)
        if df.empty:
            result["error"] = "All data invalid after validation"
            return result

        # Build records
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

        # Upsert in batches (with DB retry for transient failures)
        if records:
            max_db_retries = 3
            for attempt in range(1, max_db_retries + 1):
                try:
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

                        # Update stock metadata
                        stock_q = await session.execute(select(Stock).where(Stock.id == stock.id))
                        stock_record = stock_q.scalar_one()
                        # For earliest_date: keep the older date (existing or new)
                        new_earliest = df["date"].min()
                        if (
                            stock_record.earliest_date is None
                            or new_earliest < stock_record.earliest_date
                        ):
                            stock_record.earliest_date = new_earliest
                        # For latest_date: keep the newer date
                        new_latest = df["date"].max()
                        if (
                            stock_record.latest_date is None
                            or new_latest > stock_record.latest_date
                        ):
                            stock_record.latest_date = new_latest
                        # For total_records: query actual row count from DB
                        from sqlalchemy import func

                        count_q = await session.execute(
                            select(func.count())
                            .select_from(DailyOHLCV)
                            .where(DailyOHLCV.stock_id == stock.id)
                        )
                        stock_record.total_records = count_q.scalar() or 0

                        await session.commit()
                    break  # Success — exit retry loop

                except OperationalError as db_err:
                    if attempt < max_db_retries:
                        wait = attempt * 10  # 10s, 20s, 30s
                        logger.warning(
                            f"{stock.ticker} DB error (attempt {attempt}/{max_db_retries}), "
                            f"retrying in {wait}s: {db_err}"
                        )
                        await asyncio.sleep(wait)
                    else:
                        raise  # Let the outer except catch it

        result["records"] = len(records)
        result["date_range"] = f"{df['date'].min()} → {df['date'].max()}"

        # ---- Splits & Dividends ----
        if not skip_splits_divs:
            splits, divs = await _backfill_splits_dividends(fetcher, stock, effective_start)
            result["splits"] = splits
            result["dividends"] = divs

    except Exception as e:
        result["error"] = str(e)

    return result


async def _backfill_splits_dividends(
    fetcher: EODHDFetcher,
    stock: Stock,
    start_date: str,
) -> tuple[int, int]:
    """Backfill splits and dividends for a single stock. Returns (splits_count, divs_count)."""
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
                    result = await session.execute(stmt)
                    splits_count += result.rowcount  # type: ignore[attr-defined]
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
                        unadjusted_value=(
                            float(row.get("unadjustedValue", 0))
                            if row.get("unadjustedValue")
                            else None
                        ),
                        currency=row.get("currency", "USD"),
                        period=row.get("period"),
                        declaration_date=decl_date,
                        record_date=rec_date,
                        payment_date=pay_date,
                    )
                    stmt = stmt.on_conflict_do_nothing(constraint="uq_stock_dividends_stock_date")
                    result = await session.execute(stmt)
                    divs_count += result.rowcount  # type: ignore[attr-defined]
                await session.commit()

    except Exception as e:
        logger.warning(f"{stock.ticker} splits/divs error: {e}")

    return splits_count, divs_count


# ============================================================
# Load / Save Checkpoint
# ============================================================
def load_checkpoint(progress_file: Path = PROGRESS_FILE) -> dict[str, Any] | None:
    """Load checkpoint from a previous run, if it exists."""
    if not progress_file.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(progress_file.read_text(encoding="utf-8"))
        logger.info(
            f"Loaded checkpoint: {data.get('completed', 0)}/{data.get('total_tickers', '?')} "
            f"completed, {data.get('failed', 0)} failed"
        )
        return data
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Corrupt checkpoint file, starting fresh: {e}")
        return None


# ============================================================
# Main Backfill Orchestrator
# ============================================================
async def run_full_backfill(
    concurrency: int = DEFAULT_CONCURRENCY,
    resume: bool = False,
    dry_run: bool = False,
    asset_type_filter: str | None = None,
    skip_splits_divs: bool = False,
    start_date: str = DEFAULT_START_DATE,
) -> None:
    """
    Orchestrate the full backfill with concurrent fetching and progress tracking.

    Args:
        concurrency: Max parallel API requests
        resume: Whether to resume from checkpoint
        dry_run: Show what would be fetched, don't call API
        asset_type_filter: Override asset type filter (e.g., "ETF" only)
        skip_splits_divs: Skip splits/dividends fetching
        start_date: Earliest date to backfill from
    """
    # ---- 1. Load tickers from DB ----
    logger.info("Loading tickers from database...")
    async with async_session_factory() as session:
        query = select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.ticker)
        db_result = await session.execute(query)
        all_stocks = list(db_result.scalars().all())

    logger.info(f"Total active tickers in DB: {len(all_stocks)}")

    # ---- 2. Filter to relevant asset types ----
    allowed = {asset_type_filter} if asset_type_filter else ALLOWED_ASSET_TYPES

    stocks = filter_backfill_tickers(all_stocks, allowed_types=allowed)

    if not stocks:
        logger.error("No tickers match the filter criteria. Exiting.")
        return

    # ---- 3. Load checkpoint if resuming ----
    checkpoint = None
    if resume:
        checkpoint = load_checkpoint()

    # ---- 4. Skip already-completed AND already-failed tickers ----
    # On resume, skip both completed tickers (already have data) AND
    # previously failed tickers (will be retried in the retry phase at the end).
    # This prevents re-fetching from the API for tickers that already failed
    # and avoids the >100% progress bug from repeated resumes.
    if checkpoint:
        completed_set = set(checkpoint.get("tickers_completed", []))
        failed_set = set(checkpoint.get("tickers_failed", {}).keys())
        skip_set = completed_set | failed_set
        stocks = [s for s in stocks if s.ticker not in skip_set]
        logger.info(
            f"Resume: skipping {len(completed_set)} completed + {len(failed_set)} failed tickers, "
            f"{len(stocks)} remaining"
        )

    # ---- 5. Dry run ----
    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN — would backfill these tickers:")
        logger.info("=" * 60)
        for i, s in enumerate(stocks[:50], 1):
            existing = f" (has data to {s.latest_date})" if s.latest_date else ""
            logger.info(
                f"  {i:>5}. {s.ticker:<8} {s.asset_type or '':<15} {s.name or ''}{existing}"
            )
        if len(stocks) > 50:
            logger.info(f"  ... and {len(stocks) - 50} more")
        logger.info(f"\nTotal: {len(stocks)} tickers")
        logger.info("Run without --dry-run to start backfilling.")
        return

    # ---- 6. Initialize progress tracker ----
    if checkpoint:
        # Include both completed and failed checkpoint tickers in the total,
        # since BackfillProgressTracker initializes its state from both.
        checkpoint_completed = len(checkpoint.get("tickers_completed", []))
        checkpoint_failed = len(checkpoint.get("tickers_failed", {}))
        total_tickers_for_tracking = len(stocks) + checkpoint_completed + checkpoint_failed
    else:
        total_tickers_for_tracking = len(stocks)

    tracker = BackfillProgressTracker(
        total_tickers=total_tickers_for_tracking,
        resume_from=checkpoint,
    )

    # ---- 7. Create fetcher with longer timeout ----
    fetcher = EODHDFetcher(timeout=REQUEST_TIMEOUT)

    semaphore = asyncio.Semaphore(concurrency)

    async def _process_ticker(stock: Stock) -> None:
        """Process a single ticker with semaphore-controlled concurrency."""
        async with semaphore:
            result = await backfill_single_stock(
                fetcher,
                stock,
                start_date=start_date,
                skip_splits_divs=skip_splits_divs,
            )

            if result["error"]:
                await tracker.record_failure(stock.ticker, result["error"])
            else:
                await tracker.record_success(
                    ticker=stock.ticker,
                    records=result["records"],
                    splits=result["splits"],
                    dividends=result["dividends"],
                    date_range=result["date_range"],
                )

            # Brief pause to be nice to the API
            await asyncio.sleep(0.2)

    # ---- 8. Run backfill ----
    logger.info("=" * 60)
    logger.info("STARTING FULL BACKFILL")
    logger.info(f"  Tickers: {len(stocks)}")
    logger.info(f"  Concurrency: {concurrency}")
    logger.info(f"  Start date: {start_date}")
    logger.info(f"  Splits/dividends: {'skip' if skip_splits_divs else 'include'}")
    logger.info(f"  Progress file: {PROGRESS_FILE}")
    logger.info(f"  Live log: {LIVE_LOG_FILE}")
    logger.info(f"  Monitor with: tail -f {LIVE_LOG_FILE}")
    logger.info("=" * 60)

    try:
        # Process in chunks to avoid creating too many coroutines at once
        CHUNK_SIZE = 100
        for chunk_start in range(0, len(stocks), CHUNK_SIZE):
            chunk = stocks[chunk_start : chunk_start + CHUNK_SIZE]
            tasks = [_process_ticker(stock) for stock in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Log chunk progress
            logger.info(
                f"Chunk {chunk_start // CHUNK_SIZE + 1} complete: "
                f"{tracker.completed_count}/{tracker.total_tickers} done, "
                f"{tracker.failed_count} failed"
            )

        # ---- 9. Retry failed tickers (one attempt, sequential) ----
        # This includes both newly failed tickers AND previously failed ones
        # from the checkpoint (which were skipped in step 4).
        all_failed = dict(tracker.failed)  # Copy current failures
        if checkpoint:
            # Add back previously-failed tickers that weren't retried yet
            for ticker, err in checkpoint.get("tickers_failed", {}).items():
                if ticker not in all_failed and ticker not in tracker.completed_set:
                    all_failed[ticker] = err

        if all_failed:
            failed_tickers = list(all_failed.keys())
            logger.info(f"\nRetrying {len(failed_tickers)} failed tickers (sequential)...")

            # Build stock lookup map once for all retries
            stock_map = {s.ticker: s for s in all_stocks}

            for ticker in failed_tickers:
                stock = stock_map.get(ticker)
                if not stock:
                    continue

                # Remove from failed dict so we can re-record
                async with tracker._lock:
                    tracker.failed.pop(ticker, None)

                retry_result = await backfill_single_stock(
                    fetcher,
                    stock,
                    start_date=start_date,
                    skip_splits_divs=skip_splits_divs,
                )

                if retry_result["error"]:
                    await tracker.record_failure(stock.ticker, retry_result["error"])
                else:
                    await tracker.record_success(
                        ticker=stock.ticker,
                        records=retry_result["records"],
                        splits=retry_result["splits"],
                        dividends=retry_result["dividends"],
                        date_range=retry_result["date_range"],
                    )

                await asyncio.sleep(1)  # Slower pace for retries

    finally:
        await fetcher.close()
        tracker.write_summary()


# ============================================================
# CLI Entry Point
# ============================================================
async def main() -> None:
    parser = argparse.ArgumentParser(
        description="PraxiAlpha — Full Market Backfill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/backfill_full.py                  # Full backfill\n"
            "  python scripts/backfill_full.py --resume         # Resume after crash\n"
            "  python scripts/backfill_full.py --dry-run        # Preview without API calls\n"
            "  python scripts/backfill_full.py --concurrency 3  # Fewer parallel requests\n"
            "  python scripts/backfill_full.py --asset-type ETF # Only ETFs\n"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint (skip already-completed tickers)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without calling the API",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Max parallel API requests (default: {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--asset-type",
        type=str,
        default=None,
        help="Filter to a specific asset type (e.g., 'ETF', 'Common Stock')",
    )
    parser.add_argument(
        "--skip-splits-divs",
        action="store_true",
        help="Skip splits and dividends fetching (faster, OHLCV only)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=DEFAULT_START_DATE,
        help=f"Earliest date to backfill from (default: {DEFAULT_START_DATE})",
    )

    args = parser.parse_args()

    await run_full_backfill(
        concurrency=args.concurrency,
        resume=args.resume,
        dry_run=args.dry_run,
        asset_type_filter=args.asset_type,
        skip_splits_divs=args.skip_splits_divs,
        start_date=args.start_date,
    )


if __name__ == "__main__":
    asyncio.run(main())
