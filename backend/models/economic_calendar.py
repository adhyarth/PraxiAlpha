"""
PraxiAlpha — Economic Calendar Model

Stores upcoming and recent economic calendar events from TradingEconomics API.

Purpose: Situational awareness — know what market-moving events are coming
so you're never blindsided. NOT used as a trading signal (see Mental Model #14).

TradingEconomics API docs: https://docs.tradingeconomics.com/economic_calendar/snapshot/
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class EconomicCalendarEvent(Base):
    """
    A scheduled economic event from TradingEconomics.

    Examples: Non-Farm Payrolls, CPI, FOMC Rate Decision, GDP, etc.
    Importance levels: 1 (Low), 2 (Medium), 3 (High).
    """

    __tablename__ = "economic_calendar"
    __table_args__ = (UniqueConstraint("calendar_id", name="uq_economic_calendar_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # TradingEconomics event identifiers
    calendar_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # TE CalendarId, e.g., "384241"

    # Event details
    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )  # Scheduled release time (UTC)
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g., "Non Farm Payrolls"
    event: Mapped[str] = mapped_column(String(300), nullable=False)  # Full event name
    reference: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "Nov", "Q3"
    reference_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Values (all stored as strings — TE returns mixed formats like "0.5%", "1.307M")
    actual: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous: Mapped[str | None] = mapped_column(String(100), nullable=True)
    forecast: Mapped[str | None] = mapped_column(String(100), nullable=True)
    te_forecast: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revised: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Classification
    importance: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # 1=Low, 2=Medium, 3=High

    # Source
    source: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(300), nullable=True)  # TE relative URL

    # Units
    currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ticker: Mapped[str | None] = mapped_column(String(100), nullable=True)  # TE ticker symbol

    # Timestamps
    te_last_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When TE last updated this event
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )  # When we fetched it

    def __repr__(self) -> str:
        return (
            f"<EconomicCalendarEvent("
            f"date={self.date}, country={self.country}, "
            f"event={self.event}, importance={self.importance})>"
        )


# ---- Events we care about most (US high-importance) ----
# These are the events that actually move markets.
# Used for dashboard display and filtering.
US_HIGH_IMPACT_EVENTS = [
    "Non Farm Payrolls",
    "CPI",
    "Core CPI",
    "Fed Interest Rate Decision",
    "FOMC Press Conference",
    "GDP Growth Rate",
    "PCE Price Index",
    "Core PCE Price Index",
    "Retail Sales MoM",
    "Unemployment Rate",
    "ISM Manufacturing PMI",
    "ISM Services PMI",
    "PPI MoM",
    "Consumer Confidence",
    "Initial Jobless Claims",
    "Housing Starts",
    "Building Permits",
    "Durable Goods Orders",
    "Industrial Production MoM",
]
