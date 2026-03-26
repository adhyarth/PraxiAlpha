# 📊 PraxiAlpha — Project Progress

> **Purpose:** Full project status, phase checklists, session history, and upcoming roadmap.
> This is the reference for "where are we overall?" — not day-to-day workflow.
>
> For the session workflow and what to do next, see [`WORKFLOW.md`](../WORKFLOW.md).
>
> **Last updated:** 2026-03-25 (Session 28 — Split-Adjusted Charts)

---

## 🚨 Current Session Status (crash recovery checkpoint)

| | |
|-|-|
| **Session** | 28 — Split-Adjusted Charts |
| **Branch** | `fix/split-adjusted-charts` |
| **Status** | PR opened / awaiting review. |
| **Last checkpoint** | Code + all docs (incl. BUILD_LOG) committed and pushed. PR review in progress. |

> If Copilot crashed: read this block, run `git status` and `git log --oneline -5`, and resume from the step indicated above.

---

## 1. Component Status

| Component | Status | Details |
|-----------|--------|---------|
| **Database** | ✅ Running | PostgreSQL 16 + TimescaleDB via Docker |
| **Tables** | ✅ Populated | `stocks` (49K), `daily_ohlcv` (58.2M), `macro_data` (81K), `stock_splits` (18.4K), `stock_dividends` (634K), `economic_calendar_events` |
| **Candle Aggregates** | ✅ Populated | `weekly_ohlcv` (13.5M), `monthly_ohlcv` (3.4M), `quarterly_ohlcv` (1.2M) — TimescaleDB continuous aggregates with auto-refresh |
| **Data Pipeline** | ✅ Working | EODHD fetcher (OHLCV, splits, dividends), FRED fetcher (14 macro series), TradingEconomics fetcher (economic calendar) |
| **Backfill** | ✅ Done | `scripts/backfill_full.py` — 23,714 tickers backfilled (1990–2026), 58.2M OHLCV records, 18.4K splits, 634K dividends |
| **Daily Tasks** | ✅ Working | Celery Beat — daily OHLCV with **smart gap-fill** (auto-detects and fills all missing days) → candle aggregate refresh, daily macro (7-day incremental), daily calendar |
| **API** | ✅ Working | FastAPI — `/health`, `/api/v1/stocks/`, `/api/v1/calendar/`, `/api/v1/charts/`, `/api/v1/journal/`, `/api/v1/journal/report` |
| **Scheduler** | ✅ Working | Celery Beat — daily OHLCV (7 PM ET) → candle aggregate refresh (chained), daily macro (7:10 PM ET), daily trade snapshots (7:20 PM ET), daily economic calendar (7 AM ET) |
| **Analysis** | ✅ Working | Technical indicators: SMA, EMA, RSI, MACD, Bollinger Bands (pure pandas, no DB dependency) |
| **Charting** | ✅ Working | Plotly candlestick charts with volume subplot, indicator overlays (SMA, EMA, RSI, MACD, Bollinger), and **split-adjusted prices** (smooth continuous charts, no discontinuities at split boundaries) |
| **Stock Search** | ✅ Working | Typeahead search by ticker prefix + company name substring, ranked results, API + Streamlit widget |
| **Trading Journal** | ✅ Working | 3 models (Trade, TradeExit, TradeLeg) + TradeSnapshot, CRUD service with computed fields, 7 API endpoints + 2 snapshot endpoints + 1 report endpoint, Streamlit UI (trade list, entry form, detail view, PDF download, what-if display), 64 tests. User isolation implemented. Post-close "what-if" tracking implemented (equity only — options trades excluded). |
| **Dashboard** | ✅ Basic | Streamlit — economic calendar widget + interactive candlestick chart page with stock search + trading journal page |
| **CI/CD** | ✅ Green | GitHub Actions — ruff lint, ruff format, mypy, pytest (446 tests) |
| **Tests** | ✅ 446 passing | Model, fetcher, service, API, task, widget, helpers, backfill, candle service, technical indicators, chart builder, stock search, trading journal, user isolation, trade snapshots, journal PDF report, journal UI, OHLCV gap-fill, split adjustment |
| **Docs** | ✅ Current | DESIGN_DOC, ARCHITECTURE, BUILD_LOG, CHANGELOG, CONTRIBUTING, WORKFLOW, PROGRESS |

