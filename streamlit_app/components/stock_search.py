"""
PraxiAlpha — Stock Search Widget

Typeahead search component for Streamlit.
Queries the FastAPI backend for ticker/name matches and renders
a selection dropdown. Returns the selected ticker.
"""

import os
from typing import Any

import streamlit as st

from backend.services.stock_search import format_stock_option


def _search_api(query: str, limit: int = 10) -> list[dict[str, Any]] | None:
    """
    Call the backend search endpoint and return results.

    Returns:
        List of stock dicts on success, or None if the backend is unavailable.
    """
    import httpx

    base_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
    url = f"{base_url}/api/v1/stocks/search"
    params: dict[str, str | int] = {"q": query, "limit": limit}

    try:
        response = httpx.get(url, params=params, timeout=5)
    except (httpx.ConnectError, httpx.TimeoutException):
        st.warning("⚠️ Backend unavailable — check that Docker is running.")
        return None
    except httpx.RequestError as exc:
        st.warning(f"⚠️ Network error: {exc}")
        return None

    if response.status_code == 200:
        data: dict[str, Any] = response.json()
        results: list[dict[str, Any]] = data.get("results", [])
        return results
    elif response.status_code == 422:
        st.caption("Invalid search query.")
        return []
    else:
        st.warning(f"⚠️ API error: {response.status_code}")
        return None


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
    Persists the last selected ticker in session_state so it survives
    across re-renders and avoids silent fallback to a default.

    Args:
        label: Label for the text input.
        key: Streamlit widget key (must be unique per page).
        default_ticker: Pre-filled ticker value.
        limit: Maximum search results to show.

    Returns:
        The selected ticker string, or None if nothing is selected.
    """
    # Persist last selected ticker across re-renders
    state_key = f"{key}_selected_ticker"
    if state_key not in st.session_state:
        st.session_state[state_key] = default_ticker or None

    query = st.text_input(label, value=default_ticker, key=f"{key}_input", max_chars=50)

    if not query or len(query.strip()) < 1:
        return st.session_state[state_key]

    results = _search_api(query.strip(), limit=limit)

    # None means backend error (warning already shown by _search_api)
    if results is None:
        return st.session_state[state_key]

    if len(results) == 0:
        st.caption("No matching stocks found.")
        return st.session_state[state_key]

    # Build options list: "TICKER — Name (Exchange)"
    options = [format_stock_option(r) for r in results]

    selected_idx = st.selectbox(
        "Select a stock",
        range(len(options)),
        format_func=lambda i: options[i],
        key=f"{key}_select",
    )

    if selected_idx is not None:
        selected_ticker: str = results[selected_idx]["ticker"]
        st.session_state[state_key] = selected_ticker
        return selected_ticker

    return st.session_state[state_key]
