# 📝 PraxiAlpha — Build Log

> A chronological record of every step taken to build PraxiAlpha.
> Updated after each work session.

---

## Phase 1: Foundation & Data Pipeline

### Session 1 — 2026-03-13: Project Scaffolding

#### What We Did
1. ✅ **Finalized DESIGN_DOC.md** (v1.1)
   - Chose EODHD as primary data provider (over Yahoo Finance — more reliable, better API)
   - Chose FRED for macro/economic data (free, official Fed data)
   - Scoped full US universe (~49K tickers, 30+ years)
   - Estimated storage: ~12 GB for OHLCV data

2. ✅ **Created full project scaffolding** (125 files)
   - Backend: FastAPI app, config, database, models, API routes, services, tasks, tests
   - Scripts: setup_db.py, backfill_data.py
   - Docker: Dockerfile, docker-compose.yml (5 services)
   - Config: pyproject.toml, alembic.ini, .env, .gitignore

3. ✅ **Fixed build issues**
   - Dockerfile: needed to copy all code before `pip install -e .`
   - pyproject.toml: changed build backend from legacy to `setuptools.build_meta`
   - pyproject.toml: added explicit package discovery (`include = ["backend*"]`) — setuptools was confused by multiple top-level directories
   - DailyOHLCV model: changed from `id` primary key to composite `(stock_id, date)` primary key — required by TimescaleDB (partitioning column must be in PK)

4. ✅ **Started Docker stack**
   - All 5 containers running: db, redis, app, celery-worker, celery-beat
   - FastAPI serving on http://localhost:8000
   - Celery worker connected to Redis, 4 tasks registered
   - Celery beat scheduler running

5. ✅ **Set up database**
   - TimescaleDB extension enabled
   - 3 tables created: `stocks`, `daily_ohlcv`, `macro_data`
   - `daily_ohlcv` converted to TimescaleDB hypertable

6. ✅ **Populated stocks table**
   - Fetched 49,225 US tickers from EODHD exchange symbol list
   - All inserted into `stocks` table

7. 🔜 **Next: Test backfill** (10 blue-chip tickers)

#### Issues Encountered
- EODHD API key from initial session was expired → user got new key
- FRED API key was also invalid → user got new key  
- VS Code Copilot chat UI froze during long operation → restarted, no data lost (Docker volumes persisted)
- TimescaleDB hypertable creation failed initially because `id BIGSERIAL PRIMARY KEY` didn't include the `date` partition column → fixed by making `(stock_id, date)` the composite PK

#### Current Database State
| Table | Rows | Status |
|-------|------|--------|
| `stocks` | 49,225 | ✅ Populated |
| `daily_ohlcv` | 0 | ⏳ Awaiting backfill |
| `macro_data` | 0 | ⏳ Awaiting FRED backfill |

#### Git Commits
- `Initial commit — full project scaffolding` (125 files)

---

### Session 2 — 2026-03-13: Test Backfill & Bug Fix

#### What We Did
1. ✅ **Created new database models** — Splits & Dividends
   - `backend/models/split.py` — `StockSplit` model (records stock split events with ratio, numerator, denominator)
   - `backend/models/dividend.py` — `StockDividend` model (records dividend payments with declaration, record, and payment dates)
   - Updated `backend/models/__init__.py` to export new models
   - Updated `backend/models/stock.py` with relationships to splits and dividends
   - Updated `scripts/setup_db.py` to include new models in table creation

2. ✅ **Ran test backfill** (`--test` with 10 blue-chip tickers)
   - Initial run: only 2 of 10 stocks (META, TSLA) loaded data — the other 8 silently failed

3. ✅ **Diagnosed the bug** — PostgreSQL parameter limit overflow
   - PostgreSQL has a hard limit of ~32,767 parameters per query
   - Each OHLCV row has 8 columns, so max ~4,000 rows per INSERT
   - Stocks like AAPL, MSFT, JPM have 9,000+ rows of history (back to 1990) → exceeded the limit
   - META (~3,474 rows) and TSLA (~3,951 rows) squeaked under the limit, which is why they worked
   - The error was **silent** — SQLAlchemy/asyncpg didn't raise a visible exception, the insert just failed

4. ✅ **Fixed the bug** — Batched database inserts
   - Modified `backfill_single_stock()` in `scripts/backfill_data.py`
   - Added `BATCH_SIZE = 3000` (3,000 rows × 8 columns = 24,000 params, safely under 32,767)
   - Inserts now loop in chunks instead of one massive statement

5. ✅ **Added splits & dividends backfill**
   - Extended `scripts/backfill_data.py` with `backfill_splits_dividends()` function
   - Fetches split and dividend history from EODHD for each stock
   - Called automatically after OHLCV backfill for each ticker

6. ✅ **Verified all 10 test stocks loaded successfully**

#### Test Backfill Results
| Ticker | Records | Date Range | Splits | Dividends |
|--------|---------|------------|--------|-----------|
| AAPL | 9,116 | 1990-01-02 → 2026-03-13 | 4 | 79 |
| AMZN | 7,252 | 1997-05-15 → 2026-03-13 | 4 | 0 |
| GOOGL | 5,426 | 2004-08-19 → 2026-03-13 | 2 | 8 |
| JPM | 9,116 | 1990-01-02 → 2026-03-13 | 2 | 147 |
| META | 3,474 | 2012-05-18 → 2026-03-13 | 0 | 9 |
| MSFT | 9,116 | 1990-01-02 → 2026-03-13 | 8 | 91 |
| NVDA | 6,827 | 1999-01-22 → 2026-03-13 | 6 | 54 |
| TSLA | 3,951 | 2010-06-29 → 2026-03-13 | 2 | 0 |
| UNH | 9,116 | 1990-01-02 → 2026-03-13 | 5 | 85 |
| V | 4,525 | 2008-03-19 → 2026-03-13 | 1 | 71 |
| **Total** | **67,919** | | **34** | **544** |

#### Issues Encountered
- Silent insert failures due to PostgreSQL parameter limit — no error raised, data just didn't persist
- Diagnosed by comparing row counts: META/TSLA (shorter history) worked; AAPL/MSFT/JPM (30+ years) didn't
- Confirmed EODHD API was returning valid data for all tickers — the problem was purely on the DB insert side

#### Current Database State
| Table | Rows | Status |
|-------|------|--------|
| `stocks` | 49,225 | ✅ Populated |
| `daily_ohlcv` | 67,919 | ✅ Test backfill complete (10 stocks) |
| `stock_splits` | 34 | ✅ Test backfill complete (10 stocks) |
| `stock_dividends` | 544 | ✅ Test backfill complete (10 stocks) |
| `macro_data` | 0 | ⏳ Awaiting FRED backfill |

#### Files Changed
- `backend/models/split.py` — **NEW** — StockSplit model
- `backend/models/dividend.py` — **NEW** — StockDividend model
- `backend/models/__init__.py` — Added split/dividend exports
- `backend/models/stock.py` — Added splits/dividends relationships
- `scripts/backfill_data.py` — Batched inserts + splits/dividends backfill
- `scripts/setup_db.py` — Added split/dividend imports for table creation

#### Git Commits
- `Phase 2: Test backfill — 10 stocks, 67K records, splits & dividends`

---

### Session 3 — 2026-03-13: CI/CD Setup & Code Quality

#### What We Did
1. ✅ **Set up GitHub Actions CI pipeline** (`.github/workflows/ci.yml`)
   - **Job 1: Lint, Format & Type Check** — runs on every push/PR to `main`
     - `ruff check backend/ scripts/` — linting (style rules, import sorting, best practices)
     - `ruff format --check backend/ scripts/` — formatting verification (consistent code style)
     - `mypy backend/ --ignore-missing-imports` — static type checking
   - **Job 2: Tests** — runs after lint job passes
     - Spins up TimescaleDB (PostgreSQL 16) and Redis as service containers
     - Installs project with `pip install -e ".[dev]"`
     - Runs `pytest --tb=short -q`
     - Uses test-safe environment variables (dummy API keys)

2. ✅ **Ran all linters and formatters locally**
   - `ruff check` — fixed all lint warnings across backend/ and scripts/
   - `ruff format` — auto-formatted all files to consistent style (line length 100, import sorting, etc.)
   - `mypy` — resolved type-checking issues, configured to suppress false positives from untyped third-party libraries

3. ✅ **Updated `pyproject.toml` for code quality tooling**
   - Ruff config: `select = ["E", "W", "F", "I", "N", "UP", "B", "SIM"]` — a broad set of lint rules
   - Ruff ignores: `E501` (line length handled by formatter), `B008` (FastAPI `Depends()` pattern)
   - Per-file ignores: scripts allow uppercase constants inside functions (`N806`)
   - Mypy config: `ignore_missing_imports = true` to suppress false positives from untyped libraries

4. ✅ **Code style fixes across the codebase**
   - Removed unused imports (`date`, `func`, `Text`, `Numeric`, `get_settings`, individual model imports in `setup_db.py`)
   - Sorted imports alphabetically (PEP 8 / isort style)
   - Reformatted long lines and function signatures for consistency
   - Used f-string literals correctly (removed `f"..."` on strings with no interpolation)

#### Files Changed
- `.github/workflows/ci.yml` — **NEW** — GitHub Actions CI pipeline
- `pyproject.toml` — Added Ruff + mypy configuration
- `backend/models/__init__.py` — Sorted imports
- `backend/models/stock.py` — Removed unused imports, reformatted
- `backend/models/ohlcv.py` — Style fixes
- `backend/models/macro.py` — Style fixes
- `backend/models/split.py` — Style fixes (new file from Session 2)
- `backend/models/dividend.py` — Style fixes (new file from Session 2)
- `backend/config.py` — Style fixes
- `backend/database.py` — Style fixes
- `backend/main.py` — Style fixes
- `backend/api/routes/stocks.py` — Style fixes
- `backend/services/data_pipeline/eodhd_fetcher.py` — Style fixes
- `backend/services/data_pipeline/fred_fetcher.py` — Style fixes
- `backend/services/data_pipeline/data_validator.py` — Style fixes
- `backend/tasks/data_tasks.py` — Style fixes
- `backend/tests/test_data_pipeline.py` — Style fixes
- `scripts/backfill_data.py` — Removed unused imports, reformatted
- `scripts/setup_db.py` — Removed individual model imports (use `__init__` exports)

#### CI Pipeline Architecture
```
Push/PR to main
      │
      ▼
┌─────────────────────────┐
│  Job 1: Lint & Types    │
│  ├── ruff check         │  ← Catches bugs, style violations
│  ├── ruff format --check│  ← Ensures consistent formatting
│  └── mypy               │  ← Static type safety
└──────────┬──────────────┘
           │ (passes)
           ▼
┌─────────────────────────┐
│  Job 2: Tests           │
│  ├── TimescaleDB svc    │  ← Real database for integration tests
│  ├── Redis svc          │  ← Real message broker
│  └── pytest             │  ← Runs all tests
└─────────────────────────┘
```

#### Data Storage Note
- All PraxiAlpha data lives in **Docker volumes** (`pgdata` for PostgreSQL, `redisdata` for Redis)
- These volumes are managed by Docker and are NOT directly accessible via Finder
- Data persists across container restarts but is tied to the Docker installation
- To inspect data: use SQL queries via `docker exec`, pgAdmin, or the API
- Docker must be running at 6 PM ET for the Celery Beat auto-update to trigger
- If Docker was down, run the backfill script manually to catch up

