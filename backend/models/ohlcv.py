"""
PraxiAlpha — Daily OHLCV Model

Stores daily Open/High/Low/Close/Volume data.
This is a TimescaleDB hypertable for optimal time-series performance.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class DailyOHLCV(Base):
    """
    Daily OHLCV (Open, High, Low, Close, Volume) price data.

    One row per stock per trading day.
    Will be converted to a TimescaleDB hypertable for optimal time-series queries.
    Estimated: ~75.6 million rows for full US market (30+ years).
    """

    __tablename__ = "daily_ohlcv"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_daily_ohlcv_stock_date"),
    )

    # TimescaleDB requires the partitioning column (date) in the primary key
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    # Price data
    open: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    adjusted_close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    stock = relationship("Stock", back_populates="daily_ohlcv")

    def __repr__(self) -> str:
        return (
            f"<DailyOHLCV(stock_id={self.stock_id}, date={self.date}, "
            f"close={self.close}, volume={self.volume})>"
        )
