"""
Debug script: Compare AAPL daily volume between our DB and TradingView.

Shows the exact dates and values where volume mismatches occur.
"""

import asyncio
import os
import sys
from pathlib import Path

# When running outside Docker, override DB host BEFORE any project imports
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha"
)

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd


async def main():
    from sqlalchemy import text

    from backend.database import async_session_factory
    from backend.services.candle_service import CandleService, Timeframe
    from backend.services.tv_validation_service import (
        compare_candles,
        fetch_tv_candles,
        get_tv_client,
    )

    ticker = "AAPL"
    n_bars = 252

    # --- Fetch our data ---
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT id FROM stocks WHERE ticker = :ticker LIMIT 1"),
            {"ticker": ticker},
        )
        row = result.fetchone()
        stock_id = row.id

        service = CandleService(session)

        # Get adjusted candles (what validation uses)
        adjusted_candles = await service.get_candles(
            stock_id=stock_id, timeframe=Timeframe.DAILY, limit=n_bars, adjusted=True
        )

        # Get raw candles (no split adjustment) for comparison
        raw_candles = await service.get_candles(
            stock_id=stock_id, timeframe=Timeframe.DAILY, limit=n_bars, adjusted=False
        )

        # Get splits
        splits = await service._get_split_factors(stock_id)

    our_adj_df = pd.DataFrame(adjusted_candles)
    our_adj_df["date"] = pd.to_datetime(our_adj_df["date"]).dt.date

    our_raw_df = pd.DataFrame(raw_candles)
    our_raw_df["date"] = pd.to_datetime(our_raw_df["date"]).dt.date

    print(f"=== {ticker} ===")
    print(f"Splits in DB: {splits}")
    print(f"Our adjusted daily bars: {len(our_adj_df)}")
    print(f"Our raw daily bars:      {len(our_raw_df)}")

    # --- Fetch TV data ---
    tv = get_tv_client()
    tv_df = fetch_tv_candles(tv, ticker, "daily", n_bars)
    print(f"TV daily bars:           {len(tv_df)}")

    # --- Compare: find the 2 mismatching bars ---
    result = compare_candles(ticker, "daily", our_adj_df, tv_df)
    print(f"\nMismatches: {result.mismatch_count}")

    for m in result.mismatches:
        if m.is_significant:
            print(f"\n  Date: {m.date}")
            print(f"  Field: {m.field}")
            print(f"  Our value:  {m.our_value}")
            print(f"  TV value:   {m.tv_value}")
            print(f"  Diff:       {m.pct_diff:+.4f}%")

            # Look up the raw volume on that date
            match_date = pd.to_datetime(m.date).date()
            raw_row = our_raw_df[our_raw_df["date"] == match_date]
            if not raw_row.empty:
                print(f"  Our RAW volume: {int(raw_row.iloc[0]['volume'])}")

            # Check what factor was applied
            from backend.services.candle_service import CandleService

            dummy_service = CandleService.__new__(CandleService)
            factor = dummy_service._compute_cumulative_split_factor(match_date, splits)
            print(f"  Split factor:   {factor}")

    # --- Also check: does TV adjust volume? ---
    # Compare raw vs TV for those same dates
    merged = our_raw_df.merge(tv_df, on="date", suffixes=("_raw", "_tv"))
    vol_diff = merged[["date", "volume_raw", "volume_tv"]].copy()
    vol_diff["pct_diff"] = (
        (vol_diff["volume_raw"] - vol_diff["volume_tv"]) / vol_diff["volume_tv"] * 100
    ).round(2)

    # Show top 10 biggest diffs
    vol_diff["abs_pct"] = vol_diff["pct_diff"].abs()
    top10 = vol_diff.nlargest(10, "abs_pct")
    print("\n=== Top 10 volume diffs (raw vs TV) ===")
    print(top10[["date", "volume_raw", "volume_tv", "pct_diff"]].to_string(index=False))

    big_diffs = vol_diff[vol_diff["pct_diff"].abs() > 5]
    print(f"\n=== Raw volume vs TV (>5% diff): {len(big_diffs)} bars ===")
    if not big_diffs.empty:
        print(big_diffs[["date", "volume_raw", "volume_tv", "pct_diff"]].to_string(index=False))
    else:
        print("(none — raw volume matches TV)")

    # Also check adjusted vs TV
    merged_adj = our_adj_df.merge(tv_df, on="date", suffixes=("_adj", "_tv"))
    vol_diff_adj = merged_adj[["date", "volume_adj", "volume_tv"]].copy()
    vol_diff_adj["pct_diff"] = (
        (vol_diff_adj["volume_adj"] - vol_diff_adj["volume_tv"]) / vol_diff_adj["volume_tv"] * 100
    ).round(2)
    big_diffs_adj = vol_diff_adj[vol_diff_adj["pct_diff"].abs() > 5]
    print(f"\n=== Adjusted volume vs TV (>5% diff): {len(big_diffs_adj)} bars ===")
    if not big_diffs_adj.empty:
        print(big_diffs_adj.to_string(index=False))
    else:
        print("(none — adjusted volume matches TV)")


if __name__ == "__main__":
    asyncio.run(main())
