#!/usr/bin/env python3
"""
Quick debug script to verify yfinance works without a subscription
and produces the same data shapes the validation page expects.

Usage:
    python3 scripts/debug_yfinance.py
    python3 scripts/debug_yfinance.py --tickers AAPL MSFT --timeframes daily weekly
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

# ---- Make sure yfinance is importable ----
try:
    import yfinance as yf
except ImportError:
    print("❌ yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

import pandas as pd

# Replicate the exact constants from the validation service
FIXED_TICKERS = ["AAPL", "MSFT", "NVDA", "SMH", "TSLA"]
ALL_TIMEFRAMES = ["daily", "weekly", "monthly", "quarterly"]
TIMEFRAME_BARS = {
    "daily": 252,
    "weekly": 104,
    "monthly": 60,
    "quarterly": 20,
}
_YF_INTERVALS = {
    "daily": "1d",
    "weekly": "1wk",
    "monthly": "1mo",
}
_YF_PERIODS = {
    "daily": "2y",
    "weekly": "5y",
    "monthly": "10y",
}


def fetch_yf_candles(ticker: str, timeframe: str, n_bars: int) -> pd.DataFrame | None:
    """
    Exact replica of the service's fetch_yf_candles() for local testing.
    """
    if timeframe == "quarterly":
        monthly_df = fetch_yf_candles(ticker, "monthly", n_bars * 3)
        if monthly_df is None:
            return None
        return _aggregate_monthly_to_quarterly(monthly_df)

    interval = _YF_INTERVALS.get(timeframe)
    if interval is None:
        print(f"  ⚠️  Timeframe {timeframe} not supported")
        return None

    period = _YF_PERIODS.get(timeframe, "2y")

    try:
        yticker = yf.Ticker(ticker)
        df = yticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as e:
        print(f"  ❌ yfinance error: {e}")
        return None

    if df is None or df.empty:
        print("  ⚠️  No data returned")
        return None

    df = df.reset_index()

    # Normalise date column
    date_col = "Date" if "Date" in df.columns else "Datetime"
    if date_col not in df.columns:
        date_col = df.columns[0]

    df["date"] = pd.to_datetime(df[date_col]).dt.date

    # Rename title-case → lowercase
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
        print(f"  ⚠️  Missing columns. Got: {list(df.columns)}")
        return None

    result = df[["date", "open", "high", "low", "close", "volume"]].copy()
    if len(result) > n_bars:
        result = result.tail(n_bars).reset_index(drop=True)

    return result


def _aggregate_monthly_to_quarterly(monthly_df: pd.DataFrame) -> pd.DataFrame:
    if monthly_df is None or monthly_df.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    df = monthly_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    quarterly = (
        df.resample("QS")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    quarterly = quarterly.reset_index()
    quarterly["date"] = quarterly["date"].dt.date
    return quarterly


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug yfinance data fetcher")
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=FIXED_TICKERS,
        help="Tickers to test (default: AAPL MSFT NVDA SMH TSLA)",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=ALL_TIMEFRAMES,
        help="Timeframes to test (default: daily weekly monthly quarterly)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  yfinance Debug Script — Testing Data Fetch")
    print("=" * 70)
    print(f"  yfinance version: {yf.__version__}")
    print(f"  Tickers: {', '.join(args.tickers)}")
    print(f"  Timeframes: {', '.join(args.timeframes)}")
    print("=" * 70)

    total = 0
    success = 0
    failures: list[str] = []

    for ticker in args.tickers:
        for tf in args.timeframes:
            total += 1
            n_bars = TIMEFRAME_BARS.get(tf, 252)
            print(f"\n[{total}] {ticker} / {tf} (requesting {n_bars} bars)...")

            df = fetch_yf_candles(ticker, tf, n_bars)

            if df is None or df.empty:
                print("  ❌ FAILED — no data returned")
                failures.append(f"{ticker}/{tf}")
                continue

            success += 1
            first_date = df["date"].iloc[0]
            last_date = df["date"].iloc[-1]
            last_close = df["close"].iloc[-1]
            last_vol = df["volume"].iloc[-1]

            print(f"  ✅ Got {len(df)} bars")
            print(f"     Date range: {first_date} → {last_date}")
            print(f"     Last close: ${last_close:.2f}")
            print(f"     Last volume: {int(last_vol):,}")

            # Sanity checks
            issues: list[str] = []
            if len(df) < n_bars * 0.5:
                issues.append(f"only {len(df)}/{n_bars} bars (< 50%)")
            if df["close"].isna().any():
                issues.append(f"{df['close'].isna().sum()} NaN close values")
            if df["volume"].isna().any():
                issues.append(f"{df['volume'].isna().sum()} NaN volume values")
            if (df["close"] <= 0).any():
                issues.append("negative/zero close prices detected")
            if (df["high"] < df["low"]).any():
                issues.append("high < low on some bars")
            if last_date < date(2026, 3, 1):
                issues.append(f"most recent bar is {last_date} (stale?)")

            if issues:
                print(f"  ⚠️  Issues: {'; '.join(issues)}")
            else:
                print("     All sanity checks pass ✅")

    # ---- Extra check 1: Quarterly for a completed prior quarter ----
    print("\n" + "=" * 70)
    print("  EXTRA CHECK 1: Quarterly data — verify prior quarter (Q4 2025)")
    print("=" * 70)

    for ticker in args.tickers:
        total += 1
        print(f"\n[{total}] {ticker} / quarterly — checking Q4 2025...")
        df = fetch_yf_candles(ticker, "quarterly", 20)
        if df is None or df.empty:
            print("  ❌ FAILED — no data returned")
            failures.append(f"{ticker}/quarterly-q4check")
            continue

        # Look for Q4 2025 (should start on 2025-10-01)
        q4_rows = [r for _, r in df.iterrows() if r["date"] == date(2025, 10, 1)]
        if q4_rows:
            r = q4_rows[0]
            print(
                f"  ✅ Q4 2025 found: O={r['open']:.2f} H={r['high']:.2f} "
                f"L={r['low']:.2f} C={r['close']:.2f} V={int(r['volume']):,}"
            )
            success += 1
        else:
            # Maybe labeled differently — check dates in Q4 range
            q4_candidates = [
                r for _, r in df.iterrows() if date(2025, 10, 1) <= r["date"] <= date(2025, 12, 31)
            ]
            if q4_candidates:
                r = q4_candidates[0]
                print(
                    f"  ✅ Q4 2025 found (date={r['date']}): O={r['open']:.2f} "
                    f"H={r['high']:.2f} L={r['low']:.2f} C={r['close']:.2f} "
                    f"V={int(r['volume']):,}"
                )
                success += 1
            else:
                all_dates = sorted(df["date"].tolist())
                print(f"  ⚠️  Q4 2025 not found. Available dates: {all_dates[-8:]}")
                failures.append(f"{ticker}/quarterly-q4check")

    # ---- Extra check 2: 10 random tickers ----
    print("\n" + "=" * 70)
    print("  EXTRA CHECK 2: 10 random tickers (diverse sample)")
    print("=" * 70)

    # Mix of sectors, market caps, exchanges, and ETFs
    random_tickers = [
        "JPM",  # Financials, NYSE
        "JNJ",  # Healthcare, NYSE
        "COST",  # Consumer, NASDAQ
        "AMD",  # Semiconductors, NASDAQ
        "XOM",  # Energy, NYSE
        "DIS",  # Media, NYSE
        "BABA",  # ADR / foreign listing
        "IWM",  # ETF — Russell 2000
        "GLD",  # ETF — Gold
        "ARKK",  # ETF — actively managed
    ]

    print(f"  Testing: {', '.join(random_tickers)}")

    for ticker in random_tickers:
        for tf in ["daily", "weekly", "quarterly"]:
            total += 1
            n_bars = TIMEFRAME_BARS.get(tf, 252)
            print(f"\n[{total}] {ticker} / {tf} (requesting {n_bars} bars)...")

            df = fetch_yf_candles(ticker, tf, n_bars)

            if df is None or df.empty:
                print("  ❌ FAILED — no data returned")
                failures.append(f"{ticker}/{tf}")
                continue

            success += 1
            first_date = df["date"].iloc[0]
            last_date = df["date"].iloc[-1]
            last_close = df["close"].iloc[-1]

            print(
                f"  ✅ Got {len(df)} bars  |  {first_date} → {last_date}  |  "
                f"Last: ${last_close:.2f}"
            )

            # Quick sanity
            issues: list[str] = []
            if df["close"].isna().any():
                issues.append(f"{df['close'].isna().sum()} NaN")
            if (df["high"] < df["low"]).any():
                issues.append("high < low")
            if issues:
                print(f"  ⚠️  {'; '.join(issues)}")

    # ---- Final Summary ----
    print("\n" + "=" * 70)
    print(f"  FINAL SUMMARY: {success}/{total} passed")
    if failures:
        print(f"  FAILURES ({len(failures)}): {', '.join(failures)}")
    else:
        print("  🎉 All fetches succeeded!")
    print("=" * 70)


if __name__ == "__main__":
    main()
