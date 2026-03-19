# 📊 PraxiAlpha — Project Progress

> **Purpose:** Full project status, phase checklists, session history, and upcoming roadmap.
> This is the reference for "where are we overall?" — not day-to-day workflow.
>
> For the session workflow and what to do next, see [`WORKFLOW.md`](../WORKFLOW.md).
>
> **Last updated:** 2026-03-19 (Session 14)

---

## 🔴 Current Session Status (crash recovery checkpoint)

| | |
|-|-|
| **Session** | 14 — Workflow Improvements |
| **Branch** | `feat/workflow-improvements` (note: docs-only sessions should use `docs/` prefix per CONTRIBUTING.md) |
| **Status** | ✅ WORKFLOW.md rewritten. ✅ PROGRESS.md crash recovery block added. ✅ CI passed (215/215). ✅ Docs updated (BUILD_LOG, CHANGELOG). PR #13 opened, awaiting review. |
| **Last checkpoint** | Step 9 — PR review cycle |

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
| **Daily Tasks** | ✅ Implemented | Celery Beat — daily OHLCV (bulk endpoint) → candle aggregate refresh, daily macro (7-day incremental), daily calendar |
| **API** | ✅ Working | FastAPI — `/health`, `/api/v1/stocks/`, `/api/v1/calendar/`, `/api/v1/charts/` |
| **Scheduler** | ✅ Working | Celery Beat — daily OHLCV (6 PM ET), daily macro (6:30 PM ET), daily economic calendar (7 AM ET) |
| **Analysis** | ✅ Working | Technical indicators: SMA, EMA, RSI, MACD, Bollinger Bands (pure pandas, no DB dependency) |
| **Charting** | ✅ Working | Plotly candlestick charts with volume subplot and indicator overlays (SMA, EMA, RSI, MACD, Bollinger) |
| **Stock Search** | ✅ Working | Typeahead search by ticker prefix + company name substring, ranked results, API + Streamlit widget |
| **Dashboard** | ✅ Basic | Streamlit — economic calendar widget + interactive candlestick chart page with stock search |
| **CI/CD** | ✅ Green | GitHub Actions — ruff lint, ruff format, mypy, pytest (196 tests) |
| **Tests** | ✅ 215 passing | Model, fetcher, service, API, task, widget, helpers, backfill, candle service, technical indicators, chart builder, stock search |
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

> **Detailed session notes:** See [`BUILD_LOG.md`](./BUILD_LOG.md) for the full chronological record.

---

## 4. Upcoming Sessions Roadmap

Each session is self-contained: one branch, one PR, one merge. Work top-to-bottom.

| # | Session | Scope | Key Files to Create/Modify | Depends On |
|---|---------|-------|---------------------------|------------|
| **13** | **Stock Search** | ✅ Done — typeahead search component, API endpoint, Streamlit widget, charts page integration, 19 tests. | `backend/services/stock_search.py`, `backend/api/routes/stocks.py`, `streamlit_app/components/stock_search.py`, `backend/tests/test_stock_search.py` | Session 12 ✅ |
| **14** | **Workflow Improvements** | ✅ Done — checkpoint-based workflow, crash recovery in PROGRESS.md, Docker RAM management, OOM pitfall. | `WORKFLOW.md`, `docs/PROGRESS.md`, `docs/BUILD_LOG.md`, `docs/CHANGELOG.md` | — |
| **15** | **Watchlist — Backend** | Watchlist model (`watchlists` + `watchlist_items` tables), CRUD service, API endpoints (`GET/POST/PUT/DELETE /api/v1/watchlists/`). Migration. Tests for model, service, API. | `backend/models/watchlist.py`, `backend/services/watchlist_service.py`, `backend/api/routes/watchlists.py`, `backend/tests/test_watchlist.py`, Alembic migration | Session 13 |
| **16** | **Watchlist — UI** | Streamlit watchlist page: create/rename/delete watchlists, add/remove tickers (uses search from Session 13), display watchlist with sparkline/change columns. | `streamlit_app/pages/watchlists.py`, `streamlit_app/components/watchlist_card.py` | Session 15 |
| **17** | **Dashboard Polish** | Wire everything together: dashboard home page shows watchlist summary cards, recent price changes, upcoming economic events, and a "Jump to Chart" link per ticker. Final Phase 2 QA pass. | `streamlit_app/pages/dashboard.py` (rewrite), `streamlit_app/app.py` (nav update) | Session 16 |
| **18** | **Phase 3 Kickoff — Trend Classification** | Begin Phase 3 (Analysis Engine). Implement trend classification algorithm (short/mid/long-term) using SMA crossovers and slope analysis. Service + tests. | `backend/services/analysis/trend_classifier.py`, `backend/tests/test_trend_classifier.py` | Session 17 |
