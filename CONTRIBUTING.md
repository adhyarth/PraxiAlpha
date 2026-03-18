# 🤝 PraxiAlpha — Contributing Guide

> Standards and conventions for contributing to PraxiAlpha.
> **Reference this before every commit.**

---

## 🌿 Branch Naming Convention

All work happens on feature branches. Never commit directly to `main`.

### Format
```
<type>/<short-description>
```

### Branch Types
| Prefix | When to Use | Example |
|--------|-------------|---------|
| `feat/` | New feature or capability | `feat/full-backfill` |
| `fix/` | Bug fix | `fix/batch-insert-limit` |
| `docs/` | Documentation only | `docs/update-architecture` |
| `refactor/` | Code restructuring (no behavior change) | `refactor/fetcher-error-handling` |
| `ci/` | CI/CD pipeline changes | `ci/add-github-actions` |
| `test/` | Adding or updating tests | `test/backfill-edge-cases` |
| `chore/` | Maintenance, deps, config | `chore/update-dependencies` |

### Rules
- Use lowercase and hyphens (no spaces, no underscores)
- Keep it short but descriptive
- Branch off `main`, merge back via PR

---

## 📝 Commit Message Convention

We follow **[Conventional Commits](https://www.conventionalcommits.org/)** — the industry standard.

### Format
```
<type>(<scope>): <short summary>

<optional body — what and why, not how>

<optional footer — references, breaking changes>
```

### Types
| Type | When to Use | Example |
|------|-------------|---------|
| `feat` | New feature | `feat(pipeline): add splits and dividends backfill` |
| `fix` | Bug fix | `fix(backfill): batch inserts to avoid PG parameter limit` |
| `docs` | Documentation change | `docs: add CONTRIBUTING.md with commit conventions` |
| `style` | Formatting, no logic change | `style: apply ruff formatting across codebase` |
| `refactor` | Code change, no behavior change | `refactor(fetcher): extract validation into separate method` |
| `test` | Adding or updating tests | `test(pipeline): add OHLCV validation edge cases` |
| `ci` | CI/CD config changes | `ci: add GitHub Actions workflow for lint and tests` |
| `chore` | Deps, config, tooling | `chore: update sqlalchemy to 2.1` |
| `perf` | Performance improvement | `perf(backfill): parallelize API calls with asyncio.gather` |

### Scopes (Optional but Recommended)
| Scope | Covers |
|-------|--------|
| `pipeline` | Data pipeline (fetchers, validators, backfill) |
| `backfill` | Backfill script specifically |
| `models` | Database models |
| `api` | FastAPI routes and endpoints |
| `tasks` | Celery tasks and scheduling |
| `risk` | Risk management layer |
| `journal` | Trade journal |
| `education` | Education module |
| `ui` | Frontend / dashboard |

### Rules
1. **Subject line** — imperative mood, lowercase, no period, max 72 chars
   - ✅ `feat(pipeline): add FRED macro data fetcher`
   - ❌ `Added FRED macro data fetcher.`
   - ❌ `feat(pipeline): Add FRED Macro Data Fetcher`
2. **Body** (optional) — explain *what* and *why*, not *how*. Wrap at 80 chars.
3. **Footer** (optional) — reference issues: `Closes #12`, `Refs #5`
4. **No emojis in commit messages** — keep it clean and parseable

### Examples

**Simple commit:**
```
feat(models): add StockSplit and StockDividend models
```

**Commit with body:**
```
fix(backfill): batch inserts to avoid PostgreSQL parameter limit

PostgreSQL has a hard limit of ~32,767 parameters per query. Stocks
with 9,000+ rows (e.g., AAPL since 1990) exceeded this limit, causing
silent insert failures. Fixed by batching inserts at 3,000 rows per
batch (24,000 params, safely under the limit).
```

**Commit with scope and footer:**
```
ci: add GitHub Actions workflow for lint, format, and tests

- Job 1: ruff check + ruff format + mypy
- Job 2: pytest with TimescaleDB and Redis service containers

Refs #3
```

---

## 🔄 Git Workflow

### Day-to-Day Process
```bash
# 1. Start from up-to-date main
git checkout main
git pull origin main

# 2. Create a feature branch
git checkout -b feat/my-feature

# 3. Do work, make commits (following commit convention above)
git add -A
git commit -m "feat(scope): short description"

# 4. Push and open a PR
git push origin feat/my-feature
# → Open PR on GitHub → CI runs automatically

# 5. After CI passes and review is done → merge via GitHub
# 6. Clean up local branch
git checkout main
git pull origin main
git branch -d feat/my-feature
```

### When Multiple Commits Are Needed
It's fine to have multiple commits on a branch. Each should be a logical unit:
```
feat(models): add StockSplit model
feat(models): add StockDividend model
feat(backfill): add splits and dividends to backfill pipeline
test(backfill): add tests for splits/dividends backfill
docs: update BUILD_LOG with Session 2 results
```

---

## �️ Branch Protection & Merge Settings

### Merge Strategy: Squash and Merge Only
All PRs are merged via **squash and merge** (the only merge option enabled).
This produces a clean, linear commit history on `main` where every commit
corresponds to a single PR.

- **Commit title** = PR title (use Conventional Commits format)
- **Commit body** = PR description
- **Feature branches are auto-deleted** after merge

### Branch Protection
Direct pushes to `main` are blocked. All changes must go through a PR.

| Rule | Status |
|------|--------|
| Require PR to merge | ✅ Enforced (GitHub branch protection) |
| Block direct pushes to main | ✅ Enforced (GitHub branch protection, incl. admins) |
| No force pushes to main | ✅ Enforced (GitHub branch protection) |
| Require linear history | ✅ Enforced (GitHub branch protection) |
| No branch deletion (main) | ✅ Enforced (GitHub branch protection) |
| Squash merge only | ✅ Enforced (repo settings) |
| Auto-delete merged branches | ✅ Enabled (repo settings) |
| Pre-push local CI check | ✅ Enforced (`scripts/ci_check.sh` via git hook) |

> Branch protection is enforced for **all users including admins** via
> GitHub Pro. The pre-push hook provides an additional local safety net.

---

## �📚 Documentation Checklist

**Every PR / merge to `main` must update:**

- [ ] `docs/BUILD_LOG.md` — What was done, results, issues encountered
- [ ] `docs/CHANGELOG.md` — What changed (Added/Fixed/Changed sections)
- [ ] `WORKFLOW.md` — Last completed session, next session, last updated date
- [ ] `docs/PROGRESS.md` — Component status, phase checklists, session history, roadmap
- [ ] `docs/ARCHITECTURE.md` — If file structure, tables, or systems changed
- [ ] `DESIGN_DOC.md` — If scope, decisions, or roadmap changed

---

## ✅ PR Checklist

Before merging any PR:

- [ ] CI passes (lint, format, types, tests)
- [ ] Commit messages follow Conventional Commits
- [ ] Documentation updated (BUILD_LOG, CHANGELOG, ARCHITECTURE if applicable)
- [ ] No unused imports or dead code
- [ ] No secrets or API keys in code

---

*Last updated: 2026-03-17*
