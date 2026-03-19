# 🏗️ PraxiAlpha — Engineering Assessment

> **Purpose:** Honest evaluation of the project's software engineering maturity,
> scored as if PraxiAlpha were a commercially sold product. Use this to identify
> strengths, gaps, and prioritize improvements.
>
> **Last assessed:** 2026-03-19 (after Session 14 — 215 tests, 58M+ OHLCV rows)

---

## Overall Rating: 7.5 / 10 — Strong Foundation, Not Yet Production-Ready

This is significantly above average for a solo/small-team project and shows genuine
software engineering discipline. But there are gaps that a commercial product would
need to close before going to market.

---

## Strengths

### 1. Architecture & Separation of Concerns — 9/10
- Clean layered architecture: API → Service → Data Pipeline → Database
- Service layer pattern consistently applied (candle service, search service, stock service, calendar fetcher)
- FastAPI routes are thin controllers — business logic lives in services
- Streamlit UI is decoupled from the backend via HTTP API calls (not direct DB access)
- TimescaleDB continuous aggregates for materialized views (weekly/monthly/quarterly) — a sophisticated choice that most commercial products get wrong

### 2. Documentation — 9/10
Exceptionally well-documented for any project, commercial or otherwise:
- `DESIGN_DOC.md` — architecture, mental models, phase roadmap
- `docs/BUILD_LOG.md` — full session-by-session record with rationale
- `docs/PROGRESS.md` — project status, crash recovery
- `WORKFLOW.md` — repeatable process for any contributor
- `docs/ARCHITECTURE.md` — file structure, schema, system diagram
- `CONTRIBUTING.md` — conventions, branch naming, commit format
- `docs/CHANGELOG.md` — Keep a Changelog format

Most commercial products have worse documentation than this.

### 3. Testing Discipline — 8/10
- 215 tests across 14 sessions — tests are written alongside code, not as afterthought
- Service layer tests use proper mocking (`AsyncMock`, patching)
- CI-aware test guards (`importorskip`, `find_spec` skipif) for heavy deps
- Tests cover edge cases (empty results, invalid inputs, boundary conditions)

### 4. Data Engineering — 8.5/10
- 58M+ OHLCV rows with TimescaleDB hypertables
- Continuous aggregates for multi-timeframe rollups
- Checkpoint-based backfill with crash recovery
- Atomic file writes for progress tracking
- Batch insert sizing to respect PostgreSQL's 32K parameter limit

### 5. Process & Workflow — 8/10
- Conventional Commits, PR-based workflow, code review cycle
- Checkpoint-based development for crash resilience
- Pre-push CI hooks
- Documented pitfalls to prevent regression

---

## Gaps (What's Missing for Commercial Grade)

### 1. Authentication & Authorization — 0/10 ❌
No auth at all. Every API endpoint is publicly accessible. A commercial product needs:
- [ ] User authentication (JWT/OAuth2)
- [ ] Role-based access control
- [ ] API rate limiting
- [ ] Session management

### 2. Error Handling & Observability — 3/10 ⚠️
- [ ] Structured logging (`structlog` or JSON logging)
- [ ] Request tracing (correlation IDs)
- [ ] Error tracking service (Sentry, Datadog)
- [ ] Metrics/monitoring (Prometheus, Grafana)
- [ ] Health check beyond basic `/health` endpoint
- [ ] Custom error response schemas for API

A commercial product needs you to **know when things break before your users tell you**.

### 3. Security — 2/10 ⚠️
- [ ] Secrets manager (not just `.env` files)
- [ ] Input sanitization beyond FastAPI's basic validation
- [ ] CORS configuration
- [ ] Rate limiting
- [ ] SQL injection audit (SQLAlchemy parameterized queries are good, but not explicitly audited)
- [ ] Database credentials in a vault, not plaintext `.env`

### 4. Deployment & Infrastructure — 2/10 ⚠️
- [ ] Kubernetes or cloud deployment (beyond Docker Compose)
- [ ] CI/CD pipeline to staging/production (GitHub Actions only runs lint/tests today)
- [ ] Blue-green or canary deployment strategy
- [ ] Database migration strategy for zero-downtime deploys
- [ ] Backup/restore procedures for the 58M row database
- [ ] SSL/TLS termination

