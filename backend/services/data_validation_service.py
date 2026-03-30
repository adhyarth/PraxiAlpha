"""
PraxiAlpha — Data Validation Service (Second-Source Comparison)

Core logic for comparing OHLCV data between our database and Yahoo Finance.
Used by the Streamlit "Data Validation" page.

Provides:
- compare_candles() — bar-by-bar comparison with tolerance thresholds
- fetch_yf_candles() — Yahoo Finance data fetcher via yfinance
- fetch_our_candles() — DB data fetcher via CandleService
- sample_random_tickers() — random cross-index ticker sampling
- aggregate_monthly_to_quarterly() — derive quarterly from YF monthly
- load_previous_failures() / save_failures() — persistence for failed checks
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Lazy import yfinance (not installed in CI)
try:
    import yfinance as yf

    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

logger = logging.getLogger("data_validate")


# ------------------------------------------------------------------ #
#  Constants                                                           #
# ------------------------------------------------------------------ #

FIXED_TICKERS = [
    "AAPL",  # 7:1 (2014) + 4:1 (2020) splits
    "MSFT",  # Large cap, no recent splits
    "NVDA",  # 10:1 split (2024)
    "SMH",  # 2:1 split — the bug that started Session 28
    "TSLA",  # 5:1 (2020) + 3:1 (2022) splits
]

ALL_TIMEFRAMES = ["daily", "weekly", "monthly", "quarterly"]

TIMEFRAME_BARS: dict[str, int] = {
    "daily": 252,  # ~1 year of trading days
    "weekly": 104,  # ~2 years of weeks
    "monthly": 60,  # ~5 years of months
    "quarterly": 20,  # ~5 years of quarters
}

# Tolerance thresholds (ratio — 0.01 = 1%)
DEFAULT_PRICE_TOLERANCE = 0.01
# Volume tolerance is higher because data providers report different
# consolidated volumes (exchange-only vs. dark-pool-inclusive).  EODHD
# vs Yahoo Finance regularly differ by 5-8% on the most recent dates.
DEFAULT_VOLUME_TOLERANCE = 0.10

# Failure persistence file
FAILURES_PATH = Path("data/data_validation_failures.json")

# Random ticker sampling — exchange distribution
RANDOM_SAMPLE_CONFIG = {
    "NYSE": 3,
    "NASDAQ": 3,
    "AMEX": 2,
    # 2 ETFs from any exchange
}
RANDOM_ETF_COUNT = 2
RANDOM_TOTAL = 10


# ------------------------------------------------------------------ #
#  Data structures                                                     #
# ------------------------------------------------------------------ #


@dataclass
class CandleMismatch:
    """A single price/volume mismatch between our data and the second source."""

    ticker: str
    timeframe: str
    date: str
    field: str  # open, high, low, close, volume
    our_value: float
    tv_value: float
    pct_diff: float  # stored as percentage (e.g. 1.35 = 1.35%)
    tolerance: float | None = None  # effective tolerance ratio used when created

    @property
    def is_significant(self) -> bool:
        """True if the difference exceeds the tolerance used at creation time."""
        if self.tolerance is not None:
            tol = self.tolerance
        else:
            tol = DEFAULT_VOLUME_TOLERANCE if self.field == "volume" else DEFAULT_PRICE_TOLERANCE
        # pct_diff is percentage, tolerance is ratio — convert
        return abs(self.pct_diff) > tol * 100


@dataclass
class StockMeta:
    """Lightweight metadata for a ticker — used to annotate validation results."""

    name: str = ""
    exchange: str = ""
    asset_type: str = ""
    avg_volume_90d: int = 0

    @property
    def type_label(self) -> str:
        """Short human-readable label for the security type."""
        at = self.asset_type.lower()
        name_lower = self.name.lower()

        # Detect SPACs, warrants, units, rights from the name
        for tag in ("warrant", " wt", " ws"):
            if tag in name_lower:
                return "Warrant"
        if "right" in name_lower:
            return "Right"
        if "unit" in name_lower:
            return "Unit"
        for tag in ("acquisition", "blank check", "spac"):
            if tag in name_lower:
                return "SPAC"

        if "etf" in at:
            return "ETF"
        if "common stock" in at:
            return "Stock"
        return self.asset_type or "Unknown"

    @property
    def is_low_liquidity(self) -> bool:
        """True if average daily volume is below 10,000 shares."""
        return self.avg_volume_90d < 10_000

    @property
    def is_exotic(self) -> bool:
        """True if this is a SPAC, unit, warrant, right, or similar exotic."""
        return self.type_label in ("Warrant", "Right", "Unit", "SPAC")


@dataclass
class ValidationResult:
    """Validation result for one ticker + timeframe combination."""

    ticker: str
    timeframe: str
    our_bar_count: int
    tv_bar_count: int
    overlapping_bars: int
    group: str = "fixed"  # "fixed", "random", or "retry"
    mismatches: list[CandleMismatch] = field(default_factory=list)
    error: str | None = None
    meta: StockMeta | None = None

    @property
    def mismatch_count(self) -> int:
        return len([m for m in self.mismatches if m.is_significant])

    @property
    def match_pct(self) -> float:
        if self.overlapping_bars == 0:
            return 0.0
        total_checks = self.overlapping_bars * 5
        return (1 - self.mismatch_count / total_checks) * 100

    @property
    def status(self) -> str:
        if self.error:
            return "❌"
        if self.mismatch_count == 0:
            return "✅"
        return "⚠️"

    @property
    def worst_diff(self) -> str:
        """Human-readable worst mismatch."""
        significant = [m for m in self.mismatches if m.is_significant]
        if not significant:
            return "—"
        worst = max(significant, key=lambda m: abs(m.pct_diff))
        return f"{worst.field}: {worst.pct_diff:+.2f}%"

    @property
    def note(self) -> str:
        """Context note explaining ignorable mismatches."""
        if not self.meta:
            return ""
        parts: list[str] = []
        if self.meta.is_exotic:
            parts.append(self.meta.type_label)
        if self.meta.is_low_liquidity:
            parts.append(f"avg vol {self.meta.avg_volume_90d:,}")
        if parts and self.mismatch_count > 0:
            return "⏭️ " + ", ".join(parts) + " — safe to ignore"
        if self.meta.is_exotic or self.meta.is_low_liquidity:
            return ", ".join(parts)
        return ""


# ------------------------------------------------------------------ #
#  Comparison logic                                                    #
# ------------------------------------------------------------------ #


def _normalize_dates_for_merge(
    our_df: pd.DataFrame,
    tv_df: pd.DataFrame,
    timeframe: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Normalize dates so our DB and second-source candles can be joined.

    - **daily**: exact date match (no change needed).
    - **weekly**: both sources use Monday-start weeks, but our pandas ``W-SUN``
      resample labels the bucket on the **Saturday before** the week while YF
      labels on Monday.  Normalise to ISO year-week so the same trading week
      always matches.
    - **monthly**: our DB uses 1st-of-month (``MS`` resample), YF uses the
      first *trading* day (e.g. 2025-11-03 for November).  Normalise to
      year-month.
    - **quarterly**: same month-start logic but at quarter boundaries.
    """
    if timeframe == "daily":
        return our_df, tv_df

    our = our_df.copy()
    tv = tv_df.copy()

    if timeframe == "weekly":
        # Map each date to the Monday of that ISO week
        our["date"] = pd.to_datetime(our["date"]).apply(
            lambda d: (d - pd.Timedelta(days=d.weekday())).date()
        )
        tv["date"] = pd.to_datetime(tv["date"]).apply(
            lambda d: (d - pd.Timedelta(days=d.weekday())).date()
        )
    elif timeframe in ("monthly", "quarterly"):
        # Map each date to the 1st of its month
        our["date"] = pd.to_datetime(our["date"]).apply(
            lambda d: d.replace(day=1).date() if hasattr(d, "replace") else d
        )
        tv["date"] = pd.to_datetime(tv["date"]).apply(
            lambda d: d.replace(day=1).date() if hasattr(d, "replace") else d
        )

    return our, tv


