# 🔄 PraxiAlpha — Session Workflow

> **Purpose:** Entry point for every Copilot chat session.
> Contains only: where we left off, what's next, and how we work.
>
> For full project status, phase checklists, session history, and roadmap,
> see [`docs/PROGRESS.md`](docs/PROGRESS.md).
>
> **Last updated:** 2026-03-23 (Session 25 — Smart OHLCV Gap-Fill)

---

## 1. Where We Are

### Last Completed Session
| | |
|-|-|
| **Session** | 25 — Smart OHLCV Gap-Fill |
| **Date** | 2026-03-23 |
| **PR** | #27 (Smart OHLCV Gap-Fill) |
| **What was done** | Rewrote `daily_ohlcv_update` Celery task with gap-detection loop — auto-fills all missing trading days since last fetch. Extracted helpers, added config setting, 12 new tests (434 total). PR review fixes addressed (6 comments). |

### Current Phase
**Phase 2: Charting & Basic Dashboard** — in progress. Phase 1 is complete.

### Next Session
| | |
|-|-|
| **Session** | 26 — Watchlist Backend |
| **Scope** | Watchlist model (`watchlists` + `watchlist_items` tables), CRUD service, API endpoints (`GET/POST/PUT/DELETE /api/v1/watchlists/`). Migration. Tests for model, service, API. |
| **Key files** | `backend/models/watchlist.py`, `backend/services/watchlist_service.py`, `backend/api/routes/watchlists.py`, `backend/tests/test_watchlist.py` |
| **Depends on** | Session 16 (Trading Journal Backend) |

> **After Session 26:** Session 27 builds the Streamlit Watchlist UI — create/rename/delete watchlists,
> add/remove tickers, sparkline/change columns.

> **How to resume:** Start a new chat, paste one of the prompts in §6 (Resume Prompts).

### Key Files to Read for Context
| File | What It Tells You |
|------|-------------------|
| `docs/PROGRESS.md` | Full component status, phase checklists, session history, upcoming roadmap, **crash recovery status** |
| `DESIGN_DOC.md` | Architecture, mental models, phase roadmap, data providers |
| `docs/BUILD_LOG.md` | Chronological record of every session (read the latest session) |
| `docs/CHANGELOG.md` | What changed (Added / Fixed / Changed) |
| `CONTRIBUTING.md` | Branch naming, commit convention, PR checklist |
| `docs/ARCHITECTURE.md` | File structure, database schema, system diagram |

---

## 2. Session Workflow (follow every time)

> **Design principle:** Commit early and often. Every checkpoint saves progress
> so that if Copilot Chat crashes (OOM on 8 GB Mac), the next session can
> resume from the last commit — not from scratch.

### Step 0: Orientation (Copilot reads context)
> **When a new chat session starts, Copilot should:**
1. Read `WORKFLOW.md` (this file) — understand current state and what's next
2. Read `docs/PROGRESS.md` — understand full project status and crash recovery state
3. Read the **latest session** in `docs/BUILD_LOG.md` — understand what was done last
4. Read the **Phase Roadmap** in `DESIGN_DOC.md` — understand the bigger picture
5. Check `git status` and `git branch` — confirm branch state
6. Confirm with the developer what the goal of this session is

### Step 1: Create Feature Branch
```bash
git checkout main
git pull origin main
git checkout -b <type>/<short-description>
```
Branch types: `feat/`, `fix/`, `docs/`, `refactor/`, `ci/`, `test/`, `chore/`
(see `CONTRIBUTING.md` for full list)

> **Docker guideline:** If the session is code/test/docs only (no dashboard viewing
> or DB work), stop Docker to free ~2-3 GB RAM:
> ```bash
> docker compose stop    # free RAM for coding sessions
> docker compose up -d   # restart when you need the dashboard/DB
> ```

### Step 2: Implement Code Changes
- Write code and tests together (not tests as an afterthought)
- Follow existing patterns in the codebase (service layer, async fetchers, etc.)
- Keep commits logical — one concern per commit

### Step 3: Checkpoint #1 — Save Code
```bash
git add -A
git commit -m "wip: <what was just done>"
```
> **Why:** This saves all code changes locally. If Copilot crashes after this
> point, no code is lost. Do NOT push yet.
>
> **Note on commit messages:** `wip:` prefixed commits are local-only checkpoints.
> They will be squash-merged into a single Conventional Commit (`<type>(<scope>): ...`)
> when the PR is merged. This does not violate the Conventional Commits convention
> in `CONTRIBUTING.md` — the final merge commit follows the standard format.

### Step 4: Checkpoint #2 — Update Progress
Update `docs/PROGRESS.md` → **Current Session Status** block with:
- What's been done so far
- What remains (CI, docs, PR)
- Branch name