---

## 2. Phase Checklists

### Phase 1: Foundation (Weeks 1–4) — ✅ Complete
- [x] Project scaffolding (125 files), Docker stack, DB setup, 49K tickers
- [x] Test backfill (10 stocks, 68K OHLCV), splits & dividends, batch insert fix
- [x] CI/CD pipeline (GitHub Actions), code quality (ruff, mypy), CONTRIBUTING.md
- [x] Macro backfill (14 FRED series, 81K records), local CI tooling, pre-push hook
- [x] Economic calendar full stack (model, fetcher, service, API, Celery, Streamlit)
- [x] Full backfill (58.2M OHLCV records, 23,714 tickers, 1990–2026)
- [x] Weekly/monthly/quarterly candle aggregates (TimescaleDB continuous aggregates)

### Phase 2: Charting & Basic Dashboard (Weeks 5–8) — 🟡 In Progress
- [x] Technical indicator overlays (RSI, MACD, MAs, Bollinger Bands) — Session 11
- [x] Interactive candlestick charts (Plotly) — Session 12
- [x] Volume subplot — Session 12
- [x] Daily/weekly/monthly chart toggle — Session 12
- [x] ~~Economic calendar widget~~ ✅ Pulled into Phase 1
- [x] Stock search functionality — Session 13
- [x] Trading Journal — backend (model, service, API, migration, tests) — Session 16
- [x] Trading Journal — post-close "what-if" design (trade_snapshots schema, Celery task plan, API endpoints) — Session 17
- [x] Trading Journal — user isolation design (user_id column, PRAXIALPHA_USER_ID env var, query filtering) — Session 18
- [x] Trading Journal — user isolation implementation (model, config, service, migration, tests) — Session 19
- [x] Trading Journal — post-close "what-if" implementation (model, service, Celery task, API, tests) — Session 20
- [x] Trading Journal — PDF report generator (annotated charts, PDF export) — Session 22
- [x] Trading Journal — Streamlit UI (trade list, entry form, detail view, PDF download, what-if display) — Session 23
- [x] Split-adjusted chart prices (smooth continuous charts, toggle adjusted/raw) — Session 28
- [ ] Watchlist management backend
- [ ] Watchlist management UI
- [ ] Dashboard polish (wire everything together, final QA)

### Phase 3: Analysis Engine — ⬜ Not Started
> See `DESIGN_DOC.md` § "Phase Roadmap" for the full 9-phase plan.

---

## 3. Session History

