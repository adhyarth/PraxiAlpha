# 🏗️ PraxiAlpha — Architecture & Technology Guide

> **"Disciplined action that generates alpha."**
>
> This document explains every piece of the PraxiAlpha system — what it does, why it exists, and how it connects to everything else. Updated as we build.

---

## 📋 Table of Contents

- [The Big Picture](#-the-big-picture)
- [What Are We Building?](#-what-are-we-building)
- [The Tech Stack (Plain English)](#-the-tech-stack-plain-english)
- [Docker Containers Explained](#-docker-containers-explained)
- [The Data Pipeline](#-the-data-pipeline)
- [Database Design](#-database-design)
- [API Layer](#-api-layer)
- [Project File Structure](#-project-file-structure)
- [Key Concepts Glossary](#-key-concepts-glossary)

---

## 🎯 The Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR COMPUTER                            │
│                                                                 │
│  ┌──────────────────── Docker ────────────────────────────────┐  │
│  │                                                           │  │
│  │  ┌─────────┐   ┌──────────┐   ┌────────────────────────┐ │  │
│  │  │   📊    │   │   🧠     │   │        🗄️             │ │  │
│  │  │ FastAPI │◄─►│  Celery  │◄─►│  PostgreSQL            │ │  │
│  │  │  (API)  │   │ (Worker) │   │  + TimescaleDB         │ │  │
│  │  │ :8000   │   │          │   │  (All your data)       │ │  │
│  │  └────┬────┘   └────┬─────┘   └────────────────────────┘ │  │
│  │       │              │                                    │  │
│  │       │         ┌────┴─────┐   ┌────────────────────────┐ │  │
│  │       │         │   ⏰     │   │        📮             │ │  │
│  │       │         │  Celery  │◄─►│     Redis              │ │  │
│  │       │         │  (Beat)  │   │  (Message broker)      │ │  │
│  │       │         └──────────┘   └────────────────────────┘ │  │
│  │       │                                                   │  │
│  └───────┼───────────────────────────────────────────────────┘  │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────┐                                               │
│  │   🌐 You     │  http://localhost:8000/docs                   │
│  │  (Browser)   │  Interactive API docs                         │
│  └──────────────┘                                               │
│                                                                 │
│          ▲                                                      │
│          │  API calls                                           │
│          │                                                      │
│  ┌───────┴──────┐   ┌──────────────┐                            │
│  │   📡 EODHD  │   │   📡 FRED    │                            │
│  │ (Stock data) │   │ (Macro data) │                            │
│  │  External    │   │  External    │                            │
│  └──────────────┘   └──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

**In one sentence:** Docker runs 5 isolated services on your Mac that together form a system to collect, store, analyze, and serve stock market data through a web API.

---

## 🔨 What Are We Building?

PraxiAlpha is a **systematic trading and education platform**. Think of it in layers:

| Layer | What It Does | Status |
|-------|-------------|--------|
| **1. Data Pipeline** | Fetches & stores 30+ years of stock data | ✅ Complete |
| **2. Analysis Engine** | Calculates indicators, signals, screens stocks | 🟡 In Progress |
| **3. Trading System** | Paper trading, backtesting strategies | ⬜ Not Started |
| **4. Risk Manager** | Position sizing, portfolio risk monitoring | ⬜ Not Started |
| **5. Education Hub** | Lessons, concepts, trade journals | ⬜ Not Started |
| **6. Dashboard** | Visual interface (Streamlit → React) | 🟡 In Progress |

We're in **Phase 2** — building charting and dashboard features on top of the completed data foundation.

---

## 🧰 The Tech Stack (Plain English)

### Why Each Technology Was Chosen

| Technology | What It Is | Why We Use It | Analogy |
|-----------|-----------|---------------|---------|
| **Python 3.13** | Programming language | Best for finance/data work, huge ecosystem | The language we speak |
| **FastAPI** | Web framework | Blazing fast API server, auto-generates docs | The front door to our system |
| **PostgreSQL** | Database | Battle-tested, handles complex queries | The filing cabinet |
| **TimescaleDB** | PostgreSQL extension | Optimized for time-series data (stock prices!) | A turbocharger for the filing cabinet |
| **Redis** | In-memory cache | Lightning-fast message passing between services | The office whiteboard |
| **Celery** | Task queue | Runs background jobs (data fetching) without blocking the API | The office workers doing tasks |
| **Docker** | Containerization | Packages everything so it runs identically anywhere | Shipping containers for software |
| **SQLAlchemy** | ORM (Object-Relational Mapper) | Write Python instead of raw SQL | A translator between Python and the database |
| **Alembic** | Migration tool | Tracks database schema changes over time | Version control for the database |
| **EODHD** | Data provider API | 30+ years of US stock data, good value | Our stock data supplier |
| **FRED** | Federal Reserve API | Free macro data (interest rates, inflation, etc.) | Our economics data supplier |

---

## 🐳 Docker Containers Explained

Docker runs **5 separate containers** on your Mac. Think of each as an isolated mini-computer running one service:

### Container 1: `praxialpha-db` — The Database
```
📦 Image: timescale/timescaledb:latest-pg16
🔌 Port:  5432
💾 Data:  Persisted in Docker volume "pgdata"
```

**What it does:** Stores ALL your data — stock tickers, daily prices, macro indicators, everything. PostgreSQL is the database engine; TimescaleDB is a plugin that makes it handle time-series data (like daily stock prices) 10-100x faster than vanilla PostgreSQL.

**Why it's critical:** Without this, we have no persistent storage. Every stock price, every calculation, every user setting lives here.

**Real-world analogy:** This is the warehouse. Everything gets stored here in organized shelves (tables).

---

### Container 2: `praxialpha-redis` — The Message Broker & Cache
```
📦 Image: redis:7-alpine
🔌 Port:  6379
💾 Data:  Persisted in Docker volume "redisdata"
```

**What it does:** Two jobs:
1. **Message broker** — When we say "go fetch AAPL data," that message goes into Redis. Celery workers pick it up from there.
2. **Cache** — Stores frequently-accessed data in memory for instant retrieval (instead of hitting the database every time).

**Why it's critical:** Without Redis, the API and the background workers can't communicate. It's the glue between "I want data" and "here's your data."

**Real-world analogy:** This is the office bulletin board. Someone posts a task, workers check the board and grab tasks to complete.

---

### Container 3: `praxialpha-app` — The API Server
```
📦 Image: praxialpha-app (built from our Dockerfile)
🔌 Port:  8000
🌐 URL:   http://localhost:8000/docs
```

**What it does:** Runs FastAPI — our web server that exposes REST API endpoints. When you (or a frontend app) want to get stock data, list tickers, run analysis, etc., you make HTTP requests to this server.

**Why it's critical:** This is the interface to the entire system. No API = no way to interact with anything programmatically.

**Key endpoints right now:**
- `GET /health` — System health check
- `GET /api/v1/stocks/` — List stocks in the database
- `GET /api/v1/stocks/count` — Count of stocks
- `GET /api/v1/stocks/{ticker}` — Get details for a ticker
- `GET /docs` — Interactive Swagger documentation

**Real-world analogy:** This is the receptionist. You tell them what you need, they go get it from the warehouse (database) and hand it to you.

---

### Container 4: `praxialpha-celery-worker` — The Background Worker
```
📦 Image: praxialpha-celery-worker (same Dockerfile, different command)
⚙️ Concurrency: 4 (handles 4 tasks simultaneously)
```

**What it does:** Picks up tasks from Redis and executes them in the background. Tasks include:
- Fetching OHLCV data from EODHD for a stock
- Backfilling historical data
- Running analysis calculations
- Anything that takes too long to do in a web request

**Why it's critical:** Without workers, every data fetch would block the API. Imagine asking for 10,000 stocks' data through a web request — it would time out. Workers handle heavy lifting asynchronously.

**Currently registered tasks:**
```
backend.tasks.data_tasks.daily_ohlcv_update
backend.tasks.data_tasks.daily_macro_update
backend.tasks.data_tasks.backfill_stock
backend.tasks.data_tasks.backfill_all_stocks
```

**Real-world analogy:** These are the warehouse workers. They get instructions from the bulletin board (Redis), go to the supplier (EODHD/FRED), pick up the goods, and stock the warehouse (database).

---

### Container 5: `praxialpha-celery-beat` — The Scheduler
```
📦 Image: praxialpha-celery-beat (same Dockerfile, different command)
⏰ Schedule: Runs on a cron-like schedule
```

**What it does:** A clock that posts tasks to Redis on a schedule. Right now it's configured to:
- **6:00 PM ET daily** → Post "daily_ohlcv_update" task (fetch today's prices for all stocks)
- **6:30 PM ET daily** → Post "daily_macro_update" task (fetch latest macro indicators)

**Why it's critical:** Without Beat, we'd have to manually trigger data updates every day. Beat automates this — once the full backfill is done, new data flows in automatically every evening after market close.

**Real-world analogy:** This is the manager who comes in every evening at 6 PM and posts new task orders on the bulletin board for the workers.

---

## 📊 The Data Pipeline

### How Data Flows Into the System

```
Step 1: POPULATE                Step 2: BACKFILL              Step 3: DAILY AUTO-UPDATE
─────────────────              ─────────────────             ─────────────────────────

  EODHD API                      EODHD API                     Celery Beat (6 PM ET)
      │                              │                              │
      ▼                              ▼                              ▼
  Fetch all US                  For each ticker:               Posts task to Redis
  ticker symbols                fetch 30+ years                     │
  (~49,000)                     of daily OHLCV                      ▼
      │                              │                         Celery Worker
      ▼                              ▼                         picks up task
  Insert into                   Validate data:                      │
  `stocks` table                - Remove bad rows                   ▼
      │                         - Fix high < low               Fetches bulk EOD
      ▼                         - Drop duplicates              for all tickers
  ✅ 49,225 tickers                  │                         (1 API call!)
  now in database                    ▼                              │
                                Upsert into                         ▼
                                `daily_ohlcv`                  Upserts into DB
                                (TimescaleDB                        │
                                 hypertable)                        ▼
                                     │                         ✅ Up-to-date
                                     ▼                         every evening
                                ✅ ~75M+ rows
                                of price history

  ◄── DONE ──►                 ◄── IN PROGRESS ──►           ◄── AFTER BACKFILL ──►
```

### What "Backfill" Means

"Backfill" = filling in historical data. EODHD has stock prices going back to the 1990s. We want ALL of it so we can:
- Backtest strategies against real historical data
- Calculate long-term indicators (200-day moving averages, etc.)
- Study how stocks behaved during past crashes, recessions, bull markets

### The 3-Step Process

| Step | Command | What It Does | Status |
|------|---------|-------------|--------|
| 1. Populate | `--populate` | Fetches 49,225 US ticker symbols from EODHD | ✅ Done |
| 2. Test | `--test` | Backfills 10 blue-chip stocks (AAPL, MSFT, etc.) as a smoke test | ✅ Done (67,919 records) |
| 3. Full | `--all` | Backfills ALL 49,225 tickers (~75M+ rows, takes hours) | ⬜ After test |

---

## 🗄️ Database Design

### Tables We Have Right Now

#### `stocks` — The Universe of Tickers
```sql
-- 49,225 rows (every US-listed stock and ETF)
┌────────────────┬──────────────────────────────┐
│ Column         │ Purpose                      │
├────────────────┼──────────────────────────────┤
│ id             │ Auto-increment primary key   │
│ ticker         │ "AAPL", "MSFT", etc.        │
│ name           │ "Apple Inc"                  │
│ exchange       │ "NYSE", "NASDAQ", "AMEX"     │
│ asset_type     │ "Common Stock", "ETF"        │
│ sector         │ "Technology", "Healthcare"   │
│ industry       │ More specific classification │
│ is_active      │ Currently trading?           │
│ is_delisted    │ Was removed from exchange?   │
│ eodhd_code     │ "AAPL.US" (API identifier)  │
│ earliest_date  │ Oldest data we have          │
│ latest_date    │ Most recent data we have     │
│ total_records  │ How many days of data        │
└────────────────┴──────────────────────────────┘
```

#### `daily_ohlcv` — Price History (TimescaleDB Hypertable)
```sql
-- Target: ~75.6 million rows
┌────────────────┬──────────────────────────────┐
│ Column         │ Purpose                      │
├────────────────┼──────────────────────────────┤
│ stock_id       │ → links to stocks.id         │
│ date           │ Trading day (2024-01-15)     │
│ open           │ Price at market open         │
│ high           │ Highest price that day       │
│ low            │ Lowest price that day        │
│ close          │ Price at market close        │
│ adjusted_close │ Close adjusted for splits    │
│ volume         │ # shares traded that day     │
└────────────────┴──────────────────────────────┘
```

**Why "adjusted close"?** When a stock splits (e.g., 4:1), the price drops to 1/4 overnight, but you didn't lose money. Adjusted close accounts for splits and dividends so historical comparisons are accurate.

**Why TimescaleDB hypertable?** Regular PostgreSQL stores all rows in one big pile. TimescaleDB automatically partitions rows by time (e.g., one chunk per month). Queries like "get AAPL's price for the last 90 days" become 10-100x faster because it only scans 3 chunks instead of millions of rows.

#### `stock_splits` — Split History
```sql
-- Tracks stock split events
┌────────────────┬──────────────────────────────────────┐
│ Column         │ Purpose                              │
├────────────────┼──────────────────────────────────────┤
│ id             │ Auto-increment primary key           │
│ stock_id       │ → links to stocks.id                 │
│ date           │ Split date                           │
│ split_ratio    │ Raw string: "7.000000/1.000000"      │
│ numerator      │ 7.0 (new shares per old share)       │
│ denominator    │ 1.0 (old shares)                     │
└────────────────┴──────────────────────────────────────┘
```

**Why track splits?** Even though `adjusted_close` accounts for splits, having explicit split records lets us verify data integrity, display split events on charts, and explain sudden price drops to learners.

#### `stock_dividends` — Dividend History
```sql
-- Tracks dividend payment events
┌────────────────────┬──────────────────────────────────────┐
│ Column             │ Purpose                              │
├────────────────────┼──────────────────────────────────────┤
│ id                 │ Auto-increment primary key           │
│ stock_id           │ → links to stocks.id                 │
│ date               │ Ex-dividend date                     │
│ value              │ Dividend per share (adjusted)        │
│ unadjusted_value   │ Raw dividend per share               │
│ currency           │ "USD"                                │
│ period             │ "Quarterly", "Annual", etc.          │
│ declaration_date   │ When announced                       │
│ record_date        │ Who qualifies                        │
│ payment_date       │ When paid out                        │
└────────────────────┴──────────────────────────────────────┘
```

**Why track dividends?** For total return calculations (price appreciation + dividends), income-focused screening, and teaching users about dividend investing.

#### `macro_data` — Economic Indicators from FRED
```sql
-- Tracks macro indicators over time
┌────────────────┬──────────────────────────────────────┐
│ Column         │ Purpose                              │
├────────────────┼──────────────────────────────────────┤
│ indicator_code │ FRED series ID ("DGS10", "VIXCLS")   │
│ indicator_name │ "10-Year Treasury Yield"              │
│ date           │ Observation date                      │
│ value          │ The actual value                      │
│ source         │ "FRED"                                │
└────────────────┴──────────────────────────────────────┘
```

**Indicators we're tracking:**

| Code | Name | Why It Matters |
|------|------|---------------|
| DGS10 | 10-Year Treasury Yield | Risk-free rate, affects stock valuations |
| DGS2 | 2-Year Treasury Yield | Short-term rate expectations |
| T10Y2Y | 10Y-2Y Spread | Yield curve — inverts before recessions |
| DFF | Fed Funds Rate | The Fed's interest rate tool |
| VIXCLS | VIX | Market fear gauge |
| DCOILWTICO | WTI Crude Oil | Energy costs affect all businesses |
| T10YIE | 10-Year Breakeven Inflation Rate | Market inflation expectations |
| M2SL | M2 Money Supply | How much money is in the system |
| WALCL | Fed Balance Sheet | Quantitative easing/tightening |
| UNRATE | Unemployment Rate | Labor market health |
| CPIAUCSL | CPI | Inflation |
| PCEPI | PCE Price Index | Fed's preferred inflation measure |

#### `trades` — Trading Journal (Planned — Session 16)
```sql
-- Parent trade record: one row per trade entry
┌─────────────────────┬─────────────────────────────────────────────────┐
│ Column              │ Purpose                                         │
├─────────────────────┼─────────────────────────────────────────────────┤
│ id                  │ UUID primary key                                │
│ ticker              │ "AAPL", "TSLA" — the traded symbol              │
│ direction           │ ENUM: 'long' / 'short'                         │
│ asset_type          │ ENUM: 'shares' / 'options'                     │
│ trade_type          │ ENUM: 'single_leg' / 'multi_leg' (options)     │
│ timeframe           │ ENUM: 'daily'/'weekly'/'monthly'/'quarterly'   │
│ entry_date          │ When the trade was entered                      │
│ entry_price         │ Entry price per share/contract                  │
│ total_quantity      │ Total shares/contracts entered                  │
│ stop_loss           │ Optional stop loss price                        │
│ take_profit         │ Optional take profit target                     │
│ tags                │ JSONB array: ["breakout", "earnings-play"]      │
│ comments            │ Free-form notes / trade reasoning               │
│ created_at          │ Record creation time                            │
│ updated_at          │ Last modification time                          │
└─────────────────────┴─────────────────────────────────────────────────┘
-- NOTE: status, remaining_quantity, realized_pnl, return_pct,
-- avg_exit_price, and r_multiple are computed at the API/service
-- layer from trade_exits data. They are NOT stored columns.
-- See "Computed fields" section below.
```

**Key design decisions:**
- **UUID** primary key (not auto-increment) — less predictable than sequential IDs, which makes simple ID guessing harder. Proper authentication and authorization are still required to protect data exposed via APIs.
- **`status`** is derived from exit fills, not manually set — prevents stale state.
- **`tags`** as JSONB array — fully flexible, no fixed taxonomy. Supports filtering via `@>` operator.
- **`timeframe`** records which chart interval informed the trade decision. The PDF report uses this to generate the matching chart type.

**Computed fields (API-level, not stored in the DB):**

The following fields are **not stored as database columns**. They are computed at the service/API layer when reading trade data:

| Field | Derivation |
|-------|-----------|
| `status` | If no exits → `open`; if `sum(exit.quantity) < total_quantity` → `partial`; if equal → `closed` |
| `remaining_quantity` | `total_quantity - sum(exit.quantity)` |
| `realized_pnl` | `sum((exit.price - entry_price) * exit.quantity * direction_sign)` |
| `return_pct` | `realized_pnl / (entry_price * total_quantity) * 100` |
| `avg_exit_price` | `sum(exit.price * exit.quantity) / sum(exit.quantity)` |
| `r_multiple` | `realized_pnl / (abs(entry_price - stop_loss) * total_quantity)` — only when stop_loss is set |

This avoids data synchronization issues (no triggers or materialized views needed). The trade record stores only the raw entry data; all derived metrics are calculated on read.

#### `trade_exits` — Partial/Full Exit Fills
```sql
-- Each exit of a trade (supports partial exits)
┌─────────────────────┬──────────────────────────────────────────┐
│ Column              │ Purpose                                  │
├─────────────────────┼──────────────────────────────────────────┤
│ id                  │ UUID primary key                         │
│ trade_id            │ → links to trades.id (FK, CASCADE)       │
│ exit_date           │ When this portion was exited             │
│ exit_price          │ Exit price for this fill                 │
│ quantity            │ Shares/contracts exited in this fill     │
│ comments            │ Optional note for this specific exit     │
└─────────────────────┴──────────────────────────────────────────┘
```

**Why separate exits?** A single trade can have multiple exits (scale-out strategy). E.g., enter 100 shares, exit 50 at +5%, exit 50 more at +10%. Each exit is an independent record.

#### `trade_legs` — Multi-Leg Option Trades
```sql
-- Individual legs of a multi-leg options trade
┌─────────────────────┬──────────────────────────────────────────┐
│ Column              │ Purpose                                  │
├─────────────────────┼──────────────────────────────────────────┤
│ id                  │ UUID primary key                         │
│ trade_id            │ → links to trades.id (FK, CASCADE)       │
│ leg_type            │ ENUM: buy_call/sell_call/buy_put/sell_put│
│ strike              │ Strike price                             │
│ expiry              │ Expiration date                          │
│ quantity            │ Number of contracts for this leg         │
│ premium             │ Price paid/received per contract         │
└─────────────────────┴──────────────────────────────────────────┘
```

**Why separate legs?** Multi-leg strategies (vertical spreads, iron condors, straddles) involve multiple simultaneous positions. Each leg has its own strike, expiry, and premium.

#### `trade_snapshots` — Post-Close "What-If" Tracking (Planned)
```sql
-- Price snapshots after a trade is closed, for hypothetical PnL analysis
┌─────────────────────┬──────────────────────────────────────────────────┐
│ Column              │ Purpose                                          │
├─────────────────────┼──────────────────────────────────────────────────┤
│ id                  │ UUID primary key                                 │
│ trade_id            │ → links to trades.id (FK, CASCADE)               │
│ snapshot_date       │ The date of the price snapshot                   │
│ close_price         │ Closing price of the ticker on that date         │
│ hypothetical_pnl    │ PnL if full position held to this date           │
│ hypothetical_pnl_pct│ PnL % relative to avg entry price               │
│ created_at          │ Record creation time                             │
└─────────────────────┴──────────────────────────────────────────────────┘
-- UNIQUE constraint: (trade_id, snapshot_date)
```

**Key design decisions:**
- **Auto-generated via Celery task** — a periodic task scans closed trades, fetches the closing price from `daily_ohlcv` (or weekly/monthly aggregates), computes hypothetical PnL, and inserts snapshot rows.
- **Full position assumed** — hypothetical PnL is calculated as if the *entire original position* was still open. No partial/hybrid scenarios.
- **Direction-aware PnL** — long trades: `(close_price - entry_price) * total_quantity`; short trades: `(entry_price - close_price) * total_quantity`.
- **Max tracking duration by timeframe:**
  - Daily trades → 30 calendar days (snapshot every trading day)
  - Weekly trades → 16 calendar weeks (snapshot weekly)
  - Monthly trades → 18 calendar months (snapshot monthly)
- **Tracking stops** when the max duration is reached or no more price data is available (e.g., stock delisted).
- **Unique constraint** on `(trade_id, snapshot_date)` prevents duplicate snapshots and allows safe upsert.

---

## 🌐 API Layer

FastAPI auto-generates interactive documentation. Once running, visit:

**📖 http://localhost:8000/docs** — Swagger UI (try endpoints live!)

### Current Endpoints

| Method | Path | What It Does |
|--------|------|-------------|
| `GET` | `/health` | System health check |
| `GET` | `/` | Welcome message |
| `GET` | `/api/v1/stocks/` | List stocks (with filtering) |
| `GET` | `/api/v1/stocks/count` | Count active stocks |
| `GET` | `/api/v1/stocks/{ticker}` | Get one stock's details |

More endpoints will be added as we build analysis, trading, and other modules.

#### Planned: Trading Journal Endpoints (Session 16)
| Method | Path | What It Does |
|--------|------|-------------|
| `GET` | `/api/v1/journal/` | List trades (with filters: ticker, status, timeframe, date range, tags) |
| `POST` | `/api/v1/journal/` | Create a new trade entry |
| `GET` | `/api/v1/journal/{trade_id}` | Get trade details (includes exits & legs) |
| `PUT` | `/api/v1/journal/{trade_id}` | Update trade (tags, comments, stop/TP) |
| `DELETE` | `/api/v1/journal/{trade_id}` | Delete a trade |
| `POST` | `/api/v1/journal/{trade_id}/exits` | Add a partial/full exit fill |
| `POST` | `/api/v1/journal/{trade_id}/legs` | Add an option leg |
| `GET` | `/api/v1/journal/report` | Generate PDF report with charts (Session 18) |

#### Planned: Post-Close What-If Endpoints (Session 19)
| Method | Path | What It Does |
|--------|------|-------------|
| `GET` | `/api/v1/journal/{trade_id}/snapshots` | List post-close "what-if" snapshots |
| `GET` | `/api/v1/journal/{trade_id}/what-if` | Summary: best/worst hypothetical PnL vs actual exit |

---

## � CI/CD Pipeline

### GitHub Actions (`.github/workflows/ci.yml`)

Every push or pull request to `main` triggers an automated pipeline:

```
┌─────────────────────────────────┐     ┌─────────────────────────────────┐
│  Job 1: Lint, Format & Types    │────►│  Job 2: Tests                   │
│                                 │     │                                 │
│  • ruff check backend/ scripts/ │     │  Services:                      │
│  • ruff format --check          │     │    • TimescaleDB (PG 16)        │
│  • mypy backend/                │     │    • Redis 7                    │
│                                 │     │                                 │
│  Catches style violations,      │     │  • pip install -e ".[dev]"      │
│  import issues, type errors     │     │  • pytest --tb=short -q         │
└─────────────────────────────────┘     └─────────────────────────────────┘
```

### Code Quality Tools

| Tool | Purpose | Config Location |
|------|---------|----------------|
| **Ruff** | Linting + formatting (replaces flake8, isort, black) | `pyproject.toml` `[tool.ruff]` |
| **mypy** | Static type checking | `pyproject.toml` `[tool.mypy]` |
| **pytest** | Test runner | `pyproject.toml` `[tool.pytest.ini_options]` |

### Running Locally

```bash
# Lint
ruff check backend/ scripts/

# Format
ruff format backend/ scripts/

# Type check
mypy backend/ --ignore-missing-imports

# Tests
pytest
```

---

## �📁 Project File Structure

```
PraxiAlpha/
│
├── 📄 docker-compose.yml     ← Defines all 5 Docker containers
├── 📄 Dockerfile             ← How to build the Python container
├── 📄 pyproject.toml          ← Python dependencies, linting & test config
├── 📄 alembic.ini            ← Database migration config
├── 📄 .env                   ← API keys & secrets (NOT in Git!)
├── 📄 .env.example           ← Template for .env (IS in Git)
│
├── 📁 .github/workflows/     ← CI/CD pipeline
│   └── ci.yml                ← GitHub Actions: lint, format, type check, tests
│
├── 📁 backend/                ← All Python backend code
│   ├── main.py               ← FastAPI app entry point
│   ├── config.py             ← Settings loaded from .env
│   ├── database.py           ← Database connection setup
│   │
│   ├── 📁 models/            ← Database table definitions (SQLAlchemy)
│   │   ├── stock.py          ← Stock/ETF ticker table
│   │   ├── ohlcv.py          ← Daily price data table
│   │   ├── macro.py          ← Macro indicator table
│   │   ├── split.py          ← Stock split events table
│   │   └── dividend.py       ← Dividend payment events table
│   │
│   ├── 📁 api/               ← REST API endpoints
│   │   └── routes/
│   │       ├── stocks.py     ← /api/v1/stocks/* endpoints
│   │       └── ... (stubs)   ← Future: charts, screener, etc.
│   │
│   ├── 📁 services/          ← Business logic
│   │   └── data_pipeline/
│   │       ├── eodhd_fetcher.py  ← Talks to EODHD API
│   │       ├── fred_fetcher.py   ← Talks to FRED API
│   │       └── data_validator.py ← Validates incoming data
│   │
│   ├── 📁 tasks/             ← Background job definitions
│   │   ├── celery_app.py     ← Celery configuration + schedule
│   │   └── data_tasks.py     ← Data fetching tasks
│   │
│   └── 📁 tests/             ← Automated tests
│
├── 📁 scripts/               ← One-off utility scripts
│   ├── setup_db.py           ← Creates database tables
│   └── backfill_data.py      ← Populates stock data
│
├── 📁 data/migrations/       ← Alembic database migrations
├── 📁 docs/                  ← 📖 You are here!
├── 📁 streamlit_app/         ← MVP dashboard (future)
├── 📁 education_content/     ← Learning materials (future)
└── 📁 notebooks/             ← Jupyter notebooks for exploration
```

---

## 📖 Key Concepts Glossary

| Term | Plain English |
|------|-------------|
| **API** | A way for programs to talk to each other over the internet. Our API lets you ask "give me AAPL's price history" and get structured data back. |
| **REST API** | A style of API using standard HTTP methods (GET, POST, PUT, DELETE). |
| **Docker** | Software that packages an app + everything it needs into an isolated "container" that runs the same way on any computer. |
| **Container** | A lightweight, isolated environment running one service. Like a VM but faster and smaller. |
| **Docker Compose** | A tool that runs multiple containers together (our 5 services) with one command. |
| **Volume** | Docker's way of persisting data. Without volumes, data disappears when a container restarts. |
| **ORM** | Object-Relational Mapper. Lets you write `Stock.query.filter(ticker="AAPL")` instead of raw SQL. |
| **Migration** | A versioned change to the database schema (add a column, create a table). Like Git for your database structure. |
| **Hypertable** | TimescaleDB's magic — a regular table that's automatically partitioned by time for fast queries. |
| **Upsert** | INSERT if new, UPDATE if exists. Ensures we never get duplicate rows when re-running data loads. |
| **Task Queue** | A system where you post "jobs" and workers pick them up. Prevents blocking the main app. |
| **Celery Beat** | A scheduler that posts tasks at specific times (like cron jobs but integrated with Celery). |
| **OHLCV** | Open, High, Low, Close, Volume — the 5 core data points for each trading day. |
| **Backfill** | Loading historical data retroactively. We're backfilling 30+ years of prices. |
| **Rate Limiting** | APIs restrict how many requests you can make per minute/day to prevent abuse. |

---

*Last updated: 2026-03-22 — Phase 2 (added trade_snapshots schema for post-close "what-if" tracking)*