Then commit:
```bash
git add docs/PROGRESS.md
git commit -m "wip: update progress checkpoint"
```
> **Why:** If Copilot crashes, the next session reads PROGRESS.md and knows
> exactly where to resume. This is the crash recovery mechanism.

### Step 5: Run Local CI Checks
```bash
# Option A: Run the local CI script
./scripts/ci_check.sh

# Option B: Run each check individually
ruff check backend/ scripts/
ruff format --check backend/ scripts/
mypy backend/ --ignore-missing-imports
pytest --tb=short -q
```
**All 4 checks must pass before proceeding.** Fix any failures.

### Step 6: Checkpoint #3 — Save CI-Clean Code
```bash
# If Step 5 required code changes, commit them:
git add -A
git commit -m "wip: CI fixes"

# Update PROGRESS.md status to "CI passed" and commit:
# (Set the "Current Session Status" block → Status = "CI passed, docs pending")
git add docs/PROGRESS.md
git commit -m "wip: progress checkpoint — CI passed"
```
> **Why:** Both the code fixes AND the updated progress are committed separately,
> ensuring nothing is lost if Copilot crashes during the documentation step.

### Step 7: Update All Documentation

> ⚠️ **BUILD_LOG.md is the largest file in the project and edits to it frequently
> trigger Copilot OOM crashes on 8 GB Macs.** Always commit + push all code
> changes BEFORE starting documentation updates. This ensures that if Copilot
> crashes during the BUILD_LOG edit, no code work is lost and recovery is trivial.

#### Step 7a: Pre-docs safety checkpoint
```bash
# Commit + push ALL code changes before touching any docs
git add -A
git commit -m "wip: code complete, pre-docs checkpoint"
git push origin <branch-name>
```
> **Why:** This is the single most important checkpoint. If Copilot crashes at
> any point during documentation updates, all code is safe on the remote.
> Recovery = re-read docs and continue writing.

#### Step 7b: Update small docs FIRST (commit + push before BUILD_LOG)

Update these files **in this order**, because they are small and safe to edit:

| Order | Document | What to Update |
|-------|----------|---------------|
| 1 | `docs/CHANGELOG.md` | Add entries under `[Unreleased]` → Added / Fixed / Changed sections |
| 2 | `WORKFLOW.md` | Update "Last Completed Session", "Next Session", and "Last updated" date |
| 3 | `docs/PROGRESS.md` | Update component status table, phase checklists, session history, roadmap, and set the "Current Session Status" to "PR opened / awaiting review" |
| 4 | `docs/ARCHITECTURE.md` | Only if file structure, tables, or system diagrams changed |
| 5 | `DESIGN_DOC.md` | Only if architecture, schema, roadmap, or mental models changed |
| 6 | `CONTRIBUTING.md` | Only if workflow, conventions, or branch protection rules changed |

```bash
# Commit + push the small doc updates BEFORE touching BUILD_LOG
git add -A
git commit -m "wip: docs checkpoint — all docs except BUILD_LOG"
git push origin <branch-name>
```
> **Why:** BUILD_LOG.md is the crash-prone file. By committing all other docs
> first, a crash during BUILD_LOG editing loses only that one file's update —
> not CHANGELOG, PROGRESS, WORKFLOW, etc.

#### Step 7c: Append to BUILD_LOG.md using `cat >>` (NEVER edit in-place)

> **CRITICAL:** Do NOT use file-editing tools (insert_edit_into_file,
> replace_string_in_file) on BUILD_LOG.md. The file is too large and
> reading it causes Copilot OOM crashes. Instead, use `cat >> ... << 'EOF'`
> to blindly append the new session entry at the end.

```bash
cat >> docs/BUILD_LOG.md << 'EOF'

### Session N — YYYY-MM-DD: Title (Phase X)

**Goal:** ...

**Branch:** `<branch-name>`

#### What Was Done
...

#### Key Design Decisions
...

#### Lessons Learned
...

#### Files Changed
...

#### Test Count: XXX (Y new)
EOF

git add docs/BUILD_LOG.md
git commit -m "docs: session <number> BUILD_LOG entry"
git push origin <branch-name>
```

