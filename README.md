# 🎯 PraxiAlpha

> *"Disciplined action that generates alpha."*

A modular, cloud-hosted, systematic trading and education platform for retail investors. PraxiAlpha combines **investor education**, **market intelligence**, and **automated trading** into a single, cohesive system.

## Core Philosophy

- **Buy weakness, sell strength** — Never chase stocks in either direction
- **Follow the smart money** — Price/volume analysis reveals institutional activity
- **Risk management is everything** — Survival first, profits second
- **Simplicity over complexity** — Fewer trades, bigger wins
- **Discipline over emotion** — Systematic rules > gut feelings

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, Celery + Redis |
| **Database** | PostgreSQL + TimescaleDB |
| **Data Providers** | EODHD (market data), FRED (macro data) |
| **Dashboard (MVP)** | Streamlit |
| **Frontend (Production)** | React + TypeScript + TailwindCSS |
| **Infrastructure** | Docker, AWS ECS (Fargate) |

## Quick Start

### Prerequisites
- Python 3.11+
- Docker Desktop
- Git

### Setup

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd PraxiAlpha

# 2. Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Start infrastructure (PostgreSQL + TimescaleDB + Redis)
docker compose up -d db redis

# 4. Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 5. Install dependencies
pip install -e ".[dev]"

# 6. Set up the database
python scripts/setup_db.py

# 7. Populate stocks table from EODHD
python scripts/backfill_data.py --populate

# 8. Test with a few stocks
python scripts/backfill_data.py --test

# 9. Backfill entire US market (takes a while!)
python scripts/backfill_data.py --all

# 10. Start the API
uvicorn backend.main:app --reload

# 11. Launch the Streamlit dashboard (in a separate terminal)
# Requires Docker running (step 3) — DB is accessed via localhost:5432
PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha" streamlit run streamlit_app/app.py
```

### Docker (full stack)

```bash
docker compose up -d
```

This starts:
- **FastAPI** backend on `http://localhost:8000`
- **PostgreSQL + TimescaleDB** on port `5432`
- **Redis** on port `6379`
- **Celery Worker** for background tasks
- **Celery Beat** for scheduled tasks (daily data updates at 6 PM ET)

### Streamlit Dashboard (local dev)

```bash
# Must be run from the project root (Docker must be running for DB access)
PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha" streamlit run streamlit_app/app.py
```

This launches the Streamlit MVP dashboard on `http://localhost:8501`.

## Project Structure

```
PraxiAlpha/
├── backend/              # FastAPI backend
│   ├── main.py           # Application entry point
│   ├── config.py         # Configuration management
│   ├── database.py       # Database connection
│   ├── api/routes/       # API endpoints
│   ├── models/           # SQLAlchemy ORM models
│   ├── services/         # Business logic
│   │   ├── data_pipeline/  # EODHD & FRED fetchers
│   │   ├── analysis/       # Technical analysis
│   │   ├── trading/        # Strategy & execution
│   │   ├── risk/           # Risk management
│   │   └── ...
│   ├── tasks/            # Celery async tasks
│   └── tests/            # Test suite
├── streamlit_app/        # Streamlit MVP dashboard
├── scripts/              # Utility scripts
├── data/migrations/      # Alembic DB migrations
├── education_content/    # Curriculum content
├── notebooks/            # Jupyter exploration
└── frontend/             # React frontend (Phase 8+)
```

## Phase Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Foundation, Database, Data Pipeline | 🔧 In Progress |
| **Phase 2** | Charting & Basic Dashboard | ⏳ Upcoming |
| **Phase 3** | Analysis Engine | ⏳ Planned |
| **Phase 4** | Backtesting Framework | ⏳ Planned |
| **Phase 5** | Education Module | ⏳ Planned |
| **Phase 6** | Notifications | ⏳ Planned |
| **Phase 7** | Paper Trading | ⏳ Planned |
| **Phase 8** | React Frontend & Production | ⏳ Planned |

## API Documentation

Once the server is running, visit:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **Health Check:** `http://localhost:8000/health`

## Data Coverage

- **~10,000+ active US stocks & ETFs** (NYSE, NASDAQ, AMEX)
- **30+ years of daily OHLCV** history
- **14 macroeconomic indicators** from FRED (Treasury yields, VIX, DXY, oil, inflation expectations, etc.)
- **~33 GB** estimated total database size

---

*Built with 🎯 by Adhyarth Varia*
