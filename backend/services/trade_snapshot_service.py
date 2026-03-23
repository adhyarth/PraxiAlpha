"""
PraxiAlpha — Trade Snapshot Service

Handles post-close "what-if" analysis:
- Create snapshots (called by Celery task)
- List snapshots for a trade
- Compute what-if summary (best/worst hypothetical PnL vs actual exit)

Direction-aware PnL:
  Long:  (close_price - entry_price) * total_quantity
  Short: (entry_price - close_price) * total_quantity

Full position assumed — hypothetical PnL uses the entire original quantity,
not the remaining quantity at close time.
"""

import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.journal import AssetType, Timeframe, Trade, TradeDirection
from backend.models.trade_snapshot import TradeSnapshot
from backend.services.journal_service import _current_user_id, compute_trade_metrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Max tracking durations by timeframe (calendar days)
# ---------------------------------------------------------------------------
MAX_TRACKING_DAYS = {
    Timeframe.DAILY: 30,  # 30 calendar days
    Timeframe.WEEKLY: 112,  # 16 weeks = 112 calendar days
    Timeframe.MONTHLY: 540,  # 18 months ≈ 540 calendar days
    Timeframe.QUARTERLY: 540,  # same as monthly
}

# ---------------------------------------------------------------------------
# Snapshot cadence by timeframe (calendar days between snapshots)
# ---------------------------------------------------------------------------
SNAPSHOT_CADENCE_DAYS = {
    Timeframe.DAILY: 1,  # every trading day
    Timeframe.WEEKLY: 7,  # weekly
    Timeframe.MONTHLY: 30,  # monthly (approx)
    Timeframe.QUARTERLY: 30,  # monthly (same as monthly)
}


# ---------------------------------------------------------------------------
# PnL computation helpers
# ---------------------------------------------------------------------------


def compute_hypothetical_pnl(
    entry_price: float,
    close_price: float,
    total_quantity: float,
    direction: str,
) -> tuple[float, float]:
    """
    Compute hypothetical PnL and PnL % for a full-position hold.

    Returns (pnl_dollars, pnl_pct).
    Uses Decimal arithmetic to avoid float drift.
    """
    ep = Decimal(str(entry_price))
    cp = Decimal(str(close_price))
    qty = Decimal(str(total_quantity))

    if direction == TradeDirection.LONG or direction == "long":
        pnl = (cp - ep) * qty
    else:  # short
        pnl = (ep - cp) * qty

    cost_basis = ep * qty
    pnl_pct = Decimal("0") if cost_basis == 0 else (pnl / cost_basis) * Decimal("100")

    return float(pnl.quantize(Decimal("0.0001"))), float(pnl_pct.quantize(Decimal("0.0001")))


# ---------------------------------------------------------------------------
# Snapshot CRUD
# ---------------------------------------------------------------------------


async def create_snapshot(
    db: AsyncSession,
    trade_id: uuid.UUID,
    snapshot_date: date,
    close_price: float,
    hypothetical_pnl: float,
    hypothetical_pnl_pct: float,
) -> dict[str, Any]:
    """
    Create a single trade snapshot. Used by the Celery task.

    The UNIQUE(trade_id, snapshot_date) constraint prevents duplicates.
    """
    snapshot = TradeSnapshot(
        trade_id=trade_id,
        snapshot_date=snapshot_date,
        close_price=close_price,
        hypothetical_pnl=hypothetical_pnl,
        hypothetical_pnl_pct=hypothetical_pnl_pct,
    )
    db.add(snapshot)
    await db.flush()
    await db.refresh(snapshot)
    return _serialize_snapshot(snapshot)


async def list_snapshots(
    db: AsyncSession,
    trade_id: uuid.UUID,
) -> list[dict[str, Any]] | None:
    """
    List all snapshots for a trade, ordered by date.

    Returns None if the trade doesn't exist or belongs to another user.
    """
    # Verify trade ownership
    trade = await _get_user_trade(db, trade_id)
    if trade is None:
        return None

    stmt = (
        select(TradeSnapshot)
        .where(TradeSnapshot.trade_id == trade_id)
        .order_by(TradeSnapshot.snapshot_date)
    )
    result = await db.execute(stmt)
    snapshots = result.scalars().all()
    return [_serialize_snapshot(s) for s in snapshots]


