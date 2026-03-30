# 🛠️ PraxiAlpha — Command Cheatsheet

1. **Check Docker container status** — `docker compose ps`
2. **Start containers** — `docker compose up -d`
3. **Stop containers** — `docker compose down`
4. **Kill Streamlit** — `pkill -f "streamlit run"`
5. **Start Streamlit** — `PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha" streamlit run streamlit_app/app.py`
6. **Run data validation script locally** — `PYTHONPATH=. DATABASE_URL="postgresql+asyncpg://praxialpha:praxialpha_dev_2025@localhost:5432/praxialpha" python3 scripts/validate_local.py`
