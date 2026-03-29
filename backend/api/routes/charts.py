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
    adjusted: bool = Query(
        default=True,
        description=(
            "If true (default), return split- and dividend-adjusted OHLCV prices. "
            "Produces a smooth, continuous chart like TradingView — no jumps at "
            "split boundaries. For non-daily timeframes (weekly, monthly, quarterly), "
            "adjusted daily candles are re-aggregated in Python so that splits "
            "occurring mid-week/month are handled correctly. "
            "If false, return raw historical prices as originally recorded (daily "
            "from the hypertable, non-daily from the TimescaleDB continuous aggregates)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Get OHLCV candle data for a stock ticker.

    Returns candles in ascending date order (oldest first), suitable for
    charting libraries like Plotly or Lightweight Charts.

    By default, prices are **split-adjusted** across all timeframes so
    charts are continuous (no jumps at split boundaries).  For non-daily
    timeframes, adjusted daily candles are fetched and re-aggregated in
    Python to avoid the SQL aggregate's raw-price mixing problem.
    Pass ``adjusted=false`` to get raw historical prices from the
    pre-computed SQL aggregates.

    The response includes ``adjusted`` (boolean) indicating whether
    split/dividend adjustment was applied.

    Examples:
        GET /api/v1/charts/AAPL/candles?timeframe=daily&limit=252
        GET /api/v1/charts/AAPL/candles?timeframe=weekly&start=2024-01-01
        GET /api/v1/charts/AAPL/candles?adjusted=false&limit=500
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
        adjusted=adjusted,
    )

    # Adjustment is now applied for ALL timeframes when adjusted=True.
    # Daily candles are adjusted per-row; non-daily candles are rebuilt
    # from adjusted daily data in Python.
    adjusted_applied = bool(adjusted)

    return {
        "ticker": stock_row.ticker,
        "name": stock_row.name,
        "timeframe": timeframe.value,
        "adjusted": adjusted_applied,
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
    summary = await service.get_candle_summary(stock_row.id)

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
