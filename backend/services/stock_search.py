"""
PraxiAlpha — Stock Search Service

Provides typeahead/autocomplete search across the stocks table.
Searches by ticker (prefix match) and company name (substring match).
Returns ranked results: exact ticker match first, then ticker prefix, then name matches.
"""

import logging
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.stock import Stock

logger = logging.getLogger(__name__)


async def search_stocks(
    db: AsyncSession,
    query: str | None,
    limit: int = 10,
    active_only: bool = True,
    asset_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Search stocks by ticker or company name.

    Ranking order:
    1. Exact ticker match (e.g., query="AAPL" matches ticker "AAPL")
    2. Ticker prefix match (e.g., query="AA" matches "AAPL", "AAL", "AABA")
    3. Name substring match (e.g., query="apple" matches "Apple Inc.")

    Args:
        db: Async database session.
        query: Search string (case-insensitive). Minimum 1 character.
        limit: Maximum number of results to return (default 10, max 50).
        active_only: If True, only return active (non-delisted) stocks.
        asset_types: Optional filter for asset types (e.g., ["Common Stock", "ETF"]).

    Returns:
        List of stock dicts sorted by relevance, each containing:
        id, ticker, name, exchange, asset_type, sector.
    """
    if not query or not query.strip():
        return []

    query_str = query.strip()
    limit = max(1, min(limit, 50))  # Clamp to [1, 50]

    upper_q = query_str.upper()
    lower_q = query_str.lower()

    # Build the WHERE clause: ticker starts with query OR name contains query
    ticker_prefix = Stock.ticker.ilike(f"{upper_q}%")
    name_contains = Stock.name.ilike(f"%{lower_q}%")

    filters = [or_(ticker_prefix, name_contains)]

    if active_only:
        filters.append(Stock.is_active.is_(True))

    if asset_types:
        filters.append(Stock.asset_type.in_(asset_types))

    # Ranking: exact ticker = 0, ticker prefix = 1, name-only match = 2
    rank = case(
        (Stock.ticker == upper_q, 0),
        (Stock.ticker.ilike(f"{upper_q}%"), 1),
        else_=2,
    )

    stmt = (
        select(Stock)
        .where(*filters)
        .order_by(rank, func.length(Stock.ticker), Stock.ticker)
        .limit(limit)
    )

    result = await db.execute(stmt)
    stocks = result.scalars().all()

    return [_serialize_stock(s) for s in stocks]


def _serialize_stock(stock: Stock) -> dict[str, Any]:
    """Convert a Stock ORM object to a dict for API responses."""
    return {
        "id": stock.id,
        "ticker": stock.ticker,
        "name": stock.name,
        "exchange": stock.exchange,
        "asset_type": stock.asset_type,
        "sector": stock.sector,
        "latest_date": str(stock.latest_date) if stock.latest_date else None,
        "total_records": stock.total_records,
    }


def format_stock_option(stock: dict[str, Any]) -> str:
    """
    Format a stock dict as a human-readable option string.

    Examples:
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}
        → "AAPL — Apple Inc. (NASDAQ)"

    This function is intentionally Streamlit-free so it can be tested
    in lightweight CI environments.
    """
    ticker = stock.get("ticker", "???")
    name = stock.get("name") or ""
    exchange = stock.get("exchange") or ""
    parts = [ticker]
    if name:
        parts.append(f"— {name}")
    if exchange:
        parts.append(f"({exchange})")
    return " ".join(parts)
