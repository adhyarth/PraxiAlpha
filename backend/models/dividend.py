"""
PraxiAlpha — Stock Dividends Model

Records dividend payment events fetched from EODHD.
Used for total return calculations, income analysis, and education.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class StockDividend(Base):
    """
    Dividend payment event.

    EODHD provides rich dividend data including declaration, record,
    and payment dates, plus the period (Quarterly, Annual, etc.).
    """

    __tablename__ = "stock_dividends"
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_stock_dividends_stock_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)  # Ex-dividend date
    value: Mapped[float] = mapped_column(Float, nullable=False)  # Dividend per share (adjusted)
    unadjusted_value: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # Raw dividend per share
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    period: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # Quarterly, Annual, Monthly, etc.

    # Key dates
    declaration_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    record_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    payment_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    stock = relationship("Stock", back_populates="dividends")

    def __repr__(self) -> str:
        return (
            f"<StockDividend(stock_id={self.stock_id}, date={self.date}, "
            f"value={self.value}, period={self.period})>"
        )