def compare_candles(
    ticker: str,
    timeframe: str,
    our_df: pd.DataFrame,
    tv_df: pd.DataFrame,
    price_tolerance: float = DEFAULT_PRICE_TOLERANCE,
    volume_tolerance: float = DEFAULT_VOLUME_TOLERANCE,
    group: str = "fixed",
) -> ValidationResult:
    """
    Compare our candles against a second source's candles bar-by-bar.

    Joins on date, compares OHLCV fields, and returns a ValidationResult
    with any mismatches.
    """
    our_norm, tv_norm = _normalize_dates_for_merge(our_df, tv_df, timeframe)
    merged = our_norm.merge(tv_norm, on="date", suffixes=("_ours", "_tv"), how="inner")

    result = ValidationResult(
        ticker=ticker,
        timeframe=timeframe,
        our_bar_count=len(our_df),
        tv_bar_count=len(tv_df),
        overlapping_bars=len(merged),
        group=group,
    )

    if len(merged) == 0:
        result.error = "No overlapping dates found"
        return result

    for field_name in ["open", "high", "low", "close", "volume"]:
        tolerance = volume_tolerance if field_name == "volume" else price_tolerance

        ours_col = f"{field_name}_ours"
        tv_col = f"{field_name}_tv"

        for _, row in merged.iterrows():
            our_val = float(row[ours_col])
            tv_val = float(row[tv_col])

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
#  Quarterly aggregation from monthly data                             #
# ------------------------------------------------------------------ #


