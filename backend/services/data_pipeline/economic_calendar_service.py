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
        so re-syncing the same window is idempotent. Validates each event
        before insertion and skips malformed ones (missing calendar_id or
        unparseable date).
        """
        if not events:
            return 0

        # Validate and normalize events, dropping any with bad data
        valid_events: list[dict] = []
        for raw_event in events:
            prepared = self._prepare_event_for_upsert(raw_event)
            if prepared is not None:
                valid_events.append(prepared)

        if not valid_events:
            return 0

        # Bulk upsert — single statement for all events
        insert_stmt = pg_insert(EconomicCalendarEvent).values(valid_events)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            constraint="uq_economic_calendar_id",
            set_={
                # Update fields that can change between syncs
                "date": insert_stmt.excluded.date,
                "country": insert_stmt.excluded.country,
                "category": insert_stmt.excluded.category,
                "event": insert_stmt.excluded.event,
                "actual": insert_stmt.excluded.actual,
                "previous": insert_stmt.excluded.previous,
                "forecast": insert_stmt.excluded.forecast,
                "te_forecast": insert_stmt.excluded.te_forecast,
                "revised": insert_stmt.excluded.revised,
                "importance": insert_stmt.excluded.importance,
                "te_last_update": insert_stmt.excluded.te_last_update,
            },
        )
        await self.session.execute(upsert_stmt)
        await self.session.flush()
        return len(valid_events)

    def _prepare_event_for_upsert(self, event: dict) -> dict | None:
        """
        Validate and normalize a single event dict before upsert.

        Ensures required fields are present and timestamp fields are
        converted to timezone-aware datetimes. Returns a new, safe dict,
        or None if the event should be skipped.
        """
        # Require a stable identifier and a date; skip if missing.
        calendar_id = event.get("calendar_id")
        raw_date = event.get("date")
        if not calendar_id or not raw_date:
            logger.warning(
                "Skipping economic calendar event due to missing calendar_id or date: %s",
                event,
            )
            return None

        normalized = dict(event)

        # Normalize the primary date field.
        if isinstance(raw_date, str):
            parsed_date = self._parse_timestamp(raw_date)
            if parsed_date is None:
                logger.warning(
                    "Skipping economic calendar event due to unparseable date '%s': %s",
                    raw_date,
                    event,
                )
                return None
            normalized["date"] = parsed_date

        # Normalize TradingEconomics "last update" timestamp if present.
        te_last_update = normalized.get("te_last_update")
        if isinstance(te_last_update, str):
            parsed_update = self._parse_timestamp(te_last_update)
            if parsed_update is None:
                logger.warning(
                    "Skipping economic calendar event due to unparseable te_last_update '%s': %s",
                    te_last_update,
                    event,
                )
                return None
            normalized["te_last_update"] = parsed_update

        # Normalize reference_date if present.
        reference_date = normalized.get("reference_date")
        if isinstance(reference_date, str):
            normalized["reference_date"] = self._parse_timestamp(reference_date)
            # reference_date is optional — None is fine if unparseable

        return normalized

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        """
        Parse a timestamp string into a timezone-aware datetime.

        Returns None if parsing fails.
        """
        if not value:
            return None

        # Handle common ISO-8601 formats, including a trailing "Z"
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None

        # Ensure the datetime is timezone-aware; default to UTC if naive.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt

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
