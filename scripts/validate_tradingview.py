"""
PraxiAlpha — TradingView Data Validation Script

Compares OHLCV candle data in our database against TradingView's data
(the gold standard) to detect mismatches caused by data pipeline bugs,
split adjustment errors, or EODHD data quality issues.

Requires a TradingView Premium account and the tvdatafeed library:
    pip install "praxialpha[tv-validate]"

Usage:
    # Validate a few key tickers across all timeframes:
    python scripts/validate_tradingview.py

    # Validate specific tickers:
    python scripts/validate_tradingview.py --tickers AAPL MSFT SMH NVDA

    # Validate only weekly timeframe:
    python scripts/validate_tradingview.py --timeframes weekly

    # Custom bar count and tolerance:
    python scripts/validate_tradingview.py --bars 100 --tolerance 0.02

    # Save report to CSV:
    python scripts/validate_tradingview.py --output data/tv_validation_report.csv

    # Dry-run (show what would be validated without connecting to TradingView):
    python scripts/validate_tradingview.py --dry-run

Environment variables (set in .env):
    TV_USERNAME  — TradingView username
    TV_PASSWORD  — TradingView password
"""

import argparse
import asyncio
import csv
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Ensure project root is importable
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.config import get_settings
from backend.database import async_session_factory
from backend.services.candle_service import CandleService, Timeframe

# Lazy import tvdatafeed (not installed in CI)
try:
    from tvDatafeed import Interval, TvDatafeed

    TV_AVAILABLE = True
except ImportError:
    TV_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("tv_validate")


# ------------------------------------------------------------------ #
#  Constants & mappings                                                #
# ------------------------------------------------------------------ #

# Default tickers to validate — mix of popular stocks, ETFs, and
# stocks with known splits to stress-test our adjustment logic.
DEFAULT_TICKERS = [
    "AAPL",  # Multiple historical splits (7:1 in 2014, 4:1 in 2020)
    "MSFT",  # Large cap, no recent splits
    "NVDA",  # 10:1 split in 2024
    "SMH",  # ETF with 2:1 split (the original bug that started Session 28)
    "TSLA",  # 5:1 split (2020), 3:1 split (2022)
    "GOOGL",  # 20:1 split in 2022
    "AMZN",  # 20:1 split in 2022
    "META",  # No splits (renamed from FB)
    "SPY",  # Benchmark ETF
    "QQQ",  # Benchmark ETF
]

# Map our timeframes to tvDatafeed intervals
# NOTE: tvdatafeed doesn't support quarterly — we'll skip it or
# derive it from monthly data for comparison.
TIMEFRAME_TO_TV_INTERVAL: dict[str, Any] = {}  # populated at runtime if TV_AVAILABLE

TIMEFRAME_BARS = {
    "daily": 252,  # ~1 year of trading days
    "weekly": 104,  # ~2 years of weeks
    "monthly": 60,  # ~5 years of months
}

# Tolerance thresholds (percentage)
DEFAULT_PRICE_TOLERANCE = 0.01  # 1% — accounts for rounding and slight data timing diffs
DEFAULT_VOLUME_TOLERANCE = 0.05  # 5% — volume can differ due to exchange consolidation


# ------------------------------------------------------------------ #
#  Data structures                                                     #
# ------------------------------------------------------------------ #


@dataclass
class CandleMismatch:
    """A single price/volume mismatch between our data and TradingView."""

    ticker: str
    timeframe: str
    date: str
    field: str  # open, high, low, close, volume
    our_value: float
    tv_value: float
    pct_diff: float  # abs percentage difference (e.g. 1.35 means 1.35%)
    tolerance: float | None = None  # effective tolerance ratio used when created

    @property
    def is_significant(self) -> bool:
        """True if the difference exceeds the tolerance used at creation time."""
        if self.tolerance is not None:
            tol = self.tolerance
        else:
            tol = DEFAULT_VOLUME_TOLERANCE if self.field == "volume" else DEFAULT_PRICE_TOLERANCE
        # pct_diff is stored as a percentage (e.g. 1.35 = 1.35%),
        # tolerance is stored as a ratio (e.g. 0.01 = 1%), so convert.
        return abs(self.pct_diff) > tol * 100


@dataclass
class ValidationResult:
    """Validation result for one ticker + timeframe combination."""

    ticker: str
    timeframe: str
    our_bar_count: int
    tv_bar_count: int
    overlapping_bars: int
    mismatches: list[CandleMismatch] = field(default_factory=list)
    error: str | None = None

    @property
    def mismatch_count(self) -> int:
        return len([m for m in self.mismatches if m.is_significant])

    @property
    def match_pct(self) -> float:
        if self.overlapping_bars == 0:
            return 0.0
        # 5 fields per bar (OHLCV)
        total_checks = self.overlapping_bars * 5
        return (1 - self.mismatch_count / total_checks) * 100


