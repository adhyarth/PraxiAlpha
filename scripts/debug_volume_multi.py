"""
Debug script: Compare daily volume for N random tickers between our DB and TradingView.

Validates that the 10% volume tolerance accommodates real-world provider
discrepancies across a representative sample — not just AAPL.

Usage:
    python scripts/debug_volume_multi.py              # 10 random tickers
    python scripts/debug_volume_multi.py --n 20       # 20 random tickers
    python scripts/debug_volume_multi.py --tickers AAPL MSFT NVDA   # specific tickers
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# When running outside Docker, override DB host BEFORE any project imports
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha"
)

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd


async def sample_random_tickers(n: int) -> list[str]:
    """Pick n random active Common Stock / ETF tickers from the DB."""
    from sqlalchemy import text

    from backend.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT ticker FROM stocks "
                "WHERE asset_type IN ('Common Stock', 'ETF') "
                "AND exchange IN ('NYSE', 'NASDAQ', 'AMEX') "
                "ORDER BY random() LIMIT :n"
            ),
            {"n": n},
        )
        return [row[0] for row in result.fetchall()]


async def fetch_our_data(ticker: str, n_bars: int) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """Return (adjusted_df, raw_df, splits) for a ticker."""
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
            return pd.DataFrame(), pd.DataFrame(), []

        stock_id = row.id
        service = CandleService(session)

        adjusted = await service.get_candles(
            stock_id=stock_id, timeframe=Timeframe.DAILY, limit=n_bars, adjusted=True
        )
        raw = await service.get_candles(
            stock_id=stock_id, timeframe=Timeframe.DAILY, limit=n_bars, adjusted=False
        )
        splits = await service._get_split_factors(stock_id)

    adj_df = pd.DataFrame(adjusted)
    if not adj_df.empty:
        adj_df["date"] = pd.to_datetime(adj_df["date"]).dt.date

    raw_df = pd.DataFrame(raw)
    if not raw_df.empty:
        raw_df["date"] = pd.to_datetime(raw_df["date"]).dt.date

    return adj_df, raw_df, splits


def analyze_ticker(
    ticker: str,
    adj_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    tv_df: pd.DataFrame,
    splits: list,
) -> dict:
    """Compare one ticker's volume data. Returns a summary dict."""
    summary = {
        "ticker": ticker,
        "our_bars": len(adj_df),
        "tv_bars": len(tv_df),
        "splits": len(splits),
        "overlap": 0,
        "raw_max_diff_pct": 0.0,
        "raw_bars_gt5pct": 0,
        "raw_bars_gt10pct": 0,
        "adj_max_diff_pct": 0.0,
        "adj_bars_gt5pct": 0,
        "adj_bars_gt10pct": 0,
        "worst_date": "",
        "worst_raw_vol": 0,
        "worst_tv_vol": 0,
        "status": "✅",
    }

    # Raw volume vs TV
    merged_raw = raw_df.merge(tv_df, on="date", suffixes=("_raw", "_tv"))
    summary["overlap"] = len(merged_raw)

    if merged_raw.empty:
        summary["status"] = "⚠️ no overlap"
        return summary

    vol_raw = merged_raw[["date", "volume_raw", "volume_tv"]].copy()
    vol_raw["pct_diff"] = (
        (vol_raw["volume_raw"] - vol_raw["volume_tv"]) / vol_raw["volume_tv"] * 100
    ).round(4)
    vol_raw["abs_pct"] = vol_raw["pct_diff"].abs()

    summary["raw_max_diff_pct"] = round(vol_raw["abs_pct"].max(), 2)
    summary["raw_bars_gt5pct"] = int((vol_raw["abs_pct"] > 5).sum())
    summary["raw_bars_gt10pct"] = int((vol_raw["abs_pct"] > 10).sum())

    # Adjusted volume vs TV
    merged_adj = adj_df.merge(tv_df, on="date", suffixes=("_adj", "_tv"))
    if not merged_adj.empty:
        vol_adj = merged_adj[["date", "volume_adj", "volume_tv"]].copy()
        vol_adj["pct_diff"] = (
            (vol_adj["volume_adj"] - vol_adj["volume_tv"]) / vol_adj["volume_tv"] * 100
        ).round(4)
        vol_adj["abs_pct"] = vol_adj["pct_diff"].abs()
        summary["adj_max_diff_pct"] = round(vol_adj["abs_pct"].max(), 2)
        summary["adj_bars_gt5pct"] = int((vol_adj["abs_pct"] > 5).sum())
        summary["adj_bars_gt10pct"] = int((vol_adj["abs_pct"] > 10).sum())

        worst_row = vol_adj.loc[vol_adj["abs_pct"].idxmax()]
        summary["worst_date"] = str(worst_row["date"])
        summary["worst_raw_vol"] = int(worst_row["volume_adj"])
        summary["worst_tv_vol"] = int(worst_row["volume_tv"])
    else:
        worst_row = vol_raw.loc[vol_raw["abs_pct"].idxmax()]
        summary["worst_date"] = str(worst_row["date"])
        summary["worst_raw_vol"] = int(worst_row["volume_raw"])
        summary["worst_tv_vol"] = int(worst_row["volume_tv"])

    # Status
    if summary["adj_bars_gt10pct"] > 0 or summary["raw_bars_gt10pct"] > 0:
        summary["status"] = "❌ >10%"
    elif summary["adj_bars_gt5pct"] > 2 or summary["raw_bars_gt5pct"] > 2:
        summary["status"] = "⚠️ >5%"

    return summary


