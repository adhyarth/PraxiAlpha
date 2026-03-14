"""
PraxiAlpha — Economic Calendar Tests

Tests for the EconomicCalendarEvent model, TradingEconomicsFetcher,
and US_HIGH_IMPACT_EVENTS registry.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.economic_calendar import (
    US_HIGH_IMPACT_EVENTS,
    EconomicCalendarEvent,
)
from backend.services.data_pipeline.trading_economics_fetcher import (
    TradingEconomicsFetcher,
)

# ---- Model Tests ----


class TestEconomicCalendarModel:
    """Tests for the EconomicCalendarEvent SQLAlchemy model."""

    def test_model_tablename(self):
        """Model should map to 'economic_calendar' table."""
        assert EconomicCalendarEvent.__tablename__ == "economic_calendar"

    def test_model_has_required_columns(self):
        """Model should have all expected columns."""
        column_names = {c.name for c in EconomicCalendarEvent.__table__.columns}
        expected = {
            "id",
            "calendar_id",
            "date",
            "country",
            "category",
            "event",
            "reference",
            "reference_date",
            "actual",
            "previous",
            "forecast",
            "te_forecast",
            "revised",
            "importance",
            "source",
            "source_url",
            "url",
            "currency",
            "unit",
            "ticker",
            "te_last_update",
            "fetched_at",
        }
        assert expected.issubset(column_names), f"Missing columns: {expected - column_names}"

    def test_model_has_unique_constraint_on_calendar_id(self):
        """calendar_id should have a unique constraint."""
        constraints = EconomicCalendarEvent.__table__.constraints
        unique_names = {c.name for c in constraints if hasattr(c, "columns")}
        assert "uq_economic_calendar_id" in unique_names

    def test_model_repr(self):
        """__repr__ should include key fields."""
        event = EconomicCalendarEvent(
            date=datetime(2026, 3, 14, 13, 30, tzinfo=UTC),
            country="United States",
            event="Non Farm Payrolls",
            importance=3,
        )
        r = repr(event)
        assert "United States" in r
        assert "Non Farm Payrolls" in r
        assert "3" in r


# ---- Registry Tests ----


class TestUSHighImpactEvents:
    """Tests for the US_HIGH_IMPACT_EVENTS registry."""

    def test_registry_is_non_empty(self):
        """Should have at least 10 high-impact events defined."""
        assert len(US_HIGH_IMPACT_EVENTS) >= 10

    def test_registry_contains_key_events(self):
        """Must include the most market-moving US events."""
        must_have = [
            "Non Farm Payrolls",
            "CPI",
            "Fed Interest Rate Decision",
            "GDP Growth Rate",
            "Unemployment Rate",
        ]
        for event in must_have:
            assert event in US_HIGH_IMPACT_EVENTS, f"Missing key event: {event}"

    def test_registry_entries_are_strings(self):
        """All entries should be non-empty strings."""
        for event in US_HIGH_IMPACT_EVENTS:
            assert isinstance(event, str)
            assert len(event) > 0


# ---- Fetcher Tests ----


class TestTradingEconomicsFetcher:
    """Tests for the TradingEconomicsFetcher class."""

    def test_default_api_key_fallback(self):
        """Should fall back to guest:guest when no key is configured."""
        with patch(
            "backend.services.data_pipeline.trading_economics_fetcher.settings"
        ) as MockSettings:
            MockSettings.te_api_key = ""
            fetcher = TradingEconomicsFetcher(api_key=None)
            # With empty settings key and no explicit key, should use guest:guest
            assert fetcher.api_key == "guest:guest"

    def test_explicit_api_key(self):
        """Should use explicitly provided API key."""
        fetcher = TradingEconomicsFetcher(api_key="my-key:my-secret")
        assert fetcher.api_key == "my-key:my-secret"

    def test_parse_event_maps_fields_correctly(self):
        """parse_event should map TradingEconomics fields to our model format."""
        raw = {
            "CalendarId": "384241",
            "Date": "2026-03-14T12:30:00",
            "Country": "United States",
            "Category": "Retail Sales MoM",
            "Event": "Retail Sales MoM",
            "Reference": "Feb",
            "ReferenceDate": "2026-02-28T00:00:00",
            "Actual": "0.6%",
            "Previous": "0.5%",
            "Forecast": "0.2%",
            "TEForecast": "0.4%",
            "Revised": "0.5%",
            "Importance": 3,
            "Source": "U.S. Census Bureau",
            "SourceURL": "https://www.census.gov/",
            "URL": "/united-states/retail-sales",
            "Currency": "",
            "Unit": "%",
            "Ticker": "RSTAMOM",
            "LastUpdate": "2026-03-14T12:30:09.767",
        }

        parsed = TradingEconomicsFetcher.parse_event(raw)

        assert parsed["calendar_id"] == "384241"
        assert parsed["country"] == "United States"
        assert parsed["category"] == "Retail Sales MoM"
        assert parsed["event"] == "Retail Sales MoM"
        assert parsed["actual"] == "0.6%"
        assert parsed["previous"] == "0.5%"
        assert parsed["forecast"] == "0.2%"
        assert parsed["te_forecast"] == "0.4%"
        assert parsed["importance"] == 3
        assert parsed["source"] == "U.S. Census Bureau"
        assert parsed["unit"] == "%"
        assert parsed["ticker"] == "RSTAMOM"

    def test_parse_event_handles_missing_fields(self):
        """parse_event should handle missing/None fields gracefully."""
        raw = {
            "CalendarId": "999",
            "Country": "United States",
            "Category": "Test",
            "Event": "Test Event",
            "Importance": 1,
        }

        parsed = TradingEconomicsFetcher.parse_event(raw)

        assert parsed["calendar_id"] == "999"
        assert parsed["actual"] is None
        assert parsed["forecast"] is None
        assert parsed["previous"] is None
        assert parsed["source"] is None

    @pytest.mark.asyncio
    async def test_fetch_calendar_calls_api(self):
        """fetch_calendar should make correct API call."""
        fetcher = TradingEconomicsFetcher(api_key="test:key")

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"CalendarId": "1", "Country": "United States", "Event": "CPI", "Importance": 3}
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.is_closed = False
        fetcher._client = mock_client

        events = await fetcher.fetch_calendar(country="united states", importance=3)

        assert len(events) == 1
        assert events[0]["Event"] == "CPI"
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_closes_client(self):
        """close() should close the HTTP client."""
        fetcher = TradingEconomicsFetcher(api_key="test:key")

        mock_client = AsyncMock()
        mock_client.is_closed = False
        fetcher._client = mock_client

        await fetcher.close()
        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_noop_when_no_client(self):
        """close() should be safe to call when no client exists."""
        fetcher = TradingEconomicsFetcher(api_key="test:key")
        await fetcher.close()  # Should not raise
