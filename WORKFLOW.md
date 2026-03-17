# 🔄 PraxiAlpha — Session Workflow

> **Purpose:** This document is the entry point for every Copilot chat session.
> Paste it (or reference it) at the start of every new conversation so Copilot
> has full context on where we left off, what comes next, and how we work.
>
> **Last updated:** 2026-03-17 (Session 10)

---

## 1. Current Project State

### What Exists (as of Session 10)
| Component | Status | Details |
|-----------|--------|---------|
| **Database** | ✅ Running | PostgreSQL 16 + TimescaleDB via Docker |
| **Tables** | ✅ Populated | `stocks` (49K), `daily_ohlcv` (58.2M), `macro_data` (81K), `stock_splits` (18.4K), `stock_dividends` (634K), `economic_calendar_events` |
| **Candle Aggregates** | ✅ Populated | `weekly_ohlcv` (13.5M), `monthly_ohlcv` (3.4M), `quarterly_ohlcv` (1.2M) — TimescaleDB continuous aggregates with auto-refresh |
| **Data Pipeline** | ✅ Working | EODHD fetcher (OHLCV, splits, dividends), FRED fetcher (14 macro series), TradingEconomics fetcher (economic calendar) |
| **Backfill** | ✅ Done | `scripts/backfill_full.py` — 23,714 tickers backfilled (1990–2026), 58.2M OHLCV records, 18.4K splits, 634K dividends |
| **Daily Tasks** | ✅ Implemented | Celery Beat — daily OHLCV (bulk endpoint) → candle aggregate refresh, daily macro (7-day incremental), daily calendar |
| **API** | ✅ Working | FastAPI — `/health`, `/api/v1/stocks/`, `/api/v1/calendar/`, `/charts/` |
| **Scheduler** | ✅ Working | Celery Beat — daily OHLCV (6 PM ET), daily macro (6:30 PM ET), daily economic calendar (7 AM ET) |
| **Dashboard** | ✅ Basic | Streamlit — economic calendar widget (high-impact + all events) |
| **CI/CD** | ✅ Green | GitHub Actions — ruff lint, ruff format, mypy, pytest (117 tests) |
| **Tests** | ✅ 117 passing | Model, fetcher, service, API, task, widget, helpers, backfill, candle service |
| **Docs** | ✅ Current | DESIGN_DOC, ARCHITECTURE, BUILD_LOG (10 sessions), CHANGELOG, CONTRIBUTING, WORKFLOW |

### Current Phase
**Phase 1: Foundation (Weeks 1–4)** — mostly complete.

#### Phase 1 Remaining Tasks
- [x] **Run full backfill** — ✅ completed: 23,714 tickers, 58.2M OHLCV records (1990-01-02 → 2026-03-16)
- [x] Compute weekly/monthly/quarterly candles from daily data — ✅ TimescaleDB continuous aggregates (13.5M weekly, 3.4M monthly, 1.2M quarterly)

#### Phase 2: Charting & Basic Dashboard (Weeks 5–8) — next
- [ ] Interactive candlestick charts (Plotly / Lightweight Charts)
- [ ] Technical indicator overlays (RSI, MACD, MAs, Bollinger Bands)
- [ ] Volume subplot
- [ ] Daily/weekly/monthly chart toggle
- [ ] Watchlist management UI
- [ ] Stock search functionality
- [ ] ~~Economic calendar widget~~ ✅ Done (pulled into Phase 1)

> See `DESIGN_DOC.md` § "Phase Roadmap" for the full 9-phase plan.

### Key Files to Read for Context
| File | What It Tells You |
|------|-------------------|
| `DESIGN_DOC.md` | Architecture, mental models, phase roadmap, data providers |
| `docs/BUILD_LOG.md` | Chronological record of every session (read the latest session) |
| `docs/CHANGELOG.md` | What changed (Added / Fixed / Changed) |
| `CONTRIBUTING.md` | Branch naming, commit convention, PR checklist |
| `docs/ARCHITECTURE.md` | File structure, database schema, system diagram |
| `this file (WORKFLOW.md)` | Session workflow, current state, what's next |

---

## 2. Session Workflow (follow every time)

### Step 0: Orientation (Copilot reads context)
> **When a new chat session starts, Copilot should:**
1. Read `WORKFLOW.md` (this file) — understand current state and what's next
2. Read the **latest session** in `docs/BUILD_LOG.md` — understand what was done last
3. Read the **Phase Roadmap** in `DESIGN_DOC.md` — understand what's next on the plan
4. Check `git status` and `git branch` — confirm we're on `main` with a clean tree
5. Confirm with the developer what the goal of this session is