### 5. Performance & Scalability — 5/10
- ✅ TimescaleDB is a great foundation for time-series at scale
- ✅ Continuous aggregates avoid expensive runtime queries
- [ ] Connection pooling (PgBouncer)
- [ ] Caching layer (Redis is in Docker but not wired to the API)
- [ ] Pagination on list endpoints
- [ ] Query performance monitoring (`pg_stat_statements`)
- [ ] Horizontal scaling story (single-instance architecture today)

### 6. Data Validation & Integrity — 6/10
- ✅ Input validation via FastAPI `Query()` and Pydantic
- ✅ Data pipeline has a `DataValidator`
- [ ] Data quality monitoring (stale data alerts, missing ticker detection)
- [ ] Reconciliation between source (EODHD) and local data
- [ ] Audit trail for data mutations

### 7. Frontend / UX — 4/10
- [ ] Production frontend (Streamlit is a prototyping tool, not production-ready)
- [ ] Responsive design / mobile support
- [ ] Loading states, error boundaries, retry logic in UI
- [ ] User preferences persistence
- [ ] Chart polish (crosshair sync, drawing tools)

### 8. Automated Testing Gaps — 6/10
- [ ] Integration tests (actual DB queries against a test database)
- [ ] End-to-end tests (API → DB → response validation)
- [ ] Load/performance tests
- [ ] Contract tests for the API
- [ ] Coverage reporting (`pytest-cov`)

---

## Scorecard

| Dimension | Current | Commercial Minimum | Gap |
|-----------|---------|-------------------|-----|
| Architecture | 9/10 | 7/10 | ✅ Exceeds |
| Documentation | 9/10 | 6/10 | ✅ Exceeds |
| Testing | 8/10 | 8/10 | ✅ Meets |
| Data Engineering | 8.5/10 | 7/10 | ✅ Exceeds |
| Process/Workflow | 8/10 | 7/10 | ✅ Exceeds |
| Auth & Security | 1/10 | 8/10 | ❌ **-7** |
| Observability | 3/10 | 7/10 | ❌ **-4** |
| Deployment/Infra | 2/10 | 7/10 | ❌ **-5** |
| Performance/Scale | 5/10 | 7/10 | ⚠️ **-2** |
| Data Integrity | 6/10 | 7/10 | ⚠️ **-1** |
| Frontend/UX | 4/10 | 7/10 | ⚠️ **-3** |
| Test Coverage | 6/10 | 8/10 | ⚠️ **-2** |

---

## The Bottom Line

**What's built is an excellent engineering foundation** — the architecture, data layer,
documentation, and development process are genuinely strong. Most startups ship v1
with worse fundamentals than this.

**What makes it not-yet-commercial** is everything around the core: security,
observability, deployment, and production hardening. These are the things that keep
a product running reliably at 3 AM when you're asleep.

The hard technical problems (data pipeline, time-series storage, multi-timeframe
aggregation) are solved well. The remaining work is "boring but critical"
infrastructure — auth, logging, deployment, monitoring. That's actually a good
position to be in.

---

## Improvement Priority (suggested order)

| Priority | Area | Why First |
|----------|------|-----------|
| 🔴 P0 | Auth & Security | Can't ship without it. Everything else is moot if the API is open. |
| 🔴 P0 | Observability | Need to know when things break before users do. |
| 🟡 P1 | Deployment/Infra | Can't deliver value without a way to ship to users. |
| 🟡 P1 | Test Coverage | Coverage reporting + integration tests close the confidence gap. |
| 🟢 P2 | Performance/Scale | TimescaleDB foundation is solid; add caching + pooling when load demands it. |
| 🟢 P2 | Data Integrity | Monitoring + reconciliation prevent silent data drift. |
| 🔵 P3 | Frontend/UX | Streamlit works for now; replace when product-market fit is proven. |

---

## Revision History

| Date | Assessed At | Score | Notes |
|------|-------------|-------|-------|
| 2026-03-19 | Session 14 (215 tests, 58M rows) | **7.5/10** | Initial assessment. Strong foundation, gaps in auth/security/observability/deployment. |
