"""
PraxiAlpha — Stock Search Widget

Typeahead search component for Streamlit.
Queries the FastAPI backend for ticker/name matches and renders
a selection dropdown. Returns the selected ticker.
"""

import os
from typing import Any

import streamlit as st


def _search_api(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Call the backend search endpoint and return results."""
    try:
        import httpx

        base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
        url = f"{base_url}/api/v1/stocks/search"
        params: dict[str, str | int] = {"q": query, "limit": limit}
        response = httpx.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data: dict[str, Any] = response.json()
            results: list[dict[str, Any]] = data.get("results", [])
            return results
    except Exception:
        pass
    return []


def _format_option(stock: dict[str, Any]) -> str:
    """Format a stock dict as a human-readable option string."""
    ticker = stock.get("ticker", "???")
    name = stock.get("name") or ""
    exchange = stock.get("exchange") or ""
    parts = [ticker]
    if name:
        parts.append(f"— {name}")
    if exchange:
        parts.append(f"({exchange})")
    return " ".join(parts)


def render_stock_search(
    label: str = "Search stocks",
    key: str = "stock_search",
    default_ticker: str = "",
    limit: int = 10,
) -> str | None:
    """
    Render a stock search widget in Streamlit.

    Displays a text input. When the user types >= 1 character, queries the
    backend search API and shows matching results in a selectbox.

    Args:
        label: Label for the text input.
        key: Streamlit widget key (must be unique per page).
        default_ticker: Pre-filled ticker value.
        limit: Maximum search results to show.

    Returns:
        The selected ticker string, or None if nothing is selected.
    """
    query = st.text_input(label, value=default_ticker, key=f"{key}_input")

    if not query or len(query.strip()) < 1:
        return default_ticker if default_ticker else None

    results = _search_api(query.strip(), limit=limit)

    if not results:
        st.caption("No matching stocks found.")
        return None

    # Build options list: "TICKER — Name (Exchange)"
    options = [_format_option(r) for r in results]

    selected_idx = st.selectbox(
        "Select a stock",
        range(len(options)),
        format_func=lambda i: options[i],
        key=f"{key}_select",
    )

    if selected_idx is not None:
        selected_ticker: str = results[selected_idx]["ticker"]
        return selected_ticker
    return None