#### Git Commits
- `Session 3: CI/CD pipeline + code quality (ruff, mypy, pytest via GitHub Actions)`
- `docs: add CONTRIBUTING.md and adopt Conventional Commits`

#### Process Decision: Branching Strategy
Starting from Session 4, all work will use **feature branches + pull requests**:
- Sessions 1-3 committed directly to `main` (acceptable for initial scaffolding)
- From now on: `feat/`, `fix/`, `docs/` branches → PR → CI passes → merge to `main`
- Commit messages follow **Conventional Commits** (see `CONTRIBUTING.md`)
- Every PR must update docs (BUILD_LOG, CHANGELOG, ARCHITECTURE if applicable)

---

### Session 4 — 2026-03-13: Macro Backfill & FRED Series Fix

#### What We Did
1. ✅ **Replaced discontinued FRED series**
   - `GOLDAMGBD228NLBM` (Gold Price) was removed from FRED — fetching it returned errors
   - Replaced with `T10YIE` (10-Year Breakeven Inflation Rate) — adds inflation expectations to macro indicators
   - Updated code (`backend/models/macro.py`), docs (`DESIGN_DOC.md`, `ARCHITECTURE.md`, `README.md`), and docstrings

2. ✅ **Built macro backfill** (`--macro` flag in `scripts/backfill_data.py`)
   - Fetches all 14 FRED macro series with 30+ years of history
   - Validates data via `DataValidator.validate_macro()`
   - Upserts into `macro_data` table in batches (handles PostgreSQL parameter limits)
   - Result: **81,474 records**, 14/14 series successful, 0 failed

3. ✅ **Added comprehensive tests**
   - `test_backfill_macro.py` — **NEW** — 8 tests for backfill logic (fetcher calls, empty series, error recovery, null filtering, fetcher cleanup, record building)
   - `test_data_pipeline.py` — Added `TestFREDSeriesRegistry` (6 tests: count, fields, categories, expected IDs, discontinued guard) and `TestValidateMacroExtended` (6 tests: valid data, sort order, null preservation, negative values, dedup, index reset)
   - All tests pass in Docker

4. ✅ **Fixed mypy type errors**
   - 3 `[no-any-return]` errors in `eodhd_fetcher.py` and `fred_fetcher.py`
   - Added explicit `dict[str, Any]` type annotations for `response.json()` return values

5. ✅ **Extended CI to feature branches**
   - GitHub Actions now triggers on pushes to `feat/**` and `fix/**` branches
   - Catches lint/type/test failures before PRs are opened

6. ✅ **Fixed CI lint failures**
   - Removed unused imports (`MagicMock`, `AsyncMock`, `patch`) from test files
   - Added `N806` per-file-ignore for `backend/tests/*` in `pyproject.toml` (PascalCase mock variables like `MockFetcher` are conventional in Python tests)
   - Removed unused `MockSession` variable assignment in `test_backfill_macro_closes_fetcher_on_error`
   - Ran `ruff format` to fix formatting inconsistencies

7. ✅ **Created local CI check tooling**
   - `scripts/ci_check.sh` — runs all 3 CI checks locally (ruff lint, ruff format, mypy)
   - Supports `--fix` mode: `./scripts/ci_check.sh --fix` auto-repairs lint and format issues
   - Git pre-push hook (`.git/hooks/pre-push`) — runs `ci_check.sh` automatically before every push
   - Bypass with `git push --no-verify` for emergencies only

8. ✅ **Updated all documentation**
   - `DESIGN_DOC.md` — replaced gold series, added Inflation row to macro curriculum
   - `docs/ARCHITECTURE.md` — replaced gold series in indicators table
   - `README.md` — updated data coverage description
   - `docs/CHANGELOG.md` — documented all changes
   - `backend/models/macro.py` + `scripts/backfill_data.py` — updated docstrings

#### Macro Backfill Results (14/14 series)
| Series | Name | Records |
|--------|------|---------|
| DGS10 | 10-Year Treasury Yield | ~9,100 |
| DGS2 | 2-Year Treasury Yield | ~8,400 |
| DGS30 | 30-Year Treasury Yield | ~8,800 |
| DFF | Federal Funds Rate | ~9,100 |
| T10Y2Y | 10Y-2Y Yield Spread | ~8,700 |
| VIXCLS | VIX | ~8,400 |
| DTWEXBGS | Trade Weighted Dollar Index | ~4,400 |
| DCOILWTICO | WTI Crude Oil | ~8,000 |
| T10YIE | 10-Year Breakeven Inflation Rate | ~5,600 |
| M2SL | M2 Money Supply | ~400 |
| WALCL | Fed Balance Sheet | ~1,100 |
| UNRATE | Unemployment Rate | ~420 |
| CPIAUCSL | Consumer Price Index | ~420 |
| PCEPI | PCE Price Index | ~420 |
| **Total** | | **~81,474** |

#### Current Database State
| Table | Rows | Status |
|-------|------|--------|
| `stocks` | 49,225 | ✅ Populated |
| `daily_ohlcv` | 67,919 | ✅ Test backfill complete (10 stocks) |
| `stock_splits` | 34 | ✅ Test backfill complete (10 stocks) |
| `stock_dividends` | 544 | ✅ Test backfill complete (10 stocks) |
| `macro_data` | 81,474 | ✅ Full backfill complete (14 series) |

#### Files Changed
- `backend/models/macro.py` — Replaced `GOLDAMGBD228NLBM` with `T10YIE`, updated docstring
- `backend/services/data_pipeline/eodhd_fetcher.py` — Fixed mypy `[no-any-return]` error
- `backend/services/data_pipeline/fred_fetcher.py` — Fixed 2 mypy `[no-any-return]` errors
- `backend/services/data_pipeline/data_validator.py` — Fixed high/low swap (pandas 2.x CoW pitfall), corrected `validate_macro` docstring
- `backend/tests/test_data_pipeline.py` — Added `TestFREDSeriesRegistry` (6 tests) + `TestValidateMacroExtended` (6 tests)
- `backend/tests/test_backfill_macro.py` — **NEW** — 10 tests: backfill logic + `build_macro_records` helper tests
- `scripts/backfill_data.py` — Added `backfill_macro_data()` + `build_macro_records()` + `--macro` CLI flag
- `scripts/ci_check.sh` — **NEW** — Local CI check script; fixed `$1` nounset crash
- `.github/workflows/ci.yml` — Feature-branch triggers, pip caching, lightweight test install
- `pyproject.toml` — Added `[test]` extras, inlined into `[dev]`; `N806` per-file-ignore for tests
- `DESIGN_DOC.md` — Updated FRED series list + macro curriculum table
- `docs/ARCHITECTURE.md` — Updated indicators table
- `README.md` — Updated data coverage description
- `docs/CHANGELOG.md` — Documented all changes
- `docs/BUILD_LOG.md` — This session log

#### Git Commits
- `feat(data-pipeline): add macro backfill from FRED & replace discontinued gold series`
- `fix(types): resolve mypy no-any-return errors in EODHD and FRED fetchers`
- `ci: trigger CI on feature and fix branch pushes`
- `fix(lint): resolve ruff errors and add local CI check script + pre-push hook`
- `fix(ci): use lightweight deps in test job to avoid hanging on heavy package builds`
- `fix(validator): use explicit copy for high/low swap to avoid pandas pitfall`
- `refactor(backfill): extract build_macro_records helper + improve test assertions`
- `fix(ci-check): use ${1:-} to avoid nounset crash when no args passed`
- `fix(pyproject): inline test deps into dev extras to avoid self-referencing dep`
- `fix(test): simplify null filter test assertion + add pytest to local CI check`

#### Lessons Learned
| # | Lesson | Context |
|---|--------|---------|
| 15 | External data sources can be discontinued without warning | FRED removed `GOLDAMGBD228NLBM` — always have a fallback plan for third-party data |
| 16 | Test the actual backfill, not just the code | Running the real macro backfill in Docker caught the gold series failure that unit tests alone wouldn't |
| 17 | Run CI on feature branches, not just main/PRs | Catching failures before opening a PR saves review cycles |
| 18 | Always run linters locally before pushing | A failed CI on a PR is embarrassing and wastes time — automate local checks with pre-push hooks |
| 19 | Mock variables use PascalCase by convention, configure linters accordingly | `MockFetcher` is standard in Python tests; add `N806` ignore for test files |
| 20 | Never install full project deps in CI test jobs | `pip install -e ".[dev]"` pulls in streamlit, plotly, jupyter, celery — CI only needs test tooling + the packages the tests actually import; use an explicit lightweight install instead |
| 21 | Pandas 2.x copy-on-write breaks multi-column swaps | `df.loc[mask, ['a', 'b']] = df.loc[mask, ['b', 'a']].values` silently fails; use explicit temp variable swaps instead |
| 22 | Tests should exercise production code, not duplicate it | Copy-pasting logic into tests means tests pass even when production code changes; extract helpers and test those |
| 23 | Assertions must verify the actual behavior under test | A test that only asserts `close()` was called doesn't verify that null filtering actually happened |
| 24 | `set -u` + `$1` crashes when no args are passed | Use `${1:-}` to provide a default empty string |
| 25 | Update CHANGELOG + BUILD_LOG before every commit | Documentation that lags behind commits is worse than no documentation — make it a habit, not an afterthought |
| 26 | Run tests locally before pushing, not just lint | Lint passing ≠ tests passing; add pytest to the pre-push script so test failures never reach CI |
| 27 | Don't access SQLAlchemy statement internals in tests | `stmt._values` is `None` in modern SQLAlchemy; test your own code's output, not ORM internals |
| 28 | GitHub branch protection requires Pro for private repos | $4/month unlocks full branch protection, rulesets, and required status checks |
| 29 | Configure merge strategy early | Squash-merge keeps `main` history clean; one commit per PR = easy to revert |
| 30 | Enforce branch protection for admins too | Without `enforce_admins: true`, repo owners can bypass all rules — always enable it |
| 31 | Free API tiers can provide significant value | TradingEconomics guest:guest returns real calendar data — enough for dashboard awareness |
| 32 | Store external API values as strings when formats vary | TE returns "0.5%", "1.307M", "K" — parsing to float loses context; store raw, parse on display |
| 33 | Placeholder infrastructure enables parallel development | Model + fetcher + tests now exist; dashboard widget and scheduler can be built independently |

---

### Session 5 — 2026-03-14: Economic Calendar Integration (Full Stack)

#### What We Did
1. ✅ **Created `EconomicCalendarService`** (`backend/services/data_pipeline/economic_calendar_service.py`)
   - `sync_upcoming_events()` — fetches from TradingEconomics, upserts into DB (PostgreSQL `ON CONFLICT DO UPDATE`)
   - `prune_old_events()` — deletes events older than 90 days to keep table small
   - `get_upcoming_events()` / `get_high_impact_events()` — query DB with date/importance filters
   - `get_events_for_category()` — drill-down by specific event type (e.g., NFP only)
   - `is_high_impact()` — static method checking against `US_HIGH_IMPACT_EVENTS` registry