### Step 1: Create Feature Branch
```bash
git checkout main
git pull origin main
git checkout -b <type>/<short-description>
```
Branch types: `feat/`, `fix/`, `docs/`, `refactor/`, `ci/`, `test/`, `chore/`
(see `CONTRIBUTING.md` for full list)

### Step 2: Implement Changes
- Write code, tests, and documentation together (not docs as an afterthought)
- Follow existing patterns in the codebase (service layer, async fetchers, etc.)
- Keep commits logical — one concern per commit

### Step 3: Update Documentation
**Every session must update these files before pushing:**

| Document | What to Update |
|----------|---------------|
| `docs/BUILD_LOG.md` | Add new session entry **at the bottom** (strictly chronological). Include: what was done, files changed, test count, lessons learned. Session number = previous + 1. |
| `docs/CHANGELOG.md` | Add entries under `[Unreleased]` → Added / Fixed / Changed sections |
| `WORKFLOW.md` | Update "Current Project State" table, "Current Phase" section, and "Last updated" date |
| `CONTRIBUTING.md` | Only if workflow, conventions, or branch protection rules changed |
| `DESIGN_DOC.md` | Only if architecture, schema, roadmap, or mental models changed |
| `docs/ARCHITECTURE.md` | Only if file structure, tables, or system diagrams changed |

