"""
PraxiAlpha — Trading Journal Service

CRUD operations for the trading journal. All computed fields (status,
remaining_quantity, realized_pnl, return_pct, avg_exit_price, r_multiple)
are calculated here at read time — they are NOT stored in the database.

See docs/ARCHITECTURE.md § "Computed fields" for derivation formulas.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.config import get_settings
from backend.models.journal import (
    AssetType,
    LegType,
    Timeframe,
    Trade,
    TradeDirection,
    TradeExit,
    TradeLeg,
    TradeType,
)

logger = logging.getLogger(__name__)


def _current_user_id() -> str:
    """Return the active user_id from settings (PRAXIALPHA_USER_ID env var)."""
    return get_settings().praxialpha_user_id


# ---------------------------------------------------------------------------
# Computed field helpers
# ---------------------------------------------------------------------------


def compute_trade_metrics(trade: Trade) -> dict[str, Any]:
    """
    Compute derived fields from a Trade and its exits.

    Returns a dict with: status, remaining_quantity, realized_pnl,
    return_pct, avg_exit_price, r_multiple.

    Uses Decimal arithmetic end-to-end and converts to float only at
    the serialization boundary to avoid rounding drift.
    """
    exits = trade.exits or []
    total_qty = Decimal(str(trade.total_quantity))
    entry_price = Decimal(str(trade.entry_price))

    exited_qty = sum((Decimal(str(e.quantity)) for e in exits), Decimal("0"))
    remaining_qty = total_qty - exited_qty

    # Clamp remaining_qty to 0 if it's negative by a tiny rounding margin
    if remaining_qty < 0 and remaining_qty > Decimal("-0.0001"):
        remaining_qty = Decimal("0")

    # Status
    if exited_qty == 0:
        status = "open"
    elif remaining_qty > 0:
        status = "partial"
    else:
        status = "closed"

    # Realized PnL
    direction_sign = Decimal("1") if trade.direction == TradeDirection.LONG else Decimal("-1")
    realized_pnl = sum(
        (Decimal(str(e.exit_price)) - entry_price) * Decimal(str(e.quantity)) * direction_sign
        for e in exits
    ) or Decimal("0")

    # Return %
    cost_basis = entry_price * total_qty
    return_pct = (realized_pnl / cost_basis * 100) if cost_basis != 0 else Decimal("0")

    # Average exit price
    avg_exit_price: Decimal | None = None
    if exited_qty > 0:
        avg_exit_price = (
            sum(
                (Decimal(str(e.exit_price)) * Decimal(str(e.quantity)) for e in exits),
                Decimal("0"),
            )
            / exited_qty
        )

    # R-multiple (only when stop_loss is set)
    r_multiple = None
    if trade.stop_loss is not None and exited_qty > 0:
        risk_per_unit = abs(entry_price - Decimal(str(trade.stop_loss)))
        total_risk = risk_per_unit * total_qty
        if total_risk > 0:
            r_multiple = round(float(realized_pnl / total_risk), 2)

    return {
        "status": status,
        "remaining_quantity": round(float(remaining_qty), 4),
        "realized_pnl": round(float(realized_pnl), 4),
        "return_pct": round(float(return_pct), 2),
        "avg_exit_price": round(float(avg_exit_price), 4) if avg_exit_price is not None else None,
        "r_multiple": r_multiple,
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_exit(exit_: TradeExit) -> dict[str, Any]:
    """Serialize a TradeExit to a dict."""
    return {
        "id": str(exit_.id),
        "trade_id": str(exit_.trade_id),
        "exit_date": str(exit_.exit_date),
        "exit_price": float(exit_.exit_price),
        "quantity": float(exit_.quantity),
        "comments": exit_.comments,
    }


def _serialize_leg(leg: TradeLeg) -> dict[str, Any]:
    """Serialize a TradeLeg to a dict."""
    return {
        "id": str(leg.id),
        "trade_id": str(leg.trade_id),
        "leg_type": leg.leg_type.value if isinstance(leg.leg_type, LegType) else str(leg.leg_type),
        "strike": float(leg.strike),
        "expiry": str(leg.expiry),
        "quantity": float(leg.quantity),
        "premium": float(leg.premium),
    }


def serialize_trade(trade: Trade, include_children: bool = True) -> dict[str, Any]:
    """
    Serialize a Trade to a dict, including computed fields.

    Args:
        trade: The Trade ORM object (with exits/legs loaded if include_children).
        include_children: If True, include exits and legs arrays.
    """
    metrics = compute_trade_metrics(trade)

    result: dict[str, Any] = {
        "id": str(trade.id),
        "user_id": trade.user_id,
        "ticker": trade.ticker,
        "direction": trade.direction.value
        if isinstance(trade.direction, TradeDirection)
        else str(trade.direction),
        "asset_type": trade.asset_type.value
        if isinstance(trade.asset_type, AssetType)
        else str(trade.asset_type),
        "trade_type": trade.trade_type.value
        if isinstance(trade.trade_type, TradeType)
        else str(trade.trade_type),
        "timeframe": trade.timeframe.value
        if isinstance(trade.timeframe, Timeframe)
        else str(trade.timeframe),
        "entry_date": str(trade.entry_date),
        "entry_price": float(trade.entry_price),
        "total_quantity": float(trade.total_quantity),
        "stop_loss": float(trade.stop_loss) if trade.stop_loss is not None else None,
        "take_profit": float(trade.take_profit) if trade.take_profit is not None else None,
        "tags": trade.tags or [],
        "comments": trade.comments,
        "created_at": str(trade.created_at) if trade.created_at else None,
        "updated_at": str(trade.updated_at) if trade.updated_at else None,
        # Computed fields
        **metrics,
    }

    if include_children:
        result["exits"] = [_serialize_exit(e) for e in (trade.exits or [])]
        result["legs"] = [_serialize_leg(lg) for lg in (trade.legs or [])]

    return result


# ---------------------------------------------------------------------------
# CRUD: Create
# ---------------------------------------------------------------------------


async def create_trade(
    db: AsyncSession,
    *,
    ticker: str,
    direction: str,
    asset_type: str,
    trade_type: str = "single_leg",
    timeframe: str,
    entry_date: date,
    entry_price: float,
    total_quantity: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    tags: list[str] | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    """Create a new trade entry."""
    trade = Trade(
        ticker=ticker.upper(),
        user_id=_current_user_id(),
        direction=TradeDirection(direction),
        asset_type=AssetType(asset_type),
        trade_type=TradeType(trade_type),
        timeframe=Timeframe(timeframe),
        entry_date=entry_date,
        entry_price=Decimal(str(entry_price)),
        total_quantity=Decimal(str(total_quantity)),
        stop_loss=Decimal(str(stop_loss)) if stop_loss is not None else None,
        take_profit=Decimal(str(take_profit)) if take_profit is not None else None,
        tags=tags or [],
        comments=comments,
    )
    db.add(trade)
    await db.flush()
    # Refresh to get server defaults (created_at, updated_at)
    await db.refresh(trade, attribute_names=["id", "created_at", "updated_at"])
    # Initialize empty relationships for serialization
    trade.exits = []
    trade.legs = []
    logger.info("Created trade %s: %s %s %s", trade.id, ticker, direction, entry_date)
    return serialize_trade(trade)


# ---------------------------------------------------------------------------
# CRUD: Read
# ---------------------------------------------------------------------------


async def get_trade(db: AsyncSession, trade_id: uuid.UUID) -> dict[str, Any] | None:
    """Get a single trade by ID, including exits and legs. Scoped to current user."""
    user_id = _current_user_id()
    stmt = (
        select(Trade)
        .where(Trade.id == trade_id, Trade.user_id == user_id)
        .options(selectinload(Trade.exits), selectinload(Trade.legs))
    )
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()
    if trade is None:
        return None
    return serialize_trade(trade)


async def list_trades(
    db: AsyncSession,
    *,
    ticker: str | None = None,
    status: str | None = None,
    direction: str | None = None,
    timeframe: str | None = None,
    tags: list[str] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    List trades with optional filters.

    Note: `status` filtering is done in Python after fetching, since status
    is a computed field (not a DB column).
    """
    user_id = _current_user_id()
    stmt = select(Trade).options(selectinload(Trade.exits)).where(Trade.user_id == user_id)

    # DB-level filters
    if ticker:
        stmt = stmt.where(Trade.ticker == ticker.upper())
    if direction:
        stmt = stmt.where(Trade.direction == TradeDirection(direction))
    if timeframe:
        stmt = stmt.where(Trade.timeframe == Timeframe(timeframe))
    if tags:
        # JSONB @> operator: trade.tags must contain all specified tags
        stmt = stmt.where(Trade.tags.op("@>")(tags))
    if start_date:
        stmt = stmt.where(Trade.entry_date >= start_date)
    if end_date:
        stmt = stmt.where(Trade.entry_date <= end_date)

    stmt = stmt.order_by(Trade.entry_date.desc(), Trade.created_at.desc())

    # When no status filter is requested, we can safely paginate at the SQL level.
    # If a status filter is requested, we must fetch all rows and filter in Python
    # (since status is a computed field, not a DB column), then slice.
    if not status:
        stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    trades = list(result.scalars().all())

    # Compute metrics and serialize
    serialized = [serialize_trade(t, include_children=False) for t in trades]

    # Post-filter by computed status (if requested)
    if status:
        serialized = [t for t in serialized if t["status"] == status]
        # Apply offset/limit after status filtering
        serialized = serialized[offset : offset + limit]

    return serialized


