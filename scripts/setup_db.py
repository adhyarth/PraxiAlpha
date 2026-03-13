"""
PraxiAlpha — Database Setup Script

Creates the database schema and enables TimescaleDB extension.
Run this once after starting the Docker containers.

Usage:
    python scripts/setup_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.database import engine, Base
from backend.models.stock import Stock
from backend.models.ohlcv import DailyOHLCV
from backend.models.macro import MacroData


async def setup_database():
    """Create all tables and enable TimescaleDB."""
    print("🔧 Setting up PraxiAlpha database...")

    async with engine.begin() as conn:
        # Enable TimescaleDB extension
        print("   Enabling TimescaleDB extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))

        # Create all tables
        print("   Creating tables...")
        await conn.run_sync(Base.metadata.create_all)

        # Convert daily_ohlcv to a TimescaleDB hypertable
        print("   Converting daily_ohlcv to TimescaleDB hypertable...")
        try:
            await conn.execute(
                text(
                    "SELECT create_hypertable('daily_ohlcv', 'date', "
                    "if_not_exists => TRUE, "
                    "migrate_data => TRUE);"
                )
            )
            print("   ✅ daily_ohlcv is now a TimescaleDB hypertable")
        except Exception as e:
            if "already a hypertable" in str(e):
                print("   ℹ️  daily_ohlcv is already a hypertable")
            else:
                print(f"   ⚠️  Hypertable creation warning: {e}")

    print("")
    print("✅ Database setup complete!")
    print("   Tables created:")
    for table_name in Base.metadata.tables:
        print(f"     - {table_name}")


if __name__ == "__main__":
    asyncio.run(setup_database())