async def main():
    from backend.services.tv_validation_service import (
        fetch_tv_candles,
        get_tv_client,
    )

    parser = argparse.ArgumentParser(description="Multi-ticker volume debug")
    parser.add_argument("--n", type=int, default=10, help="Number of random tickers")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (overrides --n)")
    parser.add_argument("--bars", type=int, default=252, help="Number of bars to compare")
    args = parser.parse_args()

    n_bars = args.bars

    # --- Pick tickers ---
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        print(f"Using {len(tickers)} specified tickers: {', '.join(tickers)}")
    else:
        print(f"Sampling {args.n} random tickers from DB...")
        tickers = await sample_random_tickers(args.n)
        print(f"Selected: {', '.join(tickers)}")

    print(f"Bars per ticker: {n_bars}")
    print("=" * 100)

    summaries: list[dict] = []
    skipped: list[str] = []

    for i, ticker in enumerate(tickers):
        print(f"\n[{i + 1}/{len(tickers)}] {ticker}...", end=" ", flush=True)

        # Fetch our data
        adj_df, raw_df, splits = await fetch_our_data(ticker, n_bars)
        if adj_df.empty:
            print("SKIP (not in DB)")
            skipped.append(ticker)
            continue

        # Fetch TV data (fresh client each time to avoid TCP errors)
        try:
            tv = get_tv_client()
            time.sleep(1)  # rate limit
            tv_df = fetch_tv_candles(tv, ticker, "daily", n_bars)
        except Exception as e:
            print(f"SKIP (TV error: {e})")
            skipped.append(ticker)
            continue

        if tv_df is None or tv_df.empty:
            print("SKIP (not on TV)")
            skipped.append(ticker)
            continue

        # Analyze
        summary = analyze_ticker(ticker, adj_df, raw_df, tv_df, splits)
        summaries.append(summary)

        print(
            f"{summary['status']}  "
            f"overlap={summary['overlap']}  "
            f"splits={summary['splits']}  "
            f"raw_max={summary['raw_max_diff_pct']:.1f}%  "
            f"adj_max={summary['adj_max_diff_pct']:.1f}%  "
            f"raw>5%={summary['raw_bars_gt5pct']}  "
            f"adj>10%={summary['adj_bars_gt10pct']}"
        )

        time.sleep(1.5)  # rate limit between tickers

    # --- Summary table ---
    print("\n" + "=" * 100)
    print("  📊 MULTI-TICKER VOLUME COMPARISON SUMMARY")
    print("=" * 100)

    if summaries:
        df = pd.DataFrame(summaries)
        cols = [
            "ticker",
            "status",
            "overlap",
            "splits",
            "raw_max_diff_pct",
            "raw_bars_gt5pct",
            "raw_bars_gt10pct",
            "adj_max_diff_pct",
            "adj_bars_gt5pct",
            "adj_bars_gt10pct",
            "worst_date",
        ]
        print(df[cols].to_string(index=False))

        # Aggregate stats
        print("\n--- Aggregate ---")
        print(f"Tickers analyzed:  {len(summaries)}")
        print(f"Tickers skipped:   {len(skipped)} ({', '.join(skipped) if skipped else 'none'})")
        print(f"Max raw diff:      {df['raw_max_diff_pct'].max():.2f}%")
        print(f"Max adjusted diff: {df['adj_max_diff_pct'].max():.2f}%")
        print(f"Tickers w/ raw bars >5%:  {(df['raw_bars_gt5pct'] > 0).sum()}")
        print(f"Tickers w/ raw bars >10%: {(df['raw_bars_gt10pct'] > 0).sum()}")
        print(f"Tickers w/ adj bars >5%:  {(df['adj_bars_gt5pct'] > 0).sum()}")
        print(f"Tickers w/ adj bars >10%: {(df['adj_bars_gt10pct'] > 0).sum()}")

        # Verdict
        adj_10pct_tickers = df[df["adj_bars_gt10pct"] > 0]["ticker"].tolist()
        if adj_10pct_tickers:
            print(
                f"\n⚠️  Tickers exceeding 10% adjusted volume tolerance: {', '.join(adj_10pct_tickers)}"
            )
            print("   These may warrant investigation.")
        else:
            print(f"\n✅ All {len(summaries)} tickers within 10% adjusted volume tolerance.")
            print("   The volume tolerance fix is validated across a diverse sample.")
    else:
        print("No tickers were successfully analyzed.")


if __name__ == "__main__":
    asyncio.run(main())
