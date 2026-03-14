"""
PraxiAlpha — Economic Calendar Service

Orchestrates fetching, upserting, and querying economic calendar events.

This is the bridge between the TradingEconomicsFetcher (raw API calls) and
the EconomicCalendarEvent model (database). The dashboard and Celery tasks
call this service — they never touch the fetcher or DB directly.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.economic_calendar import (
    US_HIGH_IMPACT_EVENTS,
    EconomicCalendarEvent,
)
from backend.services.data_pipeline.trading_economics_fetcher import (
    TradingEconomicsFetcher,
)

logger = logging.getLogger(__name__)

# Events older than this are pruned on each sync
RETENTION_DAYS = 90


class EconomicCalendarService:
    """
    High-level service for economic calendar operations.

    Usage:
        async with async_session_factory() as session:
            svc = EconomicCalendarService(session)
            await svc.sync_upcoming_events()
            events = await svc.get_upcoming_events()
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- Write Operations ----

    async def sync_upcoming_events(
        self,
        days: int = 14,
        country: str = "united states",
        importance: int | None = None,
    ) -> int:
        """
        Fetch events from TradingEconomics and upsert into the database.

        Args:
            days: Lookahead window (default 14 days).
            country: Country filter (default US).
            importance: Min importance (None = all).

        Returns:
            Number of events upserted.
        """
        fetcher = TradingEconomicsFetcher()
        try:
            raw_events = await fetcher.fetch_upcoming_events(
                days=days, country=country, importance=importance
            )
        finally:
            await fetcher.close()

        if not raw_events:
            logger.info("No upcoming events returned from TradingEconomics.")
            return 0

        # Parse raw TE dicts → model-friendly dicts
        parsed = [TradingEconomicsFetcher.parse_event(e) for e in raw_events]

        upserted = await self._upsert_events(parsed)
        logger.info(f"Synced {upserted} economic calendar events.")
        return upserted

    async def _upsert_events(self, events: list[dict]) -> int:
        """
        Upsert a list of parsed event dicts into the database.

        Uses PostgreSQL INSERT ... ON CONFLICT (calendar_id) DO UPDATE
        so re-syncing the same window is idempotent.
        """
        if not events:
            return 0

        count = 0
        for event in events:
            stmt = (
                pg_insert(EconomicCalendarEvent)
                .values(**event)
                .on_conflict_do_update(
                    constraint="uq_economic_calendar_id",
                    set_={
                        "actual": event.get("actual"),
                        "previous": event.get("previous"),
                        "forecast": event.get("forecast"),
                        "te_forecast": event.get("te_forecast"),
                        "revised": event.get("revised"),
                        "importance": event.get("importance"),
                        "te_last_update": event.get("te_last_update"),
                    },
                )
            )
            await self.session.execute(stmt)
            count += 1

        await self.session.flush()
        return count

    async def prune_old_events(self, retention_days: int = RETENTION_DAYS) -> int:
        """
        Delete events older than *retention_days* to keep the table small.

        Returns:
            Number of rows deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = delete(EconomicCalendarEvent).where(EconomicCalendarEvent.date < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        deleted: int = result.rowcount  # type: ignore[assignment,attr-defined]
        logger.info(f"Pruned {deleted} economic calendar events older than {cutoff.date()}.")
        return deleted

    # ---- Read Operations ----

    async def get_upcoming_events(
        self,
        days: int = 7,
        importance: int | None = None,
        limit: int = 50,
    ) -> list[EconomicCalendarEvent]:
        """
        Query upcoming events from the database.

        Args:
            days: Lookahead window.
            importance: Filter by minimum importance (None = all).
            limit: Max results.

        Returns:
            List of EconomicCalendarEvent model instances, sorted by date.
        """
        now = datetime.now(UTC)
        end = now + timedelta(days=days)

        query = (
            select(EconomicCalendarEvent)
            .where(EconomicCalendarEvent.date >= now)
            .where(EconomicCalendarEvent.date <= end)
        )

        if importance is not None:
            query = query.where(EconomicCalendarEvent.importance >= importance)

        query = query.order_by(EconomicCalendarEvent.date).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_high_impact_events(
        self, days: int = 7, limit: int = 20
    ) -> list[EconomicCalendarEvent]:
        """
        Convenience: get only high-importance (3) events for the next N days.
        This is what the dashboard widget calls.
        """
        return await self.get_upcoming_events(days=days, importance=3, limit=limit)

    async def get_events_for_category(
        self, category: str, days: int = 30, limit: int = 20
    ) -> list[EconomicCalendarEvent]:
        """
        Get events for a specific category (e.g., "Non Farm Payrolls").

        Useful for drill-down views.
        """
        now = datetime.now(UTC)
        end = now + timedelta(days=days)

        query = (
            select(EconomicCalendarEvent)
            .where(EconomicCalendarEvent.date >= now)
            .where(EconomicCalendarEvent.date <= end)
            .where(EconomicCalendarEvent.category == category)
            .order_by(EconomicCalendarEvent.date)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def is_high_impact(event: EconomicCalendarEvent) -> bool:
        """Check if an event is in the US_HIGH_IMPACT_EVENTS registry."""
        return event.category in US_HIGH_IMPACT_EVENTS
