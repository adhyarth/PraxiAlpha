"""
PraxiAlpha — Scanner Service (Strategy Lab Engine)

Stateless computational engine that scans historical candle data for
user-defined patterns and computes forward returns.

**V1 scope:**
- Quarterly timeframe only
- ETF universe (programmatic filter from ``stocks`` table)
- Conditions: candle color, body %, upper/lower wick %, volume vs
  N-period rolling average, RSI(14)
- Forward returns: Q+1 through Q+5 with return %, max drawdown %,
  max surge %

The service is database-aware (needs an ``AsyncSession`` to fetch
candle data and resolve the ETF universe) but does NOT persist any
results — it is a pure scan-and-return engine.

See ``docs/STRATEGY_LAB.md`` §4 for the full architecture.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.analysis.technical_indicators import rsi as compute_rsi
from backend.services.candle_service import CandleService, Timeframe

logger = logging.getLogger(__name__)


# ============================================================
# Data classes — scan input / output
# ============================================================


@dataclass
class ScanCondition:
    """A single filter condition.

    Attributes:
        field: Column name — ``"body_pct"``, ``"upper_wick_pct"``,
               ``"lower_wick_pct"``, ``"volume_vs_avg"``, ``"rsi_14"``,
               ``"full_range_pct"``.
        operator: Comparison — ``"<="``, ``">="``, ``">"``, ``"<"``, ``"=="``.
        value: Threshold value.
        extra: Optional params, e.g. ``{"lookback": 2}`` for volume.
    """

    field: str
    operator: str
    value: float
    extra: dict[str, Any] | None = None


@dataclass
class ScanRequest:
    """Full scan specification.

    Attributes:
        timeframe: ``"quarterly"`` (V1 only).
        conditions: All conditions that must match (AND logic).
        universe: ``"etf"`` (V1 only).
        forward_windows: Quarter offsets for forward returns, e.g. ``[1, 2, 3, 4, 5]``.
        candle_color: ``"red"``, ``"green"``, or ``"any"``.
    """

    timeframe: str = "quarterly"
    conditions: list[ScanCondition] = field(default_factory=list)
    universe: str = "etf"
    forward_windows: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    candle_color: str = "red"


@dataclass
class ForwardReturn:
    """Forward return metrics at a specific window.

    Attributes:
        window: Offset, e.g. ``1`` = Q+1.
        window_label: Human-readable label, e.g. ``"Q+1"``.
        close_price: Close price at that future candle (or ``None``).
        return_pct: ``(future_close - signal_close) / signal_close * 100``.
        max_drawdown_pct: Worst percentage decline vs. the signal close
            observed during the window; always ≤ 0 (clamped). Zero when
            price never trades below the signal close.
        max_surge_pct: Best percentage gain vs. the signal close observed
            during the window; always ≥ 0 (clamped). Zero when price
            never trades above the signal close.
    """

    window: int
    window_label: str
    close_price: float | None = None
    return_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_surge_pct: float | None = None


@dataclass
class SignalResult:
    """A single signal — one ticker + date that matched all conditions."""

    ticker: str
    signal_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    rsi_14: float | None
    body_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    volume_vs_avg: float | None
    forward_returns: list[ForwardReturn] = field(default_factory=list)


@dataclass
class WindowSummary:
    """Aggregate stats for one forward window across all signals."""

    window: int
    window_label: str
    mean_return_pct: float | None = None
    median_return_pct: float | None = None
    win_rate_pct: float | None = None
    mean_max_drawdown_pct: float | None = None
    mean_max_surge_pct: float | None = None
    signal_count: int = 0


@dataclass
class ScanSummary:
    """Aggregate statistics across all signals."""

    total_signals: int = 0
    unique_tickers: int = 0
    date_range: str = ""
    per_window: list[WindowSummary] = field(default_factory=list)


@dataclass
class ScanResult:
    """Complete scan output."""

    summary: ScanSummary = field(default_factory=ScanSummary)
    signals: list[SignalResult] = field(default_factory=list)
    scan_duration_seconds: float = 0.0
    conditions_used: list[ScanCondition] = field(default_factory=list)


# ============================================================
# Supported operators
# ============================================================

_OPERATORS: dict[str, Any] = {
    "<=": lambda col, val: col <= val,
    ">=": lambda col, val: col >= val,
    "<": lambda col, val: col < val,
    ">": lambda col, val: col > val,
    "==": lambda col, val: col == val,
}

# Fields that the scanner knows how to compute
_VALID_FIELDS = frozenset(
    {
        "body_pct",
        "upper_wick_pct",
        "lower_wick_pct",
        "volume_vs_avg",
        "rsi_14",
        "full_range_pct",
    }
)


# ============================================================
# Scanner Service
# ============================================================


class ScannerService:
    """
    Pattern Scanner + Forward Returns Analyzer.

    Stateless — instantiate with a DB session, call ``run_scan()``,
    get back a ``ScanResult``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._candle_service = CandleService(session)

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    async def run_scan(
        self,
        request: ScanRequest,
        *,
        progress_callback: Any | None = None,
    ) -> ScanResult:
        """
        Execute a full scan: resolve universe → fetch candles →
        compute indicators → filter signals → compute forward returns →
        aggregate summary.

        Args:
            request: The scan specification.
            progress_callback: Optional callable ``(current, total) -> None``
                for progress reporting (e.g. Streamlit progress bar).

        Returns:
            Complete ``ScanResult`` with summary, signals, and metadata.
        """
        t0 = time.monotonic()

        # 1. Validate request
        self._validate_request(request)

        # 2. Resolve universe
        universe = await self.resolve_universe(request.universe)
        logger.info("Scanner: resolved %d tickers for universe=%s", len(universe), request.universe)

        if not universe:
            return ScanResult(
                summary=ScanSummary(),
                signals=[],
                scan_duration_seconds=time.monotonic() - t0,
                conditions_used=request.conditions,
            )

        # 3. Fetch candles + compute derived columns per ticker
        #    Note: We fetch sequentially because CandleService shares a single
        #    AsyncSession which is not safe for concurrent overlapping awaits.
        #    Per-ticker errors are caught and logged so one bad ticker doesn't
        #    abort the entire scan.
        timeframe = Timeframe(request.timeframe)
        total = len(universe)
        all_frames: list[pd.DataFrame] = []

        for i, (stock_id, ticker) in enumerate(universe):
            try:
                df = await self._fetch_and_enrich_ticker(stock_id, ticker, timeframe, request)
                if df is not None and not df.empty:
                    all_frames.append(df)
            except Exception:
                logger.exception(
                    "Scanner: failed to fetch/enrich data for %s (stock_id=%s); skipping",
                    ticker,
                    stock_id,
                )
            if progress_callback is not None:
                try:
                    progress_callback(i + 1, total)
                except Exception:
                    logger.exception("Scanner: progress_callback raised an exception")

        if not all_frames:
            return ScanResult(
                summary=ScanSummary(),
                signals=[],
                scan_duration_seconds=time.monotonic() - t0,
                conditions_used=request.conditions,
            )

        combined = pd.concat(all_frames, ignore_index=True)
        logger.info(
            "Scanner: combined DataFrame has %d rows across %d tickers",
            len(combined),
            len(all_frames),
        )

        # 4. Apply condition filters
        signals_df = self._apply_conditions(combined, request)
        logger.info("Scanner: %d signals after condition filtering", len(signals_df))

        # 5. Compute forward returns for each signal
        signals = self._compute_forward_returns(signals_df, combined, request.forward_windows)

        # 6. Aggregate summary
        summary = self._build_summary(signals, request)

        elapsed = time.monotonic() - t0
        return ScanResult(
            summary=summary,
            signals=signals,
            scan_duration_seconds=round(elapsed, 2),
            conditions_used=request.conditions,
        )

    # ----------------------------------------------------------
    # Universe resolution
    # ----------------------------------------------------------

    async def resolve_universe(self, universe: str) -> list[tuple[int, str]]:
        """
        Return ``(stock_id, ticker)`` pairs for the requested universe.

        Args:
            universe: ``"etf"`` — active, non-delisted ETFs from the
                ``stocks`` table.

        Returns:
            List of ``(stock_id, ticker)`` tuples, sorted by ticker.
        """
        if universe == "etf":
            result = await self._session.execute(
                text(
                    "SELECT id, ticker FROM stocks "
                    "WHERE asset_type = 'ETF' "
                    "  AND is_active = true "
                    "  AND is_delisted = false "
                    "ORDER BY ticker"
                )
            )
            return [(row.id, row.ticker) for row in result.fetchall()]

        raise ValueError(f"Unsupported universe: {universe!r}. V1 supports 'etf' only.")

    # ----------------------------------------------------------
    # Per-ticker fetch + enrichment
    # ----------------------------------------------------------

    async def _fetch_and_enrich_ticker(
        self,
        stock_id: int,
        ticker: str,
        timeframe: Timeframe,
        request: ScanRequest,
    ) -> pd.DataFrame | None:
        """
        Fetch candles for one ticker and compute all derived columns.

        Returns a DataFrame with columns: ticker, date, open, high, low,
        close, volume, body_pct, upper_wick_pct, lower_wick_pct,
        full_range_pct, volume_vs_avg, rsi_14, plus the original
        stock_id for joining.
        """
        # Determine volume lookback from conditions (default 2)
        vol_lookback = self._get_volume_lookback(request.conditions)

        # Use adjusted=False for non-daily timeframes to hit the
        # pre-computed SQL aggregates directly (single fast query) instead
        # of fetching all daily rows and re-aggregating in Python.  For
        # pattern scanning, the relative metrics (body %, wick %, RSI,
        # volume ratio) are not materially affected by split adjustment
        # at the quarterly level because each bar's OHLC is internally
        # consistent (pre-split or post-split, never mixed within a bar
        # in the aggregate).  The only risk is RSI computed across a split
        # boundary, where the price level jumps; this affects ~1 bar's
        # return and is acceptable for a screening tool.
        #
        # TODO(v2): add a `fast_raw_aggregates` flag on ScanRequest so
        # callers can opt-in to adjusted=True for precision studies.
        candles = await self._candle_service.get_candles(
            stock_id,
            timeframe,
            adjusted=False,
            limit=200,  # ~50 years of quarterly data
        )

        if not candles or len(candles) < 2:
            return None

        df = pd.DataFrame(candles)
        df["ticker"] = ticker
        df["stock_id"] = stock_id

        # Ensure numeric types
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Guard against zero / near-zero prices to prevent division errors.
        # full_range_pct divides by low, lower_wick_pct divides by min(open,close),
        # so all four price columns must be positive.
        price_ok = (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)
        if not price_ok.all():
            df = df[price_ok].copy()
            if df.empty:
                return None

        # Derived columns — vectorized
        df["body_pct"] = (df["close"] - df["open"]).abs() / df["open"]
        max_oc = df[["open", "close"]].max(axis=1)
        min_oc = df[["open", "close"]].min(axis=1)
        df["upper_wick_pct"] = (df["high"] - max_oc) / max_oc
        df["lower_wick_pct"] = (min_oc - df["low"]) / min_oc
        df["full_range_pct"] = (df["high"] - df["low"]) / df["low"]

        # Volume vs N-period rolling average
        # Need at least 2 rows (shift(1) consumes one, rolling needs at least 1)
        if len(df) >= 2:
            # shift(1) so the rolling window does NOT include the current candle
            df["volume_vs_avg"] = df["volume"] / (
                df["volume"].shift(1).rolling(window=vol_lookback, min_periods=1).mean()
            )
        else:
            df["volume_vs_avg"] = np.nan

        # RSI(14) — using the existing indicator function
        if len(df) >= 15:
            df["rsi_14"] = compute_rsi(df["close"], period=14).values
        else:
            df["rsi_14"] = np.nan

        # Clip wick percentages to [0, ∞) — guard against data anomalies
        # where high < max(open, close) or low > min(open, close)
        df["upper_wick_pct"] = df["upper_wick_pct"].clip(lower=0)
        df["lower_wick_pct"] = df["lower_wick_pct"].clip(lower=0)

        return df

    # ----------------------------------------------------------
    # Condition filtering
    # ----------------------------------------------------------

    def _apply_conditions(
        self,
        df: pd.DataFrame,
        request: ScanRequest,
    ) -> pd.DataFrame:
        """
        Build a boolean mask from all conditions (AND logic) and
        return the matching rows.
        """
        mask = pd.Series(True, index=df.index)

        # Candle color filter
        if request.candle_color == "red":
            mask &= df["close"] < df["open"]
        elif request.candle_color == "green":
            mask &= df["close"] > df["open"]
        # "any" → no color filter

        # User-defined conditions
        for cond in request.conditions:
            if cond.field not in _VALID_FIELDS:
                raise ValueError(
                    f"Unknown condition field: {cond.field!r}. "
                    f"Valid fields: {sorted(_VALID_FIELDS)}"
                )
            if cond.operator not in _OPERATORS:
                raise ValueError(
                    f"Unknown operator: {cond.operator!r}. "
                    f"Valid operators: {sorted(_OPERATORS.keys())}"
                )

            col = df[cond.field]
            op_fn = _OPERATORS[cond.operator]
            cond_mask = op_fn(col, cond.value)
            # NaN values should not pass the filter
            cond_mask = cond_mask.fillna(False)
            mask &= cond_mask

        return df[mask].copy()

    # ----------------------------------------------------------
    # Forward return computation
    # ----------------------------------------------------------

    def _compute_forward_returns(
        self,
        signals_df: pd.DataFrame,
        full_df: pd.DataFrame,
        forward_windows: list[int],
    ) -> list[SignalResult]:
        """
        For each signal row, compute forward return metrics by looking
        ahead in that ticker's candle data.
        """
        signals: list[SignalResult] = []

        # Pre-index full data by ticker for O(1) lookups, and build
        # date→positional-index dicts to avoid per-signal linear scans.
        ticker_groups: dict[str, pd.DataFrame] = {}
        ticker_date_idx: dict[str, dict[str, int]] = {}
        for ticker, group in full_df.groupby("ticker"):
            sorted_group = group.sort_values("date").reset_index(drop=True)
            ticker_groups[ticker] = sorted_group
            ticker_date_idx[ticker] = {
                str(row_date): idx for idx, row_date in enumerate(sorted_group["date"])
            }

        # Use itertuples() for lower overhead than iterrows()
        for row in signals_df.itertuples(index=False):
            ticker = row.ticker
            signal_date = str(row.date)
            signal_close = float(row.close)

            ticker_df = ticker_groups.get(ticker)
            date_idx_map = ticker_date_idx.get(ticker)
            if ticker_df is None or date_idx_map is None:
                continue

            signal_idx = date_idx_map.get(signal_date)
            if signal_idx is None:
                continue

            # Compute forward returns for each window
            fwd_returns: list[ForwardReturn] = []
            for w in forward_windows:
                fwd = self._compute_single_forward_return(ticker_df, signal_idx, signal_close, w)
                fwd_returns.append(fwd)

            signal = SignalResult(
                ticker=ticker,
                signal_date=str(signal_date),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=signal_close,
                volume=int(row.volume),
                rsi_14=round(float(row.rsi_14), 2) if pd.notna(row.rsi_14) else None,
                body_pct=round(float(row.body_pct) * 100, 2),
                upper_wick_pct=round(float(row.upper_wick_pct) * 100, 2),
                lower_wick_pct=round(float(row.lower_wick_pct) * 100, 2),
                volume_vs_avg=round(float(row.volume_vs_avg), 2)
                if pd.notna(row.volume_vs_avg)
                else None,
                forward_returns=fwd_returns,
            )
            signals.append(signal)

        return signals

    @staticmethod
    def _compute_single_forward_return(
        ticker_df: pd.DataFrame,
        signal_idx: int,
        signal_close: float,
        window: int,
    ) -> ForwardReturn:
        """
        Compute forward return metrics for one signal at one window.

        Looks ahead ``window`` candles from the signal. Computes:
        - Return %: from signal close to close at Q+window
        - Max drawdown %: min close between signal and Q+window
        - Max surge %: max close between signal and Q+window
        """
        label = f"Q+{window}"
        target_idx = signal_idx + window

        if target_idx >= len(ticker_df):
            # Not enough forward data
            return ForwardReturn(window=window, window_label=label)

        # Slice from signal+1 through target (inclusive) for intermediate prices
        forward_slice = ticker_df.iloc[signal_idx + 1 : target_idx + 1]

        if forward_slice.empty:
            return ForwardReturn(window=window, window_label=label)

        future_close = float(forward_slice.iloc[-1]["close"])
        return_pct = (future_close - signal_close) / signal_close * 100

        # Min/max close in the forward window for drawdown/surge
        all_closes = forward_slice["close"].astype(float)
        min_close = float(all_closes.min())
        max_close = float(all_closes.max())
        # Clamp: drawdown is always ≤ 0, surge is always ≥ 0
        max_drawdown_pct = min((min_close - signal_close) / signal_close * 100, 0.0)
        max_surge_pct = max((max_close - signal_close) / signal_close * 100, 0.0)

        return ForwardReturn(
            window=window,
            window_label=label,
            close_price=round(future_close, 4),
            return_pct=round(return_pct, 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            max_surge_pct=round(max_surge_pct, 2),
        )

    # ----------------------------------------------------------
    # Summary aggregation
    # ----------------------------------------------------------

    def _build_summary(
        self,
        signals: list[SignalResult],
        request: ScanRequest,
    ) -> ScanSummary:
        """
        Aggregate per-signal forward returns into summary statistics.
        """
        if not signals:
            return ScanSummary(
                total_signals=0,
                unique_tickers=0,
                date_range="",
                per_window=[
                    WindowSummary(window=w, window_label=f"Q+{w}") for w in request.forward_windows
                ],
            )

        tickers = {s.ticker for s in signals}
        dates = [s.signal_date for s in signals]
        date_range = f"{min(dates)} to {max(dates)}"

        per_window: list[WindowSummary] = []
        for w in request.forward_windows:
            returns = []
            drawdowns = []
            surges = []
            for s in signals:
                for fr in s.forward_returns:
                    if fr.window == w and fr.return_pct is not None:
                        returns.append(fr.return_pct)
                        if fr.max_drawdown_pct is not None:
                            drawdowns.append(fr.max_drawdown_pct)
                        if fr.max_surge_pct is not None:
                            surges.append(fr.max_surge_pct)

            if not returns:
                per_window.append(WindowSummary(window=w, window_label=f"Q+{w}", signal_count=0))
                continue

            arr = np.array(returns)
            # Win rate: DOWN for bearish, UP for bullish, undefined for "any"
            if request.candle_color == "red":
                win_count = int((arr < 0).sum())
                win_rate: float | None = round(win_count / len(arr) * 100, 2)
            elif request.candle_color == "green":
                win_count = int((arr > 0).sum())
                win_rate = round(win_count / len(arr) * 100, 2)
            else:
                # "any" — win direction is ambiguous; leave as None
                win_rate = None

            per_window.append(
                WindowSummary(
                    window=w,
                    window_label=f"Q+{w}",
                    mean_return_pct=round(float(arr.mean()), 2),
                    median_return_pct=round(float(np.median(arr)), 2),
                    win_rate_pct=win_rate,
                    mean_max_drawdown_pct=round(float(np.mean(drawdowns)), 2)
                    if drawdowns
                    else None,
                    mean_max_surge_pct=round(float(np.mean(surges)), 2) if surges else None,
                    signal_count=len(returns),
                )
            )

        return ScanSummary(
            total_signals=len(signals),
            unique_tickers=len(tickers),
            date_range=date_range,
            per_window=per_window,
        )

    # ----------------------------------------------------------
    # Validation & helpers
    # ----------------------------------------------------------

    @staticmethod
    def _validate_request(request: ScanRequest) -> None:
        """Validate that the scan request is well-formed."""
        valid_timeframes = {"quarterly"}  # V1
        if request.timeframe not in valid_timeframes:
            raise ValueError(
                f"Unsupported timeframe: {request.timeframe!r}. "
                f"V1 supports: {sorted(valid_timeframes)}"
            )

        valid_universes = {"etf"}  # V1
        if request.universe not in valid_universes:
            raise ValueError(
                f"Unsupported universe: {request.universe!r}. "
                f"V1 supports: {sorted(valid_universes)}"
            )

        valid_colors = {"red", "green", "any"}
        if request.candle_color not in valid_colors:
            raise ValueError(
                f"Invalid candle_color: {request.candle_color!r}. "
                f"Must be one of: {sorted(valid_colors)}"
            )

        if not request.forward_windows:
            raise ValueError("forward_windows must not be empty.")

        for w in request.forward_windows:
            if w < 1:
                raise ValueError(f"Forward window must be >= 1, got {w}.")

    @staticmethod
    def _get_volume_lookback(conditions: list[ScanCondition]) -> int:
        """
        Extract the volume lookback period from conditions.

        Looks for a condition with ``field="volume_vs_avg"`` and
        ``extra={"lookback": N}``. Defaults to 2 if not specified.
        """
        for cond in conditions:
            if cond.field == "volume_vs_avg" and cond.extra:
                lb = cond.extra.get("lookback")
                if lb is not None:
                    try:
                        lb_int = int(lb)
                    except (TypeError, ValueError):
                        # Invalid lookback value; ignore and fall back to default
                        continue
                    if lb_int >= 1:
                        return lb_int
        return 2  # default lookback
