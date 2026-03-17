"""
PraxiAlpha — Charts API Routes

Endpoints for OHLCV candle data across timeframes (daily, weekly, monthly, quarterly).
Data is served from TimescaleDB continuous aggregates for sub-second response times.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.candle_service import CandleService, Timeframe

router = APIRouter(prefix="/charts", tags=["Charts"])


@router.get("/{ticker}/candles")
async def get_candles(
    ticker: str,
    timeframe: Timeframe = Query(
        default=Timeframe.DAILY,
        description="Candle timeframe: daily, weekly, monthly, quarterly",
    ),
    start: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max candles to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get OHLCV candle data for a stock ticker.

    Returns candles in ascending date order (oldest first), suitable for
    charting libraries like Plotly or Lightweight Charts.

    Examples:
        GET /api/v1/charts/AAPL/candles?timeframe=daily&limit=252
        GET /api/v1/charts/AAPL/candles?timeframe=weekly&start=2024-01-01
        GET /api/v1/charts/AAPL/candles?timeframe=monthly&start=2020-01-01&end=2025-12-31
        GET /api/v1/charts/AAPL/candles?timeframe=quarterly&limit=40
    """
    # Resolve ticker → stock_id
    result = await db.execute(
        text("SELECT id, ticker, name FROM stocks WHERE ticker = :ticker LIMIT 1"),
        {"ticker": ticker.upper()},
    )
    stock_row = result.fetchone()
    if not stock_row:
        raise HTTPException(status_code=404, detail=f"Stock '{ticker.upper()}' not found")

    service = CandleService(db)
    candles = await service.get_candles(
        stock_id=stock_row.id,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
    )

    return {
        "ticker": stock_row.ticker,
        "name": stock_row.name,
        "timeframe": timeframe.value,
        "count": len(candles),
        "candles": candles,
    }


@router.get("/{ticker}/summary")
async def get_chart_summary(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a summary of available candle data for a stock across all timeframes.

    Useful for the UI to know what date ranges and timeframes are available.
    """
    # Resolve ticker → stock_id
    result = await db.execute(
        text("SELECT id, ticker, name FROM stocks WHERE ticker = :ticker LIMIT 1"),
        {"ticker": ticker.upper()},
    )
    stock_row = result.fetchone()
    if not stock_row:
        raise HTTPException(status_code=404, detail=f"Stock '{ticker.upper()}' not found")

    service = CandleService(db)
    summary = {}
    for tf in Timeframe:
        count = await service.get_candle_count(stock_row.id, tf)
        date_range = await service.get_date_range(stock_row.id, tf)
        summary[tf.value] = {
            "count": count,
            **date_range,
        }

    return {
        "ticker": stock_row.ticker,
        "name": stock_row.name,
        "timeframes": summary,
    }


@router.get("/stats")
async def get_aggregate_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get row counts for all candle aggregate views.

    Useful for monitoring and health checks.
    """
    service = CandleService(db)
    stats = await service.get_aggregate_stats()
    return {"candle_stats": stats}
