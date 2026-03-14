# 📋 PraxiAlpha — Changelog

> All notable changes to this project will be documented in this file.
> Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

### Added
- **Macro backfill** (`--macro` flag) — backfills all 14 FRED macro indicator series (81,474 records) with upsert support
- **`T10YIE` (10-Year Breakeven Inflation Rate)** — replaces discontinued `GOLDAMGBD228NLBM` (Gold Price) in the FRED series registry
- **Macro backfill tests** (`test_backfill_macro.py`) — unit tests for backfill logic (fetcher calls, empty series handling, error recovery, null filtering, fetcher cleanup)
- **FRED registry tests** (`test_data_pipeline.py`) — series count, required fields, valid categories, expected IDs, discontinued series guard
- **Extended macro validation tests** — sort order, null preservation, negative values, dedup behavior, index reset
- **`CONTRIBUTING.md`** — commit message convention (Conventional Commits), branch naming, git workflow, PR checklist, documentation checklist
- **Branch workflow** — all future work uses feature branches + PRs (no more direct commits to `main`)
- **CI on feature branches** — GitHub Actions now triggers on pushes to `feat/**` and `fix/**` branches (not just `main`), catching failures before PRs
- **Local CI script** (`scripts/ci_check.sh`) — runs ruff lint, ruff format, and mypy locally before pushing; supports `--fix` mode for auto-repair
- **Git pre-push hook** — automatically runs `ci_check.sh` before every `git push`, blocking pushes that would fail CI

### Fixed
- **Mypy type errors** — fixed 3 `[no-any-return]` errors in `eodhd_fetcher.py` and `fred_fetcher.py` by adding explicit type annotations for `response.json()` return values
- **Discontinued FRED series** — removed `GOLDAMGBD228NLBM` (Gold Price, no longer available on FRED) from the macro series registry
- **Ruff lint failures** — removed unused imports (`MagicMock`, `AsyncMock`, `patch`) from test files; added `N806` ignore for test files in `pyproject.toml` (PascalCase mock variables are conventional)
- **CI "tests" job hanging** — `pip install -e ".[dev]"` installed heavy packages (streamlit, celery, plotly, jupyter) that took forever to build; replaced with a lightweight explicit install of only the packages needed by tests; added pip caching

### Changed
- **FRED series registry** — replaced Gold Price (`GOLDAMGBD228NLBM`) with 10-Year Breakeven Inflation Rate (`T10YIE`) for better macro coverage
- **CI test install** — split `[dev]` optional dependencies into `[test]` (lightweight) + `[dev]` (full); CI uses explicit lightweight install to avoid building unused heavy packages
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