def aggregate_monthly_to_quarterly(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate monthly OHLCV data into quarterly bars.

    Uses calendar quarter starts (QS) matching our DB convention.
    """
    if monthly_df is None or monthly_df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = monthly_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    quarterly = (
        df.resample("QS")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
    )

    quarterly = quarterly.reset_index()
    quarterly["date"] = quarterly["date"].dt.date
    return quarterly


# ------------------------------------------------------------------ #
#  Yahoo Finance data fetcher                                          #
# ------------------------------------------------------------------ #

# yfinance interval strings for each timeframe
_YF_INTERVALS: dict[str, str] = {
    "daily": "1d",
    "weekly": "1wk",
    "monthly": "1mo",
    # quarterly is derived from monthly — no native YF interval
}

# Approximate lookback periods per timeframe
_YF_PERIODS: dict[str, str] = {
    "daily": "2y",  # ~500 trading days
    "weekly": "5y",  # ~260 weeks
    "monthly": "10y",  # ~120 months
}


def fetch_yf_candles(
    ticker: str,
    timeframe: str,
    n_bars: int,
) -> pd.DataFrame | None:
    """
    Fetch OHLCV data from Yahoo Finance for a ticker + timeframe.

    For quarterly: fetches monthly and aggregates.
    Returns DataFrame with: date, open, high, low, close, volume.

    No authentication required — yfinance uses a free REST API.
    """
    if not YF_AVAILABLE:
        raise RuntimeError('yfinance is not installed. Run: pip install "praxialpha[validate]"')

    # Quarterly: fetch monthly from YF, then aggregate
    if timeframe == "quarterly":
        monthly_df = fetch_yf_candles(ticker, "monthly", n_bars * 3)
        if monthly_df is None:
            return None
        return aggregate_monthly_to_quarterly(monthly_df)

    interval = _YF_INTERVALS.get(timeframe)
    if interval is None:
        logger.warning("Timeframe %s not supported by yfinance", timeframe)
        return None

    period = _YF_PERIODS.get(timeframe, "2y")

    try:
        yticker = yf.Ticker(ticker)
        df = yticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as e:
        logger.warning("yfinance error for %s (%s): %s", ticker, timeframe, e)
        return None

    if df is None or df.empty:
        logger.warning("No data from Yahoo Finance for %s (%s)", ticker, timeframe)
        return None

    df = df.reset_index()

    # yfinance returns "Date" (daily) or "Date" column — normalise
    date_col = "Date" if "Date" in df.columns else "Datetime"
    if date_col not in df.columns:
        # Fallback: first column
        date_col = df.columns[0]

    df["date"] = pd.to_datetime(df[date_col]).dt.date

    # yfinance uses title-case columns: Open, High, Low, Close, Volume
    col_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=col_map)

    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(set(df.columns)):
        logger.warning("Missing columns for %s (%s). Got: %s", ticker, timeframe, list(df.columns))
        return None

    result = df[["date", "open", "high", "low", "close", "volume"]].copy()

    # Trim to requested bar count (most recent n_bars)
    if len(result) > n_bars:
        result = result.tail(n_bars).reset_index(drop=True)

    return result


# ------------------------------------------------------------------ #
#  Stock metadata lookup                                               #
# ------------------------------------------------------------------ #


async def fetch_stock_metadata(ticker: str) -> StockMeta:
    """
    Look up lightweight metadata for a ticker from our DB.

    Returns name, exchange, asset_type, and 90-day average daily volume.
    Used to annotate validation results so the user can tell whether
    a mismatch is on a low-liquidity / exotic security and can be ignored.
    """
    from sqlalchemy import text

    from backend.database import async_session_factory

    meta = StockMeta()
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT s.name, s.exchange, s.asset_type, "
                "  COALESCE((SELECT AVG(volume)::bigint FROM daily_ohlcv "
                "   WHERE stock_id = s.id AND date > CURRENT_DATE - 90), 0) AS avg_vol "
                "FROM stocks s WHERE s.ticker = :ticker LIMIT 1"
            ),
            {"ticker": ticker},
        )
        row = result.fetchone()
        if row:
            meta.name = row.name or ""
            meta.exchange = row.exchange or ""
            meta.asset_type = row.asset_type or ""
            meta.avg_volume_90d = int(row.avg_vol) if row.avg_vol else 0
    return meta


# ------------------------------------------------------------------ #
#  Our DB data fetcher                                                 #
# ------------------------------------------------------------------ #


async def fetch_our_candles(
    ticker: str,
    timeframe: str,
    n_bars: int,
) -> pd.DataFrame | None:
    """Fetch split-adjusted OHLCV from our database."""
    from sqlalchemy import text

    from backend.database import async_session_factory
    from backend.services.candle_service import CandleService, Timeframe

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM stocks WHERE ticker = :ticker LIMIT 1"),
            {"ticker": ticker},
        )
        row = result.fetchone()
        if not row:
            return None

        stock_id = row.id
        tf = Timeframe(timeframe)
        service = CandleService(session)

        candles = await service.get_candles(
            stock_id=stock_id,
            timeframe=tf,
            limit=n_bars,
            adjusted=True,
        )

    if not candles:
        return None

    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df[["date", "open", "high", "low", "close", "volume"]]


# ------------------------------------------------------------------ #
#  Random ticker sampling                                              #
# ------------------------------------------------------------------ #


async def sample_random_tickers(n: int = RANDOM_TOTAL) -> list[str]:
    """
    Sample n random tickers from our DB, spread across exchanges.

    Distribution: 3 NYSE, 3 NASDAQ, 2 AMEX, 2 ETFs.
    Excludes the fixed tickers to avoid duplicates.
    """
    from sqlalchemy import text

    from backend.database import async_session_factory

    exclude = set(FIXED_TICKERS)
    sampled: list[str] = []

    async with async_session_factory() as session:
        # Sample from each exchange
        for exchange, count in RANDOM_SAMPLE_CONFIG.items():
            result = await session.execute(
                text(
                    "SELECT ticker FROM stocks "
                    "WHERE exchange = :exchange "
                    "AND asset_type = 'Common Stock' "
                    "AND ticker != ALL(:exclude) "
                    "ORDER BY random() LIMIT :limit"
                ),
                {"exchange": exchange, "exclude": list(exclude), "limit": count},
            )
            tickers = [row[0] for row in result.fetchall()]
            sampled.extend(tickers)
            exclude.update(tickers)

        # Sample ETFs from any exchange
        result = await session.execute(
            text(
                "SELECT ticker FROM stocks "
                "WHERE asset_type = 'ETF' "
                "AND ticker != ALL(:exclude) "
                "ORDER BY random() LIMIT :limit"
            ),
            {"exclude": list(exclude), "limit": RANDOM_ETF_COUNT},
        )
        etf_tickers = [row[0] for row in result.fetchall()]
        sampled.extend(etf_tickers)

    return sampled


# ------------------------------------------------------------------ #
#  Failure persistence                                                 #
# ------------------------------------------------------------------ #


def load_previous_failures() -> dict[str, Any] | None:
    """
    Load previous validation failures from JSON file.

    Returns dict with keys: timestamp, failures (list of {ticker, timeframe}),
    random_tickers (list), or None if no file exists.
    """
    if not FAILURES_PATH.exists():
        return None
    try:
        with open(FAILURES_PATH) as f:
            data: dict[str, Any] = json.load(f)
            return data
    except (json.JSONDecodeError, OSError):
        return None


def save_failures(
    results: list[ValidationResult],
    random_tickers: list[str],
) -> None:
    """
    Save failed validations to JSON for the next run.

    Only saves if there are failures; deletes the file if all pass.
    """
    failures = []
    for r in results:
        if r.mismatch_count > 0 or r.error:
            failures.append(
                {
                    "ticker": r.ticker,
                    "timeframe": r.timeframe,
                    "group": r.group,
                    "error": r.error,
                    "mismatch_count": r.mismatch_count,
                    "match_pct": round(r.match_pct, 2) if not r.error else 0.0,
                    "worst_diff": r.worst_diff,
                }
            )

    if not failures:
        # All passed — delete the failure file
        if FAILURES_PATH.exists():
            FAILURES_PATH.unlink()
        return

    FAILURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": datetime.now().isoformat(),
        "failures": failures,
        "random_tickers": random_tickers,
    }
    with open(FAILURES_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_retry_tickers_from_failures() -> list[tuple[str, str]]:
    """
    Get (ticker, timeframe) pairs that failed in the previous run.

    These should be re-checked in the next run.
    """
    prev = load_previous_failures()
    if not prev:
        return []
    return [(f["ticker"], f["timeframe"]) for f in prev.get("failures", [])]


# ------------------------------------------------------------------ #
#  Summary helpers                                                     #
# ------------------------------------------------------------------ #


def compute_summary(results: list[ValidationResult]) -> dict:
    """Compute overall summary statistics from results."""
    total_checks = 0
    total_mismatches = 0
    passed = 0
    failed = 0
    errors = 0

    for r in results:
        if r.error:
            errors += 1
        elif r.mismatch_count == 0:
            passed += 1
            total_checks += r.overlapping_bars * 5
        else:
            failed += 1
            total_checks += r.overlapping_bars * 5
            total_mismatches += r.mismatch_count

    overall_match = (
        round((1 - total_mismatches / total_checks) * 100, 2) if total_checks > 0 else 0.0
    )

    return {
        "total_combinations": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total_field_checks": total_checks,
        "total_mismatches": total_mismatches,
        "overall_match_pct": overall_match,
    }
