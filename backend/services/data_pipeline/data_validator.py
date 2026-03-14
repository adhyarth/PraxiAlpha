"""
PraxiAlpha — Data Validator

Validates and cleans fetched OHLCV and macro data before storage.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class DataValidator:
    """Validates and cleans market data before database insertion."""

    @staticmethod
    def validate_ohlcv(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """
        Validate and clean OHLCV data.

        Checks:
        - Required columns present
        - No duplicate dates
        - OHLCV values are positive
        - High >= Low
        - Volume >= 0
        - Drops rows with critical issues

        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df

        original_len = len(df)

        # Required columns
        required = ["date", "open", "high", "low", "close", "adjusted_close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns for {ticker}: {missing}")

        # Drop duplicate dates
        df = df.drop_duplicates(subset=["date"], keep="last")

        # Ensure numeric types
        for col in ["open", "high", "low", "close", "adjusted_close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

        # Drop rows where price is null or <= 0
        price_mask = (df["close"] > 0) & (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0)
        df = df[price_mask].copy()

        # Fix high < low (swap them)
        swap_mask = df["high"] < df["low"]
        if swap_mask.any():
            count = swap_mask.sum()
            logger.warning(f"{ticker}: Swapping high/low for {count} rows")
            df.loc[swap_mask, ["high", "low"]] = df.loc[swap_mask, ["low", "high"]].values

        # Sort by date
        df = df.sort_values("date").reset_index(drop=True)

        removed = original_len - len(df)
        if removed > 0:
            logger.warning(f"{ticker}: Removed {removed} invalid rows ({original_len} → {len(df)})")

        return df

    @staticmethod
    def validate_macro(df: pd.DataFrame, series_id: str) -> pd.DataFrame:
        """
        Validate and clean FRED macro data.

        Checks:
        - Required columns present
        - No duplicate dates
        - Drops rows with null values (FRED uses "." for missing)

        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df

        # Drop duplicate dates
        df = df.drop_duplicates(subset=["date"], keep="last")

        # Sort by date
        df = df.sort_values("date").reset_index(drop=True)

        non_null = df["value"].notna().sum()
        logger.info(f"{series_id}: {non_null}/{len(df)} non-null values")

        return df