**Documentation rules:**
- BUILD_LOG sessions are **strictly chronological** — always append at the end, never insert in the middle
- Session numbers are **sequential** — never reuse or skip a number
- CHANGELOG uses **[Keep a Changelog](https://keepachangelog.com/)** format
- Update the `Last updated` date in WORKFLOW.md header

### Step 4: Run Pre-Push CI Checks
```bash
# Option A: Run the local CI script
./scripts/ci_check.sh

# Option B: Run each check individually
ruff check backend/ scripts/
ruff format --check backend/ scripts/
mypy backend/ --ignore-missing-imports
pytest --tb=short -q
```
**All 4 checks must pass before pushing.** Fix any failures before proceeding.

### Step 5: Commit, Push, and Create PR
```bash
# Stage and commit (Conventional Commits format)
git add -A
git commit -m "<type>(<scope>): <short summary>"

# Push branch
git push origin <branch-name>

# Create PR via GitHub CLI
gh pr create \
  --title "<type>(<scope>): <short summary>" \
  --body "<PR description following prior PR convention>" \
  --base main
```

**PR description convention** (see merged PRs #1–#4 for examples):
```
## Summary
<One paragraph: what and why>

## Changes
### Added
- ...
### Fixed
- ...
### Changed
- ...

## Test Results
- X/X tests pass
- ruff lint: clean
- ruff format: clean
- mypy: clean

## Files Changed (N files)
- `path/to/file` — description
```

### Step 6: Developer Review & Merge
1. Developer reviews the PR on GitHub
2. If changes are needed → Copilot makes fixes → push to same branch → PR updates automatically
3. Developer approves → squash-merges on GitHub
4. Feature branch is auto-deleted after merge

### Step 7: Post-Merge Cleanup
```bash
git checkout main
git pull origin main
git branch -d <branch-name>   # delete local branch (remote is auto-deleted)
```

---

## 3. Common Pitfalls (lessons from Sessions 1–9)

| # | Pitfall | Prevention |
|---|---------|------------|
| 1 | BUILD_LOG entries inserted in the middle instead of at the end | Always append at the bottom. Grep for `^### Session` to find the last session number. |
| 2 | Duplicate content in BUILD_LOG after merges | Never copy-paste entire session blocks. Each session appears exactly once. |
| 3 | Session numbering gaps or duplicates | Always: `last_session_number + 1`. Check before writing. |
| 4 | Pushing without running CI locally | Always run `./scripts/ci_check.sh` before `git push`. The pre-push hook should catch this, but verify. |
| 5 | Git index corruption after pull | If you see hundreds of phantom changes after pull, run: `rm -f .git/index && git reset` |
| 6 | Heavy deps in CI test job | CI installs only lightweight test deps, not full `[dev]` extras. Keep tests decoupled from streamlit/celery/plotly. |
| 7 | `asyncio.get_event_loop()` on Python 3.11+ | Use `asyncio.run()` in tasks, `asyncio.get_running_loop()` with fallback in Streamlit. |
| 8 | Docs lagging behind code | Update docs in the same commit as code changes, not as an afterthought. |
| 9 | DB parameter overflow on large batch inserts | PostgreSQL has a ~32K parameter limit. With 8 columns per row, the main task path uses `DB_BATCH_SIZE=1000` → 8K params, safely under the limit. For any new batch writers, keep `batch_size × columns` well under 32K. |
| 10 | `--resume` re-fetching failed tickers from API on every run | Resume must skip both completed AND failed tickers. Failed tickers are retried only in the end-of-run retry phase, not re-fetched from the API in the main pass. |
| 11 | Empty `DATABASE_URL=` overriding `.env` defaults | When running scripts locally, either export the full `DATABASE_URL` or don't set it at all. `DATABASE_URL=` (empty) overrides `.env` and causes auth failures. |
| 12 | `str(engine.url)` masks passwords with `***` | Never use `str(engine.url)` to build raw connection strings. Use `settings.async_database_url` (the original config value) instead. |
| 13 | `CALL refresh_continuous_aggregate` inside SQLAlchemy transaction | TimescaleDB's `refresh_continuous_aggregate()` cannot run inside a transaction block. Use raw asyncpg connection, not `engine.begin()`. |

---

## 4. Quick Reference

### Docker Stack
```bash
docker compose up -d          # Start all 5 services
docker compose down           # Stop all services
docker compose logs -f app    # Follow FastAPI logs
docker compose exec db psql -U praxialpha -d praxialpha  # SQL shell
```

### Local CI
```bash
./scripts/ci_check.sh         # Run all checks (lint, format, mypy, pytest)
./scripts/ci_check.sh --fix   # Auto-fix lint and format issues
```

### Useful Git Commands
```bash
git log --oneline -10                    # Last 10 commits on main
gh pr list --state merged --limit 5      # Recent merged PRs
grep -n "^### Session" docs/BUILD_LOG.md # List all session entries
```

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/stocks/` | List stocks |
| GET | `/api/v1/stocks/count` | Stock count |
| GET | `/api/v1/stocks/{ticker}` | Single stock |
| GET | `/api/v1/calendar/upcoming` | Upcoming economic events |
| GET | `/api/v1/calendar/high-impact` | High-impact events only |
| POST | `/api/v1/calendar/sync` | Manual calendar sync |
| GET | `/charts/{ticker}/candles` | Candle data by timeframe |
| GET | `/charts/{ticker}/summary` | Multi-timeframe summary |
| GET | `/charts/stats` | Aggregate statistics |

---

## 5. Session Log Summary

| Session | Date | What Was Done | PR |
|---------|------|---------------|----|
| 1 | 2026-03-13 | Project scaffolding (125 files), Docker stack, DB setup, 49K tickers | Direct to main |
| 2 | 2026-03-13 | Test backfill (10 stocks, 68K OHLCV), splits & dividends, batch insert fix | Direct to main |
| 3 | 2026-03-13 | CI/CD pipeline (GitHub Actions), code quality (ruff, mypy), CONTRIBUTING.md | Direct to main |
| 4 | 2026-03-13 | Macro backfill (14 FRED series, 81K records), local CI tooling, pre-push hook | PR #1 |
| 5 | 2026-03-14 | Economic calendar full stack (model, fetcher, service, API, Celery, Streamlit, 32 tests) | PR #3 |
| 6 | 2026-03-15 | Copilot code review fixes (9 items: asyncio, datetime parsing, bulk upsert, validation) | PR #3 |
| 7 | 2026-03-16 | Session workflow document (this file) | PR #5 |
| 8 | 2026-03-16 | Production backfill script, daily OHLCV/macro Celery tasks, 33 new tests (95 total) | PR #6 |
| 9 | 2026-03-17 | Full backfill run (58.2M records), DB crash fixes, resume bug fix, batch size & retry hardening | PR #6 |
| 10 | 2026-03-17 | Weekly/monthly/quarterly candle aggregates, charts API, candle service, Celery refresh task, 22 new tests (117 total) | PR #7 |

---

*When starting a new chat, paste this prompt:*
> **"I'm continuing work on PraxiAlpha. Read `WORKFLOW.md`, the latest session in `docs/BUILD_LOG.md`, and the Phase Roadmap in `DESIGN_DOC.md` to understand where we left off. Then let's discuss what to build next."**
