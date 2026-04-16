"""
SOXX Overextension Analysis

Find all instances when SOXX weekly high was >= 91.71% above the 200-week SMA
(same extension as the week ending April 10, 2026: high 389.60, 200W SMA 203.23).

Output: CSV with dates, prices, and forward returns for every week (W+1 through W+52).
"""

import asyncio
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Direct localhost connection (bypassing Docker internal hostname)
DATABASE_URL = "postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main():
    # Current week's data (April 10, 2026)
    current_high = 389.60
    current_200w_sma = 203.23
    current_extension_pct = (current_high - current_200w_sma) / current_200w_sma * 100
    print(f"Current SOXX extension: {current_extension_pct:.2f}% above 200W SMA")
    print(f"  High: ${current_high:.2f}, 200W SMA: ${current_200w_sma:.2f}")
    print()

    async with async_session_factory() as session:
        # Get SOXX stock_id
        result = await session.execute(text("SELECT id FROM stocks WHERE ticker = 'SOXX' LIMIT 1"))
        row = result.fetchone()
        if not row:
            print("ERROR: SOXX not found in database")
            return
        stock_id = row.id

        # Fetch weekly candles for SOXX (from the weekly_ohlcv view)
        result = await session.execute(
            text("""
                SELECT
                    bucket as date,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM weekly_ohlcv
                WHERE stock_id = :stock_id
                ORDER BY bucket ASC
            """),
            {"stock_id": stock_id},
        )
        rows = result.fetchall()

    if not rows:
        print("ERROR: No weekly data found for SOXX")
        return

    # Convert to DataFrame
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    print(f"Loaded {len(df)} weekly candles for SOXX")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print()

    # Compute 200-week SMA of close
    df["sma_200w"] = df["close"].rolling(window=200, min_periods=200).mean()

    # Compute extension: how far the weekly HIGH is above the 200W SMA
    df["extension_pct"] = (df["high"] - df["sma_200w"]) / df["sma_200w"] * 100

    # Filter: extension >= current extension (91.71%)
    threshold = current_extension_pct
    signals = df[df["extension_pct"] >= threshold].copy()

    print(f"Found {len(signals)} weeks where SOXX high was >= {threshold:.2f}% above 200W SMA")
    print()

    if signals.empty:
        print("No signals found. Try lowering the threshold.")
        return

    # Forward return windows (every week from W+1 to W+52)
    forward_weeks = list(range(1, 53))

    # Compute forward returns for each signal
    results = []
    for idx, signal_row in signals.iterrows():
        signal_date = signal_row["date"]
        signal_close = signal_row["close"]
        signal_high = signal_row["high"]
        signal_sma = signal_row["sma_200w"]
        signal_ext = signal_row["extension_pct"]

        row_data = {
            "Date": signal_date.strftime("%Y-%m-%d"),
            "High": round(signal_high, 2),
            "Close": round(signal_close, 2),
            "200W_SMA": round(signal_sma, 2),
            "Extension_%": round(signal_ext, 2),
        }

        # Compute forward returns from the CLOSE price
        for w in forward_weeks:
            future_idx = idx + w
            if future_idx < len(df):
                future_close = df.iloc[future_idx]["close"]
                ret_pct = (future_close - signal_close) / signal_close * 100
                row_data[f"W+{w}_Ret%"] = round(ret_pct, 2)
            else:
                row_data[f"W+{w}_Ret%"] = None

        results.append(row_data)

    # Create results DataFrame
    results_df = pd.DataFrame(results)

    # Print to console
    print("=" * 120)
    print(f"SOXX Overextension Instances (High >= {threshold:.2f}% above 200W SMA)")
    print("=" * 120)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)
    print(results_df.to_string(index=False))
    print()

    # Compute summary statistics for forward returns
    print("=" * 80)
    print("SUMMARY STATISTICS (Forward Returns %)")
    print("=" * 80)
    ret_cols = [c for c in results_df.columns if c.startswith("W+")]
    summary_rows = []
    for col in ret_cols:
        vals = results_df[col].dropna()
        if len(vals) > 0:
            summary_rows.append(
                {
                    "Window": col.replace("_Ret%", ""),
                    "Count": len(vals),
                    "Mean %": round(vals.mean(), 2),
                    "Median %": round(vals.median(), 2),
                    "Min %": round(vals.min(), 2),
                    "Max %": round(vals.max(), 2),
                    "Win Rate % (>0)": round((vals > 0).mean() * 100, 1),
                }
            )
    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))
    print()

    # Save to CSV (Desktop folder)
    output_dir = Path("/Users/adhyarthvaria/Desktop/SMH_SOXX_Overextension_Analysis")
    output_path = output_dir / "soxx_overextension_analysis.csv"
    results_df.to_csv(output_path, index=False)
    print(f"Results saved to: {output_path}")

    # Also save summary
    summary_path = output_dir / "soxx_overextension_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"Summary saved to: {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
