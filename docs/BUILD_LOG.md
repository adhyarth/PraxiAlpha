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

### Session 2 — (Next Session)

_To be filled in..._

---

## Lessons Learned

| # | Lesson | Context |
|---|--------|---------|
| 1 | API keys expire — always test before building pipelines | Both EODHD and FRED keys were invalid on first try |
| 2 | TimescaleDB requires partition column in primary key | Can't use a simple `id` PK on hypertables |
| 3 | Docker volumes persist data through container restarts | VS Code crash didn't lose any database data |
| 4 | `lru_cache` + `pydantic-settings` = cached settings at import time | Need container recreation (not just restart) when .env changes |
| 5 | Setuptools auto-discovery fails with multiple top-level dirs | Must explicitly set `packages.find.include` in pyproject.toml |

---

*This log is updated after each work session.*
