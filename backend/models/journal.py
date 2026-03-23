"""
PraxiAlpha — Trading Journal Models

Three tables for trade journaling:
- `trades`      — parent trade record (one row per trade entry)
- `trade_exits` — partial/full exit fills (supports scale-out)
- `trade_legs`  — individual legs of multi-leg option trades

Computed fields (status, remaining_quantity, realized_pnl, return_pct,
avg_exit_price, r_multiple) are NOT stored — they are calculated at the
service/API layer from trade_exits data. See journal_service.py.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base

# ---------------------------------------------------------------------------
# ENUMs
# ---------------------------------------------------------------------------


class TradeDirection(enum.StrEnum):
    """Long or short trade."""

    LONG = "long"
    SHORT = "short"


class AssetType(enum.StrEnum):
    """What kind of instrument was traded."""

    SHARES = "shares"
    OPTIONS = "options"


class TradeType(enum.StrEnum):
    """Single-leg or multi-leg (options strategies)."""

    SINGLE_LEG = "single_leg"
    MULTI_LEG = "multi_leg"


class Timeframe(enum.StrEnum):
    """Which chart interval informed the trade decision."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class LegType(enum.StrEnum):
    """Type of option leg."""

    BUY_CALL = "buy_call"
    SELL_CALL = "sell_call"
    BUY_PUT = "buy_put"
    SELL_PUT = "sell_put"


# ---------------------------------------------------------------------------
# trades — parent trade record
# ---------------------------------------------------------------------------


class Trade(Base):
    """
    A single trade entry in the journal.

    Stores only raw entry data. Derived metrics (status, remaining_quantity,
    realized_pnl, etc.) are computed from related trade_exits at read time.
    """

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, server_default=text("'default'")
    )
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[TradeDirection] = mapped_column(
        Enum(
            TradeDirection, name="trade_direction", values_callable=lambda e: [x.value for x in e]
        ),
        nullable=False,
    )
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    trade_type: Mapped[TradeType] = mapped_column(
        Enum(TradeType, name="trade_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        server_default=text("'single_leg'"),
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        Enum(Timeframe, name="trade_timeframe", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    total_quantity: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    stop_loss: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=list)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships (cascade delete exits + legs when trade is deleted)
    exits: Mapped[list["TradeExit"]] = relationship(
        "TradeExit",
        back_populates="trade",
        cascade="all, delete-orphan",
        order_by="TradeExit.exit_date",
    )
    legs: Mapped[list["TradeLeg"]] = relationship(
        "TradeLeg",
        back_populates="trade",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, ticker={self.ticker}, "
            f"direction={self.direction}, entry={self.entry_date})>"
        )


# ---------------------------------------------------------------------------
# trade_exits — partial/full exit fills
# ---------------------------------------------------------------------------


class TradeExit(Base):
    """
    A single exit fill for a trade. Supports partial exits (scale-out).

    Example: enter 100 shares → exit 50 at +5% → exit 50 at +10%.
    Each exit is a separate row.
    """

    __tablename__ = "trade_exits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exit_date: Mapped[date] = mapped_column(Date, nullable=False)
    exit_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship back to parent trade
    trade: Mapped["Trade"] = relationship("Trade", back_populates="exits")

    def __repr__(self) -> str:
        return (
            f"<TradeExit(id={self.id}, trade_id={self.trade_id}, "
            f"qty={self.quantity}, price={self.exit_price})>"
        )


# ---------------------------------------------------------------------------
# trade_legs — multi-leg option trades
# ---------------------------------------------------------------------------


class TradeLeg(Base):
    """
    An individual leg of a multi-leg options trade.

    Example: iron condor = 4 legs (sell call, buy call, sell put, buy put),
    each with its own strike, expiry, quantity, and premium.
    """

    __tablename__ = "trade_legs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trades.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    leg_type: Mapped[LegType] = mapped_column(
        Enum(LegType, name="leg_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    strike: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    premium: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)

    # Relationship back to parent trade
    trade: Mapped["Trade"] = relationship("Trade", back_populates="legs")

    def __repr__(self) -> str:
        return (
            f"<TradeLeg(id={self.id}, trade_id={self.trade_id}, "
            f"type={self.leg_type}, strike={self.strike})>"
        )
