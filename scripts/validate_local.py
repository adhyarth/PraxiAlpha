#!/usr/bin/env python3
"""
Local validation: compare our DB against Yahoo Finance for
10 fixed stress-test tickers + 10 random tickers × 4 timeframes.

Usage:
    PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha" \
        python3 scripts/validate_local.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Disable SQLAlchemy echo before any backend imports
os.environ.setdefault("APP_DEBUG", "false")

# Suppress noisy SQLAlchemy / connection pool logs
logging.basicConfig(level=logging.WARNING)
for _name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool"):
    logging.getLogger(_name).setLevel(logging.WARNING)
    logging.getLogger(_name).handlers.clear()
    logging.getLogger(_name).propagate = False

import pandas as pd

from backend.services.data_validation_service import (
    ALL_TIMEFRAMES,
    FIXED_TICKERS,
    TIMEFRAME_BARS,
    ValidationResult,
    compare_candles,
    fetch_our_candles,
    fetch_yf_candles,
    sample_random_tickers,
)

# Suppress SQLAlchemy echo=True output (engine creates handlers at import time)
for _name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.pool"):
    _logger = logging.getLogger(_name)
    _logger.setLevel(logging.WARNING)
    _logger.handlers.clear()
    _logger.propagate = False


# ------------------------------------------------------------------ #
#  Summary row for the final table                                     #
# ------------------------------------------------------------------ #
@dataclass
class SummaryRow:
    ticker: str
    group: str  # "fixed" or "random"
    timeframe: str
    status: str
    our_bars: int
    yf_bars: int
    overlap: int
    match_pct: str
    mismatches: int
    worst_diff: str
    error: str


# ------------------------------------------------------------------ #
#  Validate one ticker × one timeframe                                 #
# ------------------------------------------------------------------ #
async def validate_one(
    ticker: str, tf: str, n_bars: int, group: str
) -> tuple[SummaryRow, ValidationResult | None]:
    """Run comparison for a single ticker + timeframe. Returns summary row."""
    label = f"  {ticker:6s} / {tf:10s}"

    # ---- Fetch from our DB ----
    try:
        our_df = await fetch_our_candles(ticker, tf, n_bars)
    except Exception as e:
        print(f"{label}  ❌ DB error: {e}")
        return SummaryRow(ticker, group, tf, "❌", 0, 0, 0, "—", 0, "—", str(e)), None

    if our_df is None or our_df.empty:
        print(f"{label}  ❌ No data in our DB")
        return SummaryRow(ticker, group, tf, "❌", 0, 0, 0, "—", 0, "—", "No DB data"), None

    # ---- Fetch from Yahoo Finance ----
    try:
        yf_df = fetch_yf_candles(ticker, tf, n_bars)
    except Exception as e:
        print(f"{label}  ❌ YF error: {e}")
        return (
            SummaryRow(ticker, group, tf, "❌", len(our_df), 0, 0, "—", 0, "—", str(e)),
            None,
        )

    if yf_df is None or yf_df.empty:
        print(f"{label}  ❌ No YF data")
        return (
            SummaryRow(ticker, group, tf, "❌", len(our_df), 0, 0, "—", 0, "—", "No YF data"),
            None,
        )

    # ---- Compare ----
    result = compare_candles(ticker, tf, our_df, yf_df, group=group)

    row = SummaryRow(
        ticker=ticker,
        group=group,
        timeframe=tf,
        status=result.status,
        our_bars=result.our_bar_count,
        yf_bars=result.ref_bar_count,
        overlap=result.overlapping_bars,
        match_pct=f"{result.match_pct:.1f}%",
        mismatches=result.mismatch_count,
        worst_diff=result.worst_diff if not result.error else "—",
        error=result.error or "",
    )

    # One-line progress
    if result.mismatch_count == 0 and not result.error:
        print(f"{label}  ✅  {result.match_pct:5.1f}%  ({result.overlapping_bars} bars)")
    elif result.error:
        print(f"{label}  ❌  {result.error}")
    else:
        print(
            f"{label}  ⚠️  {result.match_pct:5.1f}%  "
            f"({result.mismatch_count} mismatch, worst: {result.worst_diff})"
        )

    return row, result


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #
async def main() -> None:
    t0 = time.time()

    print("=" * 78)
    print("  PraxiAlpha — Local Data Validation")
    print("  10 fixed tickers + 10 random tickers × 4 timeframes")
    print("=" * 78)

    # ---- Sample random tickers ----
    print("\n📦 Sampling 10 random tickers from our DB...")
    try:
        random_tickers = await sample_random_tickers(10)
        print(f"   → {', '.join(random_tickers)}")
    except Exception as e:
        print(f"   ❌ Could not sample random tickers: {e}")
        random_tickers = []

    # ---- Build job list ----
    jobs: list[tuple[str, str, str]] = []  # (ticker, timeframe, group)
    for t in FIXED_TICKERS:
        for tf in ALL_TIMEFRAMES:
            jobs.append((t, tf, "fixed"))
    for t in random_tickers:
        for tf in ALL_TIMEFRAMES:
            jobs.append((t, tf, "random"))

    total = len(jobs)
    print(f"\n📋 Total: {len(FIXED_TICKERS)} fixed + {len(random_tickers)} random = "
          f"{len(FIXED_TICKERS) + len(random_tickers)} tickers × {len(ALL_TIMEFRAMES)} TF = {total} checks\n")

    # ---- Run all comparisons ----
    summary_rows: list[SummaryRow] = []
    all_results: list[ValidationResult] = []
    current_ticker = ""

    for idx, (ticker, tf, group) in enumerate(jobs):
        if ticker != current_ticker:
            current_ticker = ticker
            tag = f"[{group}]"
            print(f"\n{'─' * 78}")
            print(f"  {tag:8s}  {ticker}")
            print(f"{'─' * 78}")

        row, result = await validate_one(ticker, tf, TIMEFRAME_BARS[tf], group)
        summary_rows.append(row)
        if result:
            all_results.append(result)

        # Gentle rate limit for YF
        if idx < total - 1:
            await asyncio.sleep(0.3)

    # ---- Summary table ----
    elapsed = time.time() - t0
    print(f"\n\n{'=' * 78}")
    print(f"  SUMMARY  ({elapsed:.1f}s)")
    print(f"{'=' * 78}\n")

    # Counts
    passed = sum(1 for r in summary_rows if r.status == "✅")
    warned = sum(1 for r in summary_rows if r.status == "⚠️")
    failed = sum(1 for r in summary_rows if r.status == "❌")

    print(f"  ✅ Passed: {passed}   ⚠️ Mismatches: {warned}   ❌ Errors: {failed}   Total: {total}\n")

    # Print table header
    hdr = (
        f"  {'Status':6s}  {'Ticker':8s}  {'Group':7s}  {'Timeframe':10s}  "
        f"{'Overlap':>7s}  {'Match':>7s}  {'Mis':>4s}  {'Worst Diff':20s}  {'Error'}"
    )
    print(hdr)
    print(f"  {'─' * len(hdr)}")

    for r in summary_rows:
        error_short = (r.error[:40] + "…") if len(r.error) > 40 else r.error
        print(
            f"  {r.status:6s}  {r.ticker:8s}  {r.group:7s}  {r.timeframe:10s}  "
            f"{r.overlap:>7d}  {r.match_pct:>7s}  {r.mismatches:>4d}  {r.worst_diff:20s}  {error_short}"
        )

    # ---- Mismatch details (only for warnings) ----
    warned_results = [r for r in all_results if r.mismatch_count > 0]
    if warned_results:
        print(f"\n\n{'=' * 78}")
        print(f"  MISMATCH DETAILS (top 3 per ticker/tf)")
        print(f"{'=' * 78}")
        for r in warned_results:
            sig = [m for m in r.mismatches if m.is_significant]
            print(f"\n  {r.ticker} / {r.timeframe} — {len(sig)} significant mismatch(es)")
            for m in sorted(sig, key=lambda x: abs(x.pct_diff), reverse=True)[:3]:
                print(
                    f"    ⚠️  {m.date}  {m.field:6s}  "
                    f"ours={m.our_value:>14.4f}  yf={m.ref_value:>14.4f}  "
                    f"diff={m.pct_diff:+.2f}%"
                )

    print(f"\n{'=' * 78}")
    print(f"  Done! ({elapsed:.1f}s)")
    print(f"{'=' * 78}\n")


def _print_tail(df: pd.DataFrame, n: int = 3) -> None:
    """Print the last n rows of a candle DataFrame."""
    tail = df.tail(n)
    for _, row in tail.iterrows():
        print(
            f"    {row['date']}  O={row['open']:>10.4f}  H={row['high']:>10.4f}  "
            f"L={row['low']:>10.4f}  C={row['close']:>10.4f}  V={int(row['volume']):>14,}"
        )


if __name__ == "__main__":
    asyncio.run(main())