# ---------------------------------------------------------------------------
# CRUD: Update
# ---------------------------------------------------------------------------


async def update_trade(
    db: AsyncSession,
    trade_id: uuid.UUID,
    **updates: Any,
) -> dict[str, Any] | None:
    """
    Update mutable fields on a trade.

    Allowed fields: stop_loss, take_profit, tags, comments, timeframe.
    Supports clearing nullable fields (stop_loss, take_profit, comments, tags)
    by explicitly passing None — the caller should use exclude_unset=True
    so that only fields the user actually sent are included.
    """
    allowed_fields = {"stop_loss", "take_profit", "tags", "comments", "timeframe"}
    nullable_fields = {"stop_loss", "take_profit", "tags", "comments"}
    filtered = {
        k: v
        for k, v in updates.items()
        if k in allowed_fields and (v is not None or k in nullable_fields)
    }

    if not filtered:
        # Nothing to update — just return current state
        return await get_trade(db, trade_id)

    user_id = _current_user_id()
    stmt = (
        select(Trade)
        .where(Trade.id == trade_id, Trade.user_id == user_id)
        .options(selectinload(Trade.exits), selectinload(Trade.legs))
    )
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()
    if trade is None:
        return None

    for field, value in filtered.items():
        if field == "stop_loss":
            trade.stop_loss = Decimal(str(value)) if value is not None else None  # type: ignore[assignment]
        elif field == "take_profit":
            trade.take_profit = Decimal(str(value)) if value is not None else None  # type: ignore[assignment]
        elif field == "timeframe":
            trade.timeframe = Timeframe(value)
        else:
            setattr(trade, field, value)

    await db.flush()
    await db.refresh(trade, attribute_names=["updated_at"])
    logger.info("Updated trade %s: %s", trade_id, list(filtered.keys()))
    return serialize_trade(trade)


