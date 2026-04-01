# 🔬 Strategy Lab — Build Log

> **Purpose:** Dedicated build log for all Strategy Lab sessions.
> The main `docs/BUILD_LOG.md` contains a one-liner per session pointing here.
>
> **Design doc:** [`docs/STRATEGY_LAB.md`](./STRATEGY_LAB.md)
>
> **Last updated:** 2026-03-31 (Session 30 — merged PR #36)

---

### Session 29 — 2026-03-30: Strategy Lab — Design Doc (Phase 2)

**Goal:** Design the Strategy Lab feature — a Pattern Scanner + Forward Returns
Analyzer for rapid strategy iteration. Document the full spec before writing code.

**Branch:** `docs/strategy-lab-design`

#### What Was Done

1. Created `docs/STRATEGY_LAB.md` — comprehensive design document covering:
   - Vision and motivating example (quarterly bearish reversal candle)
   - V1 scope lock (quarterly ETFs, price shape + volume + RSI, 5 forward windows)
   - Full condition taxonomy (price shape, volume, indicators, cross-timeframe,
     fundamentals) — V1 implements first 3 categories, rest documented for later
   - Architecture: system diagram, scanner service design with dataclass API,
     step-by-step data flow, integration with existing CandleService and indicators
   - Data model for future persistence (strategies, strategy_conditions, scan_results)
   - UI wireframe (condition form builder, summary stats panel, detail table)
   - Forward return specification (5 quarterly windows, return/drawdown/surge metrics)
   - Performance considerations (~60s target for quarterly ETF scan)
   - Session roadmap (Sessions 29–38+)
   - Future phases (NLP input, entry point optimization, backtesting integration,
     alerts, journal integration)

2. Created `docs/STRATEGY_LAB_BUILD_LOG.md` — dedicated build log for Strategy
   Lab sessions (avoids growing the main BUILD_LOG further).

3. Updated all project docs (WORKFLOW, PROGRESS, CHANGELOG, DESIGN_DOC) to
   reflect the Strategy Lab priority shift and new session plan.

#### Key Design Decisions

- **Quarterly-only for V1** — eliminates daily noise, keeps scan size manageable
  (~100K rows for all ETFs), delivers the exact use case the developer wants
  to iterate on immediately.
- **Programmatic ETF filter** — uses `stocks.asset_type = 'ETF'` rather than a
  hardcoded ticker list. Extensible to all stocks later.
- **Hybrid SQL + pandas approach** — SQL fetches candle data via existing
  CandleService (split-adjusted), pandas handles condition filtering and RSI
  computation. Keeps the scanner decoupled from new DB schema.
- **No persistence in V1** — get the scanner working first, iterate on patterns,
  then add save/load in a later session. Tables are designed and documented.
- **Dedicated build log** — Strategy Lab is a multi-session effort; a separate
  build log prevents the main BUILD_LOG from growing even larger (already
  causes OOM on 8 GB Mac).
- **Win rate definition** — for bearish scans, win = price goes down. Tied to
  candle color selection so it automatically flips for bullish patterns later.
- **Forward returns use quarterly candle closes** — not intra-quarter daily
  data (that's for later cross-timeframe analysis). Max drawdown/surge are
  computed from the quarterly closes between signal and window.

#### Files Changed
- `docs/STRATEGY_LAB.md` — **new** — full design document
- `docs/STRATEGY_LAB_BUILD_LOG.md` — **new** — dedicated build log
- `docs/CHANGELOG.md` — added Strategy Lab design entries
- `WORKFLOW.md` — updated last session, next session, current phase
- `docs/PROGRESS.md` — updated component status, session history, roadmap
- `DESIGN_DOC.md` — updated phase roadmap with Strategy Lab sessions

#### Test Count: 508 (unchanged — docs-only session)

---

### Session 30 — 2026-03-30: Strategy Lab — Scanner Engine (Phase 2)

**Goal:** Build the scanner engine — the computational core that the Streamlit
UI (Session 31) will call. Implements the full scan pipeline from §4 of the
design doc.

**Branch:** `feat/scanner-engine` | **PR:** #36 (merged 2026-03-31)

#### What Was Built

**`backend/services/scanner_service.py`** — stateless pattern scanner engine:

1. **Data classes (10):** `ScanCondition`, `ScanRequest`, `ForwardReturn`,
   `SignalResult`, `WindowSummary`, `ScanSummary`, `ScanResult` — plus
   operator and field registries.

2. **`ScannerService.run_scan(request)`** — full pipeline:
   - Validate request (timeframe, universe, candle color, forward windows)
   - Resolve universe via SQL (`stocks` table ETF filter)
   - Per-ticker: fetch quarterly candles via `CandleService.get_candles()`
     (split-adjusted), compute derived columns (body %, upper/lower wick %,
     full range %, volume vs N-period rolling avg, RSI-14)
   - Apply vectorized condition filters (AND logic, NaN excluded)
   - Compute forward returns per signal (return %, max drawdown ≤ 0, max surge ≥ 0)
   - Aggregate summary stats (mean, median, win rate per window)
   - Return `ScanResult` with timing metadata

3. **Helper methods:**
   - `resolve_universe(universe)` — ETF query from `stocks` table
   - `_fetch_and_enrich_ticker()` — candle fetch + derived columns + RSI
   - `_apply_conditions()` — vectorized boolean mask from conditions
   - `_compute_forward_returns()` — per-signal forward return calculator
   - `_compute_single_forward_return()` — one signal × one window
   - `_build_summary()` — aggregate stats across all signals
   - `_validate_request()` — input validation
   - `_get_volume_lookback()` — extract from condition extra params

**`backend/tests/test_scanner.py`** — 68 tests across 10 categories:
- Data classes & operators (8)
- Request validation (6)
- Universe resolution (3)
- Per-ticker enrichment (8)
- Condition filtering (11)
- Forward return computation (5)
- Summary aggregation (8) — includes any-color win-rate=None test
- Volume lookback helper (6) — includes invalid/zero lookback fallback tests
- Full `run_scan` integration (7)
- Edge cases (6)

#### PR Review (2 cycles, 12 Copilot comments)

**Round 1 (6 comments):**
- Guard all four price columns (open/high/low/close) > 0 before division
- Loosen volume_vs_avg: allow partial windows with `min_periods=1`
- Clarify ForwardReturn docstring (drawdown/surge vs signal close)
- Add bounded async concurrency for ticker fetches (Semaphore)
- Switch `iterrows()` → `itertuples()` for signal iteration
- Precompute per-ticker `date→index` dict for O(1) signal lookup

**Round 2 (6 comments):**
- Revert to sequential fetching (AsyncSession not safe for concurrent awaits)
- Add per-ticker exception handling with logging
- Clamp `max_drawdown_pct ≤ 0` and `max_surge_pct ≥ 0` per spec
- Set `win_rate_pct=None` when `candle_color="any"` (ambiguous win direction)
- Defensive `_get_volume_lookback()`: try/except for non-numeric values
- Guard `progress_callback` calls with try/except

#### Key Design Decisions

- **RSI per ticker before concat (Option B)** — matches the design doc
  recommendation. RSI's `ewm()` doesn't vectorize across groups, and per-ticker
  computation during the fetch loop is simpler and cache-friendly.
- **Volume rolling window excludes current candle** — uses `shift(1).rolling(N)`
  so the current candle's volume isn't compared against itself.
- **Wick percentages clipped to ≥ 0** — guards against data anomalies where
  `high < max(open, close)` or `low > min(open, close)`.
- **NaN values don't pass conditions** — `fillna(False)` ensures incomplete
  data (e.g., RSI warmup period) doesn't generate false signals.
- **Display-ready percentages in SignalResult** — `body_pct`, `upper_wick_pct`,
  `lower_wick_pct` are multiplied by 100 before storage in `SignalResult`, so
  the Streamlit UI can display them directly.
- **Progress callback** — `run_scan()` accepts an optional
  `progress_callback(current, total)` so the Streamlit UI can show a progress
  bar during the scan. Callback errors are caught and logged to prevent
  UI issues from aborting the scan.
- **Drawdown/surge clamped** — `max_drawdown_pct` is always ≤ 0,
  `max_surge_pct` is always ≥ 0, matching the Strategy Lab spec. Avoids
  confusing negative "surge" or positive "drawdown" values in the UI.
- **Any-color win rate = None** — when `candle_color="any"`, win direction
  is ambiguous (user hasn't chosen bearish or bullish), so `win_rate_pct`
  is set to `None` rather than defaulting to bullish.
- **Sequential fetching** — single `AsyncSession` shared by `CandleService`
  is not safe for concurrent overlapping awaits, so tickers are fetched
  sequentially. Per-ticker errors are caught and logged.

#### Files Changed
- `backend/services/scanner_service.py` — **new** — scanner engine
- `backend/tests/test_scanner.py` — **new** — 68 tests

#### CI Status: ✅ Green
- ruff: clean
- mypy: clean
- pytest: 576 passed (508 existing + 68 new)

#### Test Count: 576 (508 + 68 new)

---

## Session 31 — 2026-04-01: Strategy Lab — Streamlit UI

**Branch:** `feat/scanner-ui` | **PR:** pending

### What Was Built

`streamlit_app/pages/scanner.py` — the user-facing scanner page for the
Strategy Lab. Calls `ScannerService.run_scan()` from Session 30 and
displays results in an interactive Streamlit dashboard.

### UI Components

1. **Sidebar condition form builder**
   - Candle color toggle (Red / Green / Any)
   - Body % threshold (slider + enable checkbox)
   - Upper wick % threshold (slider + enable checkbox)
   - Lower wick % threshold (slider + enable checkbox)
   - Volume vs N-period average (slider + lookback period + enable)
   - RSI-14 range (dual slider + enable checkbox)
   - Forward return windows (1–8 quarters, multi-select)
   - Timeframe selector (quarterly for V1)

2. **Run scan button** with `st.spinner` during execution

3. **Summary statistics panel**
   - Total signal count, unique tickers, date range
   - Per-window table: win rate %, mean return %, median return %

4. **Per-signal detail table**
   - Columns: ticker, date, open, high, low, close, volume, RSI, body %
   - Forward return columns per selected window
   - Sortable by any column (click header)
   - Expandable rows with per-signal forward return breakdown

### Performance

Switched from pandas daily resample to SQL aggregates for the 5.3K ETF
universe. The original approach timed out after ~60s; SQL aggregates
complete in ~5-10s.

### Bug Fix: Time-Dependent Validation Tests

`test_monthly_excludes_current_month` and `test_quarterly_excludes_current_quarter`
were implicitly depending on `date.today()` falling within March 2026 / Q1 2026.
After April 1, the cutoff logic no longer excluded the test bars.

Fix: added keyword-only `_today` parameter to `compare_candles()`, threaded
through to `_last_completed_period_cutoff()`. Tests now pin their date.

### Files Changed
- `streamlit_app/pages/scanner.py` — **new** — scanner page UI
- `streamlit_app/app.py` — added "🔬 Strategy Lab" nav entry
- `backend/tests/test_scanner_ui.py` — **new** — 38 UI tests
- `backend/services/scanner_service.py` — SQL aggregate performance fix
- `backend/services/data_validation_service.py` — `_today` param on `compare_candles()`
- `backend/tests/test_data_validation.py` — pinned `_today` in 2 time-dependent tests

### CI Status: ✅ Green
- ruff lint: clean
- ruff format: clean
- mypy: clean
- pytest: 614 passed (576 existing + 38 new)

### Test Count: 614 (576 + 38 new)