**Documentation rules:**
- BUILD_LOG sessions are **strictly chronological** — always append at the end
- Session numbers are **sequential** — never reuse or skip
- CHANGELOG uses **[Keep a Changelog](https://keepachangelog.com/)** format
- In Copilot Chat, **never load the full `docs/BUILD_LOG.md` or edit it in place**; if context is needed, only read the latest session/tail of the file, and append new entries via `cat >>` from the shell

### Step 8: Push Branch and Create PR
```bash
# Push branch
git push origin <branch-name>

# Create PR via GitHub CLI
gh pr create \
  --title "<type>(<scope>): <short summary>" \
  --body "<PR description following prior PR convention>" \
  --base main
```

**PR description convention** (see merged PRs for examples):
```
## Summary
<One paragraph: what and why>

## Changes
### Added / Fixed / Changed
- ...

## Test Results
- X/X tests pass (ruff, format, mypy, pytest all clean)

## Files Changed (N files)
- `path/to/file` — description
```

### Step 9: PR Review & Fix Cycle
1. Developer requests a review on GitHub (Copilot code review or human reviewer)
2. Once complete, developer tells Copilot: **"PR review is done on PR #N, fetch and fix the comments"**
3. **Copilot fetches review comments:**

```bash
# Fetch PR overview and review body
gh pr view <PR_NUMBER> --comments --json reviews,comments

# Fetch inline code review comments
gh api repos/<OWNER>/<REPO>/pulls/<PR_NUMBER>/comments \
  --jq '.[] | "---\nFile: \(.path):\(.line // .original_line)\nBody: \(.body)\n"'
```

4. Copilot reads all comments, implements fixes, runs CI, and pushes to the same branch
5. **Commit + push code fixes BEFORE updating BUILD_LOG** (same OOM safeguard as Step 7):
   ```bash
   git add -A
   git commit -m "wip: PR review fixes"
   git push origin <branch-name>
   ```
6. **Document the review fixes** in `docs/BUILD_LOG.md` — use `cat >>` to append
   a `#### PR Review Fixes` section to the current session entry. For each fix, document:
   - **What was changed**
   - **Why** (the reviewer's reasoning)
   - **Impact if not fixed** (what could go wrong at scale)
   ```bash
   cat >> docs/BUILD_LOG.md << 'EOF'

   #### PR Review Fixes (PR #N — X comments from reviewer)
   ...
   EOF
   git add docs/BUILD_LOG.md
   git commit -m "docs: session <N> PR review fixes"
   git push origin <branch-name>
   ```
   > CHANGELOG is **not** updated for review fixes — they are pre-merge quality improvements.
7. PR auto-updates → developer reviews again or approves
8. Developer squash-merges on GitHub

### Step 10: Post-Merge Cleanup
```bash
git checkout main
git pull origin main
git branch -d <branch-name>   # delete local branch (remote is auto-deleted)
```
> Clear the "Current Session Status" block in `docs/PROGRESS.md` (set to "No active session").

---

## 3. Crash Recovery

If Copilot Chat crashes mid-session, start a new chat and use this prompt:

> **"Copilot crashed mid-session. Read `docs/PROGRESS.md` for the current session status,
> check `git status` and `git log --oneline -5`, then resume where we left off."**

Copilot will:
1. Read PROGRESS.md → see what step we were on
2. Check git status → see uncommitted changes
3. Check git log → see what's already been committed on the branch
4. Resume from the last checkpoint

### Crash during BUILD_LOG.md / docs update (most common)
If Copilot crashes while editing docs (Steps 7b or 7c), code and earlier docs
are already committed and pushed. Use:

> **"Copilot crashed during docs update for Session N.
> Code is committed and pushed. Check `git log --oneline -5` and `git status`
> to see which docs were already committed. Then resume the remaining docs.
> Remember: use `cat >> docs/BUILD_LOG.md << 'EOF'` to append — do NOT read
> or edit BUILD_LOG.md with file tools."**

---

## 4. Common Pitfalls (lessons from Sessions 1–14)

| # | Pitfall | Prevention |
|---|---------|------------|
| 1 | BUILD_LOG entries inserted in the middle instead of at the end | Always append at the bottom. Grep for `^### Session` to find the last session number. |
| 2 | Duplicate content in BUILD_LOG after merges | Never copy-paste entire session blocks. Each session appears exactly once. |
| 3 | Session numbering gaps or duplicates | Always: `last_session_number + 1`. Check before writing. |
| 4 | Pushing without running CI locally | Always run `./scripts/ci_check.sh` before `git push`. The pre-push hook should catch this. |
| 5 | Git index corruption after pull | If you see hundreds of phantom changes after pull, run: `rm -f .git/index && git reset` |
| 6 | Heavy deps in CI test job | CI installs only lightweight test deps. Keep tests decoupled from streamlit/celery/plotly. Use `pytest.importorskip()` or `importlib.util.find_spec` skipif guards. |
| 7 | `asyncio.get_event_loop()` on Python 3.11+ | Use `asyncio.run()` in tasks, `asyncio.get_running_loop()` with fallback in Streamlit. |
| 8 | Docs lagging behind code | Update docs in the same commit as code changes, not as an afterthought. |
| 9 | DB parameter overflow on large batch inserts | PostgreSQL has a ~32K parameter limit. Keep `batch_size × columns` well under 32K. |
| 10 | `--resume` re-fetching failed tickers from API on every run | Resume must skip both completed AND failed tickers. Failed tickers are retried only in the end-of-run retry phase. |
| 11 | Empty `DATABASE_URL=` overriding `.env` defaults | Either export the full `DATABASE_URL` or don't set it at all. Empty string overrides `.env`. |
| 12 | `str(engine.url)` masks passwords with `***` | Use `settings.async_database_url` (the original config value) instead. |
| 13 | `CALL refresh_continuous_aggregate` inside SQLAlchemy transaction | Use raw asyncpg connection, not `engine.begin()`. |
| 14 | `time_bucket('7 days', date)` doesn't align to ISO weeks | Always pass `origin => '<a-monday>'` for weekly buckets. |
| 15 | `SELECT count(*)` on large hypertables/aggregates | Use `pg_class.reltuples` for approximate O(1) counts in monitoring endpoints. |
| 16 | **Copilot Chat OOM crash on 8 GB Mac** | Stop Docker when not needed (`docker compose stop`). Keep chat sessions short — one PR per session. Commit after every logical chunk (Steps 3, 4, 6). Start a new chat after each PR merge. See §3 for crash recovery. |
| 17 | **BUILD_LOG.md edits trigger OOM crashes** | **Never use file-editing tools on BUILD_LOG.md.** Always use `cat >> docs/BUILD_LOG.md << 'EOF'` to blindly append. Commit + push all other docs (CHANGELOG, WORKFLOW, PROGRESS) BEFORE touching BUILD_LOG (Step 7b→7c). If Copilot crashes during the `cat >>` step, only the BUILD_LOG entry is lost — all code and other docs are safe on the remote. |
| 18 | **Docs step crashes lose all doc updates** | Update small docs first (CHANGELOG, WORKFLOW, PROGRESS), commit + push, THEN append BUILD_LOG. This way a crash during BUILD_LOG loses only that one entry, not all session documentation. See Step 7b→7c ordering. |

---

## 5. Quick Reference

### Docker Management
```bash
docker compose up -d          # Start all services (need for dashboard/DB)
docker compose stop           # Stop services, free ~2-3 GB RAM (for coding sessions)
docker compose down           # Remove containers entirely
docker compose logs -f app    # Follow FastAPI logs
docker compose exec db psql -U praxialpha -d praxialpha  # SQL shell
```

| Activity | Docker Needed? | Action |
|----------|---------------|--------|
| Writing code, tests, running CI | ❌ No — tests use mocks/fixtures | `docker compose stop` |
| Viewing the dashboard / charts / API | ✅ Yes — needs Postgres, FastAPI | `docker compose up -d` |
| Running backfill scripts / DB migrations | ✅ Yes — needs Postgres | `docker compose up -d` |
| Documentation-only sessions | ❌ No | `docker compose stop` |

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
| GET | `/api/v1/stocks/search` | Search stocks by ticker/name |
| GET | `/api/v1/stocks/count` | Stock count |
| GET | `/api/v1/stocks/{ticker}` | Single stock |
| GET | `/api/v1/calendar/upcoming` | Upcoming economic events |
| GET | `/api/v1/calendar/high-impact` | High-impact events only |
| POST | `/api/v1/calendar/sync` | Manual calendar sync |
| GET | `/api/v1/charts/{ticker}/candles` | Candle data by timeframe |
| GET | `/api/v1/charts/{ticker}/summary` | Multi-timeframe summary |
| GET | `/api/v1/charts/stats` | Aggregate statistics |

#### Trading Journal (Session 16)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/journal/` | List trades (with filters) |
| POST | `/api/v1/journal/` | Create a new trade entry |
| GET | `/api/v1/journal/{trade_id}` | Get trade details (with exits & legs) |
| PUT | `/api/v1/journal/{trade_id}` | Update trade (tags, comments, stop/TP) |
| DELETE | `/api/v1/journal/{trade_id}` | Delete a trade |
| POST | `/api/v1/journal/{trade_id}/exits` | Add a partial/full exit |
| POST | `/api/v1/journal/{trade_id}/legs` | Add an option leg |
| GET | `/api/v1/journal/report` | Generate PDF report (Session 22 — planned) |

#### Post-Close What-If Snapshots (Session 20)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/journal/{trade_id}/snapshots` | List post-close price snapshots for a trade |
| GET | `/api/v1/journal/{trade_id}/what-if` | Summary: best/worst hypothetical PnL vs actual exit |

---

## 6. Resume Prompts

### Starting a new session (normal):
> **"I'm continuing work on PraxiAlpha. Read `WORKFLOW.md`, `docs/PROGRESS.md`, the latest session in `docs/BUILD_LOG.md`, and the Phase Roadmap in `DESIGN_DOC.md` to understand where we left off. Then let's discuss what to build next."**

### Recovering from a crash (mid-session):
> **"Copilot crashed mid-session. Read `docs/PROGRESS.md` for the current session status, check `git status` and `git log --oneline -5`, then resume where we left off."**
