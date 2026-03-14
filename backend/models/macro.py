"""
PraxiAlpha — Macro Data Model

Stores macroeconomic indicator time-series from FRED API.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MacroData(Base):
    """
    Macroeconomic indicator time-series data from FRED API.

    Tracks indicators like Treasury yields, VIX, DXY, oil prices,
    inflation expectations, M2 money supply, Fed balance sheet, etc.
    """

    __tablename__ = "macro_data"
    __table_args__ = (UniqueConstraint("indicator_code", "date", name="uq_macro_indicator_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicator_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # FRED series ID, e.g., "DGS10"
    indicator_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)  # Null for holidays/missing
    source: Mapped[str] = mapped_column(String(20), default="FRED")

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<MacroData(indicator={self.indicator_code}, date={self.date}, value={self.value})>"


# ---- FRED Series Registry ----
# Maps FRED series IDs to human-readable names and categories
FRED_SERIES = {
    # Treasury Yields
    "DGS10": {"name": "10-Year Treasury Yield", "category": "bonds"},
    "DGS2": {"name": "2-Year Treasury Yield", "category": "bonds"},
    "DGS30": {"name": "30-Year Treasury Yield", "category": "bonds"},
    "DFF": {"name": "Federal Funds Rate", "category": "bonds"},
    "T10Y2Y": {"name": "10Y-2Y Yield Spread (Yield Curve)", "category": "bonds"},
    # Volatility
    "VIXCLS": {"name": "VIX (CBOE Volatility Index)", "category": "volatility"},
    # Dollar
    "DTWEXBGS": {"name": "Trade Weighted Dollar Index (Broad)", "category": "currencies"},
    # Commodities
    "DCOILWTICO": {"name": "WTI Crude Oil Price", "category": "commodities"},
    # Inflation Expectations
    "T10YIE": {"name": "10-Year Breakeven Inflation Rate", "category": "economic"},
    # Money Supply & Fed
    "M2SL": {"name": "M2 Money Supply", "category": "liquidity"},
    "WALCL": {"name": "Fed Total Assets (Balance Sheet)", "category": "liquidity"},
    # Labor
    "UNRATE": {"name": "Unemployment Rate", "category": "economic"},
    # Inflation
    "CPIAUCSL": {"name": "Consumer Price Index (CPI)", "category": "economic"},
    "PCEPI": {"name": "PCE Price Index", "category": "economic"},
}
