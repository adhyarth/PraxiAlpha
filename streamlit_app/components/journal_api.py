"""
PraxiAlpha — Journal API Client

HTTP helper functions for the Streamlit journal UI to call the
FastAPI journal endpoints. All functions use httpx synchronously.
"""

import logging
import os
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

_BASE_URL: str | None = None


def _base_url() -> str:
    """Return the backend base URL (cached after first call)."""
    global _BASE_URL  # noqa: PLW0603
    if _BASE_URL is None:
        _BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
    return _BASE_URL


def _journal_url(path: str = "") -> str:
    """Build a journal API URL."""
    return f"{_base_url()}/api/v1/journal{path}"


# ---------------------------------------------------------------------------
# Trades — List / Create / Get / Update / Delete
# ---------------------------------------------------------------------------


def list_trades(
    *,
    ticker: str | None = None,
    status: str | None = None,
    direction: str | None = None,
    timeframe: str | None = None,
    tags: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any] | None:
    """Fetch trades list from the API. Returns response dict or None on error."""
    import httpx

    params: dict[str, str | int] = {"limit": limit, "offset": offset}
    if ticker:
        params["ticker"] = ticker
    if status:
        params["status"] = status
    if direction:
        params["direction"] = direction
    if timeframe:
        params["timeframe"] = timeframe
    if tags:
        params["tags"] = tags
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()

    try:
        resp = httpx.get(_journal_url("/"), params=params, timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for list_trades")
    except httpx.RequestError as exc:
        logger.warning("Network error in list_trades: %s", exc)
    return None


def get_trade(trade_id: str) -> dict[str, Any] | None:
    """Fetch a single trade by ID."""
    import httpx

    try:
        resp = httpx.get(_journal_url(f"/{trade_id}"), timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for get_trade")
    except httpx.RequestError as exc:
        logger.warning("Network error in get_trade: %s", exc)
    return None


def create_trade(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Create a new trade. Returns the created trade dict or None on error."""
    import httpx

    try:
        resp = httpx.post(_journal_url("/"), json=payload, timeout=10)
        if resp.status_code == 201:
            result: dict[str, Any] = resp.json()
            return result
        logger.warning("create_trade failed: %s %s", resp.status_code, resp.text)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for create_trade")
    except httpx.RequestError as exc:
        logger.warning("Network error in create_trade: %s", exc)
    return None


def update_trade(trade_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Update a trade. Returns the updated trade dict or None on error."""
    import httpx

    try:
        resp = httpx.put(_journal_url(f"/{trade_id}"), json=payload, timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
        logger.warning("update_trade failed: %s %s", resp.status_code, resp.text)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for update_trade")
    except httpx.RequestError as exc:
        logger.warning("Network error in update_trade: %s", exc)
    return None


def delete_trade(trade_id: str) -> bool:
    """Delete a trade. Returns True if successful."""
    import httpx

    try:
        resp = httpx.delete(_journal_url(f"/{trade_id}"), timeout=10)
        result: bool = resp.status_code == 204
        return result
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for delete_trade")
    except httpx.RequestError as exc:
        logger.warning("Network error in delete_trade: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Exits
# ---------------------------------------------------------------------------


def add_exit(trade_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Add an exit fill to a trade. Returns the updated trade."""
    import httpx

    try:
        resp = httpx.post(_journal_url(f"/{trade_id}/exits"), json=payload, timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
        logger.warning("add_exit failed: %s %s", resp.status_code, resp.text)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for add_exit")
    except httpx.RequestError as exc:
        logger.warning("Network error in add_exit: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Legs
# ---------------------------------------------------------------------------


def add_leg(trade_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Add an option leg to a trade. Returns the updated trade."""
    import httpx

    try:
        resp = httpx.post(_journal_url(f"/{trade_id}/legs"), json=payload, timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
        logger.warning("add_leg failed: %s %s", resp.status_code, resp.text)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for add_leg")
    except httpx.RequestError as exc:
        logger.warning("Network error in add_leg: %s", exc)
    return None


# ---------------------------------------------------------------------------
# What-If Snapshots
# ---------------------------------------------------------------------------


def list_snapshots(trade_id: str) -> dict[str, Any] | None:
    """List post-close snapshots for a trade."""
    import httpx

    try:
        resp = httpx.get(_journal_url(f"/{trade_id}/snapshots"), timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for list_snapshots")
    except httpx.RequestError as exc:
        logger.warning("Network error in list_snapshots: %s", exc)
    return None


def get_whatif_summary(trade_id: str) -> dict[str, Any] | None:
    """Get the what-if summary for a closed trade."""
    import httpx

    try:
        resp = httpx.get(_journal_url(f"/{trade_id}/what-if"), timeout=10)
        if resp.status_code == 200:
            result: dict[str, Any] = resp.json()
            return result
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for get_whatif_summary")
    except httpx.RequestError as exc:
        logger.warning("Network error in get_whatif_summary: %s", exc)
    return None


# ---------------------------------------------------------------------------
# PDF Report
# ---------------------------------------------------------------------------


def download_report(
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str | None = None,
    ticker: str | None = None,
    include_charts: bool = True,
) -> tuple[bytes | None, str]:
    """
    Download the PDF report.

    Returns (pdf_bytes, filename) — pdf_bytes is None on error.
    """
    import httpx

    params: dict[str, str | int | bool] = {"include_charts": include_charts}
    if start_date:
        params["start_date"] = start_date.isoformat()
    if end_date:
        params["end_date"] = end_date.isoformat()
    if status:
        params["status"] = status
    if ticker:
        params["ticker"] = ticker

    try:
        resp = httpx.get(_journal_url("/report"), params=params, timeout=60)
        if resp.status_code == 200:
            # Extract filename from Content-Disposition header
            cd = resp.headers.get("content-disposition", "")
            filename = "journal_report.pdf"
            if 'filename="' in cd:
                filename = cd.split('filename="')[1].rstrip('"')
            return resp.content, filename
        logger.warning("download_report failed: %s", resp.status_code)
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.warning("Backend unavailable for download_report")
    except httpx.RequestError as exc:
        logger.warning("Network error in download_report: %s", exc)
    return None, "journal_report.pdf"
