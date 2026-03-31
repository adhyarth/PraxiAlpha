# 📋 PraxiAlpha — Changelog

> All notable changes to this project will be documented in this file.
> Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- **Strategy Lab scanner engine** (`backend/services/scanner_service.py`) — `ScannerService.run_scan()` pipeline: universe resolution (ETF filter from `stocks` table), per-ticker candle fetch + enrichment (body %, upper/lower wick %, volume vs N-period avg, RSI-14), vectorized condition filtering with AND logic, forward return computation (return %, max drawdown %, max surge % per window), summary aggregation (mean, median, win rate). 10 data classes (`ScanCondition`, `ScanRequest`, `ForwardReturn`, `SignalResult`, `WindowSummary`, `ScanSummary`, `ScanResult`). Progress callback support for Streamlit integration. 65 comprehensive tests across 10 categories.
- **Strategy Lab design document** (`docs/STRATEGY_LAB.md`) — comprehensive spec for the Pattern Scanner + Forward Returns Analyzer: V1 scope (quarterly bearish reversal candles on ETFs), full condition taxonomy (price shape, volume, indicators, cross-timeframe, fundamentals), scanner service architecture, data model for future persistence, UI wireframe, forward return specification, performance considerations, session roadmap (Sessions 29–38+), and future phases (NLP, entry optimization, backtesting, alerts, journal integration).
- **Strategy Lab dedicated build log** (`docs/STRATEGY_LAB_BUILD_LOG.md`) — separate build log for Strategy Lab sessions to avoid growing the main BUILD_LOG.

### Added (continued — data validation)
- **`StockMeta` metadata enrichment** (`data_validation_service.py`) — new `StockMeta` dataclass with `type_label`, `is_low_liquidity`, and `is_exotic` properties. `fetch_stock_metadata()` async function queries the DB for name, exchange, asset_type, and 90-day average daily volume. Used to annotate validation results so users can distinguish real data issues from ignorable mismatches on SPACs, warrants, rights, or micro-cap securities.
- **Validation UI enrichment** (`streamlit_app/pages/validation.py`) — results table now displays "Type" (Stock, ETF, SPAC, Warrant, etc.), "Avg Vol (90d)" (formatted with commas), and "Note" columns. The Note column flags low-liquidity or exotic securities with "⏭️ safe to ignore" when they have mismatches.
- **`ValidationResult.note` property** — contextual note explaining ignorable mismatches based on security type and liquidity.
- **`ValidationResult.meta` field** — optional `StockMeta` attached to each result, fetched once per ticker and cached across timeframes.
- **`fetch_yf_candles()` function** — Yahoo Finance data fetcher using `yfinance` REST API. Supports daily, weekly, monthly, and quarterly (via monthly aggregation) timeframes. No authentication required.
- **YF retry with exponential backoff** — `fetch_yf_candles()` retries up to 3 times with 2s/4s backoff on transient failures (Yahoo Finance rate-limits / TCP drops).
- **Random ticker sampling in Streamlit validation GUI** — re-enabled `sample_random_tickers(10)` for 10 fixed + 10 random tickers per validation run (80 checks total).
- **Incomplete period exclusion** — `compare_candles()` now excludes the current incomplete week/month/quarter from validation to prevent false mismatches on partial periods.
- **CHEATSHEET.md** — quick-reference command cheatsheet for Docker, Streamlit, and validation scripts.

### Changed
- **Migrated validation from tvdatafeed to yfinance** — replaced `fetch_tv_candles()` + `get_tv_client()` with `fetch_yf_candles()`. Removed tvdatafeed dependency in favor of `yfinance` (stable PyPI package, REST API, actively maintained). Renamed `tv_validation_service.py` → `data_validation_service.py` and `test_tv_validation.py` → `test_data_validation.py`. All existing validation logic preserved — only the data-fetch layer swapped.
- **Dependency swap** — `pyproject.toml` optional dependency group renamed from `tv-validate` (tvdatafeed from GitHub) to `validate` (yfinance from PyPI).
- **Removed `tv_username`/`tv_password` config** — `backend/config.py` and `.env.example` no longer require TradingView credentials. yfinance uses a free REST API with no authentication.
- **Deleted obsolete tvdatafeed scripts** — removed `scripts/validate_tradingview.py`, `scripts/debug_aapl_volume.py`, and `scripts/debug_volume_multi.py`.
- **Streamlit validation UI updated** — all labels changed from "TradingView" to "Yahoo Finance", removed TV credential verification step, reduced rate-limit sleep from 2s to 0.5s.
- **Persistent event loop for Streamlit async** — replaced per-call `asyncio.run()` with a single long-lived event loop in a daemon thread. Fixes `TCPTransport closed` errors caused by asyncpg connections dying when the event loop is destroyed between calls.
- **Rate-limit delays increased** — CLI script 0.3s → 1.0s, Streamlit GUI 0.5s → 1.5s to reduce Yahoo Finance rate-limit drops.
- **Expanded fixed ticker set to 10** — AAPL, MSFT, NVDA, SMH, TSLA, QQQ, SPY, GLD, CVNA, XBI.
- **Extended validation windows** — daily: 2520 bars (~10yr), weekly: 520, monthly: 120, quarterly: 40.
- **Vectorized `compare_candles()`** — replaced `iterrows()` loop with pandas vectorized percentage-difference computation for ~10x speedup on large comparison sets.
- **Streamlit event loop via `@st.cache_resource`** — persistent background event loop now managed by Streamlit's resource cache instead of a module-level global, ensuring proper lifecycle across reruns.
- **Log handler cleanup in `try/finally`** — validation page wraps the entire run block in `try/finally` to guarantee log handler removal even on exceptions, preventing duplicate log lines on rerun.
- **Debug script imports from service** — `scripts/debug_yfinance.py` now imports `FIXED_TICKERS`, `ALL_TIMEFRAMES`, `TIMEFRAME_BARS`, and `fetch_yf_candles` from the canonical `data_validation_service` module instead of duplicating them.
- **14 new tests (508 total)** — additional test coverage from self-review fixes (cutoff logic, random ticker filtering, tolerance comments, dead code removal).
- **`sample_random_tickers()` honors `n` parameter** — exchange/ETF counts are now scaled proportionally when `n` differs from the default (10); any remainder is filled from a mixed-exchange pool and the result is trimmed to exactly `n`.
- **Editable pip install hints** — all `pip install "praxialpha[validate]"` messages changed to `pip install -e ".[validate]"` (correct for local dev).
- **Inline DB credentials removed from commands** — WORKFLOW.md, README.md, and CHEATSHEET.md now use `export DATABASE_URL=...` + separate `streamlit run` invocation to avoid leaking credentials via shell history / process listings.

