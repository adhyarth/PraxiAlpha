"""
PraxiAlpha — Economic Calendar Integration Tests

Tests for EconomicCalendarService (service layer) and calendar API routes.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.economic_calendar import EconomicCalendarEvent
from backend.services.data_pipeline.economic_calendar_service import (
    EconomicCalendarService,
)

# ---- Service Tests ----


class TestEconomicCalendarService:
    """Tests for the EconomicCalendarService class."""

    @pytest.mark.asyncio
    async def test_sync_upcoming_events_calls_fetcher(self):
        """sync_upcoming_events should call the fetcher and upsert results."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        raw_events = [
            {
                "CalendarId": "100",
                "Date": "2026-04-01T13:30:00",
                "Country": "United States",
                "Category": "Non Farm Payrolls",
                "Event": "Non Farm Payrolls",
                "Importance": 3,
                "Actual": None,
                "Previous": "225K",
                "Forecast": "200K",
                "TEForecast": "210K",
                "Revised": None,
                "Reference": "Mar",
                "ReferenceDate": None,
                "Source": "BLS",
                "SourceURL": None,
                "URL": "/nfp",
                "Currency": "",
                "Unit": "K",
                "Ticker": "NFP",
                "LastUpdate": None,
            },
        ]

        with patch(
            "backend.services.data_pipeline.economic_calendar_service.TradingEconomicsFetcher"
        ) as MockFetcher:
            mock_fetcher_instance = AsyncMock()
            mock_fetcher_instance.fetch_upcoming_events.return_value = raw_events
            mock_fetcher_instance.close = AsyncMock()
            # parse_event is a static method — use the real one
            MockFetcher.return_value = mock_fetcher_instance
            MockFetcher.parse_event = __import__(
                "backend.services.data_pipeline.trading_economics_fetcher",
                fromlist=["TradingEconomicsFetcher"],
            ).TradingEconomicsFetcher.parse_event

            svc = EconomicCalendarService(mock_session)
            count = await svc.sync_upcoming_events(days=7)

        assert count == 1
        mock_fetcher_instance.fetch_upcoming_events.assert_called_once()
        mock_fetcher_instance.close.assert_called_once()
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_sync_no_events_returns_zero(self):
        """sync_upcoming_events should return 0 when no events are returned."""
        mock_session = AsyncMock()

        with patch(
            "backend.services.data_pipeline.economic_calendar_service.TradingEconomicsFetcher"
        ) as MockFetcher:
            mock_fetcher_instance = AsyncMock()
            mock_fetcher_instance.fetch_upcoming_events.return_value = []
            mock_fetcher_instance.close = AsyncMock()
            MockFetcher.return_value = mock_fetcher_instance

            svc = EconomicCalendarService(mock_session)
            count = await svc.sync_upcoming_events(days=7)

        assert count == 0

    @pytest.mark.asyncio
    async def test_prune_old_events(self):
        """prune_old_events should execute a DELETE and return the rowcount."""
        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        svc = EconomicCalendarService(mock_session)
        pruned = await svc.prune_old_events(retention_days=30)

        assert pruned == 5
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_upcoming_events_builds_correct_query(self):
        """get_upcoming_events should query the DB with correct filters."""
        mock_event = MagicMock(spec=EconomicCalendarEvent)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_event]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = EconomicCalendarService(mock_session)
        events = await svc.get_upcoming_events(days=7, importance=3, limit=10)

        assert len(events) == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_high_impact_events_delegates(self):
        """get_high_impact_events should call get_upcoming_events with importance=3."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        svc = EconomicCalendarService(mock_session)
        events = await svc.get_high_impact_events(days=7)

        assert events == []
        mock_session.execute.assert_called_once()

    def test_is_high_impact_true(self):
        """is_high_impact should return True for events in the registry."""
        event = MagicMock(spec=EconomicCalendarEvent)
        event.category = "Non Farm Payrolls"
        assert EconomicCalendarService.is_high_impact(event) is True

    def test_is_high_impact_false(self):
        """is_high_impact should return False for events NOT in the registry."""
        event = MagicMock(spec=EconomicCalendarEvent)
        event.category = "Some Obscure Metric"
        assert EconomicCalendarService.is_high_impact(event) is False


# ---- API Serialization Tests ----


class TestCalendarAPISerialization:
    """Tests for the _serialize_event helper."""

    def test_serialize_event_full(self):
        """Should serialize all fields from a model instance."""
        from backend.api.routes.calendar import _serialize_event

        event = MagicMock(spec=EconomicCalendarEvent)
        event.id = 1
        event.calendar_id = "384241"
        event.date = datetime(2026, 4, 1, 13, 30, tzinfo=UTC)
        event.country = "United States"
        event.category = "CPI"
        event.event = "CPI YoY"
        event.reference = "Mar"
        event.actual = "3.2%"
        event.previous = "3.1%"
        event.forecast = "3.3%"
        event.te_forecast = "3.2%"
        event.importance = 3
        event.source = "BLS"
        event.currency = "USD"
        event.unit = "%"

        result = _serialize_event(event)

        assert result["id"] == 1
        assert result["calendar_id"] == "384241"
        assert result["country"] == "United States"
        assert result["category"] == "CPI"
        assert result["importance"] == 3
        assert result["actual"] == "3.2%"
        assert "2026-04-01" in result["date"]

    def test_serialize_event_none_date(self):
        """Should handle None date gracefully."""
        from backend.api.routes.calendar import _serialize_event

        event = MagicMock(spec=EconomicCalendarEvent)
        event.id = 2
        event.calendar_id = "999"
        event.date = None
        event.country = "US"
        event.category = "Test"
        event.event = "Test"
        event.reference = None
        event.actual = None
        event.previous = None
        event.forecast = None
        event.te_forecast = None
        event.importance = 1
        event.source = None
        event.currency = None
        event.unit = None

        result = _serialize_event(event)
        assert result["date"] is None


# ---- Celery Task Tests ----


class TestEconomicCalendarTask:
    """Tests for the daily_economic_calendar_sync Celery task."""

    def test_task_is_registered(self):
        """The task should be importable and callable."""
        from backend.tasks.data_tasks import daily_economic_calendar_sync

        assert callable(daily_economic_calendar_sync)


# ---- Dashboard Widget Tests ----


class TestDashboardWidgetHelpers:
    """Tests for the Streamlit widget helper functions."""

    def test_importance_badge_high(self):
        from streamlit_app.components.economic_calendar import _importance_badge

        assert "High" in _importance_badge(3)

    def test_importance_badge_medium(self):
        from streamlit_app.components.economic_calendar import _importance_badge

        assert "Medium" in _importance_badge(2)

    def test_importance_badge_low(self):
        from streamlit_app.components.economic_calendar import _importance_badge

        assert "Low" in _importance_badge(1)

    def test_importance_badge_unknown(self):
        from streamlit_app.components.economic_calendar import _importance_badge

        assert "Unknown" in _importance_badge(99)

    def test_days_until_today(self):
        from streamlit_app.components.economic_calendar import _days_until

        # Use a time a few hours in the future to ensure it's still "today"
        now = datetime.now() + timedelta(hours=2)
        result = _days_until(now.isoformat())
        assert result in ("Today", "Tomorrow")  # Could be either near midnight

    def test_days_until_future(self):
        from streamlit_app.components.economic_calendar import _days_until

        future = (datetime.now() + timedelta(days=5, hours=12)).isoformat()
        result = _days_until(future)
        assert "days" in result  # Should be "In N days" for N >= 2

    def test_days_until_past(self):
        from streamlit_app.components.economic_calendar import _days_until

        past = (datetime.now() - timedelta(days=3)).isoformat()
        result = _days_until(past)
        assert result == "Past"

    def test_days_until_invalid(self):
        from streamlit_app.components.economic_calendar import _days_until

        assert _days_until("not-a-date") == ""
        assert _days_until(None) == ""
