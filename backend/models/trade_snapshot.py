"""
PraxiAlpha — Trade Snapshot Model

Post-close price snapshots for "what-if" analysis. After a trade is closed,
a Celery task periodically captures the ticker's closing price and computes
hypothetical PnL (what if I'd held?).

See docs/ARCHITECTURE.md § "trade_snapshots" for the full schema design.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

if TYPE_CHECKING:
    from backend.models.journal import Trade


class TradeSnapshot(Base):
    """
    A single post-close price snapshot for a trade.

    Captures the closing price on a given date and the hypothetical PnL
    if the full original position had been held until that date.
    """

    __tablename__ = "trade_snapshots"
    __table_args__ = (UniqueConstraint("trade_id", "snapshot_date", name="uq_trade_snapshot_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    hypothetical_pnl: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    hypothetical_pnl_pct: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to parent trade
    trade: Mapped[Trade] = relationship("Trade", backref="snapshots")

    def __repr__(self) -> str:
        return (
            f"<TradeSnapshot(id={self.id}, trade_id={self.trade_id}, "
            f"date={self.snapshot_date}, pnl={self.hypothetical_pnl})>"
        )