| Session | Date | What Was Done | PR |
|---------|------|---------------|----|
| 1 | 2026-03-13 | Project scaffolding (125 files), Docker stack, DB setup, 49K tickers | Direct to main |
| 2 | 2026-03-13 | Test backfill (10 stocks, 68K OHLCV), splits & dividends, batch insert fix | Direct to main |
| 3 | 2026-03-13 | CI/CD pipeline (GitHub Actions), code quality (ruff, mypy), CONTRIBUTING.md | Direct to main |
| 4 | 2026-03-13 | Macro backfill (14 FRED series, 81K records), local CI tooling, pre-push hook | PR #1 |
| 5 | 2026-03-14 | Economic calendar full stack (model, fetcher, service, API, Celery, Streamlit, 32 tests) | PR #3 |
| 6 | 2026-03-15 | Copilot code review fixes (9 items: asyncio, datetime parsing, bulk upsert, validation) | PR #3 |
| 7 | 2026-03-16 | Session workflow document (WORKFLOW.md) | PR #5 |
| 8 | 2026-03-16 | Production backfill script, daily OHLCV/macro Celery tasks, 33 new tests (95 total) | PR #6 |
| 9 | 2026-03-17 | Full backfill run (58.2M records), DB crash fixes, resume bug fix, batch size & retry hardening | PR #6 |
| 10 | 2026-03-17 | Weekly/monthly/quarterly candle aggregates, charts API, candle service, Celery refresh task, 22 new tests (117 total) | PR #7 |
| 11 | 2026-03-17 | Technical indicators service (SMA, EMA, RSI, MACD, Bollinger Bands), 52 new tests (171 total) | PR #8 |
| 12 | 2026-03-17 | Candlestick chart component (Plotly), charts page, volume subplot, indicator overlays, 25 new tests (196 total) | PR #9 |
| 13 | 2026-03-17 | Stock search service (ticker prefix + name substring), API endpoint, Streamlit widget, charts page integration, 19 new tests (215 total) | PR #12 |
| 14 | 2026-03-19 | Workflow improvements: checkpoint-based session flow, crash recovery in PROGRESS.md, Docker RAM management, OOM pitfall | PR #13 |
| 15 | 2026-03-20 | Trading Journal roadmap: schema design (trades, exits, legs), PDF report plan, session reorder (Journal before Watchlist), docs updates | PR #15 |
| 16 | 2026-03-22 | Trading Journal backend: 3 models (Trade, TradeExit, TradeLeg), CRUD service with computed fields, 7 API endpoints, Alembic migration support, 53 new tests (268 total) | PR #16 |
| 17 | 2026-03-22 | Post-close "what-if" design: trade_snapshots table schema, Celery task plan, API endpoints, max tracking durations by timeframe. Docs-only session. | PR #17 |
| 18 | 2026-03-22 | User isolation design: lightweight user_id column + PRAXIALPHA_USER_ID env var for per-user trade privacy. Evaluated 3 options (full auth, env-var user_id, separate DB), chose Option B. Docs-only session. | PR #18 |
| 19 | 2026-03-22 | User isolation implementation: user_id column on trades, config setting, all journal queries scoped, Alembic migration 002, 11 new tests (279 total). WORKFLOW.md Step 7 overhaul. | PR #19 |
| 20 | 2026-03-22 | Post-close "what-if" implementation: TradeSnapshot model, snapshot service (PnL calc, what-if summary), Celery periodic task, 2 API endpoints, Alembic migration 003, 45 tests (331 total). PR review: fixed OHLCV query join, per-trade rollback, Celery retry, US/Eastern timezone, snapshot cadence, batch existence check. | PR #20 |
| 21 | 2026-03-23 | Journal UI Roadmap Reorder: inserted Journal Streamlit UI as Session 23, renumbered Sessions 22–27, updated Phase 2 checklists in DESIGN_DOC and PROGRESS. Docs-only session. | PR #21 |
| 22 | 2026-03-23 | Trading Journal PDF Report: report service (annotated Plotly charts, PDF export via fpdf2), API endpoint `GET /api/v1/journal/report`, 36 new tests (367 total). Added fpdf2 + kaleido deps. | PR #22 |
| 23 | 2026-03-23 | Trading Journal Streamlit UI: journal page (trade list with filters/PnL, entry form, detail view with exits/legs/what-if/edit/delete), PDF report download, API client module, 3 reusable components, 55 new tests (422 total). | PR #24 |
| — | 2026-03-23 | Bugfix: MissingGreenlet in `create_trade` (selectinload re-fetch) and `list_trades` (conditional legs eager-load for PDF report). 3 tests updated with re-fetch assertions. | PR #25 |
| 25 | 2026-03-23 | Smart OHLCV gap-fill: rewrote `daily_ohlcv_update` with gap-detection loop, extracted helpers, added `ohlcv_max_gap_days` config, 12 new tests (434 total). | PR #27 |
| 26 | 2026-03-23 | Skip options what-if: excluded options trades from snapshot generation and what-if summary (no live options pricing data), Streamlit UI reason message, 3 new tests (437 total). | PR #28 |
| 27 | 2026-03-23 | Celery task bug fixes: engine.dispose() in all async tasks, timestamp cast fix in candle aggregate refresh, worker queue routing fix (`-Q celery,data_pipeline`), beat schedule staggered to 7 PM ET window. | PR #29 |
| 28 | 2026-03-25 | Split-adjusted chart prices: candle service applies `adjusted_close / close` ratio to OHLCV at query time, `adjusted` API param, Streamlit sidebar toggle, 9 new tests (446 total). | PR #31 |

> **Detailed session notes:** See [`BUILD_LOG.md`](./BUILD_LOG.md) for the full chronological record.

---

## 4. Upcoming Sessions Roadmap

Each session is self-contained: one branch, one PR, one merge. Work top-to-bottom.

| # | Session | Scope | Key Files to Create/Modify | Depends On |
|---|---------|-------|---------------------------|------------|
| **13** | **Stock Search** | ✅ Done — typeahead search component, API endpoint, Streamlit widget, charts page integration, 19 tests. | `backend/services/stock_search.py`, `backend/api/routes/stocks.py`, `streamlit_app/components/stock_search.py`, `backend/tests/test_stock_search.py` | Session 12 ✅ |
| **14** | **Workflow Improvements** | ✅ Done — checkpoint-based workflow, crash recovery in PROGRESS.md, Docker RAM management, OOM pitfall. | `WORKFLOW.md`, `docs/PROGRESS.md`, `docs/BUILD_LOG.md`, `docs/CHANGELOG.md` | — |
| **15** | **Trading Journal Roadmap** | ✅ Done — docs-only session to plan and document the Trading Journal feature (schema, sessions, roadmap updates). | `docs/PROGRESS.md`, `WORKFLOW.md`, `DESIGN_DOC.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_LOG.md`, `docs/CHANGELOG.md` | — |
| **16** | **Trading Journal — Backend** | ✅ Done — 3 models, CRUD service with computed fields, 7 API endpoints, Alembic migration support, 53 new tests (268 total). | `backend/models/journal.py`, `backend/services/journal_service.py`, `backend/api/routes/journal.py`, `backend/tests/test_journal.py`, `data/migrations/env.py` | Session 15 ✅ |
| **17** | **Post-Close "What-If" Design** | ✅ Done — docs-only session: designed `trade_snapshots` table, Celery task, snapshot schedule (daily/weekly/monthly by timeframe), API endpoints (`/snapshots`, `/what-if`). | `DESIGN_DOC.md`, `docs/ARCHITECTURE.md`, `WORKFLOW.md`, `docs/PROGRESS.md`, `docs/BUILD_LOG.md`, `docs/CHANGELOG.md` | Session 16 ✅ |
| **18** | **User Isolation Design** | ✅ Done — docs-only session: designed user_id column + PRAXIALPHA_USER_ID env var, evaluated 3 options, chose Option B. | `DESIGN_DOC.md`, `docs/ARCHITECTURE.md`, `WORKFLOW.md`, `docs/PROGRESS.md`, `docs/CHANGELOG.md` | Session 16 ✅ |
| **19** | **User Isolation Implementation** | ✅ Done — user_id column on trades, config setting, journal queries scoped, Alembic migration 002, 11 new tests (279 total). WORKFLOW.md Step 7 overhaul. | `backend/config.py`, `backend/models/journal.py`, `backend/services/journal_service.py`, `.env.example`, migration, tests | Session 18 ✅ |
| **20** | **Post-Close "What-If" — Implementation** | ✅ Done — TradeSnapshot model, snapshot service, Celery periodic task, 2 API endpoints, Alembic migration, 45 snapshot tests (331 total). PR review fixes: OHLCV query join, per-trade rollback, Celery retry, US/Eastern TZ, snapshot cadence, batch existence check. | `backend/models/trade_snapshot.py`, `backend/services/trade_snapshot_service.py`, `backend/tasks/trade_snapshot_task.py`, `backend/api/routes/journal.py`, `backend/tests/test_trade_snapshots.py`, Alembic migration | Session 17, 19 ✅ |
| **21** | **Journal UI Roadmap Reorder** | ✅ Done — docs-only session: inserted Journal Streamlit UI as Session 23, renumbered Sessions 22–27, updated Phase 2 checklists. | `DESIGN_DOC.md`, `WORKFLOW.md`, `docs/PROGRESS.md`, `docs/CHANGELOG.md`, `docs/BUILD_LOG.md` | — |
| **22** | **Trading Journal — PDF Report** | ✅ Done — Report service (annotated Plotly charts, PDF export via fpdf2), API endpoint `GET /api/v1/journal/report` with date/status/ticker filters, 36 new tests (367 total). Added fpdf2 + kaleido deps. | `backend/services/journal_report_service.py`, `backend/api/routes/journal.py` (report endpoint), `backend/tests/test_journal_report.py` | Session 16 ✅ |
| **23** | **Trading Journal — Streamlit UI** | ✅ Done — Journal page: trade list table (status, PnL, tags, filters), trade entry form (ticker, direction, qty, entry price, stop/TP), trade detail view (exits, legs, snapshots, what-if summary), PDF report download button, 55 new tests (422 total). | `streamlit_app/pages/journal.py`, `streamlit_app/components/journal_trade_form.py`, `streamlit_app/components/journal_trade_detail.py`, `streamlit_app/components/journal_api.py`, `streamlit_app/app.py` (nav update) | Session 22 ✅ |
| **25** | **Smart OHLCV Gap-Fill** | ✅ Done — Rewrote `daily_ohlcv_update` with gap-detection loop, extracted helpers, added `ohlcv_max_gap_days` config, 12 new tests (434 total). | `backend/tasks/data_tasks.py`, `backend/config.py`, `backend/tests/test_data_pipeline.py` | Session 8 ✅ |
| **26** | **Skip Options What-If** | ✅ Done — excluded options trades from snapshot generation, Streamlit UI reason message, 3 new tests (437 total). | `backend/services/trade_snapshot_service.py`, `backend/tasks/trade_snapshot_task.py`, `streamlit_app/components/journal_trade_detail.py`, `backend/tests/test_trade_snapshots.py` | Session 20 ✅ |
| **27** | **Celery Task Bug Fixes** | ✅ Done — engine.dispose() in all async tasks, timestamp cast fix, worker queue routing fix, beat schedule staggered to 7 PM ET. | `backend/tasks/data_tasks.py`, `backend/tasks/trade_snapshot_task.py`, `backend/tasks/celery_app.py`, `docker-compose.yml` | Session 8 ✅ |
| **28** | **Split-Adjusted Charts** | ✅ Done — candle service applies `adjusted_close / close` ratio to OHLCV at query time (daily only), `adjusted` API parameter, Streamlit sidebar toggle, 9 new tests (446 total). | `backend/services/candle_service.py`, `backend/api/routes/charts.py`, `streamlit_app/pages/charts.py`, `backend/tests/test_candle_service.py` | Session 12 ✅ |
| **29** | **Watchlist — Backend** | Watchlist model (`watchlists` + `watchlist_items` tables), CRUD service, API endpoints (`GET/POST/PUT/DELETE /api/v1/watchlists/`). Migration. Tests for model, service, API. | `backend/models/watchlist.py`, `backend/services/watchlist_service.py`, `backend/api/routes/watchlists.py`, `backend/tests/test_watchlist.py`, Alembic migration | Session 16 |
| **30** | **Watchlist — UI** | Streamlit watchlist page: create/rename/delete watchlists, add/remove tickers (uses search from Session 13), display watchlist with sparkline/change columns. | `streamlit_app/pages/watchlists.py`, `streamlit_app/components/watchlist_card.py` | Session 29 |
| **31** | **Dashboard Polish** | Wire everything together: dashboard home page shows watchlist summary cards, recent price changes, upcoming economic events, and a "Jump to Chart" link per ticker. Final Phase 2 QA pass. | `streamlit_app/pages/dashboard.py` (rewrite), `streamlit_app/app.py` (nav update) | Session 30 |
| **32** | **Phase 3 Kickoff — Trend Classification** | Begin Phase 3 (Analysis Engine). Implement trend classification algorithm (short/mid/long-term) using SMA crossovers and slope analysis. Service + tests. | `backend/services/analysis/trend_classifier.py`, `backend/tests/test_trend_classifier.py` | Session 31 |
