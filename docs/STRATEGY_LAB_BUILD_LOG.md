# 🔬 Strategy Lab — Build Log

> **Purpose:** Dedicated build log for all Strategy Lab sessions.
> The main `docs/BUILD_LOG.md` contains a one-liner per session pointing here.
>
> **Design doc:** [`docs/STRATEGY_LAB.md`](./STRATEGY_LAB.md)
>
> **Last updated:** 2026-03-30 (Session 30)

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

**Branch:** `feat/scanner-engine`

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
   - Compute forward returns per signal (return %, max drawdown, max surge)
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

**`backend/tests/test_scanner.py`** — 65 tests across 10 categories:
- Data classes & operators (8)
- Request validation (6)
- Universe resolution (3)
- Per-ticker enrichment (8)
- Condition filtering (11)
- Forward return computation (5)
- Summary aggregation (7)
- Volume lookback helper (4)
- Full `run_scan` integration (7)
- Edge cases (6)

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
  bar during the scan.

#### Files Changed
- `backend/services/scanner_service.py` — **new** — scanner engine
- `backend/tests/test_scanner.py` — **new** — 65 tests

#### CI Status: ✅ Green
- ruff: clean
- mypy: clean
- pytest: 573 passed (508 existing + 65 new)

#### Test Count: 573 (508 + 65 new)
