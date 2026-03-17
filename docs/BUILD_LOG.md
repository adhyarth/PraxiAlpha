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
   - **Smart ticker filtering** — only `Common Stock` + `ETF` asset types (skips warrants, preferred shares, units, OTC junk). Filters from 49K → ~10K tickers
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
