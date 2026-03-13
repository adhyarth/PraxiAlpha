"""
PraxiAlpha — Stock Model

Represents a stock/ETF ticker in the universe.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Stock(Base):
    """
    A stock or ETF in the PraxiAlpha universe.

    Populated from EODHD exchange symbol list.
    Covers all active US stocks/ETFs across NYSE, NASDAQ, AMEX.
    """

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NYSE, NASDAQ, AMEX
    asset_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Common Stock, ETF
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    country: Mapped[str] = mapped_column(String(10), default="US")
    isin: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_delisted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Data tracking
    eodhd_code: Mapped[str | None] = mapped_column(String(30), nullable=True)  # e.g., AAPL.US
    earliest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    latest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    daily_ohlcv = relationship("DailyOHLCV", back_populates="stock", lazy="dynamic")
    splits = relationship("StockSplit", back_populates="stock", lazy="dynamic")
    dividends = relationship("StockDividend", back_populates="stock", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Stock(ticker={self.ticker}, name={self.name}, exchange={self.exchange})>"
