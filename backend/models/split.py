"""
PraxiAlpha — Stock Splits Model

Records stock split events fetched from EODHD.
Used for data integrity verification and education context.
"""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class StockSplit(Base):
    """
    Stock split event.

    Example: AAPL did a 7:1 split on 2014-06-09 and a 4:1 split on 2020-08-31.
    We store the ratio as a float (7.0, 4.0) for easy math.
    """

    __tablename__ = "stock_splits"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_stock_splits_stock_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    split_ratio: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # Raw from EODHD: "7.000000/1.000000"
    numerator: Mapped[float] = mapped_column(Float, nullable=False)  # e.g., 7.0
    denominator: Mapped[float] = mapped_column(Float, nullable=False)  # e.g., 1.0

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    stock = relationship("Stock", back_populates="splits")

    @property
    def ratio(self) -> float:
        """Effective split ratio (e.g., 7.0 for a 7:1 split)."""
        return self.numerator / self.denominator if self.denominator else 1.0

    def __repr__(self) -> str:
        return (
            f"<StockSplit(stock_id={self.stock_id}, date={self.date}, "
            f"ratio={self.numerator}:{self.denominator})>"
        )