2. ✅ **Created calendar API routes** (`backend/api/routes/calendar.py`)
   - `GET /api/v1/calendar/upcoming` — events with `days`, `importance`, `limit` query params
   - `GET /api/v1/calendar/high-impact` — convenience endpoint (importance=3 only)
   - `POST /api/v1/calendar/sync` — manual trigger for development/debugging
   - Registered in `backend/main.py`

3. ✅ **Created Celery Beat task** (`daily_economic_calendar_sync`)
   - Runs at 7 AM ET daily (before market open)
   - Syncs all importance levels for 14-day lookahead
   - Prunes old events after sync
   - Added to Celery Beat schedule in `celery_app.py`

4. ✅ **Created Streamlit dashboard widget** (`streamlit_app/components/economic_calendar.py`)
   - `render_economic_calendar_widget()` — renders compact event cards with importance badges (🔴/🟡/🟢), date/time, countdown ("In 3 days"), and forecast/actual/previous
   - Dual data source: tries FastAPI backend first, falls back to direct TradingEconomics API call
   - Handles async-in-sync (Streamlit's event loop) via thread pool executor

5. ✅ **Updated dashboard page** (`streamlit_app/pages/dashboard.py`)
   - Replaced Phase 2 placeholder with working economic calendar widget
   - Tabbed interface: "High Impact" (importance=3) vs "All Events"

6. ✅ **Wrote 18 integration tests** (`backend/tests/test_calendar_integration.py`)
   - Service: sync with fetcher mock, sync with no events, prune, query, high-impact delegation, `is_high_impact` true/false
   - API: `_serialize_event` with full fields and None date
   - Task: Celery task is registered and callable
   - Widget: importance badges (4 levels), `_days_until` (today, future, past, invalid/None)

7. ✅ **Added `__init__.py` files** for `streamlit_app/`, `components/`, `pages/` — fixes mypy module resolution
8. ✅ **All CI checks pass** — 62/62 tests, ruff lint clean, ruff format clean, mypy clean (only pre-existing `database.py` warning)

#### Architecture Decisions
- **Service layer pattern**: Dashboard/tasks never touch the fetcher or DB directly — they go through `EconomicCalendarService`. This makes testing easy (mock the session) and keeps the pipeline logic in one place.
- **Upsert with ON CONFLICT**: Re-syncing the same window is idempotent. If an event gets updated with actual values, the upsert updates forecast/actual/previous without creating duplicates.
- **7 AM ET sync**: Economic releases cluster around 8:30 AM ET. Syncing at 7 AM gives the dashboard fresh data before the pre-market session.
- **Fallback to direct API**: The Streamlit widget works even without the backend running, which is useful during development.
- **Pruning**: Events older than 90 days are auto-deleted. The calendar is for awareness, not historical analysis.

#### Files Created
- `backend/services/data_pipeline/economic_calendar_service.py` (new)
- `backend/api/routes/calendar.py` (new)
- `backend/tests/test_calendar_integration.py` (new)
- `streamlit_app/components/economic_calendar.py` (new)
- `streamlit_app/__init__.py` (new)
- `streamlit_app/components/__init__.py` (new)
- `streamlit_app/pages/__init__.py` (new)

#### Files Modified
- `backend/main.py` — registered calendar router
- `backend/tasks/data_tasks.py` — added `daily_economic_calendar_sync` task
- `backend/tasks/celery_app.py` — added Celery Beat schedule entry
- `streamlit_app/pages/dashboard.py` — replaced placeholder with calendar widget
- `docs/CHANGELOG.md` — documented new features
- `docs/BUILD_LOG.md` — this entry

#### Lessons Learned
| # | Lesson | Context |
|---|--------|---------|
| 31 | Free API tiers can provide significant value | TradingEconomics guest:guest returns real calendar data — enough for dashboard awareness |
| 32 | Store external API values as strings when formats vary | TE returns "0.5%", "1.307M", "K" — parsing to float loses context; store raw, parse on display |
| 33 | Placeholder infrastructure enables parallel development | Model + fetcher + tests now exist; dashboard widget and scheduler can be built independently |

#### Test Count: 62 (was 44)

---

### Session 6 — 2026-03-15: Copilot Code Review Fixes (PR #3)

#### What We Did
Addressed all 9 Copilot review comments on PR #3 (economic calendar integration):

1. ✅ **Fixed `asyncio.get_event_loop().run_until_complete()` in Celery task** (🔴 High)
   - `data_tasks.py`: Replaced with `asyncio.run()` — safe on Python 3.11+ and Celery workers where no event loop exists
2. ✅ **Added `_parse_datetime()` to `TradingEconomicsFetcher`** (🔴 High)
   - `parse_event()` now returns timezone-aware `datetime` objects for `date`, `reference_date`, and `te_last_update` instead of raw strings
   - Handles ISO-8601 with/without timezone, trailing `Z`, `None`, empty strings, and already-parsed `datetime` objects
3. ✅ **Added event validation in `EconomicCalendarService._upsert_events()`** (🔴 High)
   - New `_prepare_event_for_upsert()` validates required fields (`calendar_id`, `date`) and normalizes timestamp strings to datetimes before insertion
   - Malformed events are logged and skipped instead of crashing the whole sync
   - New `_parse_timestamp()` static method for string → timezone-aware datetime conversion
4. ✅ **Expanded upsert `set_=` to include all mutable fields** (🟡 Medium)
   - ON CONFLICT now also updates `date`, `country`, `category`, `event` — not just actual/forecast/previous
5. ✅ **Switched to bulk upsert** (🟡 Medium)
   - Replaced per-event `INSERT` loop with a single `pg_insert(...).values(events).on_conflict_do_update(...)` statement using `insert_stmt.excluded` references
6. ✅ **Fixed `asyncio.get_event_loop()` in Streamlit widget** (🔴 High)
   - `_fetch_events_direct()` now uses `asyncio.get_running_loop()` with `RuntimeError` fallback, and `asyncio.run()` when no loop is running
7. ✅ **Made backend URL configurable** (🟡 Medium)
   - `_fetch_events_from_api()` reads `BACKEND_BASE_URL` env var (default `http://localhost:8000`) instead of hardcoded URL
8. ✅ **Fixed `pytest.importorskip` in skipif condition** (🔴 High)
   - Replaced with `importlib.util.find_spec("celery") is None` — no side effects during test collection
9. ✅ **Fixed corrupted ASCII schema diagram in DESIGN_DOC.md** (🟡 Medium)
   - Rebuilt the `watchlists`/`alerts`/`trades` section with proper box-drawing characters and properly closed boxes

#### Files Modified
- `backend/tasks/data_tasks.py` — `asyncio.run()` instead of `get_event_loop().run_until_complete()`
- `backend/services/data_pipeline/trading_economics_fetcher.py` — `_parse_datetime()`, updated `parse_event()`
- `backend/services/data_pipeline/economic_calendar_service.py` — `_prepare_event_for_upsert()`, `_parse_timestamp()`, bulk upsert, expanded `set_=`
- `streamlit_app/components/economic_calendar.py` — safe async loop detection, configurable backend URL
- `backend/tests/test_calendar_integration.py` — `importlib.util.find_spec()` for celery skipif
- `DESIGN_DOC.md` — fixed corrupted ASCII schema diagram
- `docs/CHANGELOG.md` — documented changes
- `docs/BUILD_LOG.md` — this entry

#### Test Count: 62 (unchanged)

---

### Session 7 — 2026-03-16: Session Workflow Document

#### What We Did
1. ✅ **Created `WORKFLOW.md`** — session entry point document for Copilot chat sessions
   - **§1 Current Project State** — table of all components and their status, current phase, remaining tasks, next phase preview, key files to read
   - **§2 Session Workflow** — 7-step checklist (orientation → branch → implement → docs → CI → PR → cleanup) with exact commands and conventions
   - **§3 Common Pitfalls** — 8 lessons distilled from Sessions 1–6 (build log ordering, index corruption, asyncio, docs drift, etc.)
   - **§4 Quick Reference** — Docker, CI, Git, and API cheat sheet
   - **§5 Session Log Summary** — one-line summary table of all sessions with PR references
   - Includes a **copy-paste prompt** for starting new chat sessions

2. ✅ **Motivation:** Ensure consistency across chat sessions — same workflow every time, no ad-hoc steps, no documentation drift, no build log ordering issues

#### Architecture Decisions
- **Workflow doc lives at project root** (`WORKFLOW.md`) — it's the entry point, not buried in `docs/`
- **Step 0 (Orientation)** is explicit — Copilot must read WORKFLOW.md, BUILD_LOG latest session, and DESIGN_DOC phase roadmap before writing any code
- **Documentation is part of the implementation step**, not a separate afterthought — this prevents the build log duplication and ordering bugs from Sessions 5–6
- **Session Log Summary table** in WORKFLOW.md gives a quick birds-eye view without reading the full BUILD_LOG

#### Files Created
- `WORKFLOW.md` (new) — session workflow, current state, quick reference

#### Files Modified
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented new workflow document

#### Test Count: 62 (unchanged)

---

### Session 8 — 2026-03-16: Production Backfill Script & Daily Task Implementation

#### What We Did
1. ✅ **Created `scripts/backfill_full.py`** — production-grade full market backfill
   - **Smart ticker filtering** — only `Common Stock` + `ETF` asset types (skips warrants, preferred shares, units, OTC junk). Filters from 49K → 23,714 tickers
   - **Async concurrency** — configurable semaphore (default 5 parallel requests) to stay well under EODHD's 1K calls/min limit
   - **Real-time progress tracking** — `data/backfill_live.log` (one line per ticker, `tail -f` friendly) + `data/backfill_progress.json` (full snapshot with ETA, completed/failed lists)
   - **Checkpoint/resume** — `--resume` flag reads the progress JSON, skips already-completed tickers. Safe to Ctrl+C and restart
   - **Failed ticker retry** — failed tickers are collected and retried sequentially at the end (single retry attempt)
   - **Incremental start date** — if `stock.latest_date` exists, fetches from `latest_date - 5 days` (overlap for corrections) instead of full 30+ year history
   - **Dry-run mode** — `--dry-run` shows what would be fetched without calling the API
   - **CLI options** — `--concurrency`, `--asset-type`, `--skip-splits-divs`, `--start-date`
   - Longer timeout (60s vs default 30s) for heavy historical pulls

2. ✅ **Implemented `daily_ohlcv_update` Celery task** — replaced TODO stub
   - Uses `EODHDFetcher.fetch_bulk_eod()` — single API call returns all US tickers' EOD for a date
   - Matches bulk data against `stocks` table for `stock_id` lookup
   - Upserts into `daily_ohlcv` with ON CONFLICT
   - Updates `stock.latest_date` for every affected stock after successful upsert
   - Retry logic: max 3 retries with 5-minute delay (`bind=True`, `self.retry(exc=exc)`)

3. ✅ **Implemented `daily_macro_update` Celery task** — replaced TODO stub
   - Fetches only the **last 7 days** of observations per FRED series (incremental, not full re-fetch)
   - Upserts with ON CONFLICT deduplication
   - Same retry logic as OHLCV task

4. ✅ **Made `EODHDFetcher` timeout configurable**
   - Added `timeout` parameter to constructor (default 30s for normal use, 60s for backfill)

5. ✅ **Wrote 33 new tests** (95 total, up from 62)
   - `test_backfill_full.py` — 4 test classes:
     - `TestFilterBackfillTickers` (14 tests) — all asset type filtering edge cases
     - `TestBackfillProgressTracker` (12 tests) — success/failure recording, JSON persistence, resume, summary, ETA, atomic writes
     - `TestLoadCheckpoint` (3 tests) — nonexistent, valid, corrupt checkpoint files
     - `TestIncrementalDateLogic` (4 tests) — incremental start date calculation with overlap

#### Architecture Decisions
- **New script, not modifying `backfill_data.py`** — the existing script works for small ad-hoc runs (`--test`, `--tickers`). The new script is purpose-built for the full 10K+ ticker production run
- **Progress file as checkpoint** — JSON is human-readable, can be `cat`'d to check status, and doubles as the resume checkpoint
- **Atomic file writes** — progress JSON is written to `.tmp` then renamed to avoid corruption on crash
- **Bulk endpoint for daily updates** — EODHD's `eod-bulk-last-day` endpoint returns all tickers in one call (vs. 10K individual calls), massively more efficient for daily updates
- **5-day overlap on incremental** — ensures we catch any late corrections/adjustments from the exchange

#### Files Created
- `scripts/backfill_full.py` (new) — production backfill script
- `backend/tests/test_backfill_full.py` (new) — 33 tests for backfill logic

#### Files Modified
- `backend/tasks/data_tasks.py` — implemented `daily_ohlcv_update`, `daily_macro_update`, updated `backfill_stock` and `backfill_all_stocks`
- `backend/services/data_pipeline/eodhd_fetcher.py` — added `timeout` parameter to `EODHDFetcher.__init__`
- `.gitignore` — added `data/backfill_progress.json`, `data/backfill_progress.tmp`, `data/backfill_live.log`
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all changes
- `WORKFLOW.md` — updated current state, phase status, session log

#### Test Count: 95 (was 62, +33 new)

#### Lessons Learned
- EODHD has a `eod-bulk-last-day` endpoint that returns all tickers in one call — much more efficient for daily updates than per-ticker requests
- The `stocks` table has 49K tickers but only ~10K are Common Stock or ETF — the rest are warrants, preferred, units, OTC junk
- Atomic file writes (write to .tmp, then rename) prevent checkpoint corruption on crash

### Session 9 — 2026-03-17: Full Backfill Production Run & Hardening

#### What We Did
1. ✅ **Ran full production backfill** — 23,714 tickers backfilled from 1990-01-02 → 2026-03-16
   - **58,153,151 OHLCV records** inserted via upsert (ON CONFLICT)
   - **18,438 stock splits** and **634,313 dividends** loaded
   - Ran across ~18 hours with 11 resume cycles

2. ✅ **Fixed DB crash from parameter overflow**
   - **Root cause:** `DB_BATCH_SIZE=3000` → 3000 rows × 8 columns = 24,000 SQL parameters, right at PostgreSQL's ~32K parameter limit. A large ticker with 3,000+ records caused the DB to crash into recovery mode
   - **Cascade:** 695 tickers failed with "database system is in recovery mode" / "not yet accepting connections", 36 with "connection was closed in the middle of operation"
   - **Fix:** Reduced `DB_BATCH_SIZE` from 3000 → 1000 (8K params, well under 32K limit)

3. ✅ **Added DB retry logic with backoff**
   - Wrapped the upsert block with `OperationalError` catch and retry (up to 3 attempts with 10s/20s/30s backoff)
   - Prevents transient DB restarts from permanently failing tickers

4. ✅ **Fixed `record_success` to clean up failed dict**
   - When a previously-failed ticker succeeds on retry, it's now removed from `tickers_failed` dict
   - Prevents tickers from appearing in both completed and failed lists

5. ✅ **Fixed resume logic — skip both completed AND failed tickers**
   - **Root cause of >100% progress bug:** `--resume` only skipped completed tickers but re-processed failed ones in the main pass. Each resume re-fetched ~742 failed tickers from the API, even though the retry phase at the end had already handled them
   - **Fix:** Resume now skips both `tickers_completed` and `tickers_failed` from the checkpoint. Previously-failed tickers are retried only in the end-of-run retry phase (step 9)
   - Added checkpoint-aware retry: step 9 now merges both new failures and checkpoint failures for a single retry pass

6. ✅ **Fixed retry loop `KeyError`**
   - Changed `del tracker.failed[ticker]` → `tracker.failed.pop(ticker, None)` to handle tickers from the checkpoint that aren't in the current tracker's failed dict

#### Final Database State
| Table | Records |
|-------|---------|
| `daily_ohlcv` | 58,153,151 |
| `stock_splits` | 18,438 |
| `stock_dividends` | 634,313 |
| Unique stocks with OHLCV data | 23,714 |
| Date range | 1990-01-02 → 2026-03-16 |
| Permanently failed (no data / invalid) | 468 |

#### Files Modified
- `scripts/backfill_full.py` — batch size reduction, DB retry logic, resume bug fix, record_success cleanup
- `WORKFLOW.md` — updated state table, marked backfill ✅ Done, added pitfalls #9–#11, session log
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all fixes

#### Test Count: 95 (unchanged — fixes were in production logic, not test-facing)

#### Lessons Learned
- PostgreSQL has a ~32,767 parameter limit per query. With N columns per row, keep `batch_size × N` well under that limit. We used 3000 × 8 = 24K and it was too close to the edge under load
- Resume logic must skip **both** completed and failed tickers to avoid re-fetching from the API. Failed tickers should only be retried in a dedicated retry phase, not re-processed from scratch
- Setting `DATABASE_URL=` (empty string) as an env var override will mask the `.env` file default — either export the full URL or don't set the variable at all
- The backfill completed 23,714 tickers with only 468 genuine failures (no data / invalid), a 98% success rate

### Session 10 — 2026-03-17: Weekly/Monthly/Quarterly Candle Aggregates

#### What We Did
1. ✅ **Created TimescaleDB continuous aggregates** for weekly, monthly, and quarterly OHLCV candles
   - `weekly_ohlcv` — 7-day time buckets (Monday-aligned via explicit origin), auto-refresh every hour with 4-week lookback
   - `monthly_ohlcv` — 1-month time buckets, auto-refresh every hour with 3-month lookback
   - `quarterly_ohlcv` — 3-month time buckets, auto-refresh every hour with 6-month lookback
   - Each aggregate computes: `open` (first), `high` (max), `low` (min), `close` (last), `adjusted_close` (last), `volume` (sum), `trading_days` (count)
   - Indexes: `(stock_id, bucket DESC)` on all three views for fast lookups
   - Setup script: `scripts/create_candle_aggregates.py` with `--drop` flag for recreation

2. ✅ **Initial data refresh** — populated all aggregates from 58.2M daily rows
   - Weekly: **13,524,873 rows**
   - Monthly: **3,393,032 rows**
   - Quarterly: **1,185,118 rows**
   - Verified with AAPL sample data across all three timeframes

3. ✅ **Created unified candle service** (`backend/services/candle_service.py`)
   - `get_candles(ticker, timeframe, start, end, limit)` — queries the appropriate aggregate view
   - `get_candle_summary(ticker)` — returns latest candle + data range for all timeframes
   - `get_aggregate_stats()` — returns row counts and freshness for all aggregates
   - Supports timeframes: `daily`, `weekly`, `monthly`, `quarterly`

4. ✅ **Created charts API endpoints** (`backend/api/routes/charts.py`)
   - `GET /charts/{ticker}/candles` — query candles by timeframe with date range and limit filters
   - `GET /charts/{ticker}/summary` — multi-timeframe summary for a ticker
   - `GET /charts/stats` — aggregate health/stats endpoint
   - Registered in `backend/main.py` under `/charts` prefix

5. ✅ **Created Celery task** for aggregate refresh (`refresh_candle_aggregates`)
   - Runs automatically after `daily_ohlcv_update` completes
   - Uses raw asyncpg connection (required for `CALL refresh_continuous_aggregate`)
   - Refreshes each view with appropriate lookback window

6. ✅ **Wrote 19 new tests** (`backend/tests/test_candle_service.py`)
   - Service layer: `get_candles` (all timeframes, date filters, default limit), `get_candle_summary`, `get_aggregate_stats`
   - API layer: candle endpoint (default, with params), summary endpoint, stats endpoint, invalid ticker/timeframe handling
   - Celery task: `refresh_candle_aggregates` registration check

7. ✅ **Fixed `str(engine.url)` password masking bug**
   - `str(engine.url)` replaces the password with `***`, causing authentication failures for raw asyncpg connections
   - Fixed in `scripts/create_candle_aggregates.py` and `backend/tasks/data_tasks.py` to use `settings.async_database_url` directly

#### Architecture Decisions
- **TimescaleDB continuous aggregates** over manual materialized views — auto-refresh only recomputes changed time buckets, orders of magnitude faster than raw `GROUP BY` on 58M rows
- **Raw asyncpg for CALL statements** — `refresh_continuous_aggregate()` cannot run inside a transaction block; SQLAlchemy's `engine.begin()` always opens a transaction. Used `asyncpg.connect()` directly with the URL from settings
- **Unified service layer** — single `CandleService` handles all timeframes, abstracting the view names and query patterns from the API layer
- **3M quarterly buckets** — user requested quarterly in addition to weekly/monthly for longer-term analysis

#### Files Created
- `scripts/create_candle_aggregates.py` (new) — aggregate creation, refresh policies, indexes, initial refresh, verification
- `backend/services/candle_service.py` (new) — unified candle query service
- `backend/api/routes/charts.py` (new) — charts API endpoints
- `backend/tests/test_candle_service.py` (new) — 19 tests for service, API, and task

#### Files Modified
- `backend/main.py` — registered charts router
- `backend/tasks/data_tasks.py` — added `refresh_candle_aggregates` task, wired to daily update chain, fixed `str(engine.url)` password masking
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all changes
- `WORKFLOW.md` — updated state table, phase status, API endpoints, session log

#### Database State Update
| View | Rows | Refresh |
|------|------|---------|
| `weekly_ohlcv` | 13,524,873 | Every 1h, 4-week lookback |
| `monthly_ohlcv` | 3,393,032 | Every 1h, 3-month lookback |
| `quarterly_ohlcv` | 1,185,118 | Every 1h, 6-month lookback |

#### Test Count: 117 (was 95, +22 including candle service tests + prior session additions)

#### Lessons Learned
- `str(engine.url)` in SQLAlchemy masks the password with `***` — never use it to build raw connection strings. Use `settings.async_database_url` (the original config value) instead
- TimescaleDB's `refresh_continuous_aggregate()` is a stored procedure (`CALL`), not a function (`SELECT`) — it cannot run inside a transaction block. This is a common gotcha when using SQLAlchemy which wraps everything in transactions
- When running scripts locally against a Dockerized DB, the hostname is `localhost` (not the Docker service name `db`). Override via `DATABASE_URL` env var or `POSTGRES_HOST=localhost`

---

### Session 11 — 2026-03-17: Technical Indicators Service (Phase 2)

#### What We Did
1. ✅ **Implemented technical indicators service** (`backend/services/analysis/technical_indicators.py`)
   - **SMA** — Simple Moving Average with configurable period (default 20)
   - **EMA** — Exponential Moving Average using span-based smoothing (default 20)
   - **RSI** — Relative Strength Index with Wilder's smoothing method (default period 14)
   - **MACD** — Moving Average Convergence/Divergence returning macd_line, signal_line, histogram (default 12/26/9)
   - **Bollinger Bands** — Middle/Upper/Lower bands with configurable period and num_std (default 20, 2σ)
   - All functions are pure, stateless, side-effect-free — accept `pd.Series`, return `pd.Series` or `pd.DataFrame`
   - Shared `_validate_inputs()` helper for consistent error handling across all indicators
   - Population-level std dev (`ddof=0`) for Bollinger Bands to match industry convention

2. ✅ **Updated analysis package exports** (`backend/services/analysis/__init__.py`)
   - Exports all five indicator functions via `__all__`
   - Clean public API: `from backend.services.analysis import sma, ema, rsi, macd, bollinger_bands`

3. ✅ **Wrote 52 new tests** (`backend/tests/test_analysis.py`)
   - `TestValidation` (5 tests) — type checking, empty series, zero/negative period
   - `TestSMA` (7 tests) — basic computation, period=1, period=length, constant series, defaults, edge cases
   - `TestEMA` (7 tests) — basic, no NaNs, period=1, constant, EMA-vs-SMA reactivity, defaults, edge cases
   - `TestRSI` (8 tests) — basic, range [0,100], leading NaNs, all-gains (100), all-losses (0), constant price, defaults, edge cases
   - `TestMACD` (10 tests) — DataFrame shape, histogram=line−signal, constant series, custom periods, fast≥slow rejection, zero/negative period, empty series
   - `TestBollingerBands` (11 tests) — DataFrame shape, middle=SMA, upper≥middle, lower≤middle, symmetry, constant series, wider with more σ, defaults, zero/negative num_std, invalid period
   - `TestIntegration` (3 tests) — RSI of EMA, EMA-based Bollinger Bands, all indicators same length

#### Architecture Decisions
- **Pure pandas, no external TA library** — keeps dependencies minimal and gives us full control over the smoothing method (Wilder's for RSI, standard EWM for EMA/MACD). TA-Lib can be added later as an optional accelerator if needed.
- **Wilder's smoothing for RSI** (`com = period − 1`) — matches the canonical RSI definition used by TradingView, Bloomberg, and most institutional platforms. Many libraries incorrectly use SMA-based RSI.
- **Population std dev (`ddof=0`) for Bollinger Bands** — matches the standard Bollinger Band definition. Sample std dev (`ddof=1`) would produce slightly wider bands.
- **NaN for insufficient data** — rather than forward-filling or guessing, we return NaN where the look-back window has insufficient data. This prevents misleading signals at series boundaries.
- **Functions, not classes** — indicators are stateless mathematical transformations. Functions compose better than classes for this use case (e.g., `rsi(ema(close, 5), 14)`).

#### Files Created / Modified
- `backend/services/analysis/technical_indicators.py` (replaced stub) — 5 indicator functions + shared validator
- `backend/services/analysis/__init__.py` (replaced stub) — public API exports
- `backend/tests/test_analysis.py` (replaced stub) — 52 comprehensive tests

#### Files Updated
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all changes
- `WORKFLOW.md` — updated state table, phase checklist, session log

#### Test Count: 171 (was 119, +52 technical indicator tests)

#### Lessons Learned
- Wilder's smoothing factor `α = 1/period` maps to pandas `ewm(com=period-1)`, not `ewm(span=period)`. Using `span` gives the standard EMA smoothing factor `α = 2/(period+1)`, which is subtly different and produces incorrect RSI values
- `ddof=0` vs `ddof=1` in rolling std affects Bollinger Band width — industry standard is population std dev (`ddof=0`)
- RSI with constant prices produces `0/0` (no gains, no losses) → NaN via pandas, which is the mathematically correct result. Some platforms display 50 for this edge case, but NaN is more honest

#### PR Review Fixes (PR #8 — 4 comments from Copilot code review)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 1 | **Replaced `np.random.seed(42)` with `np.random.default_rng(42)`** in `test_analysis.py` `realistic_series` fixture | `np.random.seed()` mutates NumPy's global RNG state. If any other test in the suite relies on random output, execution order could produce different results — classic source of flaky tests. | As the test suite grows (171 → 500+), order-dependent failures would appear sporadically and be extremely hard to diagnose. In CI with parallel test execution, this becomes even worse. Using a local generator isolates randomness to the fixture. |
| 2 | **Clarified module docstring** — distinguished rolling-window indicators (SMA, RSI, Bollinger → leading NaNs) from EWM-based indicators (EMA, MACD → seeded from index 0, no leading NaNs) | The original docstring said "NaN is used where there is insufficient data" which is only true for rolling-window indicators. EMA/MACD produce values starting at index 0. | Misleading docstrings compound over time. A future developer (or Copilot in a later session) building chart overlays would assume all indicators have leading NaNs and add unnecessary NaN-handling logic, or worse, skip valid data points. Accurate docs prevent phantom bugs in downstream consumers. |
| 3 | **Replaced Unicode `≥` with ASCII `>=`** in MACD validation error message | Codebase convention uses ASCII operators in error messages. Unicode characters can cause encoding issues in log aggregators, grep searches, and test assertions that use string matching. | In production, log pipelines (ELK, Datadog, CloudWatch) may silently drop or mangle Unicode in error messages. `grep ">=1"` wouldn't find `"≥ 1"`. As the project scales to more services, inconsistent encoding in error messages makes incident debugging harder. |
| 4 | **Replaced Unicode `≥` with ASCII `>=`** in `_validate_inputs()` error message | Same reasoning as #3 — consistency and searchability. This function is the shared validator called by every indicator, so the impact is multiplied. | Every indicator (SMA, EMA, RSI, Bollinger) routes through `_validate_inputs()`. A single encoding inconsistency here would affect error handling for all 5 indicators and any future indicators that use the same validator. |

---

### Session 12 — 2026-03-17: Candlestick Chart Component (Phase 2)

#### What We Did
1. ✅ **Created Plotly candlestick chart builder** (`streamlit_app/components/candlestick_chart.py`)
   - `candles_to_dataframe()` — converts API candle response to DatetimeIndex DataFrame
   - `build_candlestick_figure()` — builds OHLCV candlestick chart with configurable overlays
   - Volume subplot with bull/bear color coding (green=bullish, red=bearish)
   - Indicator overlays: SMA, EMA, RSI, MACD, Bollinger Bands (via technical indicators service)
   - Dynamic subplot layout (1–4 rows based on selected indicators)
   - Dark theme styling with custom color palette

2. ✅ **Created Streamlit charts page** (`streamlit_app/pages/charts.py`)
   - Sidebar controls: ticker input, timeframe selector (daily/weekly/monthly/quarterly), candle limit slider
   - Indicator panel: toggles with configurable periods for all 5 indicators
   - Backend integration via `/api/v1/charts/{ticker}/candles` API endpoint

3. ✅ **Wrote 25 new tests** (`backend/tests/test_candlestick_chart.py`)
   - Guarded with `pytest.importorskip('plotly')` for CI compatibility
   - Tests: data prep, figure structure, indicator overlays, subplot layout

#### Architecture Decisions
- **Plotly over Lightweight Charts** — native `st.plotly_chart()` integration, subplot support for indicators
- **Chart builder as testable component** — separated from Streamlit page logic for unit testing
- **Dynamic subplot layout** — adapts row count based on which indicators are selected
- **`pytest.importorskip` guard** — chart tests run locally with plotly, skip gracefully in CI

#### Files Created
- `streamlit_app/components/candlestick_chart.py` — chart builder
- `streamlit_app/pages/charts.py` — Streamlit charts page
- `backend/tests/test_candlestick_chart.py` — 25 chart builder tests

#### Files Modified
- `streamlit_app/app.py` — updated Phase 2 status and navigation
- `pyproject.toml` — added `E402` ignore for test files
- `docs/BUILD_LOG.md`, `docs/CHANGELOG.md`, `WORKFLOW.md`

#### Test Count: 196 (was 171, +25 candlestick chart tests)

---

### Session 13 — 2026-03-17: Stock Search (Phase 2)

#### What We Did
1. ✅ **Created stock search service** (`backend/services/stock_search.py`)
   - `search_stocks()` — async function querying the `stocks` table by ticker prefix (`ILIKE 'Q%'`) and company name substring (`ILIKE '%query%'`)
   - **Relevance ranking** via SQL `CASE`: exact ticker match (rank 0) → ticker prefix (rank 1) → name-only match (rank 2), then by ticker length (shorter = more relevant), then alphabetical
   - Input validation: empty/whitespace queries return `[]` immediately (no DB hit)
   - Limit clamping: `[1, 50]` range enforced regardless of input
   - Optional `active_only` and `asset_types` filters
   - `_serialize_stock()` helper for consistent API response format

2. ✅ **Added search API endpoint** (`backend/api/routes/stocks.py`)
   - `GET /api/v1/stocks/search?q=<query>&limit=10&active_only=true&asset_type=Common+Stock`
   - Uses FastAPI `Query()` validators: `min_length=1`, `max_length=50` for `q`; `ge=1, le=50` for `limit`
   - Returns `{ "count": N, "results": [...] }`

3. ✅ **Created Streamlit search widget** (`streamlit_app/components/stock_search.py`)
   - `render_stock_search()` — reusable component with text input + selectbox
   - `_search_api()` — calls backend `/api/v1/stocks/search` with httpx
   - `_format_option()` — formats stock dict as `"TICKER — Name (Exchange)"`
   - Graceful fallback: shows "No matching stocks found" when API returns empty or is unavailable

4. ✅ **Integrated search into Charts page** (`streamlit_app/pages/charts.py`)
   - Replaced plain `st.text_input("Ticker")` with `render_stock_search()` widget
   - Search results appear as a selectbox; selected ticker feeds into chart rendering

5. ✅ **Wrote 19 new tests** (`backend/tests/test_stock_search.py`)
   - `TestSerializeStock` (3 tests) — full serialization, None latest_date, key completeness
   - `TestSearchStocksEdgeCases` (6 tests) — empty query, whitespace, None, limit clamping (min/max), serialized output, no results
   - `TestSearchAPI` (3 tests) — service delegation, asset_type wrapping, empty results
   - `TestStockSearchWidget` (6 tests) — `_format_option` with full/no-name/no-exchange/ticker-only/empty-strings/missing-ticker

#### Architecture Decisions
- **Service layer, not inline query** — `search_stocks()` lives in its own service file, not embedded in the route handler.
- **SQL-level ranking with `CASE`** — ranking is done in the database, not in Python.
- **Prefix match for ticker, substring for name** — tickers are short codes that users type from the start; names need substring matching.
- **Reusable widget** — `render_stock_search()` accepts `key` and `default_ticker` params for multi-page use.

#### Files Created
- `backend/services/stock_search.py` — search service
- `streamlit_app/components/stock_search.py` — Streamlit widget
- `backend/tests/test_stock_search.py` — 19 tests

#### Files Modified
- `backend/api/routes/stocks.py` — added `/search` endpoint
- `streamlit_app/pages/charts.py` — replaced text input with search widget
- `docs/BUILD_LOG.md`, `docs/CHANGELOG.md`, `WORKFLOW.md`, `docs/PROGRESS.md`

#### Test Count: 215 (was 196, +19 stock search tests)

#### PR Review Fixes (PR #12 — 6 comments from Copilot code review)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 1 | **Charts page uses `st.session_state` instead of silent AAPL fallback** — when search returns `None` (backend down or no match), the last successfully selected ticker is preserved; an `st.info` message surfaces when no ticker is selected | The original code silently fell back to `"AAPL"` whenever the search widget returned `None`, hiding backend connectivity issues and making it impossible to tell whether a search genuinely found nothing. | Users would see AAPL's chart after searching for a different ticker and getting no results, with no indication that anything went wrong. Backend outages would be invisible from the UI. |
| 2 | **`_search_api()` handles errors explicitly** — catches `httpx.ConnectError`/`httpx.TimeoutException` separately (shows "Backend unavailable" warning), handles non-200 responses (422 → "Invalid query"), returns `None` for errors vs `[]` for empty results | The original `except Exception: pass` swallowed all errors and returned `[]`, making backend downtime, timeouts, and validation errors all look like "No matching stocks found." | Debugging would be nearly impossible — a 422 from an overly long query, a timeout from a slow DB, and a genuinely empty result set would all display the same message. In production, users would never know the backend was down. |
| 3 | **Added `max_chars=50` to `st.text_input`** in the search widget | The backend API enforces `max_length=50` on the `q` parameter. Without a client-side limit, users could type longer queries that would always 422. | Users would type long company names, get a 422 from the API, and see "Invalid query" with no explanation of the length limit. The client should prevent the invalid input before it reaches the server. |
| 4 | **Changed `search_stocks` signature from `query: str` to `query: str \| None`** | The function body explicitly handles `None` (returns `[]`), and the test suite tests `None` input, but the type annotation said `str`. This mismatch would cause mypy to flag callers that pass `None`. | As the codebase grows and stricter type checking is enabled, callers passing `None` (e.g., from optional form fields) would trigger mypy errors. The annotation should match the actual behavior. |
| 5 | **Moved `format_stock_option()` from `stock_search.py` widget (Streamlit module) to `backend/services/stock_search.py`** (Streamlit-free) | The widget module imports `streamlit`, which isn't installed in CI's lightweight test environment. The `_format_option` helper is pure logic with no Streamlit dependency, but because it lived in a module that imports Streamlit, its tests were skipped in CI. | All 6 format tests now run in every CI build instead of being silently skipped. A future refactor could break the formatting logic and it would pass CI undetected. |
| 6 | **Removed `streamlit` skipif from widget helper test class** — renamed `TestStockSearchWidget` → `TestFormatStockOption`, tests now import `format_stock_option` from the service module | Same root cause as #5 — tests were importing from a Streamlit-dependent module. Now they import from `backend.services.stock_search` which only depends on SQLAlchemy (available in CI). | All 6 format tests now run in every CI build instead of being silently skipped. A future refactor could break the formatting logic and it would pass CI undetected. |

---

### Session 14 — 2026-03-19: Workflow Improvements

#### Summary
Rewrote `WORKFLOW.md` to use a checkpoint-based session flow designed for crash resilience on an 8 GB Mac. Added a crash recovery mechanism to `docs/PROGRESS.md` and documented the OOM pitfall.

#### What We Did
1. ✅ **Rewrote `WORKFLOW.md` with checkpoint-based session flow (Steps 0–10)**
   - 3 explicit commit checkpoints: after code (Step 3), after progress update (Step 4), after CI fixes (Step 6)
   - Each checkpoint saves progress locally so Copilot Chat crashes don't lose work
   - Added Docker management guideline: stop Docker during code-only sessions to free ~2-3 GB RAM
   - Added activity table (when Docker is needed vs. not)
2. ✅ **Added crash recovery mechanism to `docs/PROGRESS.md`**
   - New "🔴 Current Session Status" block at the top — always reflects in-progress work
   - Dedicated crash recovery prompt in WORKFLOW.md §3 reads this block to resume
3. ✅ **Updated resume prompts in WORKFLOW.md §6**
   - Normal session prompt now includes `docs/PROGRESS.md`
   - Added separate crash recovery prompt
4. ✅ **Added OOM pitfall (#16) to Common Pitfalls**
   - Documents 8 GB Mac memory pressure issue and mitigations
5. ✅ **Renumbered upcoming sessions in PROGRESS.md**
   - Session 14 = Workflow Improvements (this session)
   - Session 15 = Trading Journal Backend, 16 = Trading Journal PDF Report, 17 = Watchlist Backend, 18 = Watchlist UI, 19 = Dashboard Polish, 20 = Phase 3 Kickoff

#### Architecture Decision
- **Checkpoint-based workflow over single-commit-at-end** — on an 8 GB Mac running VS Code + Docker + Copilot Chat, OOM crashes are common during long sessions. The old workflow committed everything at the end, meaning a crash lost the entire session. The new flow commits after code (Step 3), progress (Step 4), and CI (Step 6), ensuring at most one step of work is lost.
- **PROGRESS.md as crash recovery file** — rather than relying on chat history (lost on crash), the "Current Session Status" block serves as a persistent checkpoint. Any new chat session reads it and resumes exactly.
- **Docker stop/start over mem_limit** — capping Docker memory could degrade dashboard performance with 58M+ OHLCV rows. Instead, stop Docker during code sessions (`docker compose stop`) and restart for dashboard/DB work.

#### Lessons Learned
- VS Code Copilot Chat runs in Electron (Chromium). On 8 GB Mac with Docker, OOM crashes are inevitable during long sessions.
- The fix isn't more RAM — it's resilient workflow design. Frequent commits + progress checkpoints make crashes recoverable.
- `docker compose stop` preserves container state while freeing RAM. `docker compose up -d` restarts instantly.
- Copilot "Ask" mode can describe changes but cannot execute tools (file edits, terminal commands). Always use "Agent" mode for implementation sessions.

#### Files Changed
- `WORKFLOW.md` — complete rewrite: Steps 0–10, crash recovery §3, Docker management, OOM pitfall #16, resume prompts §6
- `docs/PROGRESS.md` — added "Current Session Status" crash recovery block, renumbered sessions 14–18, added Session 14 to history
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all changes

#### Test Count: 215 (unchanged — documentation-only session)

#### PR Review Fixes (PR #13 — 8 comments across 2 review rounds)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 1 | **Added note that `wip:` commits are local-only and get squash-merged** into a Conventional Commit when the PR merges | `wip:` prefixed checkpoint commits conflict with the Conventional Commits format in `CONTRIBUTING.md`. Without clarification, future sessions might think the convention was changed. | Confusion about commit message standards. Contributors might push `wip:` commits directly to main or skip squash-merging. |
| 2 | **Added explicit `git add` + `git commit` commands for PROGRESS.md update in Step 6** | Step 6 only showed a conditional `wip: CI fixes` commit but mentioned updating PROGRESS.md without commands. Easy to forget the PROGRESS commit. | PROGRESS.md would not be committed after CI passes, defeating the crash recovery mechanism for the remaining steps. |
| 3 | **Changed Step 7 from "clear the Current Session Status block" to "set to PR opened / awaiting review"** | Clearing the crash recovery block before push/PR/review means if Copilot crashes during those steps, the next session has no recovery info. | Crash during push, PR creation, or review cycle would leave no breadcrumb in PROGRESS.md. Recovery would require manual git log inspection instead of just reading the file. |
| 4 | **Added note that `feat/workflow-improvements` should have been `docs/` prefix for docs-only sessions** | Branch is `feat/` but session is docs-only. Conflicts with `CONTRIBUTING.md` branch naming convention. Can't rename mid-PR, but documented for future reference. | Future docs-only sessions might copy this pattern and use `feat/` prefix, diluting branch type semantics. |
| 5 | **Restored missing Session 12 (Candlestick Charts) and Session 13 (Stock Search) entries in BUILD_LOG** | Session 11's PR review fixes block had grown to include items from Sessions 12 and 13, and Session 12's header was never written. Session 13's header was lost. | BUILD_LOG is the canonical chronological record. Missing sessions would make it impossible to trace what happened in Sessions 12-13, breaking the audit trail. |
| 6 | **Updated PROGRESS.md crash recovery status to "PR opened, awaiting review"** | Status still said "Ready for push + PR" and checkpoint said "Step 7" even though the PR was already open at Step 9. Stale checkpoint misleads crash recovery. | A crash recovery session would try to push and create a PR that already exists, wasting time and causing `gh pr create` errors. |
| 7 | **Spelled out `docker compose up -d` in CHANGELOG** | Shorthand `up -d` without the full command is unclear when skimming the changelog. | Readers unfamiliar with Docker might not know what `up -d` means without the `docker compose` prefix. Minor clarity issue. |
| 8 | **Changed `"docs: session N documentation"` to `"docs: session <number> documentation"`** | Literal `N` placeholder could be copied verbatim into a real commit message. Angle-bracket style `<number>` matches the rest of the doc's placeholder convention. | Accidental `"docs: session N documentation"` commits on real branches — cosmetic but sloppy. |

---

### Session 15 — 2026-03-20: Trading Journal Roadmap (Docs-Only)

**Goal:** Plan and document the Trading Journal feature — finalize schema, update all docs, and reprioritize the session roadmap (Journal before Watchlist).

**Branch:** `docs/trading-journal-roadmap`

#### What Was Done

1. **Designed the Trading Journal schema** through iterative discussion:
   - `trades` table (18 columns): UUID PK, ticker, direction (long/short), asset_type (shares/options), trade_type (single_leg/multi_leg), timeframe (daily/weekly/monthly/quarterly), status (open/partial/closed — computed), entry_date, entry_price, total_quantity, remaining_quantity, stop_loss, take_profit, tags (JSONB), comments (TEXT), realized_pnl, created_at, updated_at
   - `trade_exits` table (6 columns): UUID PK, trade_id FK (CASCADE), exit_date, exit_price, quantity, comments — supports partial exits (scale-out strategy)
   - `trade_legs` table (7 columns): UUID PK, trade_id FK (CASCADE), leg_type (buy_call/sell_call/buy_put/sell_put), strike, expiry, quantity, premium — for multi-leg options trades
   - 5 ENUMs: `TradeDirection`, `AssetType`, `TradeType`, `Timeframe`, `LegType` (all `StrEnum` for Python 3.11+)
   - Relationships: cascade delete from Trade → exits/legs, `order_by=exit_date` on exits
   - 6 computed fields NOT stored: status, remaining_quantity, realized_pnl, return_pct, avg_exit_price, r_multiple

2. **Planned the PDF Trade Journal Report** (Session 17):
   - Summary page: total trades, win rate, total P&L, best/worst trade, breakdown by timeframe
   - Per-trade section: full details + annotated candlestick chart matching the trade's timeframe
   - Chart annotations: green entry arrow, red exit arrow(s), dashed stop/TP lines, volume subplot
   - Chart lookback by timeframe: daily=1yr, weekly=2yr, monthly=5yr, quarterly=10yr
   - Leverages existing Plotly chart builder (Session 12) and all 4 candle aggregates (Session 10)

3. **Updated roadmap** — inserted Trading Journal sessions (16–17) before Watchlist (18–19):
   - Session 15: Trading Journal Roadmap (this session, docs-only)
   - Session 16: Trading Journal Backend (model, service, API, migration, tests)
   - Session 17: Trading Journal PDF Report (report service, chart annotation, PDF export)
   - Session 18: Watchlist Backend (was Session 15)
   - Session 19: Watchlist UI (was Session 16)
   - Session 20: Dashboard Polish (was Session 17)
   - Session 21: Phase 3 Kickoff (was Session 18)

4. **Updated documentation:**
   - `DESIGN_DOC.md` — schema diagram updated with `trades`, `trade_exits`, `trade_legs` (replaced placeholder `trades` box); Phase 2 roadmap updated to include Journal + PDF report
   - `docs/ARCHITECTURE.md` — added full table schemas for all 3 journal tables with design decision notes; added planned API endpoints section (8 endpoints)
   - `WORKFLOW.md` — updated "Last Completed Session" (14), "Next Session" (16 — Journal Backend), added planned journal API endpoints to quick reference
   - `docs/PROGRESS.md` — updated Phase 2 checklist (added journal items), updated session roadmap (15–21), added Session 15 to history

#### Key Design Decisions
- **UUID primary keys** (not auto-increment) — safer for API exposure, no enumeration attacks
- **Status computed from exits** (not manually set) — prevents stale state; `open` if no exits, `partial` if some, `closed` if all exited
- **Tags as JSONB array** — fully flexible, no fixed taxonomy. Supports `@>` operator for filtering. Can formalize into structured taxonomy later.
- **Timeframe field** — records which chart interval informed the trade decision. PDF report matches the chart type to the timeframe (daily chart for daily trades, weekly chart for weekly trades, etc.)
- **Separate exits table** — enables partial exit tracking (scale-out). Each exit is an independent record with its own price, quantity, and optional comment.
- **Separate legs table** — multi-leg options strategies (spreads, iron condors, straddles) need per-leg tracking with strike, expiry, premium.
- **Comments on both trades and exits** — trade-level comments for overall reasoning; exit-level comments for explaining specific exit decisions.

#### Lessons Learned
- Prioritizing the Trading Journal before Watchlist gives immediate value: you can start journaling manual trades while building the rest of the platform.
- The journal becomes the foundation for auto-trade logging later — when the analysis engine generates signals, they can auto-create journal entries with strategy context.
- Designing the schema through iterative discussion (5+ rounds) caught requirements that wouldn't surface in a single pass: timeframe field, exit-level comments, multi-leg support, PDF report with annotated charts.

#### Files Changed
- `DESIGN_DOC.md` — schema diagram (trades/exits/legs), Phase 2 roadmap, Phase 2 deliverable
- `WORKFLOW.md` — last completed session, next session, planned API endpoints
- `docs/ARCHITECTURE.md` — 3 new table schemas with design notes, planned API endpoints
- `docs/PROGRESS.md` — Phase 2 checklist, session roadmap (15–21), crash recovery block, session history
- `docs/BUILD_LOG.md` — this entry
- `docs/CHANGELOG.md` — documented all changes

#### Test Count: 215 (unchanged — documentation-only session)

#### PR Review Fixes (PR #15 — 6 comments from Copilot code review)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 1 | **Aligned DESIGN_DOC schema diagram naming with ARCHITECTURE.md** — `remaining_qty` → `remaining_quantity`, `single/multi` → `single_leg/multi_leg`, `D/W/M/Q` → `daily/weekly/monthly/quarterly` | Schema diagram used abbreviations/shorthand that didn't match the canonical schema in ARCHITECTURE.md. Would cause confusion when implementing models in Session 16. | Developers could implement the wrong field names or enum values, requiring a schema migration fix later. |
| 2 | **BUILD_LOG.md truncation** — already fixed in prior commit (verified table properly closed, Sessions 14/15 present) | The initial PR diff appeared to truncate the BUILD_LOG, but the subsequent `fix: restore Session 14 entry` commit had already corrected this. No further changes needed. | N/A — already resolved. |
| 3 | **Moved Trading Journal endpoints to dedicated subsection in WORKFLOW.md** — separated from the main API table with a `#### Trading Journal (Session 16 — planned)` header and its own table | Blank separator rows and section headers inside a markdown table render inconsistently and are harder to read. Separate subsection is cleaner. | Markdown table would render broken in some viewers. Planned vs. implemented endpoints would be visually confusing. |
| 4 | **Clarified computed vs stored fields in ARCHITECTURE.md** — removed `status`, `remaining_quantity`, `realized_pnl` from the stored columns table; added a dedicated "Computed fields" section with derivation formulas for all 6 computed properties | Schema table listed computed fields alongside stored columns with only a "(computed)" annotation. Unclear whether they were DB columns with triggers/materialized views or API-level computed properties. | Session 16 implementation could incorrectly create DB columns for computed fields, adding unnecessary complexity (triggers, sync issues). |
| 5 | **Reworded UUID rationale in ARCHITECTURE.md** — changed from "no enumeration attacks" to "less predictable than sequential IDs" with explicit note that auth/authz is still required | Original wording implied UUIDs prevent enumeration attacks, which is misleading — they reduce predictability but don't replace authentication/authorization. | False sense of security. Developers might skip proper authorization checks thinking UUIDs are sufficient protection. |
| 6 | **Updated watchlist schema in DESIGN_DOC diagram** — replaced `tickers (array)` with `watchlists` + `watchlist_items` two-table design | Diagram showed a single `watchlists` table with `tickers (array)`, but the roadmap describes a normalized `watchlists` + `watchlist_items` approach. Conflicting guidance. | Session 18 implementation would need to choose between two contradictory designs, potentially requiring rework. |

---

### Session 16 — 2026-03-22: Trading Journal Backend (Phase 2)

**Goal:** Implement the full Trading Journal backend — models, service layer, API endpoints, Alembic migration support, and comprehensive tests.

**Branch:** `feat/trading-journal-backend`

#### What Was Done

1. **Implemented Trading Journal models** (`backend/models/journal.py`):
   - `Trade` — parent trade record (18 columns): UUID PK, ticker, direction (long/short), asset_type (shares/options), trade_type (single_leg/multi_leg), timeframe (daily/weekly/monthly/quarterly), entry_date, entry_price, total_quantity, stop_loss, take_profit, tags (JSONB), comments (TEXT), created_at, updated_at
   - `TradeExit` — partial/full exit fills (7 columns): UUID PK, trade_id FK (CASCADE), exit_date, exit_price, quantity, comments
   - `TradeLeg` — multi-leg option trades (8 columns): UUID PK, trade_id FK (CASCADE), leg_type (buy_call/sell_call/buy_put/sell_put), strike, expiry, quantity, premium
   - 5 ENUMs: `TradeDirection`, `AssetType`, `TradeType`, `Timeframe`, `LegType` (all `StrEnum` for Python 3.11+)
   - Relationships: cascade delete from Trade → exits/legs, `order_by=exit_date` on exits
   - 6 computed fields NOT stored: status, remaining_quantity, realized_pnl, return_pct, avg_exit_price, r_multiple

2. **Implemented journal service layer** (`backend/services/journal_service.py`):
   - `compute_trade_metrics()` — derives all 6 computed fields from trade + exits data
   - `serialize_trade()` — converts ORM objects to API-ready dicts with computed fields
   - `create_trade()` — creates trade with uppercase ticker, Decimal precision
   - `get_trade()` — fetch by UUID with eager-loaded exits/legs
   - `list_trades()` — filter by ticker, direction, timeframe, tags (JSONB `@>`), date range, with post-fetch status filtering and pagination
   - `update_trade()` — update mutable fields only (stop_loss, take_profit, tags, comments, timeframe)
   - `delete_trade()` — cascade delete via SQLAlchemy
   - `add_exit()` — validates quantity doesn't exceed remaining, returns updated trade
   - `add_leg()` — adds option leg, returns updated trade

3. **Implemented journal API routes** (`backend/api/routes/journal.py`):
   - `GET /api/v1/journal/` — list trades with filters (ticker, status, direction, timeframe, tags, date range, limit, offset)
   - `POST /api/v1/journal/` — create trade (201 response)
   - `GET /api/v1/journal/{trade_id}` — get trade with exits/legs
   - `PUT /api/v1/journal/{trade_id}` — update mutable fields
   - `DELETE /api/v1/journal/{trade_id}` — delete trade (204 response)
   - `POST /api/v1/journal/{trade_id}/exits` — add exit fill (400 if quantity exceeds remaining)
   - `POST /api/v1/journal/{trade_id}/legs` — add option leg
   - 5 Pydantic request schemas with validation: regex patterns for enums, `gt=0` for prices/quantities

4. **Registered journal router** in `backend/main.py` — follows existing router pattern

5. **Updated Alembic migration support** (`data/migrations/env.py`):
   - Added imports for `Trade`, `TradeExit`, `TradeLeg` so autogenerate picks up new tables
   - Migration script to be generated when DB is available (`alembic revision --autogenerate`)

6. **Updated model exports** (`backend/models/__init__.py`, `backend/models/trade.py`):
   - `__init__.py` exports `Trade`, `TradeExit`, `TradeLeg`
   - `trade.py` re-exports from `journal.py` for backwards compatibility

7. **Wrote 53 new tests** (`backend/tests/test_journal.py`):
   - ENUM tests (values, from_string, invalid raises) — 10 tests
   - Model table name tests — 3 tests
   - `compute_trade_metrics` tests (open, partial, closed, short PnL, R-multiple, edge cases) — 12 tests
   - Serialization tests (serialize_trade, _serialize_exit, _serialize_leg) — 7 tests
   - CRUD service tests with mocked AsyncSession — 11 tests
   - Pydantic schema validation tests — 7 tests
   - Router registration tests — 2 tests
   - All tests use mocked DB (no real Postgres needed in CI)

#### Key Design Decisions
- **Computed fields at service layer** — status, remaining_quantity, realized_pnl, return_pct, avg_exit_price, r_multiple are calculated from exits at read time, not stored. Prevents stale state.
- **StrEnum (Python 3.11+)** — ENUMs inherit from `enum.StrEnum` instead of `str, enum.Enum` per ruff UP042 rule
- **Decimal precision** — all monetary values use `Decimal(str(value))` to avoid floating point errors
- **JSONB tags with @> operator** — filter by tags uses PostgreSQL's `@>` containment operator for "all tags must match" semantics
- **Status filtering post-fetch** — since status is computed (not a DB column), we fetch all matching trades then filter in Python. Acceptable because journal queries are small-scale (personal trades, not millions of records)
- **Quantity validation on exits** — `add_exit()` raises `ValueError` if exit quantity exceeds remaining, preventing over-exit

#### Lessons Learned
- **mypy + SQLAlchemy Mapped columns:** Assigning `Decimal` to `Mapped[float | None]` triggers mypy `[assignment]` errors. Using `# type: ignore[assignment]` is the pragmatic fix since SQLAlchemy handles the conversion at runtime.
- **ruff B010 vs mypy:** `setattr(obj, "field", val)` fixes mypy but violates ruff B010 ("don't call setattr with constant"). Direct assignment with `# type: ignore` is the cleanest solution.
- **AsyncMock and sync methods:** `AsyncMock` wraps ALL methods as coroutines, including sync ones like `db.add()`. Fix: `mock_db.add = MagicMock()` to prevent "coroutine never awaited" warnings.
- **FastAPI router paths include prefix:** Route paths in `router.routes` include the prefix (e.g., `/journal/` not `/`), which affects test assertions.

#### Files Changed
- `backend/models/journal.py` — full Trade, TradeExit, TradeLeg models with ENUMs (replaced stub)
- `backend/models/__init__.py` — added journal model exports
- `backend/models/trade.py` — re-exports from journal.py for backwards compatibility
- `backend/services/journal_service.py` — new file, full CRUD + computed fields + serialization
- `backend/api/routes/journal.py` — full CRUD endpoints with Pydantic schemas (replaced stub)
- `backend/main.py` — registered journal router
- `data/migrations/env.py` — added journal model imports for Alembic
- `backend/tests/test_journal.py` — 53 new tests (replaced stub)

#### PR Review Fixes (PR #16 — 5 comments from Copilot code review)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 1 | **Fixed `server_default` for `trade_type`** — changed from bare `"single_leg"` to `text("'single_leg'")` in `journal.py` | SQLAlchemy treats a bare string as raw SQL text. `DEFAULT single_leg` (unquoted) is an invalid SQL identifier, not a string literal. Using `text("'single_leg'")` produces the correct `DEFAULT 'single_leg'`. | Alembic migration or `CREATE TABLE` would fail with a SQL syntax error, or worse, silently use a wrong default if a `single_leg` identifier existed. |
| 2 | **Fixed Date/DateTime type annotations** — changed `Mapped[str]` to `Mapped[date]` / `Mapped[datetime]` for `entry_date`, `exit_date`, `expiry`, `created_at`, `updated_at` in `journal.py` | Columns use `Date` and `DateTime(timezone=True)` SQL types, which map to Python `date`/`datetime`, not `str`. The `Mapped[str]` annotations mislead mypy and callers. | Type-checking would not catch bugs where code passes a string where a date is expected. IDE autocompletion would suggest string methods instead of date methods. |
| 3 | **Refactored `compute_trade_metrics()` to use Decimal end-to-end** — all quantity/price/PnL calculations now use `Decimal(str(value))` throughout, converting to `float` only at the final return | The original implementation converted everything to `float` immediately, undermining the stated "Decimal precision" goal. Float arithmetic can cause `remaining_qty` to become slightly negative (e.g., `-0.0000000001`), incorrectly flipping status to `closed`. | Rounding drift could cause a trade with 100 shares and two 50-share exits to show `remaining_quantity: -0.0001` and status `closed` with a negative remaining — or worse, `partial` when it should be `closed`. Added tolerance clamping as a safety net. |
| 4 | **Fixed `update_trade()` to support clearing nullable fields** — changed filter from `v is not None` to allow `None` for `stop_loss`, `take_profit`, `tags`, `comments` (nullable fields) | The route uses `model_dump(exclude_unset=True)`, so an explicit `null` in the request is a meaningful update (user wants to remove their stop loss). The old filter silently dropped these, making it impossible to clear a field. | Users could set a stop_loss but never remove it. The API would accept `{"stop_loss": null}` without error but silently ignore it — a subtle, hard-to-debug behavior mismatch. |
| 5 | **Fixed `add_exit()` to use Decimal-based remaining quantity validation** — replaced `metrics["remaining_quantity"]` (rounded float) with direct `Decimal(str(trade.total_quantity)) - sum(Decimal(str(e.quantity)))` | The old code validated against a rounded float from `compute_trade_metrics()`. Near rounding boundaries, this could reject a valid exact exit (e.g., 33.3333 remaining but rounded to 33.3333 vs request of 33.33330001) or allow a tiny over-exit. | Edge case: entering a trade of 100 shares, exiting 33.3333, 33.3333, and 33.3334 — the final exit could be rejected because the rounded remaining (33.3334) didn't exactly match. Using unrounded Decimal arithmetic eliminates this class of bugs entirely. |

#### CI Fix
- **9 tests failing** in CI due to `ModuleNotFoundError: No module named 'fastapi'` — `TestAPISchemas` (7 tests) and `TestRouterRegistration` (2 tests) import from `backend.api.routes.journal` which imports `fastapi`
- **Fix:** Added `@pytest.mark.skipif(not _has_fastapi, ...)` decorator on both test classes using `importlib.util.find_spec("fastapi")` — tests run locally with fastapi, skip gracefully in CI's lightweight test environment
- Follows the same pattern used in `test_calendar_integration.py` (celery skipif) and `test_candle_service.py` (plotly importorskip)

#### PR Review Fixes — Round 2 (PR #16 — 4 additional comments from Copilot code review)

| # | What Was Changed | Why | Impact If Not Fixed |
|---|-----------------|-----|---------------------|
| 6 | **SQL-level pagination in `list_trades()`** — when no `status` filter is provided, `offset()` and `limit()` are now applied at the SQL level; when `status` is requested, all rows are fetched and sliced in Python after filtering | The original code always fetched all matching rows and sliced in Python, even when status filtering wasn't needed. Unnecessary for the common no-filter case. | As the number of trades grows, every list call would fetch the entire table into memory, even for simple paginated requests. SQL-level pagination lets the DB do the heavy lifting. |
| 7 | **Dropped `selectinload(Trade.legs)` from `list_trades()`** — the function only needs exits for metric computation and calls `serialize_trade(..., include_children=False)`, so legs are never used | Eagerly loading legs adds an extra SQL subquery per list call for data that's immediately discarded. | Wasted DB round-trip and memory allocation. Minor now with few trades, but compounds with scale and adds latency to every list request. |
| 8 | **Added `gt=0` validation to `UpdateTradeRequest.stop_loss` and `take_profit`** — now uses `Field(default=None, gt=0)` matching `CreateTradeRequest` | The create schema validated `stop_loss > 0` and `take_profit > 0`, but the update schema accepted any value including negative/zero. Inconsistent validation. | Users could update a stop_loss to `-5.0` or `0`, which is nonsensical and could break R-multiple calculations (division by zero/negative risk). |
| 9 | **Typed `tags` as `Mapped[list[str] \| None]`** instead of `Mapped[list \| None]` in `journal.py` | The unparameterized `list` loses element type info. The API/service always treat tags as `list[str]`, but the model allowed any JSON array elements (ints, dicts, etc.) to slip through. | Mypy can't catch bugs where non-string values are appended to tags. A future `tags.contains("momentum")` call could silently fail if the list contained integers. Explicit typing prevents this. |

#### Test Count: 268 (53 new, up from 215)
---

### Session 17 — 2026-03-22: Post-Close "What-If" Tracking Design (Phase 2)

**Goal:** Design the post-close "what-if" feature — after a trade is closed, automatically track what would have happened if the position had been held longer. Docs-only session (no code changes).

**Branch:** `docs/post-close-what-if-design`

#### What Was Done

1. **Designed `trade_snapshots` table** (7 columns):
   - `id` (UUID PK), `trade_id` (FK → trades.id, CASCADE), `snapshot_date` (DATE), `close_price` (NUMERIC), `hypothetical_pnl` (NUMERIC), `hypothetical_pnl_pct` (NUMERIC), `created_at` (TIMESTAMPTZ)
   - UNIQUE constraint on `(trade_id, snapshot_date)` — prevents duplicates, enables safe upsert

2. **Defined snapshot schedule by trade timeframe:**
   - **Daily trades** → snapshot every trading day for 30 calendar days
   - **Weekly trades** → snapshot weekly for 16 calendar weeks
   - **Monthly trades** → snapshot monthly for 18 calendar months

3. **Planned Celery periodic task:**
   - Scans for closed trades with remaining snapshots to capture
   - Fetches closing price from `daily_ohlcv` (or weekly/monthly aggregates)
   - Computes direction-aware hypothetical PnL: long = `(close - entry) × qty`, short = `(entry - close) × qty`
   - Inserts snapshot row; stops when max duration reached or no price data available

4. **Planned 2 API endpoints:**
   - `GET /api/v1/journal/{trade_id}/snapshots` — list all post-close snapshots for a trade
   - `GET /api/v1/journal/{trade_id}/what-if` — summary: best/worst hypothetical PnL vs actual exit

5. **Design decisions documented:**
   - Full position assumed (no partial/hybrid scenarios)
   - Auto-generated only (no manual trigger needed)
   - Tracking stops at max duration or delisting
   - Unique constraint enables idempotent upsert

6. **Updated all documentation:**
   - `DESIGN_DOC.md` v1.3 — `trade_snapshots` in schema diagram, data volume estimates row, Phase 2 roadmap item
   - `docs/ARCHITECTURE.md` — full table schema with design decisions, 2 planned API endpoints, updated last-modified date
   - `WORKFLOW.md` — Last Completed = Session 17, Next = Session 18 (PDF Report), what-if endpoints in API quick reference
   - `docs/PROGRESS.md` — crash recovery block, component status, Phase 2 checklist (+what-if design ✅, +what-if implementation ☐), Session 17 in history, roadmap renumbered (17–23)
   - `docs/CHANGELOG.md` — 6 Added + 4 Changed entries under [Unreleased]
   - `docs/BUILD_LOG.md` — this entry

7. **Added Session 19 to roadmap** — "Post-Close What-If — Implementation" (model, service, Celery task, API, migration, tests). Renumbered Sessions 18–23 accordingly.

#### Key Design Decisions
- **Option A: Dedicated `trade_snapshots` table** (chosen over JSONB column or on-demand query) — cleanest schema, easy to query/aggregate, no document-size bloat, standard relational pattern
- **Full position assumed** — simplifies calculation; no partial exit hypotheticals. The what-if always assumes the entire original position was held.
- **Every trading day for daily trades** — 30 rows per trade is trivial storage; gives the richest hindsight data
- **Direction-aware PnL** — short trades profit when price drops, so the formula must account for trade direction
- **Max tracking duration by timeframe** — prevents indefinite snapshot accumulation for old trades

#### Lessons Learned
- BUILD_LOG.md edits are the #1 crash trigger on 8 GB Macs — always commit + push all other work before touching this file
- Docs-only design sessions (like Session 15 and this one) are valuable for catching requirements before writing code — the iterative discussion surfaced snapshot intervals, max durations, and the "full position" simplification
- Crash recovery checkpoint in PROGRESS.md must accurately reflect what is done vs. pending — marking "docs complete" when BUILD_LOG was not yet written would mislead a recovery session
- The `insert_edit_into_file` tool is unreliable for large files — it corrupted BUILD_LOG.md (deleted 328 lines). Use `cat >> file` via terminal for safe appends to large files.

#### Files Changed
- `DESIGN_DOC.md` — v1.3: schema diagram (trade_snapshots), data volume estimates, Phase 2 roadmap
- `WORKFLOW.md` — last completed session (17), next session (18), what-if API endpoints
- `docs/ARCHITECTURE.md` — trade_snapshots table schema + design decisions, 2 planned API endpoints
- `docs/PROGRESS.md` — crash recovery block, component status, Phase 2 checklist, session history, roadmap (renumbered 17–23)
- `docs/CHANGELOG.md` — 6 Added + 4 Changed entries
- `docs/BUILD_LOG.md` — this entry

#### Test Count: 268 (unchanged — documentation-only session)