### Changed (continued — data validation details)
- **Data Validation service** (`backend/services/data_validation_service.py`) — backend service for comparing OHLCV data (daily, weekly, monthly, quarterly) between PraxiAlpha's database and Yahoo Finance. Includes bar-by-bar comparison with configurable tolerances (1% price, 10% volume), quarterly aggregation from YF monthly data, failure persistence (JSON), and summary computation.
- **43 validation tests** (`backend/tests/test_data_validation.py`, 494 total) — all tests pass with no changes to test logic (tests exercise comparison/aggregation/persistence, not the fetch layer).
- **Volume tolerance at 10%** — `DEFAULT_VOLUME_TOLERANCE` accounts for data provider consolidation differences (exchange-only vs dark-pool-inclusive volumes).
- **Date normalization for non-daily comparisons** — `_normalize_dates_for_merge()` aligns weekly dates to ISO-Monday, monthly/quarterly to 1st-of-month before merging.
- **Split-only adjustment (no dividend adjustment)** — candle service now computes adjustment factors from the `stock_splits` table using cumulative split ratios (product of `1/ratio` for all future splits), matching Yahoo Finance / Bloomberg defaults. The EODHD `adjusted_close` column (which includes both split and dividend adjustments) is no longer used for price adjustment, eliminating ~1-2% per-year dividend drag that caused our charts to diverge from second sources.
- **`_get_split_factors()` and `_compute_cumulative_split_factor()` helpers** — new methods on `CandleService` for computing split adjustment from the `stock_splits` table.
- **Split-adjusted weekly/monthly/quarterly candles** — non-daily timeframes with `adjusted=True` now re-aggregate from split-adjusted daily candles in Python (pandas `resample` with `W-SUN` for weekly, `MS` for monthly, `QS` for quarterly) instead of reading raw TimescaleDB continuous aggregates. This produces smooth, continuous charts with correct moving averages (e.g., 200-week SMA for SMH matches industry-standard charting). Raw aggregates are still used when `adjusted=False`.
- **4 new aggregate-adjustment tests** (451 total) — `test_weekly_adjusted_aggregates_from_daily` (verifies weekly OHLCV aggregation from adjusted daily candles), `test_weekly_unadjusted_uses_raw_aggregate` (raw path unchanged), `test_split_boundary_weekly_continuous` (10-day series spanning a split produces smooth weekly candles), `test_monthly_adjusted_aggregates_from_daily` (monthly aggregation).
- **`test_dividend_not_applied`** — verifies that stocks with dividends but no splits show raw prices unchanged (EODHD dividend drag not applied).
- **`test_multiple_splits`** — verifies cumulative split factor for stocks with multiple historical splits (e.g., Apple's 7:1 + 4:1).
- **`test_no_splits_returns_raw`** — verifies that adjusted=True with no splits returns raw prices unchanged (no dividend drag).
- **`adjusted` parameter on candle API** — `GET /api/v1/charts/{ticker}/candles?adjusted=true|false` (default `true`). Toggles between split-adjusted and raw historical prices for all timeframes. Response `adjusted` field reflects whether adjustment was requested and applicable.
- **Split-Adjusted toggle in Streamlit chart sidebar** — checkbox to switch between adjusted (default) and raw price views; enabled for all timeframes. Info bar shows whether adjustment was applied.
- **Smart OHLCV gap-fill** — `daily_ohlcv_update` Celery task now auto-detects missing dates since the last successful fetch and fills all gaps using one EODHD bulk API call per missing trading day. On a normal day this is still 1 API call; after a 5-day outage it self-heals with ~3-4 calls (weekdays only).
- **`_candidate_dates()` helper** — generates weekday-only date lists for gap-fill, extracted for testability.
- **`_fetch_and_upsert_date()` helper** — handles single-date bulk fetch, record matching, batch upsert, and `latest_date` update. Extracted from the monolithic task for testability.
- **`ohlcv_max_gap_days` config setting** — caps auto-fill at 60 calendar days (configurable). Beyond that, the task logs a warning and recommends the manual backfill script.
- **12 new gap-fill tests** (434 total) — `_candidate_dates` (6 scenarios: no gap, single day, weekend skip, multi-day, full week, Saturday anchor), `_fetch_and_upsert_date` (2 scenarios: empty bulk, known/unknown ticker matching), integration (4 scenarios: up-to-date, cap exceeded, 5-day outage, holiday in gap).
- **3 new options-exclusion tests** (437 total) — `test_skips_options_trades`, `test_includes_equity_but_skips_options`, `test_returns_reason_for_options_trade`.
- **Trading Journal PDF Report** — `journal_report_service.py` with annotated candlestick chart generation (Plotly + kaleido) and PDF export (fpdf2). Charts show entry/exit markers, stop-loss/take-profit lines, trade context.
- **Report API endpoint** — `GET /api/v1/journal/report` with date range, status, ticker, and `include_charts` filters. Returns downloadable PDF with trade summaries, aggregate stats (win rate, profit factor, avg winner/loser), and embedded charts.
- **36 new report tests** (367 total) — helper functions (format_pnl, format_pct, lookback, chart end date), chart builder (6 scenarios), PDF generation (7 scenarios), API endpoint (5 scenarios).
- **fpdf2 + kaleido dependencies** — added to `pyproject.toml` for PDF generation and Plotly static image export.
- **Post-close "what-if" implementation** — `TradeSnapshot` model, snapshot service (create, list, what-if summary), Celery periodic task (`generate_snapshots`), 2 new API endpoints (`GET /snapshots`, `GET /what-if`), Alembic migration 003 (local-only)
- **Direction-aware hypothetical PnL** — `compute_hypothetical_pnl()` helper using Decimal arithmetic, supports long and short trades
- **Max tracking durations by timeframe** — daily: 30 days, weekly: 112 days (16 weeks), monthly/quarterly: 540 days (18 months)
- **Celery beat schedule entry** — `daily-trade-snapshots` runs at 7:00 PM ET to snapshot all eligible closed trades
- **Snapshot cadence by timeframe** — daily trades: every day, weekly trades: every 7 days, monthly/quarterly trades: every 30 days
- **37 new snapshot tests** (323 total) — model structure, PnL computation (7 scenarios), serialization, service CRUD, what-if summary, user isolation, max tracking, Celery task registration, API routes, create snapshot, eligible trade finder
- **User isolation implementation** — `user_id` column on `trades` table, `PRAXIALPHA_USER_ID` env var in `config.py`, all journal service queries filtered by `user_id`, Alembic migration (local-only, not tracked in repo)
- **11 new isolation tests** (279 total) — create sets user_id, get/list/update/delete/add_exit/add_leg scoped to user, cross-user access returns None, serialization includes user_id
- **User isolation design (Option B)** — lightweight per-user trade privacy via `user_id` column on `trades` table + `PRAXIALPHA_USER_ID` environment variable. Each user's `.env` sets a unique ID; all journal queries filter by this value so users only see their own trades. No UI changes required.
- **`PRAXIALPHA_USER_ID` env var** — new config setting (defaults to `"default"`) that identifies the current user for journal row ownership
- **User isolation decision rationale** — evaluated 3 options: (A) full JWT/OAuth auth (too heavy), (B) env-var user_id column (chosen — lightweight, upgradeable), (C) separate DB per user (not scalable). Documented in DESIGN_DOC.md §11.
- **User isolation implementation plan** — 7 files to change: `.env.example`, `config.py`, `backend/models/journal.py` model, `journal_service.py`, Alembic migration, tests. Child tables (`trade_exits`, `trade_legs`, `trade_snapshots`) inherit isolation via `trade_id` FK — no separate `user_id` column needed.
- **Post-close "what-if" tracking design** — `trade_snapshots` table schema (7 columns: UUID PK, trade_id FK, snapshot_date, close_price, hypothetical_pnl, hypothetical_pnl_pct, created_at) with UNIQUE constraint on `(trade_id, snapshot_date)`
- **Snapshot schedule by timeframe** — daily trades: every trading day for 30 calendar days; weekly trades: weekly for 16 calendar weeks; monthly trades: monthly for 18 calendar months
- **Celery task plan** — periodic task to auto-generate snapshots for closed trades, fetching prices from `daily_ohlcv`/aggregates, computing direction-aware hypothetical PnL
- **2 planned API endpoints** — `GET /api/v1/journal/{trade_id}/snapshots` (list snapshots) and `GET /api/v1/journal/{trade_id}/what-if` (best/worst hypothetical PnL summary)
- **Trading Journal backend** — full CRUD implementation for trade journaling with 3 tables (`trades`, `trade_exits`, `trade_legs`), service layer with computed fields (status, PnL, R-multiple), and 7 API endpoints (`/api/v1/journal/`)
- **Trading Journal models** — `Trade`, `TradeExit`, `TradeLeg` ORM models with 5 ENUMs (`TradeDirection`, `AssetType`, `TradeType`, `Timeframe`, `LegType`), UUID PKs, JSONB tags, cascade relationships
- **Trading Journal service** — `journal_service.py` with `compute_trade_metrics()` for 6 derived fields, full async CRUD (create, get, list, update, delete), `add_exit()` with quantity validation, `add_leg()` for multi-leg options
- **Trading Journal API** — 7 endpoints with Pydantic request schemas, regex-validated enums, price/quantity constraints (`gt=0`), filter support (ticker, status, direction, timeframe, tags, date range)
- **53 new tests** (268 total) — ENUMs, model table names, computed field logic (12 scenarios), serialization, mocked CRUD, Pydantic validation, router registration
- **Trading Journal schema design** — 3 tables (`trades`, `trade_exits`, `trade_legs`) with 31 columns total, supporting open/partial/closed trades, partial exits (scale-out), multi-leg options, timeframe tracking, JSONB tags, and free-form comments
- **Trading Journal PDF report plan** — per-trade annotated candlestick charts (matching trade timeframe), entry/exit markers, stop/TP lines, summary statistics, timeframe-based lookback (daily=1yr, weekly=2yr, monthly=5yr, quarterly=10yr)
- **Trading Journal API endpoints planned** — 8 endpoints for CRUD, partial exits, option legs, and PDF report generation (`/api/v1/journal/`)
- **Trading Journal sessions added to roadmap** — Session 16 (Backend), Session 20 (PDF Report) inserted before Watchlist sessions
- **Trading Journal Streamlit UI** — full journal page (`streamlit_app/pages/journal.py`) with trade list (filters, PnL columns, status badges), new trade entry form, trade detail view (exits, option legs, what-if snapshots, edit, delete), and PDF report download button in sidebar.
- **Journal API client** — `streamlit_app/components/journal_api.py` — HTTP helper functions for all 10 journal API endpoints (list, get, create, update, delete, add exit, add leg, list snapshots, what-if summary, download report).
- **Journal trade form component** — `streamlit_app/components/journal_trade_form.py` — reusable Streamlit forms for create, edit, add exit, and add option leg.
- **Journal trade detail component** — `streamlit_app/components/journal_trade_detail.py` — renders trade info card, exits table, legs table, what-if summary, and snapshot history.
- **55 new UI tests** (422 total) — formatting helpers (12), API client (19), URL construction (3), rendering with mocked st (12), page helpers (9).

### Fixed
- **AAPL daily volume validation false-positives** — investigation confirmed that AAPL volume mismatches (5-8% on the most recent 1-2 bars) are caused by data provider consolidation lag between EODHD and second sources, not a code bug. Raised `DEFAULT_VOLUME_TOLERANCE` from 5% → 10% to accommodate this real-world provider discrepancy.
- **TCPTransport websocket errors in validation** — (historical, now resolved) the previous tvdatafeed dependency had frequent websocket failures. Replaced with yfinance REST API which has no such issues.
- **TCPTransport closed errors in Streamlit validation** — asyncpg connections were dying because each `_run_async()` call created a new event loop via `asyncio.run()`. Fixed by using a persistent background event loop shared across all DB queries.
- **Double volume adjustment on split tickers** — EODHD already returns split-adjusted volume, but `_apply_split_adjustment()` was dividing volume by the split ratio again. Removed the redundant volume adjustment; only OHLC prices are now adjusted.
- **Future splits applied to current data** — `_get_split_factors()` was including splits with future dates (e.g., CVNA's announced 1:5 reverse split). Added `date <= CURRENT_DATE` filter so only completed splits affect candle data.
- **Split volume test updated** — `test_adjusted_applies_split_factor_to_ohlc` now expects unchanged volume (EODHD provides pre-adjusted volume), matching the corrected production behavior.
- **Sidebar emoji encoding** — `streamlit_app/app.py` had corrupted Unicode codepoints for 🔍, 📋, and 🔎; replaced with correct emoji characters.
- **Misleading auto-retry banner** — validation page UI warned "Those tickers will be automatically re-checked" but retry logic is not yet implemented; updated text to "Review them below — automatic re-checking will be enabled in a future release."

---

## [Session 14] — 2026-03-19

### Added
- **Checkpoint-based session workflow** in `WORKFLOW.md` — 3 explicit commit checkpoints (code, progress, CI-clean) to survive Copilot Chat OOM crashes on 8 GB Mac
- **Crash recovery mechanism** in `docs/PROGRESS.md` — "🔴 Current Session Status" block serves as persistent checkpoint for mid-session crash recovery
- **Docker RAM management guideline** — `docker compose stop` during code-only sessions, `docker compose up -d` for dashboard/DB (saves ~2-3 GB)
- **OOM pitfall (#16)** in Common Pitfalls — documents 8 GB Mac memory pressure and mitigations
- **Resume prompts** in `WORKFLOW.md` §6 — separate prompts for normal sessions and crash recovery, both include `docs/PROGRESS.md`

### Changed
- `WORKFLOW.md` session steps renumbered 0–10 (was 0–7) with 3 new checkpoint steps
- `WORKFLOW.md` Step 0 now reads `docs/PROGRESS.md` in addition to BUILD_LOG and DESIGN_DOC
- `docs/PROGRESS.md` upcoming sessions renumbered — Session 14 = Workflow Improvements, 15 = Watchlist Backend, etc.
- Resume prompt now includes `docs/PROGRESS.md` in the orientation file list
- **Stock search service** (`backend/services/stock_search.py`) — typeahead search across the `stocks` table by ticker (prefix match) and company name (substring match), with relevance ranking (exact → prefix → name)
- **Stock search API endpoint** — `GET /api/v1/stocks/search?q=<query>` with `limit`, `active_only`, `asset_type` filters
- **Stock search Streamlit widget** (`streamlit_app/components/stock_search.py`) — reusable typeahead component with selectbox for search results
- **19 new tests** (215 total) — serialization, edge cases, limit clamping, API endpoint, widget helpers
- **`docs/PROGRESS.md`** — new file for full project status, phase checklists, session history, and upcoming sessions roadmap
- **Candlestick chart component** (`streamlit_app/components/candlestick_chart.py`) — Plotly-based interactive chart builder
  - `candles_to_dataframe()` — converts API candle response to DatetimeIndex DataFrame
  - `build_candlestick_figure()` — builds OHLCV candlestick chart with configurable overlays
  - Volume subplot with bull/bear color coding
  - Indicator overlays: SMA, EMA, RSI, MACD, Bollinger Bands (via technical indicators service)
  - Dynamic subplot layout (1–4 rows based on selected indicators)
  - Dark theme styling with custom color palette
- **Charts page** (`streamlit_app/pages/charts.py`) — Streamlit interactive charting page
  - Sidebar controls: ticker, timeframe (daily/weekly/monthly/quarterly), candle limit
  - Indicator toggles with configurable periods for all 5 indicators
  - Backend integration via `/api/v1/charts/{ticker}/candles` API endpoint
- **25 new tests** (196 total) — candlestick chart builder: data prep, figure structure, indicator overlays, subplot layout
- **Technical indicators service** (`backend/services/analysis/technical_indicators.py`) — pure Python/pandas implementations
  - `sma()` — Simple Moving Average (configurable period, default 20)
  - `ema()` — Exponential Moving Average (span-based, default 20)
  - `rsi()` — Relative Strength Index with Wilder's smoothing (default period 14)
  - `macd()` — MACD line, signal line, histogram (default 12/26/9)
  - `bollinger_bands()` — Middle/Upper/Lower bands (default 20-period, 2σ)
- **Analysis package public API** (`backend/services/analysis/__init__.py`) — exports all five indicator functions
- **52 new tests** (171 total) — comprehensive coverage for all indicators including edge cases, validation, and integration tests
- **Weekly/Monthly/Quarterly candle aggregates** — TimescaleDB continuous aggregates on the `daily_ohlcv` hypertable
  - `weekly_ohlcv` (13.5M rows), `monthly_ohlcv` (3.4M rows), `quarterly_ohlcv` (1.2M rows)
  - Auto-refresh policies: every 1 hour with appropriate lookback windows
  - Composite indexes `(stock_id, bucket DESC)` for fast queries
  - Setup script: `scripts/create_candle_aggregates.py` with `--drop` flag
- **Candle service layer** (`backend/services/candle_service.py`) — unified queries across all timeframes (daily/weekly/monthly/quarterly)
  - `get_candles()` — query candles with ticker, timeframe, date range, and limit
  - `get_candle_summary()` — latest candle + data range per timeframe
  - `get_aggregate_stats()` — row counts and freshness for aggregate health monitoring
- **Charts API endpoints** (`backend/api/routes/charts.py`)
  - `GET /charts/{ticker}/candles` — candle data by timeframe with date range/limit filters
  - `GET /charts/{ticker}/summary` — multi-timeframe summary for a ticker
  - `GET /charts/stats` — aggregate statistics and health
- **Celery task `refresh_candle_aggregates`** — refreshes all three aggregates after daily OHLCV update, uses raw asyncpg connection for `CALL refresh_continuous_aggregate`
- **24 new tests** (119 total) — candle service, charts API, Celery task registration, candle summary
- **PR review workflow** — documented `gh` CLI commands in `WORKFLOW.md` Step 6 for fetching GitHub Copilot PR review comments programmatically
- **Full market backfill completed** — 58.2M OHLCV records, 18.4K splits, 634K dividends across 23,714 tickers (1990–2026)
- **Production backfill script (`scripts/backfill_full.py`)** — full market backfill for ~20K+ active US stocks & ETFs
  - Smart ticker filtering: only Common Stock + ETF (skips warrants, preferred, units, OTC)
  - Async concurrency with configurable semaphore (default 5 parallel requests)
  - Real-time `data/backfill_live.log` for `tail -f` monitoring (one line per ticker)
  - `data/backfill_progress.json` checkpoint file — tracks completed/failed tickers, records count, ETA
  - Resume from checkpoint after crash (`--resume` flag)
  - Dry-run mode (`--dry-run`) to preview without API calls
  - Failed ticker retry queue (automatic sequential retry after main pass)
  - Incremental start date: uses `stock.latest_date - 5 days` overlap to avoid re-fetching full history
  - CLI flags: `--concurrency`, `--asset-type`, `--skip-splits-divs`, `--start-date`
- **Implemented `daily_ohlcv_update` Celery task** — replaces TODO stub with working incremental logic
  - Uses EODHD bulk endpoint (single API call for all tickers on a given date)
  - Updates `stock.latest_date` after successful upsert
  - Includes retry logic (max 3 retries, 5-minute delay)
- **Implemented `daily_macro_update` Celery task** — replaces TODO stub with working incremental logic
  - Fetches only last 7 days of observations per FRED series (incremental, not full re-fetch)
  - Upserts with ON CONFLICT deduplication
- **33 new tests** (95 total) — ticker filtering, progress tracker, checkpoint load/save, incremental date calculation

### Changed
- **Charts page ticker input replaced with search widget** — sidebar now uses typeahead stock search instead of a plain text input
- **Documentation restructure** — trimmed `WORKFLOW.md` to focused actionable content (last/next session, workflow, pitfalls); moved all project status, phase checklists, session history, and roadmap to new `docs/PROGRESS.md`; updated cross-references in `CONTRIBUTING.md` and `ARCHITECTURE.md`
- `EODHDFetcher` now accepts `timeout` parameter (default 30s, backfill uses 60s)
- `backfill_stock` and `backfill_all_stocks` Celery tasks now use shared logic from `backfill_full.py`
- `.gitignore` updated to exclude backfill progress/log files
- **`daily_ohlcv_update` now chains `refresh_candle_aggregates`** — weekly/monthly/quarterly aggregates are refreshed automatically after each daily OHLCV update
- **`get_aggregate_stats()` uses approximate row counts** — switched from `SELECT count(*)` (full table scan on 58M rows) to `pg_class.reltuples` (O(1)) + `max(bucket)` freshness signal
- **Celery `refresh_candle_aggregates` uses `max(bucket)` instead of `count(*)`** — cheaper freshness signal after each refresh, avoids scanning millions of rows in the daily pipeline
- **Summary endpoint consolidated queries** — `/{ticker}/summary` now runs 1 query per timeframe (was 2) by combining count + min/max in a single query, reducing round-trips from 8 → 4
- **`daily_ohlcv_update` bulk `latest_date` update** — replaced N+1 per-stock SELECT+UPDATE loop with a single bulk `UPDATE ... WHERE id IN (...)` statement
- **Celery `DB_BATCH_SIZE` aligned to 1000** — `data_tasks.py` batch size now matches `backfill_full.py` (was still 3000)
- **Splits/dividends rowcount accuracy** — `_backfill_splits_dividends` now uses `result.rowcount` from `on_conflict_do_nothing` instead of blindly incrementing per row; skipped duplicates no longer inflate the count

### Fixed
- **Weekly bucket misalignment** — `time_bucket('7 days', date)` anchored to Unix epoch (Thursday); added `origin => '2026-01-05'` (a Monday) so weekly buckets always start on Monday
- **`get_candles()` docstring mismatch** — documented "newest first" but query returns oldest→newest; updated docstring to correctly describe the subquery + re-sort behavior
- **`str(engine.url)` password masking** — `str(engine.url)` replaces the password with `***`, causing raw asyncpg connection failures; fixed to use `settings.async_database_url` directly
- **DB parameter overflow crash** — reduced `DB_BATCH_SIZE` from 3000 → 1000 (24K params → 8K params) to stay safely under PostgreSQL's ~32K parameter limit
- **DB retry with backoff** — upsert operations now retry up to 3 times with progressive backoff (10s/20s/30s) on `OperationalError` (handles transient DB restarts/recovery)
- **Resume >100% progress bug** — `--resume` now skips both completed AND failed tickers; previously-failed tickers are retried only in the end-of-run retry phase, not re-fetched from the API in the main pass
- **`record_success` not cleaning failed dict** — successful retries now remove the ticker from `tickers_failed`, preventing tickers from appearing in both completed and failed lists
- **Retry loop `KeyError`** — changed `del tracker.failed[ticker]` → `tracker.failed.pop(ticker, None)` to handle checkpoint-sourced tickers not yet in the tracker

- **`WORKFLOW.md` — session workflow document** — entry point for every Copilot chat session; includes current project state, 7-step session workflow, common pitfalls, quick reference, and session log summary
- **Economic calendar full integration** — service layer, API, Celery scheduler, and Streamlit dashboard widget
  - `EconomicCalendarService` — orchestrates fetch/upsert/query/prune operations for calendar events (PostgreSQL upsert with ON CONFLICT)
  - `GET /api/v1/calendar/upcoming` — query upcoming events with `days`, `importance`, and `limit` filters
  - `GET /api/v1/calendar/high-impact` — convenience endpoint for dashboard (importance=3 only)
  - `POST /api/v1/calendar/sync` — manual trigger for TradingEconomics sync (for dev/testing)
  - `daily_economic_calendar_sync` Celery Beat task — runs at 7 AM ET daily, syncs 14-day lookahead, prunes events >90 days old
  - Streamlit `render_economic_calendar_widget()` — shows upcoming events with importance badges, countdown timers, and forecast/actual/previous values; falls back to direct TE API if backend is unavailable
  - Dashboard page (`pages/dashboard.py`) — tabbed widget with "High Impact" and "All Events" views
  - 18 new integration tests: service (sync, prune, query, is_high_impact), API serialization, Celery task registration, and widget helpers (badges, countdown, edge cases)
  - `__init__.py` files for `streamlit_app/`, `streamlit_app/components/`, `streamlit_app/pages/` (fixes mypy module resolution)
  - `calendar_helpers.py` — pure helper module (`importance_badge`, `days_until`, `serialize_event`) with zero heavy deps, safe for lightweight CI
- **Economic calendar infrastructure** — placeholder model, fetcher, and tests for TradingEconomics API integration
  - `EconomicCalendarEvent` SQLAlchemy model with all TE fields (calendar_id, importance, actual/previous/forecast, etc.)
  - `TradingEconomicsFetcher` async fetcher with retry logic, country/importance/date filtering, and `parse_event()` mapper
  - `US_HIGH_IMPACT_EVENTS` registry of 19 key US events (NFP, CPI, FOMC, GDP, etc.)
  - 14 unit tests covering model, registry, and fetcher (44 total tests now)
  - `te_api_key` config setting with `guest:guest` free-tier fallback
- **Mental Model #14: "Economic events are noise, price action is signal"** — calendar events create short-term volatility but the tape is set by smart money; use the calendar defensively, not as a trading signal
- **GitHub Pro upgrade** — enables full branch protection for private repos
- **Branch protection on `main`** — require PRs, block direct pushes (including admins), block force pushes, require linear history, block branch deletion
- **Squash-and-merge enforcement** — only squash merge is allowed for PRs; PR title becomes commit message, PR body becomes commit description
- **Auto-delete merged branches** — feature branches are cleaned up automatically after merge
- **Branch protection documentation** — `CONTRIBUTING.md` updated with merge strategy and protection rules
- **`T10YIE` (10-Year Breakeven Inflation Rate)** — replaces discontinued `GOLDAMGBD228NLBM` (Gold Price) in the FRED series registry
- **Macro backfill tests** (`test_backfill_macro.py`) — unit tests for backfill logic (fetcher calls, empty series handling, error recovery, null filtering, fetcher cleanup)
- **FRED registry tests** (`test_data_pipeline.py`) — series count, required fields, valid categories, expected IDs, discontinued series guard
- **Extended macro validation tests** — sort order, null preservation, negative values, dedup behavior, index reset
- **`build_macro_records()` helper** — extracted record-building logic from `backfill_macro_data()` into a testable pure function
- **`CONTRIBUTING.md`** — commit message convention (Conventional Commits), branch naming, git workflow, PR checklist, documentation checklist
- **Branch workflow** — all future work uses feature branches + PRs (no more direct commits to `main`)
- **CI on feature branches** — GitHub Actions now triggers on pushes to `feat/**` and `fix/**` branches (not just `main`), catching failures before PRs
- **Local CI script** (`scripts/ci_check.sh`) — runs ruff lint, ruff format, and mypy locally before pushing; supports `--fix` mode for auto-repair
- **Git pre-push hook** — automatically runs `ci_check.sh` before every `git push`, blocking pushes that would fail CI

### Fixed
- **Celery task `RuntimeError` on Python 3.11+** — `daily_economic_calendar_sync` used `asyncio.get_event_loop().run_until_complete()` which can raise `RuntimeError` when no loop exists; replaced with `asyncio.run()`
- **Raw string timestamps in `parse_event()`** — `TradingEconomicsFetcher.parse_event()` returned raw strings for `date`, `reference_date`, and `te_last_update` but the model expects `DateTime(timezone=True)`; added `_parse_datetime()` to produce timezone-aware datetimes
- **Malformed events crash full sync** — a single event with missing `calendar_id` or unparseable `date` would crash the entire upsert batch; added `_prepare_event_for_upsert()` validation/normalization in `EconomicCalendarService`
- **Stale fields on upsert** — ON CONFLICT `set_=` only updated `actual`/`forecast`/`previous` etc.; now also updates `date`, `country`, `category`, `event` so rescheduled events are reflected
- **N+1 upsert queries** — replaced per-event INSERT loop with a single bulk `pg_insert(...).values(events).on_conflict_do_update(...)` using `insert_stmt.excluded` references
- **Streamlit `RuntimeError` on Python 3.11+** — `_fetch_events_direct()` used `asyncio.get_event_loop()` which can raise `RuntimeError`; replaced with `asyncio.get_running_loop()` + fallback to `asyncio.run()`
- **Hardcoded backend URL** — Streamlit widget's `_fetch_events_from_api()` used `http://localhost:8000`; now reads `BACKEND_BASE_URL` env var
- **`pytest.importorskip` side effect** — `skipif` condition called `pytest.importorskip("celery")` which raises a skip during collection, potentially skipping the entire file; replaced with `importlib.util.find_spec("celery") is None`
- **Corrupted DESIGN_DOC.md schema** — ASCII box-drawing for `watchlists`/`alerts`/`trades` tables was corrupted (missing headers, unclosed boxes); rebuilt with clean box-drawing characters
- **Mypy type errors** — fixed 3 `[no-any-return]` errors in `eodhd_fetcher.py` and `fred_fetcher.py` by adding explicit type annotations for `response.json()` return values
- **Discontinued FRED series** — removed `GOLDAMGBD228NLBM` (Gold Price, no longer available on FRED) from the macro series registry
- **Ruff lint failures** — removed unused imports (`MagicMock`, `AsyncMock`, `patch`) from test files; added `N806` ignore for test files in `pyproject.toml` (PascalCase mock variables are conventional)
- **CI "tests" job hanging** — `pip install -e ".[dev]"` installed heavy packages (streamlit, celery, plotly, jupyter) that took forever to build; replaced with a lightweight explicit install of only the packages needed by tests; added pip caching
- **OHLCV high/low swap** — pandas 2.x copy-on-write broke the one-liner multi-column swap; replaced with explicit copy-based swap
- **`ci_check.sh` nounset crash** — `$1` was unset when no args passed; fixed with `${1:-}` default
- **Self-referencing optional dep** — `praxialpha[test]` inside `[dev]` extras could fail during source installs; inlined test deps into `[dev]`
- **`validate_macro` docstring** — incorrectly claimed "Drops rows with null values"; updated to reflect actual behavior (nulls preserved, filtered at insert time)
- **Null filter test** — `test_backfill_macro_filters_null_values` accessed internal SQLAlchemy `stmt._values` which is `None`; simplified to verify `build_macro_records` output directly

### Changed
- **DESIGN_DOC.md** — Added Mental Model #14, economic calendar data type, TradingEconomics as data provider, updated pipeline diagram, database schema, Phase 2 roadmap, cost table, architecture diagrams, and project structure
- **FRED series registry** — replaced Gold Price (`GOLDAMGBD228NLBM`) with 10-Year Breakeven Inflation Rate (`T10YIE`) for better macro coverage
- **CI test install** — split `[dev]` optional dependencies into `[test]` (lightweight) + `[dev]` (full); CI uses explicit lightweight install to avoid building unused heavy packages
- **Macro backfill tests** — `TestBackfillMacroRecordBuilding` now tests the extracted `build_macro_records()` function directly instead of duplicating production logic
- **Null filtering test** — `test_backfill_macro_filters_null_values` verifies `build_macro_records` returns only non-null records and that execute was called
- **Local CI script** — `ci_check.sh` now runs pytest (step 4/4) in addition to lint, format, and type checks; pre-push hook catches test failures before they reach GitHub
- **Documentation** — updated `DESIGN_DOC.md`, `docs/ARCHITECTURE.md`, and `README.md` to reflect the new macro series and removal of gold

### Data Milestones
- 14/14 FRED macro series backfilled successfully (81,474 records)
- Series: DGS10, DGS2, DGS30, DFF, T10Y2Y, VIXCLS, DTWEXBGS, DCOILWTICO, T10YIE, M2SL, WALCL, UNRATE, CPIAUCSL, PCEPI

---

## [0.1.0] — 2026-03-13

### Added
- **Project scaffolding** — 125 files: FastAPI backend, Celery workers, Docker stack, database models, API routes, scripts
- **Docker Compose stack** — 5 services: PostgreSQL/TimescaleDB, Redis, FastAPI, Celery worker, Celery beat
- **Database models** — `Stock`, `DailyOHLCV` (TimescaleDB hypertable), `MacroData`, `StockSplit`, `StockDividend`
- **Data pipeline** — EODHD fetcher (stocks, OHLCV, splits, dividends), FRED fetcher (macro indicators), data validator
- **Backfill script** (`scripts/backfill_data.py`) — `--populate`, `--test`, `--all`, `--tickers` modes
- **Database setup script** (`scripts/setup_db.py`) — creates tables, enables TimescaleDB, sets up hypertable
- **API endpoints** — `/health`, `/api/v1/stocks/`, `/api/v1/stocks/count`, `/api/v1/stocks/{ticker}`
- **Celery tasks** — `daily_ohlcv_update`, `daily_macro_update`, `backfill_stock`, `backfill_all_stocks`
- **CI/CD pipeline** (`.github/workflows/ci.yml`) — GitHub Actions with Ruff lint/format, mypy type checking, pytest (with TimescaleDB + Redis service containers)
- **Documentation** — `DESIGN_DOC.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_LOG.md`, `docs/CHANGELOG.md`

### Fixed
- **Backfill bug** — PostgreSQL parameter limit (~32,767) exceeded during bulk inserts for stocks with 9,000+ rows of history; fixed with batched inserts (3,000 rows per batch)
- **TimescaleDB hypertable** — partition column (`date`) must be in the primary key; switched from `id` PK to composite `(stock_id, date)` PK

### Changed
- **Code quality** — Applied Ruff formatting + linting across entire codebase (import sorting, unused import removal, consistent line lengths, f-string fixes)
- **`pyproject.toml`** — Added Ruff, mypy, and pytest configuration; explicit `setuptools` package discovery

### Data Milestones
- 49,225 US tickers populated from EODHD
- 67,919 OHLCV records backfilled (10 test stocks: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, UNH)
- 34 stock splits tracked
- 544 dividend events tracked

---

*This changelog is updated with every commit.*
