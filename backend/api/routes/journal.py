"""
PraxiAlpha — Trading Journal API Routes

CRUD endpoints for the trading journal:
- GET/POST /api/v1/journal/           — list & create trades
- GET/PUT/DELETE /api/v1/journal/{id} — read, update, delete a trade
- POST /api/v1/journal/{id}/exits     — add a partial/full exit
- POST /api/v1/journal/{id}/legs      — add an option leg
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services import journal_service, trade_snapshot_service
from backend.services.candle_service import CandleService
from backend.services.candle_service import Timeframe as CandleTimeframe
from backend.services.journal_report_service import (
    build_trade_chart,
    generate_report_pdf,
    get_chart_end_date,
    get_lookback_start,
)

router = APIRouter(prefix="/journal", tags=["Trading Journal"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateTradeRequest(BaseModel):
    """Request body for creating a new trade."""

    ticker: str = Field(..., min_length=1, max_length=20)
    direction: str = Field(..., pattern="^(long|short)$")
    asset_type: str = Field(..., pattern="^(shares|options)$")
    trade_type: str = Field(default="single_leg", pattern="^(single_leg|multi_leg)$")
    timeframe: str = Field(..., pattern="^(daily|weekly|monthly|quarterly)$")
    entry_date: date
    entry_price: float = Field(..., gt=0)
    total_quantity: float = Field(..., gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    tags: list[str] | None = None
    comments: str | None = None


class UpdateTradeRequest(BaseModel):
    """Request body for updating a trade. All fields optional."""

    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    tags: list[str] | None = None
    comments: str | None = None
    timeframe: str | None = Field(default=None, pattern="^(daily|weekly|monthly|quarterly)$")


class AddExitRequest(BaseModel):
    """Request body for adding an exit fill."""

    exit_date: date
    exit_price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    comments: str | None = None


class AddLegRequest(BaseModel):
    """Request body for adding an option leg."""

    leg_type: str = Field(..., pattern="^(buy_call|sell_call|buy_put|sell_put)$")
    strike: float = Field(..., gt=0)
    expiry: date
    quantity: float = Field(..., gt=0)
    premium: float = Field(...)  # Can be negative for credits received


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_trades(
    ticker: str | None = Query(default=None, description="Filter by ticker"),
    status: str | None = Query(default=None, pattern="^(open|partial|closed)$"),
    direction: str | None = Query(default=None, pattern="^(long|short)$"),
    timeframe: str | None = Query(default=None, pattern="^(daily|weekly|monthly|quarterly)$"),
    tags: str | None = Query(default=None, description="Comma-separated tags (all must match)"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    List trades with optional filters.

    Supports filtering by ticker, status (computed), direction, timeframe,
    tags (comma-separated), and date range.
    """
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    trades = await journal_service.list_trades(
        db,
        ticker=ticker,
        status=status,
        direction=direction,
        timeframe=timeframe,
        tags=tag_list,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {"count": len(trades), "trades": trades}


@router.post("/", status_code=201)
async def create_trade(
    body: CreateTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new trade entry in the journal."""
    trade = await journal_service.create_trade(
        db,
        ticker=body.ticker,
        direction=body.direction,
        asset_type=body.asset_type,
        trade_type=body.trade_type,
        timeframe=body.timeframe,
        entry_date=body.entry_date,
        entry_price=body.entry_price,
        total_quantity=body.total_quantity,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        tags=body.tags,
        comments=body.comments,
    )
    return trade


# ---------------------------------------------------------------------------
# PDF Report Endpoint (must be before /{trade_id} to avoid path collision)
# ---------------------------------------------------------------------------


@router.get("/report")
async def generate_journal_report(
    start_date: date | None = Query(default=None, description="Report start date"),
    end_date: date | None = Query(default=None, description="Report end date"),
    status: str | None = Query(default=None, pattern="^(open|partial|closed)$"),
    ticker: str | None = Query(default=None),
    include_charts: bool = Query(default=True, description="Embed candlestick charts"),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a PDF report of journal trades.

    Filters trades by date range / status / ticker, builds annotated
    candlestick charts per trade, and returns a downloadable PDF.
    """
    trades = await journal_service.list_trades(
        db,
        ticker=ticker,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=200,
        offset=0,
    )

    chart_images: dict[str, bytes] = {}

    if include_charts:
        candle_svc = CandleService(db)
        for trade in trades:
            try:
                tf = CandleTimeframe(trade["timeframe"])
                chart_start = get_lookback_start(trade)
                chart_end = get_chart_end_date(trade)

                # Resolve stock_id from ticker — use the stocks table
                from sqlalchemy import text as sa_text  # noqa: PLC0415

                row = (
                    await db.execute(
                        sa_text("SELECT id FROM stocks WHERE ticker = :t LIMIT 1"),
                        {"t": trade["ticker"]},
                    )
                ).fetchone()
                if row is None:
                    continue
                stock_id = row[0]

                candles = await candle_svc.get_candles(
                    stock_id=stock_id,
                    timeframe=tf,
                    start=chart_start,
                    end=chart_end,
                    limit=1000,
                )
                img = build_trade_chart(candles, trade)
                if img:
                    chart_images[trade["id"]] = img
            except Exception:
                # Chart generation is best-effort — don't fail the report
                import logging  # noqa: PLC0415

                logging.getLogger(__name__).warning(
                    "Chart generation failed for trade %s",
                    trade.get("id"),
                    exc_info=True,
                )

    pdf_bytes = generate_report_pdf(
        trades,
        chart_images,
        start_date=start_date,
        end_date=end_date,
    )

    filename = "journal_report"
    if start_date:
        filename += f"_{start_date.isoformat()}"
    if end_date:
        filename += f"_to_{end_date.isoformat()}"
    filename += ".pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Single-Trade CRUD
# ---------------------------------------------------------------------------


@router.get("/{trade_id}")
async def get_trade(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a trade by ID, including exits and legs."""
    trade = await journal_service.get_trade(db, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.put("/{trade_id}")
async def update_trade(
    trade_id: uuid.UUID,
    body: UpdateTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update mutable fields on a trade.

    Allowed: stop_loss, take_profit, tags, comments, timeframe.
    """
    updates = body.model_dump(exclude_unset=True)
    trade = await journal_service.update_trade(db, trade_id, **updates)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.delete("/{trade_id}", status_code=204)
async def delete_trade(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a trade and all its exits/legs."""
    deleted = await journal_service.delete_trade(db, trade_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trade not found")


@router.post("/{trade_id}/exits")
async def add_exit(
    trade_id: uuid.UUID,
    body: AddExitRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a partial or full exit fill to a trade."""
    try:
        trade = await journal_service.add_exit(
            db,
            trade_id,
            exit_date=body.exit_date,
            exit_price=body.exit_price,
            quantity=body.quantity,
            comments=body.comments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.post("/{trade_id}/legs")
async def add_leg(
    trade_id: uuid.UUID,
    body: AddLegRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add an option leg to a trade."""
    trade = await journal_service.add_leg(
        db,
        trade_id,
        leg_type=body.leg_type,
        strike=body.strike,
        expiry=body.expiry,
        quantity=body.quantity,
        premium=body.premium,
    )
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


# ---------------------------------------------------------------------------
# Post-Close What-If Snapshot Endpoints
# ---------------------------------------------------------------------------


@router.get("/{trade_id}/snapshots")
async def list_trade_snapshots(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all post-close price snapshots for a trade, ordered by date."""
    snapshots = await trade_snapshot_service.list_snapshots(db, trade_id)
    if snapshots is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"count": len(snapshots), "snapshots": snapshots}


@router.get("/{trade_id}/what-if")
async def get_whatif_summary(
    trade_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the what-if summary for a closed trade.

    Compares actual exit PnL against the best/worst hypothetical PnL
    if the full position had been held longer.
    """
    summary = await trade_snapshot_service.get_whatif_summary(db, trade_id)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="Trade not found or not closed",
        )
    return summary
