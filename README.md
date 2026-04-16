# 🎯 PraxiAlpha

> *"Disciplined action that generates alpha."*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-614%20passing-brightgreen)](https://github.com/adhyarth/PraxiAlpha/actions)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-FDB515?logo=timescale&logoColor=black)](https://www.timescale.com/)

A systematic trading platform that removes emotion from investing through **data-driven strategies**, **automated analysis**, and **disciplined execution**.

```mermaid
flowchart LR
    subgraph Problem["😰 The Problem"]
        E[Emotional Decisions]
        F[Fear & Greed]
        G[Inconsistent Results]
    end
    
    subgraph Solution["🎯 PraxiAlpha"]
        D[(58M+ Data Points)]
        A[Backtested Strategies]
        R[Risk Management]
    end
    
    subgraph Outcome["📈 The Outcome"]
        C[Consistent Process]
        O[Data-Driven Decisions]
        L[Continuous Learning]
    end
    
    Problem --> Solution --> Outcome
    
    style Problem fill:#ffcccc,stroke:#cc0000
    style Solution fill:#cce5ff,stroke:#0066cc
    style Outcome fill:#ccffcc,stroke:#00cc00
```

---

## 🧠 Why PraxiAlpha?

The biggest challenge in investing isn't finding good stocks — it's **separating emotion from analysis**. Fear makes us sell at bottoms; greed makes us buy at tops. PraxiAlpha solves this through:

| Goal | How PraxiAlpha Achieves It |
|------|---------------------------|
| **🤖 Automate Trading Decisions** | Rule-based strategies that execute without emotional interference |
| **📊 Data-Backed Strategies** | Every strategy is backtested against 58M+ historical data points before deployment |
| **📚 Track, Learn & Teach** | Trading journal with what-if analysis, PDF reports, and forward return tracking |

> *"Investing is a marathon, not a sprint. Slow and steady gains beat chasing 10-baggers."*

### Core Philosophy

- **Buy weakness, sell strength** — Never chase stocks in either direction
- **Follow the smart money** — Price/volume analysis reveals institutional activity  
- **Risk management is everything** — Survival first, profits second
- **Simplicity over complexity** — Fewer trades, bigger wins
- **Discipline over emotion** — Systematic rules > gut feelings

---

## ✨ What's Built

```mermaid
flowchart TB
    subgraph Data["📊 Data Layer"]
        EODHD[EODHD API]
        FRED[FRED API]
        YF[Yahoo Finance]
    end
    
    subgraph Storage["🗄️ Storage"]
        PG[(PostgreSQL + TimescaleDB)]
        OHLCV[58M OHLCV Records]
        MACRO[14 Macro Indicators]
        CAL[Economic Calendar]
    end
    
    subgraph Backend["⚙️ Backend"]
        API[FastAPI]
        CELERY[Celery Workers]
        ANALYSIS[Technical Analysis]
    end
    
    subgraph Features["🎯 Features"]
        CHARTS[Interactive Charts]
        SCANNER[Strategy Lab Scanner]
        JOURNAL[Trading Journal]
        VALID[Data Validation]
    end
    
    subgraph UI["🖥️ Dashboard"]
        STREAMLIT[Streamlit App]
    end
    
    Data --> Storage
    Storage --> Backend
    Backend --> Features
    Features --> UI
    
    style Data fill:#e1f5fe
    style Storage fill:#fff3e0
    style Backend fill:#f3e5f5
    style Features fill:#e8f5e9
    style UI fill:#fce4ec
```

### Feature Highlights

| Feature | Description | Status |
|---------|-------------|--------|
| 📈 **Interactive Charts** | Candlestick charts with RSI, MACD, Bollinger Bands, moving averages. Daily/weekly/monthly/quarterly views with split-adjusted prices. | ✅ Live |
| 🔬 **Strategy Lab** | Pattern scanner with configurable conditions (candle color, body %, wick %, volume ratio, RSI). Forward return analysis (Q+1 to Q+8). | ✅ Live |
| 📝 **Trading Journal** | Log trades, track P&L, partial exits, options legs. Post-close "what-if" analysis shows best/worst hypothetical exits. PDF reports. | ✅ Live |
| ✅ **Data Validation** | Cross-checks EODHD data against Yahoo Finance (1% price tolerance, 10% volume tolerance). Ensures data integrity. | ✅ Live |
| 📅 **Economic Calendar** | Upcoming economic events (CPI, FOMC, NFP) with impact ratings. Situational awareness, not trading signals. | ✅ Live |
| 🔄 **Automated Pipelines** | Celery tasks for daily OHLCV updates (7 PM ET), macro data refresh, calendar sync. Smart gap-fill for missed days. | ✅ Live |

### By the Numbers

| Metric | Value |
|--------|-------|
| 📊 OHLCV Records | **58.2 million** |
| 🏢 Tickers Covered | **49,000+** (NYSE, NASDAQ, AMEX) |
| 📅 History Depth | **1990 — Present** |
| 🧪 Test Coverage | **614 tests** passing |
| 🔄 PRs Merged | **38** |
| 📝 Development Sessions | **31** |

---

## 🛠️ Tech Stack

```mermaid
flowchart LR
    subgraph Frontend["Frontend"]
        ST[Streamlit]
        PLOTLY[Plotly Charts]
    end
    
    subgraph Backend["Backend"]
        PY[Python 3.11+]
        FAST[FastAPI]
        CEL[Celery + Redis]
    end
    
    subgraph Database["Database"]
        PG[(PostgreSQL 16)]
        TS[TimescaleDB]
    end
    
    subgraph Data["Data Providers"]
        EOD[EODHD]
        FR[FRED]
        TE[TradingEconomics]
    end
    
    subgraph Infra["Infrastructure"]
        DOCKER[Docker]
        GH[GitHub Actions CI]
    end
    
    Frontend <--> Backend
    Backend <--> Database
    Data --> Backend
    Infra --- Backend
    
    style Frontend fill:#ff6b6b,color:#fff
    style Backend fill:#4ecdc4,color:#fff
    style Database fill:#45b7d1,color:#fff
    style Data fill:#96ceb4,color:#000
    style Infra fill:#dfe6e9,color:#000
```

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | FastAPI | Async REST API with auto-generated OpenAPI docs |
| **Database** | PostgreSQL + TimescaleDB | Time-series optimized storage with continuous aggregates |
| **Task Queue** | Celery + Redis | Background jobs for data fetching, report generation |
| **Dashboard** | Streamlit + Plotly | Interactive charts, forms, and data exploration |
| **Data** | EODHD, FRED, TradingEconomics | Market data, macro indicators, economic calendar |
| **CI/CD** | GitHub Actions | Automated linting (ruff), type checking (mypy), testing (pytest) |
| **Container** | Docker Compose | One-command local development environment |

---

## ⚡ AI-Accelerated Development

PraxiAlpha was built using **AI-assisted development** (GitHub Copilot) as a force multiplier for a solo side project.

```mermaid
flowchart TB
    subgraph Context["📚 Context System"]
        WF[WORKFLOW.md<br/>Session workflow]
        PROG[PROGRESS.md<br/>Crash recovery]
        DESIGN[DESIGN_DOC.md<br/>Architecture]
        BUILD[BUILD_LOG.md<br/>Session history]
        CHANGE[CHANGELOG.md<br/>What changed]
    end
    
    subgraph Process["🔄 Each Session"]
        READ[1. AI reads context]
        CODE[2. Implement feature]
        TEST[3. Write tests]
        CI[4. Run CI locally]
        DOC[5. Update docs]
        PR[6. Open PR]
    end
    
    Context --> READ
    READ --> CODE --> TEST --> CI --> DOC --> PR
    PR -.->|"Updates"| Context
    
    style Context fill:#fff9c4
    style Process fill:#e3f2fd
```

### The Approach

| Aspect | Human (Me) | AI (Copilot) |
|--------|-----------|--------------|
| **Architecture & Design** | ✅ All design decisions, mental models, system architecture | — |
| **Product Direction** | ✅ What to build, why, priorities | — |
| **Code Implementation** | Review & approve | ✅ Write code following patterns |
| **Testing** | Define test cases | ✅ Implement tests |
| **Documentation** | Define structure | ✅ Write content |

### Why This Works

The **context system** (`WORKFLOW.md`, `PROGRESS.md`, `DESIGN_DOC.md`) allows AI to maintain continuity across chat sessions. This enables:

- **Crash recovery** — If the AI session crashes, the next session reads `PROGRESS.md` and resumes from the last checkpoint
- **Consistent patterns** — AI follows established codebase conventions by reading existing code
- **Rapid iteration** — 31 sessions → 38 PRs → 614 tests in ~3 weeks of part-time work (1 hour/day)

> *This structured approach to AI-assisted development is itself a transferable skill — designing systems that allow AI tools to be productive.*

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker Desktop
- Git

### One-Command Setup

```bash
# 1. Clone the repository
git clone https://github.com/adhyarth/PraxiAlpha.git
cd PraxiAlpha

# 2. Copy environment variables
cp .env.example .env
# Edit .env with your API keys (EODHD_API_KEY, etc.)

# 3. Start everything with Docker
docker compose up -d

# 4. Wait for services to be healthy
curl -sf http://localhost:8000/health
```

### Launch the Dashboard

```bash
# Set database URL for Streamlit (runs outside Docker)
export DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha"

# Launch Streamlit
PYTHONPATH=. streamlit run streamlit_app/app.py
```

Open [http://localhost:8501](http://localhost:8501) to explore:
- 📈 **Charts** — Interactive candlestick charts with indicators
- 🔬 **Strategy Lab** — Pattern scanner with forward returns
- 📝 **Trading Journal** — Log and analyze trades
- ✅ **Data Validation** — Verify data integrity

### API Documentation

Once running, visit:
- **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📁 Project Structure

```
PraxiAlpha/
├── backend/                  # FastAPI backend
│   ├── api/routes/           # REST endpoints
│   ├── models/               # SQLAlchemy ORM models
│   ├── services/             # Business logic
│   │   ├── scanner_service.py      # Strategy Lab engine
│   │   ├── journal_service.py      # Trading journal
│   │   ├── candle_service.py       # Split-adjusted OHLCV
│   │   └── data_pipeline/          # EODHD & FRED fetchers
│   ├── tasks/                # Celery background tasks
│   └── tests/                # 614 tests
├── streamlit_app/            # Streamlit dashboard
│   └── pages/                # Charts, Scanner, Journal, Validation
├── scripts/                  # Utility scripts (backfill, setup)
├── docs/                     # Documentation
│   ├── PROGRESS.md           # Project status & crash recovery
│   ├── BUILD_LOG.md          # Session history
│   └── ARCHITECTURE.md       # System design
├── WORKFLOW.md               # Session workflow (AI context)
├── DESIGN_DOC.md             # Architecture & mental models
└── docker-compose.yml        # One-command dev environment
```

---

## 🗺️ Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Foundation — Database, Data Pipeline, 58M records backfill | ✅ Complete |
| **Phase 2** | Charting & Dashboard — Charts, Journal, Strategy Lab, Validation | 🔧 In Progress |
| **Phase 3** | Analysis Engine — Trend classification, support/resistance, stock reports | ⏳ Planned |
| **Phase 4** | Backtesting Framework — Walk-forward testing, performance metrics | ⏳ Planned |
| **Phase 5** | Education Module — Interactive lessons, case studies | ⏳ Planned |
| **Phase 6** | Notifications — Alerts, watchlist triggers | ⏳ Planned |
| **Phase 7** | Paper Trading — Strategy execution simulation | ⏳ Planned |
| **Phase 8** | Production — React frontend, AWS deployment | ⏳ Planned |

---

## 📸 Screenshots

### Interactive Charts
*Split-adjusted candlestick charts with volume, multiple timeframes, and real-time price data*

![Charts](docs/images/charts.png)

### Strategy Lab — Pattern Scanner
*Configure scan conditions (candle shape, volume, RSI) and analyze forward returns across 5,300+ ETFs*

![Scanner](docs/images/scanner.png)

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [`DESIGN_DOC.md`](DESIGN_DOC.md) | Architecture, mental models, phase roadmap |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Current project status, session history |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Database schema, file structure |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Branch naming, commit conventions |
| [`WORKFLOW.md`](WORKFLOW.md) | Development session workflow |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <i>Built with 🎯 by <a href="https://github.com/adhyarth">Adhyarth Varia</a></i>
</p>
