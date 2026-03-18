"""
PraxiAlpha — Stocks API Routes

Endpoints for stock data queries and search.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.stock import Stock
from backend.services.stock_search import search_stocks

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=50, description="Search query (ticker or name)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    active_only: bool = Query(True, description="Only return active (non-delisted) stocks"),
    asset_type: str | None = Query(None, description="Filter by asset type (e.g., 'Common Stock')"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search stocks by ticker or company name.

    Returns ranked results: exact ticker match first, then ticker prefix matches,
    then company name matches. Case-insensitive.

    Examples:
    - `/search?q=AAPL` → exact match for Apple
    - `/search?q=AA` → AAPL, AAL, AABA, etc.
    - `/search?q=apple` → Apple Inc. via name match
    """
    asset_types = [asset_type] if asset_type else None
    results = await search_stocks(
        db=db,
        query=q,
        limit=limit,
        active_only=active_only,
        asset_types=asset_types,
    )
    return {"count": len(results), "results": results}


@router.get("/")
async def list_stocks(
    exchange: str | None = None,
    asset_type: str | None = None,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List stocks with optional filtering."""
    query = select(Stock)
    if active_only:
        query = query.where(Stock.is_active.is_(True))
    if exchange:
        query = query.where(Stock.exchange == exchange)
    if asset_type:
        query = query.where(Stock.asset_type == asset_type)

    query = query.order_by(Stock.ticker).limit(limit).offset(offset)
    result = await db.execute(query)
    stocks = result.scalars().all()

    return {
        "count": len(stocks),
        "stocks": [
            {
                "id": s.id,
                "ticker": s.ticker,
                "name": s.name,
                "exchange": s.exchange,
                "asset_type": s.asset_type,
                "sector": s.sector,
                "is_active": s.is_active,
                "total_records": s.total_records,
                "earliest_date": str(s.earliest_date) if s.earliest_date else None,
                "latest_date": str(s.latest_date) if s.latest_date else None,
            }
            for s in stocks
        ],
    }


@router.get("/count")
async def stock_count(db: AsyncSession = Depends(get_db)):
    """Get total count of stocks in the database."""
    from sqlalchemy import func

    result = await db.execute(select(func.count(Stock.id)).where(Stock.is_active.is_(True)))
    total_active = result.scalar()

    result = await db.execute(select(func.count(Stock.id)))
    total = result.scalar()

    return {"total": total, "active": total_active}


@router.get("/{ticker}")
async def get_stock(ticker: str, db: AsyncSession = Depends(get_db)):
    """Get stock details by ticker."""
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()
    if not stock:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Stock {ticker.upper()} not found")

    return {
        "id": stock.id,
        "ticker": stock.ticker,
        "name": stock.name,
        "exchange": stock.exchange,
        "asset_type": stock.asset_type,
        "sector": stock.sector,
        "industry": stock.industry,
        "is_active": stock.is_active,
        "eodhd_code": stock.eodhd_code,
        "earliest_date": str(stock.earliest_date) if stock.earliest_date else None,
        "latest_date": str(stock.latest_date) if stock.latest_date else None,
        "total_records": stock.total_records,
    }
