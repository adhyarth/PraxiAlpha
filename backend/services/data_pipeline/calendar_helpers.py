"""
PraxiAlpha — Economic Calendar Helpers

Pure utility functions for formatting economic calendar data.
No heavy dependencies (no streamlit, fastapi, celery) — safe to use in tests
and lightweight CI environments.
"""

from datetime import datetime


def importance_badge(level: int) -> str:
    """Return a colored emoji badge for importance level."""
    return {3: "🔴 High", 2: "🟡 Medium", 1: "🟢 Low"}.get(level, "⚪ Unknown")


def days_until(date_str: str | None) -> str:
    """Human-readable countdown from now to event date."""
    if not date_str:
        return ""
    try:
        event_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(event_dt.tzinfo) if event_dt.tzinfo else datetime.now()
        delta = (event_dt - now).days
        if delta < 0:
            return "Past"
        if delta == 0:
            return "Today"
        if delta == 1:
            return "Tomorrow"
        return f"In {delta} days"
    except (ValueError, TypeError):
        return ""


def serialize_event(e) -> dict:  # type: ignore[no-untyped-def]
    """Convert an EconomicCalendarEvent model to a JSON-friendly dict."""
    return {
        "id": e.id,
        "calendar_id": e.calendar_id,
        "date": e.date.isoformat() if e.date else None,
        "country": e.country,
        "category": e.category,
        "event": e.event,
        "reference": e.reference,
        "actual": e.actual,
        "previous": e.previous,
        "forecast": e.forecast,
        "te_forecast": e.te_forecast,
        "importance": e.importance,
        "source": e.source,
        "currency": e.currency,
        "unit": e.unit,
    }
