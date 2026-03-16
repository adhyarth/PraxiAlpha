"""
PraxiAlpha — Economic Calendar Dashboard Component

Renders an upcoming economic events widget in the Streamlit dashboard.
Shows high-impact US events for the next 7 days so you're never
blindsided by a data release.

Note: This component calls the FastAPI backend. If the backend is
unavailable, it falls back to a direct TradingEconomics API call.
"""

import asyncio
from datetime import datetime

import streamlit as st

from backend.services.data_pipeline.calendar_helpers import (
    days_until as _days_until,
)
from backend.services.data_pipeline.calendar_helpers import (
    importance_badge as _importance_badge,
)


def _fetch_events_from_api(days: int = 7, importance: int | None = 3) -> list[dict] | None:
    """Try to fetch events from the FastAPI backend."""
    try:
        import httpx

        params: dict[str, str | int] = {"days": days, "limit": 20}
        if importance is not None:
            params["importance"] = importance

        response = httpx.get(
            "http://localhost:8000/api/v1/calendar/upcoming", params=params, timeout=5
        )
        if response.status_code == 200:
            result: list[dict] = response.json().get("events", [])
            return result
    except Exception:
        pass
    return None


def _fetch_events_direct(days: int = 7, importance: int | None = 3) -> list[dict]:
    """Fallback: fetch directly from TradingEconomics API (no DB required)."""
    from backend.services.data_pipeline.trading_economics_fetcher import (
        TradingEconomicsFetcher,
    )

    async def _fetch():
        fetcher = TradingEconomicsFetcher()
        try:
            raw = await fetcher.fetch_upcoming_events(days=days, importance=importance)
            return [TradingEconomicsFetcher.parse_event(e) for e in raw]
        finally:
            await fetcher.close()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Streamlit runs its own event loop — use a new one
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                events_result: list[dict] = pool.submit(lambda: asyncio.run(_fetch())).result(
                    timeout=15
                )
                return events_result
        else:
            sync_result: list[dict] = loop.run_until_complete(_fetch())
            return sync_result
    except Exception as exc:
        st.warning(f"Could not fetch economic calendar: {exc}")
        return []


def render_economic_calendar_widget(
    days: int = 7,
    importance: int | None = 3,
    title: str = "📅 Economic Calendar",
) -> None:
    """
    Render the economic calendar widget in a Streamlit dashboard.

    Args:
        days: Lookahead window.
        importance: Min importance filter (3 = high-impact only).
        title: Widget title.
    """
    st.subheader(title)

    # Try backend API first, fall back to direct TE fetch
    events = _fetch_events_from_api(days=days, importance=importance)
    source = "API"
    if events is None:
        events = _fetch_events_direct(days=days, importance=importance)
        source = "TradingEconomics (direct)"

    if not events:
        st.info("No upcoming events found for the selected filters.")
        return

    st.caption(f"Next {days} days · Source: {source} · {len(events)} event(s)")

    # Render each event as a compact card
    for event in events:
        importance_level = event.get("importance", 1)
        badge = _importance_badge(importance_level)
        event_name = event.get("event") or event.get("category", "Unknown")
        date_str = event.get("date", "")
        countdown = _days_until(date_str)

        # Format date for display
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            display_date = dt.strftime("%a %b %d, %I:%M %p")
        except (ValueError, TypeError):
            display_date = date_str

        with st.container():
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{event_name}**")
            with col2:
                st.markdown(f"📆 {display_date}")
            with col3:
                st.markdown(f"{badge}")

            # Show actual/forecast/previous if available
            details = []
            if event.get("forecast"):
                details.append(f"Forecast: **{event['forecast']}**")
            if event.get("previous"):
                details.append(f"Previous: {event['previous']}")
            if event.get("actual"):
                details.append(f"Actual: **{event['actual']}**")

            if details:
                st.caption(" · ".join(details))
            if countdown:
                st.caption(f"⏰ {countdown}")

        st.divider()
