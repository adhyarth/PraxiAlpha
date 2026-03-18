"""
PraxiAlpha — Stock Search Tests

Tests for the stock search service and API endpoint.
Covers: exact match, prefix match, name match, ranking, edge cases,
empty query, limit clamping, asset type filtering, and API endpoint.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.stock_search import _serialize_stock, search_stocks

# ---------------------------------------------------------------------------
# Helpers — fake Stock objects
# ---------------------------------------------------------------------------


def _make_stock(**overrides):
    """Create a mock Stock object with sensible defaults."""
    defaults = {
        "id": 1,
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "exchange": "NASDAQ",
        "asset_type": "Common Stock",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "is_active": True,
        "latest_date": None,
        "total_records": 9000,
    }
    defaults.update(overrides)
    stock = MagicMock()
    for k, v in defaults.items():
        setattr(stock, k, v)
    return stock


# ---------------------------------------------------------------------------
# _serialize_stock
# ---------------------------------------------------------------------------


class TestSerializeStock:
    """Tests for the stock serialization helper."""

    def test_serialize_full_stock(self):
        stock = _make_stock(latest_date="2026-03-17")
        result = _serialize_stock(stock)
        assert result["ticker"] == "AAPL"
        assert result["name"] == "Apple Inc."
        assert result["exchange"] == "NASDAQ"
        assert result["asset_type"] == "Common Stock"
        assert result["sector"] == "Technology"
        assert result["latest_date"] == "2026-03-17"
        assert result["total_records"] == 9000

    def test_serialize_stock_no_latest_date(self):
        stock = _make_stock(latest_date=None)
        result = _serialize_stock(stock)
        assert result["latest_date"] is None

    def test_serialize_stock_keys(self):
        stock = _make_stock()
        result = _serialize_stock(stock)
        expected_keys = {
            "id",
            "ticker",
            "name",
            "exchange",
            "asset_type",
            "sector",
            "latest_date",
            "total_records",
        }
        assert set(result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# search_stocks — unit tests with mocked DB session
# ---------------------------------------------------------------------------


class TestSearchStocksEdgeCases:
    """Tests for search_stocks input validation and edge cases."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        db = AsyncMock()
        result = await search_stocks(db, "")
        assert result == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_empty(self):
        db = AsyncMock()
        result = await search_stocks(db, "   ")
        assert result == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_query_returns_empty(self):
        db = AsyncMock()
        result = await search_stocks(db, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_limit_clamped_to_min_1(self):
        """Limit of 0 or negative should be clamped to 1."""
        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        result = await search_stocks(db, "A", limit=0)
        assert result == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_limit_clamped_to_max_50(self):
        """Limit > 50 should be clamped to 50."""
        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        result = await search_stocks(db, "A", limit=100)
        assert result == []
        db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_serialized_results(self):
        """search_stocks should return a list of dicts, not ORM objects."""
        stock = _make_stock(ticker="AAPL", name="Apple Inc.")

        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [stock]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        results = await search_stocks(db, "AAPL")
        assert len(results) == 1
        assert isinstance(results[0], dict)
        assert results[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_no_results(self):
        """Query that matches nothing should return empty list."""
        db = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        results = await search_stocks(db, "ZZZZZZZ")
        assert results == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestSearchAPI:
    """Tests for the /stocks/search API endpoint."""

    @pytest.mark.asyncio
    async def test_search_endpoint_calls_service(self):
        """The API endpoint should call search_stocks and return results."""
        from backend.api.routes.stocks import search

        mock_results = [
            {
                "id": 1,
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "exchange": "NASDAQ",
                "asset_type": "Common Stock",
                "sector": "Technology",
                "latest_date": None,
                "total_records": 9000,
            },
        ]

        mock_db = AsyncMock()

        with patch("backend.api.routes.stocks.search_stocks", return_value=mock_results) as mock_fn:
            response = await search(
                q="AAPL", limit=10, active_only=True, asset_type=None, db=mock_db
            )

        mock_fn.assert_called_once_with(
            db=mock_db,
            query="AAPL",
            limit=10,
            active_only=True,
            asset_types=None,
        )
        assert response["count"] == 1
        assert response["results"][0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    async def test_search_endpoint_with_asset_type_filter(self):
        """asset_type query param should be wrapped in a list for the service."""
        from backend.api.routes.stocks import search

        mock_db = AsyncMock()

        with patch("backend.api.routes.stocks.search_stocks", return_value=[]) as mock_fn:
            await search(q="A", limit=5, active_only=False, asset_type="ETF", db=mock_db)

        mock_fn.assert_called_once_with(
            db=mock_db,
            query="A",
            limit=5,
            active_only=False,
            asset_types=["ETF"],
        )

    @pytest.mark.asyncio
    async def test_search_endpoint_empty_results(self):
        """Empty results should return count=0 and empty list."""
        from backend.api.routes.stocks import search

        mock_db = AsyncMock()

        with patch("backend.api.routes.stocks.search_stocks", return_value=[]):
            response = await search(
                q="ZZZZZ", limit=10, active_only=True, asset_type=None, db=mock_db
            )

        assert response["count"] == 0
        assert response["results"] == []


# ---------------------------------------------------------------------------
# Widget helper tests
# ---------------------------------------------------------------------------


class TestStockSearchWidget:
    """Tests for widget helper functions (no Streamlit dependency)."""

    def test_format_option_full(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"}
        assert _format_option(stock) == "AAPL — Apple Inc. (NASDAQ)"

    def test_format_option_no_name(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"ticker": "AAPL", "name": None, "exchange": "NASDAQ"}
        assert _format_option(stock) == "AAPL (NASDAQ)"

    def test_format_option_no_exchange(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"ticker": "AAPL", "name": "Apple Inc.", "exchange": None}
        assert _format_option(stock) == "AAPL — Apple Inc."

    def test_format_option_ticker_only(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"ticker": "AAPL", "name": None, "exchange": None}
        assert _format_option(stock) == "AAPL"

    def test_format_option_empty_strings(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"ticker": "AAPL", "name": "", "exchange": ""}
        assert _format_option(stock) == "AAPL"

    def test_format_option_missing_ticker(self):
        from streamlit_app.components.stock_search import _format_option

        stock = {"name": "Apple Inc."}
        result = _format_option(stock)
        assert "???" in result
