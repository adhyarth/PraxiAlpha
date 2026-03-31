# 🔬 Strategy Lab — Build Log

> **Purpose:** Dedicated build log for all Strategy Lab sessions.
> The main `docs/BUILD_LOG.md` contains a one-liner per session pointing here.
>
> **Design doc:** [`docs/STRATEGY_LAB.md`](./STRATEGY_LAB.md)
>
> **Last updated:** 2026-03-30 (Session 29)

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
