"""
PraxiAlpha — TradingEconomics Calendar Fetcher

Fetches upcoming economic calendar events from the TradingEconomics API.

Purpose: Situational awareness on the dashboard — show upcoming high-impact
events so you're never blindsided by a data release. NOT a trading signal
(see Mental Model #14: economic events are noise, price action is signal).

TradingEconomics API docs: https://docs.tradingeconomics.com/economic_calendar/snapshot/

Free tier uses guest:guest credentials with limited access.
Upgrade to Professional API plan for full access + WebSocket streaming.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---- Constants ----
TE_BASE_URL = "https://api.tradingeconomics.com"
REQUEST_TIMEOUT = 30.0
DEFAULT_COUNTRY = "united states"
DEFAULT_IMPORTANCE = 3  # High importance only
DEFAULT_LOOKAHEAD_DAYS = 7


class TradingEconomicsFetcher:
    """
    Fetches economic calendar data from TradingEconomics API.

    Usage:
        fetcher = TradingEconomicsFetcher()
        events = await fetcher.fetch_calendar(country="united states", importance=3)
        upcoming = await fetcher.fetch_upcoming_events(days=7)
    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the fetcher.

        Args:
            api_key: TradingEconomics API key. Falls back to settings,
                     then to guest:guest (free tier with limited data).
        """
        self.api_key = api_key or getattr(settings, "te_api_key", "") or "guest:guest"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def _request(
        self, endpoint: str, params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Make an authenticated request to TradingEconomics API.

        Returns a list of event dictionaries.
        """
        client = await self._get_client()
        url = f"{TE_BASE_URL}{endpoint}"

        request_params: dict[str, str] = {"c": self.api_key}
        if params:
            request_params.update(params)

        logger.debug(f"TradingEconomics request: {endpoint}")
        response = await client.get(url, params=request_params)
        response.raise_for_status()
        result: list[dict[str, Any]] = response.json()
        return result

    async def fetch_calendar(
        self,
        country: str = DEFAULT_COUNTRY,
        importance: int | None = DEFAULT_IMPORTANCE,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch economic calendar events.

        Args:
            country: Country name (e.g., "united states"). Use "All" for global.
            importance: 1=Low, 2=Medium, 3=High. None for all.
            start_date: Start date (YYYY-MM-DD). None for default range.
            end_date: End date (YYYY-MM-DD). None for default range.

        Returns:
            List of event dictionaries from TradingEconomics.
        """
        if start_date and end_date:
            endpoint = f"/calendar/country/{country}/{start_date}/{end_date}"
        else:
            endpoint = f"/calendar/country/{country}"

        params: dict[str, str] = {}
        if importance is not None:
            params["importance"] = str(importance)

        events: list[dict[str, Any]] = await self._request(endpoint, params)
        logger.info(
            f"Fetched {len(events)} calendar events for {country} (importance={importance})"
        )
        return events

    async def fetch_upcoming_events(
        self,
        days: int = DEFAULT_LOOKAHEAD_DAYS,
        country: str = DEFAULT_COUNTRY,
        importance: int | None = DEFAULT_IMPORTANCE,
    ) -> list[dict[str, Any]]:
        """
        Fetch upcoming events for the next N days.

        This is the primary method used by the dashboard widget.

        Args:
            days: Number of days to look ahead (default: 7).
            country: Country to filter by (default: "united states").
            importance: Minimum importance level (default: 3 = High only).

        Returns:
            List of upcoming event dictionaries, sorted by date.
        """
        today = datetime.now()
        end = today + timedelta(days=days)

        start_str = today.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        events = await self.fetch_calendar(
            country=country,
            importance=importance,
            start_date=start_str,
            end_date=end_str,
        )

        # Sort by date ascending
        events.sort(key=lambda e: e.get("Date", ""))

        return events

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """
        Best-effort parsing of TradingEconomics date/time values into
        timezone-aware datetimes (UTC). Returns None if parsing fails.
        """
        if value is None or value == "":
            return None

        if isinstance(value, datetime):
            # Ensure timezone-aware (assume UTC if naive)
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value

        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            # Normalize trailing 'Z' (UTC) so fromisoformat can handle it
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                logger.warning("Failed to parse TradingEconomics datetime value: %r", value)
                return None
            # Attach UTC if no timezone info was provided
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt

        logger.warning(
            "Unexpected type for TradingEconomics datetime value: %r (%s)", value, type(value)
        )
        return None

    @staticmethod
    def parse_event(raw: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a raw TradingEconomics event dict into our model-friendly format.

        Maps TradingEconomics field names → EconomicCalendarEvent columns.
        Timestamp fields (date, reference_date, te_last_update) are parsed
        into timezone-aware datetime objects for safe SQLAlchemy insertion.
        """
        return {
            "calendar_id": str(raw.get("CalendarId", "")),
            "date": TradingEconomicsFetcher._parse_datetime(raw.get("Date")),
            "country": raw.get("Country", ""),
            "category": raw.get("Category", ""),
            "event": raw.get("Event", ""),
            "reference": raw.get("Reference"),
            "reference_date": TradingEconomicsFetcher._parse_datetime(raw.get("ReferenceDate")),
            "actual": raw.get("Actual"),
            "previous": raw.get("Previous"),
            "forecast": raw.get("Forecast"),
            "te_forecast": raw.get("TEForecast"),
            "revised": raw.get("Revised"),
            "importance": raw.get("Importance", 1),
            "source": raw.get("Source"),
            "source_url": raw.get("SourceURL"),
            "url": raw.get("URL"),
            "currency": raw.get("Currency"),
            "unit": raw.get("Unit"),
            "ticker": raw.get("Ticker"),
            "te_last_update": TradingEconomicsFetcher._parse_datetime(raw.get("LastUpdate")),
        }