# ---------------------------------------------------------------------------
# CRUD: Delete
# ---------------------------------------------------------------------------


async def delete_trade(db: AsyncSession, trade_id: uuid.UUID) -> bool:
    """Delete a trade and all its exits/legs (CASCADE). Returns True if found. Scoped to current user."""
    user_id = _current_user_id()
    stmt = delete(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    result = await db.execute(stmt)
    deleted: bool = result.rowcount > 0  # type: ignore[attr-defined]
    if deleted:
        logger.info("Deleted trade %s", trade_id)
    return deleted


# ---------------------------------------------------------------------------
# Sub-resource: Exits
# ---------------------------------------------------------------------------


async def add_exit(
    db: AsyncSession,
    trade_id: uuid.UUID,
    *,
    exit_date: date,
    exit_price: float,
    quantity: float,
    comments: str | None = None,
) -> dict[str, Any] | None:
    """
    Add an exit fill to a trade.

    Validates that exit quantity doesn't exceed remaining quantity.
    Returns the updated trade (with new exit included), or None if trade not found.
    """
    # Fetch trade with exits (scoped to current user)
    user_id = _current_user_id()
    stmt = (
        select(Trade)
        .where(Trade.id == trade_id, Trade.user_id == user_id)
        .options(selectinload(Trade.exits), selectinload(Trade.legs))
    )
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()
    if trade is None:
        return None

    # Validate quantity using unrounded, Decimal-based remaining quantity
    requested_quantity = Decimal(str(quantity))
    total_quantity = Decimal(str(trade.total_quantity))
    exited_quantity = sum((Decimal(str(exit_.quantity)) for exit_ in trade.exits), Decimal("0"))
    remaining_unrounded = total_quantity - exited_quantity
    if requested_quantity > remaining_unrounded:
        raise ValueError(
            f"Exit quantity ({requested_quantity}) exceeds remaining quantity ({remaining_unrounded})"
        )

    exit_ = TradeExit(
        trade_id=trade_id,
        exit_date=exit_date,
        exit_price=Decimal(str(exit_price)),
        quantity=requested_quantity,
        comments=comments,
    )
    db.add(exit_)
    await db.flush()

    # Re-fetch to get updated state
    return await get_trade(db, trade_id)


# ---------------------------------------------------------------------------
# Sub-resource: Legs
# ---------------------------------------------------------------------------


async def add_leg(
    db: AsyncSession,
    trade_id: uuid.UUID,
    *,
    leg_type: str,
    strike: float,
    expiry: date,
    quantity: float,
    premium: float,
) -> dict[str, Any] | None:
    """
    Add an option leg to a trade.

    Returns the updated trade (with new leg included), or None if trade not found.
    """
    # Verify trade exists (scoped to current user)
    user_id = _current_user_id()
    stmt = select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    result = await db.execute(stmt)
    trade = result.scalar_one_or_none()
    if trade is None:
        return None

    leg = TradeLeg(
        trade_id=trade_id,
        leg_type=LegType(leg_type),
        strike=Decimal(str(strike)),
        expiry=expiry,
        quantity=Decimal(str(quantity)),
        premium=Decimal(str(premium)),
    )
    db.add(leg)
    await db.flush()

    # Re-fetch to get updated state with all children
    return await get_trade(db, trade_id)
