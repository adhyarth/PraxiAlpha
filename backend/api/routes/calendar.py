"""
PraxiAlpha — Economic Calendar API Routes

Endpoints that power the dashboard's economic calendar widget.
All data comes from the local database (synced by Celery task).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.data_pipeline.calendar_helpers import serialize_event
from backend.services.data_pipeline.economic_calendar_service import (
    EconomicCalendarService,
)

router = APIRouter(prefix="/calendar", tags=["Economic Calendar"])


@router.get("/upcoming")
async def upcoming_events(
    days: int = Query(default=7, ge=1, le=30, description="Lookahead window in days"),
    importance: int | None = Query(
        default=None, ge=1, le=3, description="Min importance (1=Low, 2=Med, 3=High)"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Get upcoming economic calendar events from the database.

    Sorted by date ascending. Use `importance=3` for high-impact only.
    """
    svc = EconomicCalendarService(db)
    events = await svc.get_upcoming_events(days=days, importance=importance, limit=limit)
    return {
        "count": len(events),
        "events": [serialize_event(e) for e in events],
    }


@router.get("/high-impact")
async def high_impact_events(
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get only high-importance (3) events for the next N days.

    This is the primary endpoint for the dashboard widget.
    """
    svc = EconomicCalendarService(db)
    events = await svc.get_high_impact_events(days=days, limit=limit)
    return {
        "count": len(events),
        "events": [serialize_event(e) for e in events],
    }


@router.post("/sync")
async def sync_calendar(
    days: int = Query(default=14, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger a sync of upcoming events from TradingEconomics.

    Normally this is handled by the Celery beat schedule, but this endpoint
    lets you force a refresh from the dashboard or during development.
    """
    svc = EconomicCalendarService(db)
    count = await svc.sync_upcoming_events(days=days)
    return {"synced": count, "message": f"Upserted {count} events from TradingEconomics."}
