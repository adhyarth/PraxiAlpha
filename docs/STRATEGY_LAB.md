# 🔬 PraxiAlpha — Strategy Lab

> **Purpose:** Design document for the Strategy Lab — a Pattern Scanner + Forward
> Returns Analyzer that enables rapid, data-driven strategy iteration.
>
> **Status:** Engine implemented (Session 30). UI next (Session 31).
>
> **Last updated:** 2026-03-30 (Session 30 — scanner engine complete)

---

## Table of Contents

1. [Vision](#1-vision)
2. [V1 Scope](#2-v1-scope)
3. [Condition Taxonomy](#3-condition-taxonomy)
4. [Architecture](#4-architecture)
5. [Data Model (Future — Persistence)](#5-data-model-future--persistence)
6. [UI Wireframe](#6-ui-wireframe)
7. [Forward Return Specification](#7-forward-return-specification)
8. [Performance Considerations](#8-performance-considerations)
9. [Session Roadmap](#9-session-roadmap)
10. [Future Phases](#10-future-phases)

---

## 1. Vision

### What Is the Strategy Lab?

The Strategy Lab is PraxiAlpha's core analytical tool for building trading
strategies through rapid iteration. The workflow:

```
Define conditions → Scan historical data → Find matching signals →
Compute forward returns → Analyze results → Tweak conditions → Repeat
```

The key insight: **strategies are built through trial and error**, not
theoretical perfection. The Lab provides a tight feedback loop — define a
pattern hypothesis, see what happens historically when it fires, adjust
thresholds, and repeat until you find an edge.

### Why Build This Now?

The database has **58.2M daily OHLCV records** across **23,714 tickers** with
**30+ years of history**. This data is the foundation — but without a way to
query patterns and measure outcomes, it's just storage. The Strategy Lab
transforms the data into actionable signals.

### The Motivating Example

> "Find ETFs that show a quarterly bearish reversal candle: a red candle with
> a small body (open ≈ close), a huge upper wick (signaling rejection at highs),
> tiny lower wick, volume exceeding the last 2 quarters, and RSI above 70.
> What happens over the next 5 quarters? Is buying puts profitable?"

This is the kind of question the Strategy Lab answers in under 60 seconds.

---

## 2. V1 Scope

V1 is laser-focused: **quarterly bearish reversal candles on ETFs**.
Everything else is documented for later phases.

### V1 Feature Summary

| Feature | V1 | Later |
|---------|:--:|:-----:|
| Quarterly timeframe scanning | ✅ | |
| Weekly/monthly timeframe scanning | | ✅ |
| Daily timeframe scanning | | ✅ |
| Price shape conditions (body, wick %) | ✅ | |
| Volume vs N-period rolling average | ✅ | |
| RSI(14) threshold | ✅ | |
| Other indicators (MACD, Bollinger, SMA) | | ✅ |
| Multi-candle patterns (engulfing, inside bar) | | ✅ |
| Cross-timeframe conditions | | ✅ |
| Fundamental filters (market cap, sector) | | ✅ |
| ETF universe (programmatic filter) | ✅ | |
| All stocks + ETFs universe | | ✅ |
| Configurable condition form builder | ✅ | |
| Natural language input | | ✅ |
| Forward returns (5 quarterly windows) | ✅ | |
| Target hit-rate analysis table | | ✅ |
| Summary statistics panel | ✅ | |
| Per-signal detail table | ✅ | |
| Strategy persistence (save/load/name) | | ✅ |
| Strategy comparison (side-by-side) | | ✅ |
| Strategy versioning | | ✅ |
| Split-adjusted prices | ✅ | |

### V1 Default Preset: "Bearish Reversal Candle"

This is the default condition set pre-filled in the UI. All values are
configurable — the user can tweak any threshold and re-run.

| Condition | Field | Operator | Default | Configurable |
|-----------|-------|----------|---------|:------------:|
| Candle color | `close` vs `open` | `<` (red) | red | ✅ dropdown: red / green / any |
| Body size | `abs(close - open) / open` | `≤` | 2% | ✅ slider: 0–20% |
| Upper wick | `(high - max(open, close)) / max(open, close)` | `≥` | 10% | ✅ slider: 0–50% |
| Lower wick | `(min(open, close) - low) / min(open, close)` | `≤` | 2% | ✅ slider: 0–20% |
| Volume vs avg | `volume / rolling_mean(volume, N)` | `>` | 1.0 (> avg of last N) | ✅ multiplier + lookback N (default N=2) |
| RSI(14) | `RSI(close, 14)` | `>` | 70 | ✅ slider: 0–100 |

### Universe: ETFs (Programmatic Filter)

The scan universe is determined programmatically from the `stocks` table:

```sql
SELECT id, ticker, name
FROM stocks
WHERE asset_type = 'ETF'
  AND is_active = true
  AND is_delisted = false
```

This is extensible — future versions can add filters for:
- Minimum history length (e.g., `total_records > 1000`)
- Minimum average daily volume
- Asset type toggle (ETF / Stock / Both)
- Exchange filter (NYSE / NASDAQ / AMEX)
- Specific ticker list (user-provided)

---

## 3. Condition Taxonomy

This is the full catalog of condition types, organized by category.
**V1 implements only the first two categories.** The rest are documented
for future sessions.

### 3.1 Price Shape (V1) ✅

These conditions describe the shape of a single candle.

| Condition | Formula | Use Case |
|-----------|---------|----------|
| Body size % | `abs(close - open) / open` | Doji, small/large body detection |
| Upper wick % | `(high - max(open, close)) / max(open, close)` | Shooting star, rejection wick |
| Lower wick % | `(min(open, close) - low) / min(open, close)` | Hammer, pin bar |
| Candle color | `close > open` (green) or `close < open` (red) | Directional filter |
| Full range % | `(high - low) / low` | Volatility / candle size filter |

### 3.2 Volume (V1) ✅

| Condition | Formula | Use Case |
|-----------|---------|----------|
| Volume vs N-period avg | `volume / rolling_mean(volume, N)` | Volume surge detection |
| Volume vs previous candle | `volume / volume.shift(1)` | Volume expansion |
| Absolute volume threshold | `volume > X` | Minimum liquidity filter |

### 3.3 Technical Indicators (V1: RSI only) ✅

| Indicator | Parameters | Formula | V1? |
|-----------|-----------|---------|:---:|
| RSI | period (default 14) | Wilder's RSI | ✅ |
| SMA | period | Simple moving average | ❌ |
| EMA | period | Exponential moving average | ❌ |
| MACD | fast, slow, signal | MACD line, signal, histogram | ❌ |
| Bollinger Bands | period, std_dev | %B position within bands | ❌ |
| Stochastic | K, D periods | %K and %D | ❌ |

### 3.4 Price vs Moving Average (Future)

| Condition | Formula | Use Case |
|-----------|---------|----------|
| Price above/below SMA(N) | `close > SMA(close, N)` | Trend filter |
| Distance from SMA(N) % | `(close - SMA(close, N)) / SMA(close, N)` | Overextension |
| SMA crossover | `SMA(short) > SMA(long)` | Golden/death cross |

### 3.5 Multi-Candle Patterns (Future)

| Pattern | Description | Candles |
|---------|-------------|---------|
| Engulfing | Current candle's body engulfs previous | 2 |
| Inside bar | Current candle's range within previous | 2 |
| N consecutive green/red | Directional streak | N |
| Gap up/down | Open vs previous close | 2 |
| Three white soldiers / black crows | Directional pattern | 3 |

### 3.6 Cross-Timeframe Conditions (Future)

> **Key for entry timing:** The bearish reversal is spotted on the quarterly
> chart, but the optimal entry (after a snap-back rally to a lower high) is
> identified on the weekly or daily chart. This requires conditions that
> reference multiple timeframes simultaneously.

| Condition | Example | Complexity |
|-----------|---------|-----------|
| Higher timeframe signal + lower timeframe entry | "Quarterly bearish reversal AND weekly RSI crosses below 60" | High |
| Divergence across timeframes | "Quarterly RSI declining while monthly price makes new high" | High |
| Confirmation candle on lower TF | "Wait for first red weekly candle after quarterly signal" | Medium |

### 3.7 Fundamental Filters (Future)

> Requires a fundamentals data source (not yet implemented in PraxiAlpha).

| Filter | Example |
|--------|---------|
| Market cap | Large-cap only (> $10B) |
| Sector | Technology, Healthcare, etc. |
| P/E ratio | Below industry average |
| Revenue growth | > 10% YoY |

---

## 4. Architecture

### 4.1 System Diagram

```
┌─────────────────────────────────────────────────────┐
│                 Streamlit UI                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │  Condition    │  │  Summary     │  │  Detail   │ │
│  │  Builder Form │  │  Stats Panel │  │  Table    │ │
│  └──────┬───────┘  └──────▲───────┘  └─────▲─────┘ │
│         │                 │                │        │
└─────────┼─────────────────┼────────────────┼────────┘
          │ conditions      │ results        │ signals
          ▼                 │                │
┌─────────────────────────────────────────────────────┐
│              Scanner Service                         │
│  ┌──────────────────────────────────────────────┐   │
│  │  1. Resolve universe (ETF tickers from DB)   │   │
│  │  2. Fetch quarterly candles per ticker        │   │
│  │     (via CandleService, adjusted=True)        │   │
│  │  3. Compute RSI(14) on close prices           │   │
│  │  4. Apply vectorized condition filters        │   │
│  │  5. For each signal: compute forward returns  │   │
│  │  6. Aggregate summary statistics              │   │
│  │  7. Return results                            │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
          │                          │
          ▼                          ▼
┌──────────────────┐   ┌──────────────────────────────┐
│  CandleService   │   │  Indicators Service          │
│  (existing)      │   │  (existing — RSI, SMA, etc.) │
│  get_candles()   │   │  compute_rsi()               │
└──────────────────┘   └──────────────────────────────┘
          │
          ▼
┌──────────────────┐
│  PostgreSQL +    │
│  TimescaleDB     │
│  daily_ohlcv     │
│  stock_splits    │
│  stocks          │
└──────────────────┘
```

### 4.2 Scanner Service Design

**File:** `backend/services/scanner_service.py`

The scanner service is a stateless function that takes conditions and returns
results. It is not an ORM-backed CRUD service — it's a computational engine.

```python
# Conceptual API (not final code)

@dataclass
class ScanCondition:
    """A single filter condition."""
    field: str           # "body_pct", "upper_wick_pct", "rsi_14", "volume_vs_avg", etc.
    operator: str        # "<=", ">=", ">", "<", "==", "between"
    value: float         # threshold value
    extra: dict | None   # optional params, e.g. {"lookback": 2} for volume

@dataclass
class ScanRequest:
    """Full scan specification."""
    timeframe: str                   # "quarterly" (V1), "weekly", "monthly" (later)
    conditions: list[ScanCondition]  # all conditions must match (AND logic)
    universe: str                    # "etf" (V1), "all", "custom"
    forward_windows: list[int]       # [1, 2, 3, 4, 5] (quarters ahead)
    candle_color: str                # "red", "green", "any"

@dataclass
class SignalResult:
    """A single signal (one ticker + one date that matched all conditions)."""
    ticker: str
    signal_date: str          # ISO date of the matching candle
    open: float
    high: float
    low: float
    close: float
    volume: int
    rsi_14: float
    body_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    volume_vs_avg: float
    forward_returns: list[ForwardReturn]

@dataclass
class ForwardReturn:
    """Forward return at a specific window."""
    window: int               # e.g. 1 = Q+1
    window_label: str         # "Q+1", "Q+2", etc.
    close_price: float        # close at that future date
    return_pct: float         # % return from signal close
    max_drawdown_pct: float   # worst peak-to-trough during window
    max_surge_pct: float      # best trough-to-peak during window

@dataclass
class ScanSummary:
    """Aggregate statistics across all signals."""
    total_signals: int
    unique_tickers: int
    date_range: str             # "2002-Q1 to 2025-Q4"
    per_window: list[WindowSummary]

@dataclass
class WindowSummary:
    """Summary stats for one forward window."""
    window: int
    window_label: str
    mean_return_pct: float
    median_return_pct: float
    win_rate_pct: float         # % of signals with negative return (bearish = down is winning)
    mean_max_drawdown_pct: float
    mean_max_surge_pct: float

@dataclass
class ScanResult:
    """Complete scan output."""
    summary: ScanSummary
    signals: list[SignalResult]
    scan_duration_seconds: float
    conditions_used: list[ScanCondition]
```

### 4.3 Data Flow — Step by Step

1. **Resolve universe** — Query `stocks` table for all active, non-delisted
   ETFs. Get back a list of `(stock_id, ticker)` pairs.

2. **Fetch candles per ticker** — For each ETF, call
   `CandleService.get_candles(stock_id, Timeframe.QUARTERLY, adjusted=True, limit=200)`.
   This fetches up to ~50 years of quarterly candles, split-adjusted.

   > **Performance note:** This is a per-ticker query. For ~500 ETFs × 200
   > candles = ~100K rows. We'll batch these queries and concatenate into
   > a single DataFrame.

3. **Compute derived columns** — On the combined DataFrame, vectorized:
   ```python
   df['body_pct'] = abs(df['close'] - df['open']) / df['open']
   df['upper_wick_pct'] = (df['high'] - df[['open','close']].max(axis=1)) / df[['open','close']].max(axis=1)
   df['lower_wick_pct'] = (df[['open','close']].min(axis=1) - df['low']) / df[['open','close']].min(axis=1)
   df['volume_vs_avg'] = df.groupby('ticker')['volume'].transform(
       lambda x: x / x.rolling(N).mean()
   )
   ```

4. **Compute RSI** — Per ticker, compute RSI(14) on the close column using
   the existing `compute_rsi()` from `backend/services/indicators.py`
   (or a vectorized pandas equivalent for batch computation).

5. **Apply conditions** — Build a boolean mask from all conditions (AND logic):
   ```python
   mask = (
       (df['close'] < df['open']) &              # red candle
       (df['body_pct'] <= body_threshold) &       # small body
       (df['upper_wick_pct'] >= wick_threshold) &  # big upper wick
       (df['lower_wick_pct'] <= lower_threshold) & # small lower wick
       (df['volume_vs_avg'] > vol_multiplier) &    # volume surge
       (df['rsi_14'] > rsi_threshold)              # overbought
   )
   signals = df[mask]
   ```

6. **Compute forward returns** — For each signal, look ahead in that ticker's
   candle data. For each forward window (Q+1 through Q+5):
   - Get the close price at Q+N
   - Compute return: `(future_close - signal_close) / signal_close`
   - For max drawdown: find the minimum close between signal and Q+N,
     compute `(min_close - signal_close) / signal_close`
   - For max surge: find the maximum close between signal and Q+N,
     compute `(max_close - signal_close) / signal_close`

   > **Edge case:** If a ticker doesn't have enough future data (e.g., signal
   > in 2025-Q1, only 1 quarter of forward data exists), mark missing windows
   > as `null`. These signals still count in the summary for windows that DO
   > have data.

7. **Aggregate summary** — Compute mean, median, win rate across all signals
   for each forward window.

### 4.4 Integration with Existing Services

| Existing Service | How Scanner Uses It |
|---|---|
| `CandleService.get_candles()` | Fetch split-adjusted quarterly candles per ticker |
| `backend/services/indicators.py` | RSI computation (may need a batch-friendly wrapper) |
| `stocks` table / `Stock` model | Universe resolution (ETF filter query) |

The scanner does NOT need:
- New database tables (V1 — persistence is a later session)
- New Alembic migrations
- New API endpoints (V1 — the Streamlit page calls the service directly)
- Celery tasks

### 4.5 Indicator Computation for Batch Scanning

The existing `compute_rsi()` in `backend/services/indicators.py` works on a
single ticker's DataFrame. For the scanner, we need RSI across many tickers
in one DataFrame. Two approaches:

- **A) groupby + apply:** `df.groupby('ticker')['close'].transform(compute_rsi_series)`
- **B) Loop per ticker:** Compute RSI per ticker before concatenation.

Option A is cleaner but RSI uses `ewm()` which doesn't vectorize across groups
perfectly. Option B is simpler and cache-friendly. **Decision: use option B**
— compute RSI per ticker during the candle fetch loop, then concatenate.

---

## 5. Data Model (Future — Persistence)

> **Not implemented in V1.** Documented here for future sessions.

When we add strategy persistence, we'll need these tables:

### 5.1 `strategies` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | VARCHAR(100) | Owner (same pattern as journal) |
| `name` | VARCHAR(255) | User-given strategy name, e.g. "Quarterly Bearish Reversal" |
| `description` | TEXT | Free-text description of the hypothesis |
| `timeframe` | VARCHAR(20) | "quarterly", "weekly", "monthly" |
| `universe` | VARCHAR(50) | "etf", "all", "custom" |
| `candle_color` | VARCHAR(10) | "red", "green", "any" |
| `forward_windows` | JSONB | `[1, 2, 3, 4, 5]` |
| `version` | INTEGER | Auto-incrementing version number |
| `tags` | JSONB | User tags, e.g. `["bearish", "reversal", "etf"]` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

### 5.2 `strategy_conditions` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `strategy_id` | UUID | FK → strategies |
| `field` | VARCHAR(50) | "body_pct", "upper_wick_pct", "rsi_14", etc. |
| `operator` | VARCHAR(10) | "<=", ">=", ">", "<", "between" |
| `value` | NUMERIC | Threshold value |
| `extra` | JSONB | Optional params, e.g. `{"lookback": 2}` |
| `sort_order` | INTEGER | Display order in UI |

### 5.3 `scan_results` Table (Optional)

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `strategy_id` | UUID | FK → strategies |
| `run_date` | TIMESTAMPTZ | When the scan was executed |
| `total_signals` | INTEGER | |
| `summary_json` | JSONB | Full summary stats snapshot |
| `signals_json` | JSONB | All signal rows (for re-display without re-running) |
| `scan_duration_seconds` | NUMERIC | |

---

## 6. UI Wireframe

### 6.1 Page Layout — `streamlit_app/pages/scanner.py`

```
┌──────────────────────────────────────────────────────────┐
│  🔬 Strategy Lab — Pattern Scanner                       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─ Scan Configuration ────────────────────────────────┐ │
│  │                                                     │ │
│  │  Timeframe: [Quarterly ▼]     Universe: [ETFs ▼]   │ │
│  │                                                     │ │
│  │  Candle Color: [Red ▼]                              │ │
│  │                                                     │ │
│  │  ── Price Shape ──────────────────────────────────  │ │
│  │  Body size ≤  [===●====] 2%                         │ │
│  │  Upper wick ≥ [========●] 10%                       │ │
│  │  Lower wick ≤ [===●====] 2%                         │ │
│  │                                                     │ │
│  │  ── Volume ───────────────────────────────────────  │ │
│  │  Volume > [1.0]x avg of last [2] candles            │ │
│  │                                                     │ │
│  │  ── Indicators ───────────────────────────────────  │ │
│  │  RSI(14) > [=======●==] 70                          │ │
│  │                                                     │ │
│  │  [🔍 Run Scan]                                      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Summary ───────────────────────────────────────────┐ │
│  │  Signals: 47 across 23 ETFs | 2002-Q1 to 2025-Q4   │ │
│  │  Scan time: 34.2s                                   │ │
│  │                                                     │ │
│  │  Window │ Mean Ret │ Median │ Win Rate │ Avg DD │   │ │
│  │  ───────┼──────────┼────────┼──────────┼────────┤   │ │
│  │  Q+1    │  -4.2%   │ -3.8%  │  62%     │ -8.1%  │   │ │
│  │  Q+2    │  -7.1%   │ -6.5%  │  68%     │ -12.3% │   │ │
│  │  Q+3    │  -5.8%   │ -4.9%  │  58%     │ -15.7% │   │ │
│  │  Q+4    │  -3.2%   │ -2.1%  │  53%     │ -18.4% │   │ │
│  │  Q+5    │  -1.5%   │ +0.3%  │  48%     │ -20.1% │   │ │
│  │                                                     │ │
│  │  (Win rate = % of signals where price went DOWN,    │ │
│  │   i.e. puts would have been profitable)             │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Signal Details ────────────────────────────────────┐ │
│  │                                                     │ │
│  │  ▸ SMH — 2024-Q3 (close: $248.12, RSI: 79.7)       │ │
│  │    Q+1: -6.2% | Q+2: -11.4% | ... | DD: -14.8%    │ │
│  │                                                     │ │
│  │  ▸ QQQ — 2021-Q4 (close: $398.45, RSI: 74.3)       │ │
│  │    Q+1: -8.1% | Q+2: -15.2% | ... | DD: -22.3%    │ │
│  │                                                     │ │
│  │  ▸ XBI — 2021-Q1 (close: $142.30, RSI: 71.2)       │ │
│  │    Q+1: -12.5% | Q+2: -18.7% | ... | DD: -28.1%   │ │
│  │                                                     │ │
│  │  ... (expandable rows, sortable by any column)      │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 6.2 UI Interaction Flow

1. User adjusts condition sliders/dropdowns (defaults pre-filled for bearish reversal)
2. User clicks **"🔍 Run Scan"**
3. Progress bar shows: "Scanning 487 ETFs... (142/487)"
4. Summary table appears at top with aggregate stats
5. Detail table appears below with expandable per-signal rows
6. User tweaks a threshold (e.g., RSI from 70 → 65), clicks Run Scan again
7. Results update — the tight feedback loop

### 6.3 Win Rate Definition

For the **bearish reversal** pattern, "winning" means the price went **down**
(puts profitable). The win rate in the summary reflects this:

- **Win rate** = % of signals where `forward_return < 0` (price declined)
- For a future **bullish** pattern scan, win rate would flip to `forward_return > 0`

This is tied to the candle color selection:
- **Red candle scan** → win = price goes down (bearish thesis)
- **Green candle scan** → win = price goes up (bullish thesis)
- **Any color** → user defines win direction separately (future enhancement)

---

## 7. Forward Return Specification

### 7.1 Forward Windows (V1 — Quarterly)

| Window | Label | Meaning |
|--------|-------|---------|
| 1 | Q+1 | Close price 1 quarter after signal |
| 2 | Q+2 | Close price 2 quarters after signal |
| 3 | Q+3 | Close price 3 quarters after signal |
| 4 | Q+4 | Close price 4 quarters after signal (1 year) |
| 5 | Q+5 | Close price 5 quarters after signal |

### 7.2 Metrics per Window

| Metric | Formula | Description |
|--------|---------|-------------|
| **Return %** | `(close_at_Q+N - signal_close) / signal_close × 100` | Simple price return |
| **Max Drawdown %** | `(min_close_between_signal_and_Q+N - signal_close) / signal_close × 100` | Worst adverse move (price dropped this far from signal). Always ≤ 0. |
| **Max Surge %** | `(max_close_between_signal_and_Q+N - signal_close) / signal_close × 100` | Best favorable move (price rose this far from signal). Always ≥ 0. |

> **Note on drawdown/surge:** For a bearish thesis (puts), drawdown is actually
> the *favorable* move (price going down is good for puts) and surge is the
> *adverse* move (price going up means puts lose). The UI labels will clarify
> this based on the scan direction.

### 7.3 Edge Cases

| Situation | Handling |
|-----------|----------|
| Signal too recent — not enough forward quarters | Mark missing windows as `null`. Include signal in summary for windows that DO have data. |
| Ticker delisted before Q+5 | Use last available close for remaining windows. Flag in detail table. |
| Signal on last available candle | Only include if at least Q+1 data exists. |
| Zero-volume candle in forward data | Skip (this shouldn't happen for ETFs but guard against it). |

### 7.4 Summary Statistics

For each forward window, across all signals:

| Stat | How Computed |
|------|-------------|
| Mean return % | `signals[window].return_pct.mean()` |
| Median return % | `signals[window].return_pct.median()` |
| Win rate % | `(signals[window].return_pct < 0).mean() × 100` (for bearish scans) |
| Mean max drawdown % | `signals[window].max_drawdown_pct.mean()` |
| Mean max surge % | `signals[window].max_surge_pct.mean()` |
| Signal count for this window | Number of signals with non-null data for this window |

---

## 8. Performance Considerations

### 8.1 V1 Performance Budget

| Metric | Target | Rationale |
|--------|--------|-----------|
| Quarterly ETF scan | < 60 seconds | User-acceptable for iteration |
| Memory usage | < 500 MB | Must work alongside Streamlit on 8 GB Mac |
| DB queries | ~500 (one per ETF) | Acceptable for quarterly (small result sets) |

### 8.2 Query Strategy

**V1:** One `get_candles()` call per ETF ticker. For ~500 ETFs with 200
quarterly candles each = ~100K rows loaded into pandas. This is very
manageable.

**Future optimization (if needed for daily/all-stocks scans):**
- Bulk SQL query: `SELECT * FROM daily_ohlcv WHERE stock_id IN (...) ORDER BY stock_id, date`
- Batch stock_ids into groups of 100 to avoid parameter overflow
- Stream results into pandas in chunks

### 8.3 Caching

- **Universe cache:** The list of ETF tickers changes rarely. Cache it for
  the Streamlit session with `@st.cache_data(ttl=3600)`.
- **Candle cache:** Individual ticker candles could be cached, but quarterly
  data is small enough that re-fetching is fine.
- **No pre-computation needed for V1** — quarterly candle counts are small.

---

## 9. Session Roadmap

| Session | Name | Type | Deliverable |
|---------|------|------|-------------|
| **29** | Strategy Lab — Design Doc | Docs-only | `docs/STRATEGY_LAB.md` (this file), `docs/STRATEGY_LAB_BUILD_LOG.md`, updates to WORKFLOW/PROGRESS/CHANGELOG |
| **30** | Strategy Lab — Scanner Engine | Code | `backend/services/scanner_service.py` — universe resolution, candle fetching, condition filtering, RSI computation, forward returns. Comprehensive tests. |
| **31** | Strategy Lab — Streamlit UI | Code | `streamlit_app/pages/scanner.py` — condition form builder, run button, progress bar, summary panel, detail table. |
| **32** | Strategy Lab — Iteration & Polish | Code | Bug fixes, performance tuning, UX improvements from real-world usage feedback. |
| **33** | Strategy Lab — Add Weekly/Monthly | Code | Extend scanner to support weekly and monthly timeframes. Adjust forward windows per timeframe. |
| **34** | Strategy Lab — More Indicators | Code | Add SMA, EMA, MACD, Bollinger conditions to the form builder. |
| **35** | Strategy Lab — Persistence | Code | `strategies` + `strategy_conditions` tables, save/load/name/version, re-run saved scans. |
| **36** | Strategy Lab — Cross-Timeframe | Code | Conditions that reference multiple timeframes (e.g., quarterly signal + weekly entry). |
| **37** | Strategy Lab — Target Analysis | Code | Hit-rate table at various downside targets with median time-to-hit. |
| **38+** | Watchlist Backend | Code | Original Session 29 scope (deprioritized). |

> Sessions 32+ are flexible — the order may change based on what you learn
> from using the scanner in Sessions 30–31.

---

## 10. Future Phases

### 10.1 Natural Language Input

Add a text box where the user can describe a pattern in plain English. An LLM
(or rule-based parser) converts it to structured `ScanCondition` objects.
The structured form is pre-filled so the user can verify and tweak before
running.

### 10.2 Entry Point Optimization

> "The best quarterly reversals already drop 10-12% by end of quarter. Wait
> for a snap-back rally, enter at a lower high."

This requires cross-timeframe analysis:
1. Quarterly scan identifies the reversal signal
2. Switch to weekly/daily view for that ticker
3. Identify the snap-back rally (X% bounce from post-signal low)
4. Identify the lower high (weekly high below the quarterly candle high)
5. Entry = breakdown below the lower high's low

This is a multi-step workflow that the Strategy Lab can guide with a
"Signal → Entry" pipeline in later sessions.

### 10.3 Backtesting Integration

Once strategies are persisted and entry/exit rules are defined, the Strategy
Lab can feed into the Phase 4 backtesting framework:
- Strategy Lab defines the signal
- Backtester defines position sizing, stop loss, take profit
- Performance metrics (Sharpe, Sortino, max drawdown) are computed
- Equity curves are plotted

### 10.4 Alerts

When a saved strategy's conditions are met on new data (e.g., a new quarterly
candle just formed that matches the bearish reversal pattern), trigger a
notification via the Phase 6 alert system (Telegram, email).

### 10.5 Journal Integration

When you enter a trade based on a Strategy Lab signal, the journal entry can
link back to the strategy and specific signal that triggered it. This creates
a feedback loop: "Strategy X generated 12 signals → I traded 5 → here's how
they performed vs. the historical backtest."

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **Signal** | A specific ticker + date combination where all scan conditions matched |
| **Forward return** | The price change from signal date to a future date |
| **Win rate** | Percentage of signals where the price moved in the hypothesized direction |
| **Max drawdown** | The worst adverse price move between signal and the forward window |
| **Max surge** | The best favorable price move between signal and the forward window |
| **Universe** | The set of tickers scanned (e.g., all ETFs) |
| **Condition** | A single filter rule (e.g., "RSI > 70") |
| **Strategy** | A named collection of conditions + timeframe + universe + forward windows |

## Appendix B: Related Files

| File | Role |
|------|------|
| `backend/services/scanner_service.py` | Scanner engine (Session 30) |
| `backend/services/candle_service.py` | Existing candle data access |
| `backend/services/indicators.py` | Existing indicator computation (RSI, SMA, etc.) |
| `backend/models/strategy.py` | Strategy persistence model (Session 35) |
| `streamlit_app/pages/scanner.py` | Scanner UI (Session 31) |
| `docs/STRATEGY_LAB_BUILD_LOG.md` | Dedicated build log for Strategy Lab sessions |