# ------------------------------------------------------------------ #
#  TradingView data fetcher                                            #
# ------------------------------------------------------------------ #


def init_tv_intervals() -> None:
    """Initialize the timeframe→interval mapping (requires tvdatafeed import)."""
    global TIMEFRAME_TO_TV_INTERVAL
    if TV_AVAILABLE:
        TIMEFRAME_TO_TV_INTERVAL = {
            "daily": Interval.in_daily,
            "weekly": Interval.in_weekly,
            "monthly": Interval.in_monthly,
        }


def get_tv_client() -> "TvDatafeed":
    """Create an authenticated TvDatafeed client from .env credentials."""
    if not TV_AVAILABLE:
        raise RuntimeError(
            'tvdatafeed is not installed. Run: pip install "praxialpha[tv-validate]"'
        )

    settings = get_settings()
    if not settings.tv_username or not settings.tv_password:
        raise RuntimeError(
            "TV_USERNAME and TV_PASSWORD must be set in .env. See .env.example for details."
        )

    logger.info("Connecting to TradingView as %s...", settings.tv_username)
    tv = TvDatafeed(settings.tv_username, settings.tv_password)
    logger.info("TradingView connection established.")
    return tv


def fetch_tv_candles(
    tv: "TvDatafeed",
    ticker: str,
    timeframe: str,
    n_bars: int,
) -> pd.DataFrame | None:
    """
    Fetch OHLCV data from TradingView for a ticker + timeframe.

    Returns a DataFrame with columns: date, open, high, low, close, volume
    or None if fetch fails.

    TradingView uses split-adjusted prices by default (same as our
    adjusted=True behavior), so the comparison is apples-to-apples.
    """
    interval = TIMEFRAME_TO_TV_INTERVAL.get(timeframe)
    if interval is None:
        logger.warning("Timeframe %s not supported by tvdatafeed, skipping", timeframe)
        return None

    # TradingView uses exchange codes. For US stocks, common exchanges are:
    # NASDAQ, NYSE, AMEX. We'll try NASDAQ first, then NYSE (covers 99% of cases).
    exchanges = ["NASDAQ", "NYSE", "AMEX"]
    df = None

    for exchange in exchanges:
        try:
            df = tv.get_hist(
                symbol=ticker,
                exchange=exchange,
                interval=interval,
                n_bars=n_bars,
            )
            if df is not None and not df.empty:
                logger.debug(
                    "Fetched %d bars for %s from %s (%s)",
                    len(df),
                    ticker,
                    exchange,
                    timeframe,
                )
                break
        except Exception as e:
            logger.debug("Failed to fetch %s from %s: %s", ticker, exchange, e)
            continue

    if df is None or df.empty:
        logger.warning("Could not fetch %s from TradingView for any exchange", ticker)
        return None

    # Normalize the DataFrame
    df = df.reset_index()

    # tvdatafeed returns a datetime index; extract date
    if "datetime" in df.columns:
        df["date"] = pd.to_datetime(df["datetime"]).dt.date
    elif df.index.name == "datetime":
        df["date"] = pd.to_datetime(df.index).date
        df = df.reset_index(drop=True)

    # Standardize column names (tvdatafeed uses lowercase: open, high, low, close, volume)
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        logger.warning(
            "Unexpected columns from tvdatafeed for %s: %s",
            ticker,
            list(df.columns),
        )
        return None

    return df[["date", "open", "high", "low", "close", "volume"]]


# ------------------------------------------------------------------ #
#  Our database data fetcher                                           #
# ------------------------------------------------------------------ #


async def fetch_our_candles(
    ticker: str,
    timeframe: str,
    n_bars: int,
) -> pd.DataFrame | None:
    """
    Fetch split-adjusted OHLCV data from our database.

    Returns a DataFrame matching the TV format: date, open, high, low, close, volume.
    """
    from sqlalchemy import text

    async with async_session_factory() as session:
        # Resolve ticker → stock_id
        result = await session.execute(
            text("SELECT id FROM stocks WHERE ticker = :ticker LIMIT 1"),
            {"ticker": ticker},
        )
        row = result.fetchone()
        if not row:
            logger.warning("Ticker %s not found in our database", ticker)
            return None

        stock_id = row.id
        tf = Timeframe(timeframe)
        service = CandleService(session)

        candles = await service.get_candles(
            stock_id=stock_id,
            timeframe=tf,
            limit=n_bars,
            adjusted=True,  # split-adjusted to match TradingView default
        )

    if not candles:
        logger.warning("No %s candles for %s in our database", timeframe, ticker)
        return None

    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    return df[["date", "open", "high", "low", "close", "volume"]]