async def get_whatif_summary(
    db: AsyncSession,
    trade_id: uuid.UUID,
) -> dict[str, Any] | None:
    """
    Compute the what-if summary for a closed trade.

    Returns:
    - actual_pnl, actual_pnl_pct (from trade exits)
    - best hypothetical (max PnL snapshot)
    - worst hypothetical (min PnL snapshot)
    - latest snapshot
    - total snapshots count

    Returns None if the trade doesn't exist, belongs to another user,
    or is not closed.
    """
    trade = await _get_user_trade(db, trade_id)
    if trade is None:
        return None

    # Compute actual trade metrics
    metrics = compute_trade_metrics(trade)
    if metrics["status"] != "closed":
        return None

    # Options trades are not eligible for what-if analysis (no live options pricing)
    if trade.asset_type == AssetType.OPTIONS:
        return {
            "trade_id": str(trade_id),
            "ticker": trade.ticker,
            "direction": trade.direction.value
            if hasattr(trade.direction, "value")
            else str(trade.direction),
            "actual_pnl": metrics["realized_pnl"],
            "actual_pnl_pct": metrics["return_pct"],
            "best_hypothetical": None,
            "worst_hypothetical": None,
            "latest_snapshot": None,
            "total_snapshots": 0,
            "reason": "What-if analysis is not available for options trades (no live options pricing data).",
        }

    # Fetch all snapshots
    stmt = (
        select(TradeSnapshot)
        .where(TradeSnapshot.trade_id == trade_id)
        .order_by(TradeSnapshot.snapshot_date)
    )
    result = await db.execute(stmt)
    snapshots = list(result.scalars().all())

    if not snapshots:
        return {
            "trade_id": str(trade_id),
            "ticker": trade.ticker,
            "direction": trade.direction.value
            if hasattr(trade.direction, "value")
            else str(trade.direction),
            "actual_pnl": metrics["realized_pnl"],
            "actual_pnl_pct": metrics["return_pct"],
            "best_hypothetical": None,
            "worst_hypothetical": None,
            "latest_snapshot": None,
            "total_snapshots": 0,
        }

    best = max(snapshots, key=lambda s: float(s.hypothetical_pnl))
    worst = min(snapshots, key=lambda s: float(s.hypothetical_pnl))
    latest = snapshots[-1]

    return {
        "trade_id": str(trade_id),
        "ticker": trade.ticker,
        "direction": trade.direction.value
        if hasattr(trade.direction, "value")
        else str(trade.direction),
        "actual_pnl": metrics["realized_pnl"],
        "actual_pnl_pct": metrics["return_pct"],
        "best_hypothetical": _serialize_snapshot(best),
        "worst_hypothetical": _serialize_snapshot(worst),
        "latest_snapshot": _serialize_snapshot(latest),
        "total_snapshots": len(snapshots),
    }


# ---------------------------------------------------------------------------
# Closed trades finder (for Celery task)
# ---------------------------------------------------------------------------


async def get_closed_trades_needing_snapshots(
    db: AsyncSession,
    reference_date: date | None = None,
) -> list[dict[str, Any]]:
    """
    Find all closed trades that need a new snapshot on the given date.

    A trade needs a snapshot if:
    1. It is closed (all quantity exited)
    2. It hasn't exceeded its max tracking duration
    3. The reference_date aligns with the trade's snapshot cadence
    4. It doesn't already have a snapshot for this date

    Returns a list of dicts with trade info needed to create snapshots.
    """
    if reference_date is None:
        reference_date = date.today()

    # Load all trades with exits for the current user
    stmt = (
        select(Trade).options(selectinload(Trade.exits)).where(Trade.user_id == _current_user_id())
    )
    result = await db.execute(stmt)
    trades = result.scalars().all()

    # Filter to closed trades within tracking window + cadence check
    candidates = []
    candidate_ids = []
    for trade in trades:
        metrics = compute_trade_metrics(trade)
        if metrics["status"] != "closed":
            continue

        # Skip options trades — we don't have live options pricing data,
        # so equity OHLCV prices would produce meaningless what-if PnL.
        if trade.asset_type == AssetType.OPTIONS:
            continue

        # Check max tracking duration
        last_exit_date = max(e.exit_date for e in trade.exits)
        max_days = MAX_TRACKING_DAYS.get(trade.timeframe, 30)
        cutoff_date = last_exit_date + timedelta(days=max_days)
        if reference_date > cutoff_date:
            continue

        # Check timeframe-aware cadence
        cadence = SNAPSHOT_CADENCE_DAYS.get(trade.timeframe, 1)
        days_since_exit = (reference_date - last_exit_date).days
        if cadence > 1 and days_since_exit % cadence != 0:
            continue

        candidates.append(trade)
        candidate_ids.append(trade.id)

    if not candidate_ids:
        return []

    # Batch check: fetch all existing snapshot trade_ids for this date in one query
    existing_stmt = select(TradeSnapshot.trade_id).where(
        TradeSnapshot.trade_id.in_(candidate_ids),
        TradeSnapshot.snapshot_date == reference_date,
    )
    existing_result = await db.execute(existing_stmt)
    already_snapshotted = {row[0] for row in existing_result.all()}

    eligible = []
    for trade in candidates:
        if trade.id in already_snapshotted:
            continue

        eligible.append(
            {
                "trade_id": trade.id,
                "ticker": trade.ticker,
                "entry_price": float(trade.entry_price),
                "total_quantity": float(trade.total_quantity),
                "direction": trade.direction.value
                if hasattr(trade.direction, "value")
                else str(trade.direction),
                "timeframe": trade.timeframe.value
                if hasattr(trade.timeframe, "value")
                else str(trade.timeframe),
            }
        )

    return eligible


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_trade(db: AsyncSession, trade_id: uuid.UUID) -> Trade | None:
    """Fetch a trade by ID scoped to the current user, with exits loaded."""
    stmt = (
        select(Trade)
        .options(selectinload(Trade.exits))
        .where(Trade.id == trade_id, Trade.user_id == _current_user_id())
    )
    result = await db.execute(stmt)
    trade: Trade | None = result.scalar_one_or_none()
    return trade


def _serialize_snapshot(snapshot: TradeSnapshot) -> dict[str, Any]:
    """Convert a TradeSnapshot to a JSON-serializable dict."""
    return {
        "id": str(snapshot.id),
        "trade_id": str(snapshot.trade_id),
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "close_price": float(snapshot.close_price),
        "hypothetical_pnl": float(snapshot.hypothetical_pnl),
        "hypothetical_pnl_pct": float(snapshot.hypothetical_pnl_pct),
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }
