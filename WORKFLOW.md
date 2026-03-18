# 🔄 PraxiAlpha — Session Workflow

> **Purpose:** Entry point for every Copilot chat session.
> Contains only: where we left off, what's next, and how we work.
>
> For full project status, phase checklists, session history, and roadmap,
> see [`docs/PROGRESS.md`](docs/PROGRESS.md).
>
> **Last updated:** 2026-03-17 (Session 12)

---

## 1. Where We Are

### Last Completed Session
| | |
|-|-|
| **Session** | 12 — Candlestick Chart Component |
| **Date** | 2026-03-17 |
| **PR** | #9 |
| **What was done** | Plotly candlestick chart builder, charts page, volume subplot, indicator overlays (SMA/EMA/RSI/MACD/Bollinger), 25 new tests (196 total) |

### Current Phase
**Phase 2: Charting & Basic Dashboard** — in progress. Phase 1 is complete.

### Next Session
| | |
|-|-|
| **Session** | 13 — Stock Search |
| **Scope** | Typeahead search component — query `stocks` table by ticker/name, return top-N matches. API endpoint `GET /api/v1/stocks/search?q=`. Streamlit search widget in sidebar. Tests for service + API + widget. |
| **Key files** | `backend/services/stock_search.py`, `backend/api/routes/stocks.py` (add search), `streamlit_app/components/stock_search.py`, `backend/tests/test_stock_search.py` |
| **Depends on** | Session 12 ✅ |

> **How to resume:** Start a new chat, paste the prompt at the bottom of this file, and say
> *"Let's do Session 13"*.

### Key Files to Read for Context
| File | What It Tells You |
|------|-------------------|
| `DESIGN_DOC.md` | Architecture, mental models, phase roadmap, data providers |
| `docs/PROGRESS.md` | Full component status, phase checklists, session history, upcoming roadmap |
| `docs/BUILD_LOG.md` | Chronological record of every session (read the latest session) |
| `docs/CHANGELOG.md` | What changed (Added / Fixed / Changed) |
| `CONTRIBUTING.md` | Branch naming, commit convention, PR checklist |
| `docs/ARCHITECTURE.md` | File structure, database schema, system diagram |

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
| `WORKFLOW.md` | Update "Last Completed Session", "Next Session", and "Last updated" date |
| `docs/PROGRESS.md` | Update component status table, phase checklists, session history, and roadmap |
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

### Step 6: PR Review & Fix Cycle
1. Developer requests a review on GitHub (Copilot code review or human reviewer)
2. Once the review is complete, developer tells Copilot: **"PR review is done on PR #N, fetch and fix the comments"**
3. **Copilot fetches review comments** using these commands:

```bash
# Fetch the PR overview and review body
gh pr view <PR_NUMBER> --comments --json reviews,comments

# Fetch inline review comments (the specific code suggestions)
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments \
  --jq '.[] | "---\nFile: \(.path):\(.line // .original_line)\nBody: \(.body)\n"'
```

4. Copilot reads all comments, implements fixes, runs CI, and pushes to the same branch
5. **Document the review fixes** in `docs/BUILD_LOG.md` — append a `#### PR Review Fixes` section to the current session entry. For each fix, document:
   - **What was changed** — the concrete code/doc change
   - **Why** — the reviewer's reasoning and the underlying principle
   - **Impact if not fixed** — what could go wrong at scale, in CI, or in the broader project if this was left as-is
   > This section is added *after* the initial session entry, not as a separate session.
   > CHANGELOG is **not** updated for review fixes — they are pre-merge quality improvements, not new user-facing changes.
6. PR auto-updates → developer reviews again or approves
7. Developer squash-merges on GitHub
8. Feature branch is auto-deleted after merge

### Step 7: Post-Merge Cleanup
```bash
git checkout main
git pull origin main
git branch -d <branch-name>   # delete local branch (remote is auto-deleted)
```

---

## 3. Common Pitfalls (lessons from Sessions 1–12)

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
| 14 | `time_bucket('7 days', date)` doesn't align to ISO weeks | TimescaleDB's default `time_bucket` origin is the Unix epoch (a Thursday). Always pass `origin => '<a-monday>'` for weekly buckets. |
| 15 | `SELECT count(*)` on large hypertables/aggregates | Exact counts scan millions of rows. Use `pg_class.reltuples` for approximate O(1) counts in monitoring/health endpoints. |

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
| GET | `/api/v1/charts/{ticker}/candles` | Candle data by timeframe |
| GET | `/api/v1/charts/{ticker}/summary` | Multi-timeframe summary |
| GET | `/api/v1/charts/stats` | Aggregate statistics |

---

*When starting a new chat, paste this prompt:*
> **"I'm continuing work on PraxiAlpha. Read `WORKFLOW.md`, the latest session in `docs/BUILD_LOG.md`, and the Phase Roadmap in `DESIGN_DOC.md` to understand where we left off. Then let's discuss what to build next."**