# ------------------------------------------------------------------ #
#  Comparison logic                                                    #
# ------------------------------------------------------------------ #


def compare_candles(
    ticker: str,
    timeframe: str,
    our_df: pd.DataFrame,
    tv_df: pd.DataFrame,
    price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
    volume_tolerance: float = DEFAULT_VOLUME_TOLERANCE,
) -> ValidationResult:
    """
    Compare our candles against TradingView's candles bar-by-bar.

    Joins on date, compares OHLCV fields, and returns a ValidationResult
    with any mismatches.
    """
    # Merge on date (inner join — only compare dates we both have)
    merged = our_df.merge(tv_df, on="date", suffixes=("_ours", "_tv"), how="inner")

    result = ValidationResult(
        ticker=ticker,
        timeframe=timeframe,
        our_bar_count=len(our_df),
        tv_bar_count=len(tv_df),
        overlapping_bars=len(merged),
    )

    if len(merged) == 0:
        result.error = "No overlapping dates found"
        return result

    # Compare each OHLCV field
    for field_name in ["open", "high", "low", "close", "volume"]:
        tolerance = volume_tolerance if field_name == "volume" else price_tolerance

        ours_col = f"{field_name}_ours"
        tv_col = f"{field_name}_tv"

        for _, row in merged.iterrows():
            our_val = float(row[ours_col])
            tv_val = float(row[tv_col])

            # Skip zero comparisons (no division by zero)
            if tv_val == 0 and our_val == 0:
                continue
            pct_diff = 1.0 if tv_val == 0 else abs(our_val - tv_val) / abs(tv_val)

            if pct_diff > tolerance:
                result.mismatches.append(
                    CandleMismatch(
                        ticker=ticker,
                        timeframe=timeframe,
                        date=str(row["date"]),
                        field=field_name,
                        our_value=our_val,
                        tv_value=tv_val,
                        pct_diff=round(pct_diff * 100, 4),
                        tolerance=tolerance,
                    )
                )

    return result


# ------------------------------------------------------------------ #
#  Report generation                                                   #
# ------------------------------------------------------------------ #


def print_summary(results: list[ValidationResult]) -> None:
    """Print a human-readable validation summary."""
    print("\n" + "=" * 80)
    print("  📊 TradingView Data Validation Report")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    total_checks = 0
    total_mismatches = 0
    errors = []

    for r in results:
        status = "✅" if r.mismatch_count == 0 and not r.error else "❌"
        if r.error:
            errors.append(f"  {r.ticker}/{r.timeframe}: {r.error}")
            print(f"\n  {status} {r.ticker} ({r.timeframe}): ERROR — {r.error}")
            continue

        total_checks += r.overlapping_bars * 5
        total_mismatches += r.mismatch_count

        print(
            f"\n  {status} {r.ticker} ({r.timeframe}): "
            f"{r.match_pct:.1f}% match "
            f"({r.overlapping_bars} bars, {r.mismatch_count} mismatches)"
        )

        # Show top 5 worst mismatches
        worst = sorted(r.mismatches, key=lambda m: abs(m.pct_diff), reverse=True)[:5]
        for m in worst:
            print(
                f"    ⚠ {m.date} {m.field}: "
                f"ours={m.our_value:.4f} vs TV={m.tv_value:.4f} "
                f"({m.pct_diff:+.2f}%)"
            )

    print("\n" + "-" * 80)
    if total_checks > 0:
        overall_match = (1 - total_mismatches / total_checks) * 100
        print(f"  Overall: {overall_match:.2f}% match across {total_checks:,} field checks")
    else:
        print("  No data to compare.")

    if total_mismatches == 0 and not errors:
        print("  🎉 All data matches TradingView within tolerance!")
    elif total_mismatches > 0:
        print(f"  ⚠️  {total_mismatches} mismatches found — review above.")
    if errors:
        print(f"  ❗ {len(errors)} errors occurred:")
        for e in errors:
            print(e)
    print("=" * 80 + "\n")


