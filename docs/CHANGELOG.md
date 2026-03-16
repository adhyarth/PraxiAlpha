# 📋 PraxiAlpha — Changelog

> All notable changes to this project will be documented in this file.
> Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
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
