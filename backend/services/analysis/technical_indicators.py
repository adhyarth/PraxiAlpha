"""
PraxiAlpha — Technical Indicators Service

Pure Python / pandas implementations of common technical indicators.
Each function accepts a ``pandas.Series`` (typically the *close* price)
and returns a ``pandas.Series`` or ``pandas.DataFrame`` with the
computed indicator values.

Rolling-window indicators (SMA, RSI, Bollinger Bands) return NaN for
positions where the look-back window has insufficient data.  EWM-based
indicators (EMA, MACD) are seeded from the first value and produce
output starting at index 0 (no leading NaNs).

Supported indicators
--------------------
* **SMA**  — Simple Moving Average
* **EMA**  — Exponential Moving Average
* **RSI**  — Relative Strength Index (Wilder's smoothing)
* **MACD** — Moving Average Convergence/Divergence
* **Bollinger Bands** — Middle / Upper / Lower bands

All functions are stateless, side-effect-free, and database-agnostic.
"""

from __future__ import annotations

import pandas as pd

# ============================================================
# Simple Moving Average
# ============================================================


def sma(series: pd.Series, period: int = 20) -> pd.Series:
    """
    Simple Moving Average.

    Parameters
    ----------
    series : pd.Series
        Typically the *close* price series.
    period : int
        Look-back window length (default 20).

    Returns
    -------
    pd.Series
        Rolling mean with ``min_periods=period`` (leading values are NaN).

    Raises
    ------
    ValueError
        If *period* < 1 or *series* is empty.
    """
    _validate_inputs(series, period)
    return series.rolling(window=period, min_periods=period).mean()


# ============================================================
# Exponential Moving Average
# ============================================================


def ema(series: pd.Series, period: int = 20, *, adjust: bool = False) -> pd.Series:
    """
    Exponential Moving Average.

    Uses the standard span-based smoothing factor ``α = 2 / (period + 1)``.

    Parameters
    ----------
    series : pd.Series
        Typically the *close* price series.
    period : int
        Span for the EMA calculation (default 20).
    adjust : bool
        Whether to use the "adjusted" EWM calculation (default ``False``
        to match most charting platforms which use recursive smoothing).

    Returns
    -------
    pd.Series
        Exponentially weighted mean.

    Raises
    ------
    ValueError
        If *period* < 1 or *series* is empty.
    """
    _validate_inputs(series, period)
    return series.ewm(span=period, adjust=adjust).mean()


# ============================================================
# Relative Strength Index
# ============================================================


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (Wilder's smoothing method).

    Uses Wilder's smoothed moving average (``com = period − 1``) for the
    average gain / average loss, matching the canonical RSI definition.

    Parameters
    ----------
    series : pd.Series
        Typically the *close* price series.
    period : int
        Look-back window (default 14).

    Returns
    -------
    pd.Series
        RSI values in the range [0, 100].  The first *period* values are NaN.

    Raises
    ------
    ValueError
        If *period* < 1 or *series* is empty.
    """
    _validate_inputs(series, period)

    delta = series.diff()

    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder's smoothed moving average: α = 1/period  →  com = period − 1
    avg_gain = gain.ewm(com=period - 1, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_values = 100.0 - (100.0 / (1.0 + rs))

    return rsi_values


# ============================================================
# MACD  (Moving Average Convergence / Divergence)
# ============================================================


def macd(
    series: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> pd.DataFrame:
    """
    Moving Average Convergence / Divergence.

    Parameters
    ----------
    series : pd.Series
        Typically the *close* price series.
    fast_period : int
        Span for the fast EMA (default 12).
    slow_period : int
        Span for the slow EMA (default 26).
    signal_period : int
        Span for the signal line EMA (default 9).

    Returns
    -------
    pd.DataFrame
        Three columns: ``macd_line``, ``signal_line``, ``histogram``.

    Raises
    ------
    ValueError
        If any period < 1, *fast_period* >= *slow_period*, or *series*
        is empty.
    """
    if fast_period < 1 or slow_period < 1 or signal_period < 1:
        raise ValueError("All MACD periods must be >= 1.")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be < slow_period.")
    _validate_inputs(series, 1)  # just validate series is non-empty

    fast_ema = ema(series, period=fast_period)
    slow_ema = ema(series, period=slow_period)

    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
        },
        index=series.index,
    )


# ============================================================
# Bollinger Bands
# ============================================================


def bollinger_bands(
    series: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """
    Bollinger Bands.

    Parameters
    ----------
    series : pd.Series
        Typically the *close* price series.
    period : int
        Look-back window for the middle band / SMA (default 20).
    num_std : float
        Number of standard deviations for the upper/lower bands
        (default 2.0).

    Returns
    -------
    pd.DataFrame
        Three columns: ``middle_band``, ``upper_band``, ``lower_band``.

    Raises
    ------
    ValueError
        If *period* < 1, *num_std* ≤ 0, or *series* is empty.
    """
    if num_std <= 0:
        raise ValueError("num_std must be > 0.")
    _validate_inputs(series, period)

    middle = sma(series, period)
    rolling_std = series.rolling(window=period, min_periods=period).std(ddof=0)

    upper = middle + num_std * rolling_std
    lower = middle - num_std * rolling_std

    return pd.DataFrame(
        {
            "middle_band": middle,
            "upper_band": upper,
            "lower_band": lower,
        },
        index=series.index,
    )


# ============================================================
# Internal helpers
# ============================================================


def _validate_inputs(series: pd.Series, period: int) -> None:
    """Shared validation for all indicator functions."""
    if not isinstance(series, pd.Series):
        raise TypeError(f"Expected pd.Series, got {type(series).__name__}.")
    if series.empty:
        raise ValueError("Input series must not be empty.")
    if period < 1:
        raise ValueError(f"Period must be >= 1, got {period}.")