def save_csv_report(results: list[ValidationResult], output_path: str) -> None:
    """Save all mismatches to a CSV file for further analysis."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for r in results:
        for m in r.mismatches:
            rows.append(
                {
                    "ticker": m.ticker,
                    "timeframe": m.timeframe,
                    "date": m.date,
                    "field": m.field,
                    "our_value": m.our_value,
                    "tv_value": m.tv_value,
                    "pct_diff": m.pct_diff,
                    "significant": m.is_significant,
                }
            )

    if not rows:
        logger.info("No mismatches to save — CSV not written.")
        return

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Saved %d mismatches to %s", len(rows), path)


# ------------------------------------------------------------------ #
#  Main orchestrator                                                   #
# ------------------------------------------------------------------ #


async def run_validation(
    tickers: list[str],
    timeframes: list[str],
    n_bars: int,
    price_tolerance: float,
    volume_tolerance: float,
    dry_run: bool = False,
    rate_limit_delay: float = 1.5,
) -> list[ValidationResult]:
    """
    Run the full validation pipeline.

    For each ticker × timeframe:
    1. Fetch our split-adjusted data from the DB
    2. Fetch TradingView's data via tvdatafeed
    3. Compare bar-by-bar
    4. Collect results
    """
    if dry_run:
        print("\n🔍 DRY RUN — would validate:")
        for ticker in tickers:
            for tf in timeframes:
                bars = TIMEFRAME_BARS.get(tf, n_bars)
                print(f"  {ticker} × {tf} ({bars} bars)")
        print(f"\nTotal: {len(tickers) * len(timeframes)} combinations")
        return []

    init_tv_intervals()
    tv = get_tv_client()
    results: list[ValidationResult] = []

    total = len(tickers) * len(timeframes)
    completed = 0

    for ticker in tickers:
        for tf in timeframes:
            completed += 1
            bars = TIMEFRAME_BARS.get(tf, n_bars)
            logger.info(
                "[%d/%d] Validating %s (%s, %d bars)...",
                completed,
                total,
                ticker,
                tf,
                bars,
            )

            try:
                # Fetch from our DB
                our_df = await fetch_our_candles(ticker, tf, bars)
                if our_df is None or our_df.empty:
                    results.append(
                        ValidationResult(
                            ticker=ticker,
                            timeframe=tf,
                            our_bar_count=0,
                            tv_bar_count=0,
                            overlapping_bars=0,
                            error="No data in our database",
                        )
                    )
                    continue

                # Fetch from TradingView
                tv_df = fetch_tv_candles(tv, ticker, tf, bars)
                if tv_df is None or tv_df.empty:
                    results.append(
                        ValidationResult(
                            ticker=ticker,
                            timeframe=tf,
                            our_bar_count=len(our_df),
                            tv_bar_count=0,
                            overlapping_bars=0,
                            error="Could not fetch from TradingView",
                        )
                    )
                    continue

                # Compare
                result = compare_candles(
                    ticker,
                    tf,
                    our_df,
                    tv_df,
                    price_tolerance=price_tolerance,
                    volume_tolerance=volume_tolerance,
                )
                results.append(result)

            except Exception as e:
                logger.error("Error validating %s/%s: %s", ticker, tf, e)
                results.append(
                    ValidationResult(
                        ticker=ticker,
                        timeframe=tf,
                        our_bar_count=0,
                        tv_bar_count=0,
                        overlapping_bars=0,
                        error=str(e),
                    )
                )

            # Rate limit to avoid TradingView throttling
            if completed < total:
                time.sleep(rate_limit_delay)

    return results


# ------------------------------------------------------------------ #
#  CLI                                                                 #
# ------------------------------------------------------------------ #


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate PraxiAlpha OHLCV data against TradingView",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="Tickers to validate (default: %(default)s)",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["daily", "weekly", "monthly"],
        choices=["daily", "weekly", "monthly"],
        help="Timeframes to validate (default: daily weekly monthly)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=252,
        help="Number of bars to compare per timeframe (default: 252)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_PRICE_TOLERANCE,
        help=f"Price tolerance as decimal (default: {DEFAULT_PRICE_TOLERANCE})",
    )
    parser.add_argument(
        "--volume-tolerance",
        type=float,
        default=DEFAULT_VOLUME_TOLERANCE,
        help=f"Volume tolerance as decimal (default: {DEFAULT_VOLUME_TOLERANCE})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save mismatch report to CSV file (e.g., data/tv_validation_report.csv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be validated without connecting to TradingView",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.5,
        help="Seconds between TradingView requests (default: 1.5)",
    )

    args = parser.parse_args()

    if not args.dry_run and not TV_AVAILABLE:
        print(
            "❌ tvdatafeed is not installed.\n"
            "   Install it with: pip install --upgrade --no-cache-dir "
            "git+https://github.com/rongardF/tvdatafeed.git\n"
            "   Or: pip install 'praxialpha[tv-validate]'"
        )
        sys.exit(1)

    results = asyncio.run(
        run_validation(
            tickers=[t.upper() for t in args.tickers],
            timeframes=args.timeframes,
            n_bars=args.bars,
            price_tolerance=args.tolerance,
            volume_tolerance=args.volume_tolerance,
            dry_run=args.dry_run,
            rate_limit_delay=args.rate_limit,
        )
    )

    if results:
        print_summary(results)
        if args.output:
            save_csv_report(results, args.output)


if __name__ == "__main__":
    main()
