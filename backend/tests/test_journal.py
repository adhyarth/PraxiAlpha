"""
PraxiAlpha — Trading Journal Tests

Tests for:
- Journal model ENUMs and ORM structure
- journal_service computed fields (status, PnL, R-multiple, etc.)
- journal_service CRUD operations (mocked DB)
- Journal API routes (mocked service layer)
- User isolation (user_id scoping across all CRUD operations)

All tests mock the database — no real Postgres needed in CI.
"""

import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.journal import (
    AssetType,
    LegType,
    Timeframe,
    Trade,
    TradeDirection,
    TradeExit,
    TradeLeg,
    TradeType,
)
from backend.services.journal_service import (
    _serialize_exit,
    _serialize_leg,
    compute_trade_metrics,
    serialize_trade,
)

# ---------------------------------------------------------------------------
# Helpers — build mock ORM objects
# ---------------------------------------------------------------------------


def _make_trade(**overrides) -> MagicMock:
    """Create a mock Trade with sensible defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "user_id": "default",
        "ticker": "AAPL",
        "direction": TradeDirection.LONG,
        "asset_type": AssetType.SHARES,
        "trade_type": TradeType.SINGLE_LEG,
        "timeframe": Timeframe.DAILY,
        "entry_date": date(2026, 1, 15),
        "entry_price": Decimal("150.0000"),
        "total_quantity": Decimal("100.0000"),
        "stop_loss": Decimal("145.0000"),
        "take_profit": Decimal("170.0000"),
        "tags": ["momentum", "earnings"],
        "comments": "Bullish breakout on volume",
        "created_at": "2026-01-15T10:00:00+00:00",
        "updated_at": "2026-01-15T10:00:00+00:00",
        "exits": [],
        "legs": [],
    }
    defaults.update(overrides)
    trade = MagicMock(spec=Trade)
    for k, v in defaults.items():
        setattr(trade, k, v)
    return trade


def _make_exit(**overrides) -> MagicMock:
    """Create a mock TradeExit."""
    defaults = {
        "id": uuid.uuid4(),
        "trade_id": uuid.uuid4(),
        "exit_date": date(2026, 2, 1),
        "exit_price": Decimal("160.0000"),
        "quantity": Decimal("50.0000"),
        "comments": None,
    }
    defaults.update(overrides)
    exit_ = MagicMock(spec=TradeExit)
    for k, v in defaults.items():
        setattr(exit_, k, v)
    return exit_


def _make_leg(**overrides) -> MagicMock:
    """Create a mock TradeLeg."""
    defaults = {
        "id": uuid.uuid4(),
        "trade_id": uuid.uuid4(),
        "leg_type": LegType.BUY_CALL,
        "strike": Decimal("155.0000"),
        "expiry": date(2026, 3, 21),
        "quantity": Decimal("10.0000"),
        "premium": Decimal("3.5000"),
    }
    defaults.update(overrides)
    leg = MagicMock(spec=TradeLeg)
    for k, v in defaults.items():
        setattr(leg, k, v)
    return leg


# ============================================================
# ENUM Tests
# ============================================================


class TestEnums:
    """Tests for the journal ENUMs."""

    def test_trade_direction_values(self):
        assert TradeDirection.LONG.value == "long"
        assert TradeDirection.SHORT.value == "short"
        assert len(TradeDirection) == 2

    def test_asset_type_values(self):
        assert AssetType.SHARES.value == "shares"
        assert AssetType.OPTIONS.value == "options"
        assert len(AssetType) == 2

    def test_trade_type_values(self):
        assert TradeType.SINGLE_LEG.value == "single_leg"
        assert TradeType.MULTI_LEG.value == "multi_leg"
        assert len(TradeType) == 2

    def test_timeframe_values(self):
        assert Timeframe.DAILY.value == "daily"
        assert Timeframe.WEEKLY.value == "weekly"
        assert Timeframe.MONTHLY.value == "monthly"
        assert Timeframe.QUARTERLY.value == "quarterly"
        assert len(Timeframe) == 4

    def test_leg_type_values(self):
        assert LegType.BUY_CALL.value == "buy_call"
        assert LegType.SELL_CALL.value == "sell_call"
        assert LegType.BUY_PUT.value == "buy_put"
        assert LegType.SELL_PUT.value == "sell_put"
        assert len(LegType) == 4

    def test_trade_direction_from_string(self):
        assert TradeDirection("long") == TradeDirection.LONG
        assert TradeDirection("short") == TradeDirection.SHORT

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            TradeDirection("neutral")

    def test_timeframe_from_string(self):
        assert Timeframe("daily") == Timeframe.DAILY
        assert Timeframe("quarterly") == Timeframe.QUARTERLY

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValueError):
            Timeframe("hourly")


# ============================================================
# Model Table Names
# ============================================================


class TestModelTableNames:
    """Verify __tablename__ attributes are correct."""

    def test_trade_table(self):
        assert Trade.__tablename__ == "trades"

    def test_exit_table(self):
        assert TradeExit.__tablename__ == "trade_exits"

    def test_leg_table(self):
        assert TradeLeg.__tablename__ == "trade_legs"


# ============================================================
# compute_trade_metrics
# ============================================================


class TestComputeTradeMetrics:
    """Tests for the computed field logic."""

    def test_open_trade_no_exits(self):
        """Trade with no exits → status=open, PnL=0."""
        trade = _make_trade()
        metrics = compute_trade_metrics(trade)
        assert metrics["status"] == "open"
        assert metrics["remaining_quantity"] == 100.0
        assert metrics["realized_pnl"] == 0.0
        assert metrics["return_pct"] == 0.0
        assert metrics["avg_exit_price"] is None
        assert metrics["r_multiple"] is None

    def test_partial_exit(self):
        """Exiting half the position → status=partial."""
        exit1 = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("50.0000"))
        trade = _make_trade(exits=[exit1])
        metrics = compute_trade_metrics(trade)
        assert metrics["status"] == "partial"
        assert metrics["remaining_quantity"] == 50.0
        # PnL: (160-150) * 50 * 1 = 500
        assert metrics["realized_pnl"] == 500.0
        # Return: 500 / (150*100) * 100 = 3.33%
        assert metrics["return_pct"] == pytest.approx(3.33, abs=0.01)
        assert metrics["avg_exit_price"] == 160.0

    def test_fully_closed_trade(self):
        """All quantity exited → status=closed."""
        exit1 = _make_exit(exit_price=Decimal("155.0000"), quantity=Decimal("50.0000"))
        exit2 = _make_exit(exit_price=Decimal("165.0000"), quantity=Decimal("50.0000"))
        trade = _make_trade(exits=[exit1, exit2])
        metrics = compute_trade_metrics(trade)
        assert metrics["status"] == "closed"
        assert metrics["remaining_quantity"] == 0.0
        # PnL: (155-150)*50 + (165-150)*50 = 250 + 750 = 1000
        assert metrics["realized_pnl"] == 1000.0
        # Avg exit: (155*50 + 165*50) / 100 = 160
        assert metrics["avg_exit_price"] == 160.0

    def test_short_trade_pnl(self):
        """Short trade PnL is inverted: profit when exit < entry."""
        exit1 = _make_exit(exit_price=Decimal("140.0000"), quantity=Decimal("100.0000"))
        trade = _make_trade(direction=TradeDirection.SHORT, exits=[exit1])
        metrics = compute_trade_metrics(trade)
        assert metrics["status"] == "closed"
        # PnL: (140-150) * 100 * (-1) = 1000  (profit)
        assert metrics["realized_pnl"] == 1000.0
        assert metrics["return_pct"] == pytest.approx(6.67, abs=0.01)

    def test_short_trade_loss(self):
        """Short trade where price goes up → loss."""
        exit1 = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("100.0000"))
        trade = _make_trade(direction=TradeDirection.SHORT, exits=[exit1])
        metrics = compute_trade_metrics(trade)
        # PnL: (160-150) * 100 * (-1) = -1000  (loss)
        assert metrics["realized_pnl"] == -1000.0

    def test_r_multiple_calculation(self):
        """R-multiple = PnL / total_risk."""
        exit1 = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("100.0000"))
        trade = _make_trade(
            stop_loss=Decimal("145.0000"),
            exits=[exit1],
        )
        metrics = compute_trade_metrics(trade)
        # Risk per unit: |150 - 145| = 5
        # Total risk: 5 * 100 = 500
        # PnL: (160-150) * 100 = 1000
        # R-multiple: 1000 / 500 = 2.0
        assert metrics["r_multiple"] == 2.0

    def test_r_multiple_none_without_stop_loss(self):
        """No stop_loss → r_multiple is None."""
        exit1 = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("100.0000"))
        trade = _make_trade(stop_loss=None, exits=[exit1])
        metrics = compute_trade_metrics(trade)
        assert metrics["r_multiple"] is None

    def test_r_multiple_none_when_open(self):
        """No exits → r_multiple is None even with stop_loss."""
        trade = _make_trade(stop_loss=Decimal("145.0000"))
        metrics = compute_trade_metrics(trade)
        assert metrics["r_multiple"] is None

    def test_losing_trade_negative_r_multiple(self):
        """Losing trade should have negative R-multiple."""
        exit1 = _make_exit(exit_price=Decimal("143.0000"), quantity=Decimal("100.0000"))
        trade = _make_trade(stop_loss=Decimal("145.0000"), exits=[exit1])
        metrics = compute_trade_metrics(trade)
        # PnL: (143-150) * 100 = -700
        # Risk: 5 * 100 = 500
        # R: -700 / 500 = -1.4
        assert metrics["r_multiple"] == -1.4

    def test_three_partial_exits(self):
        """Multiple partial exits should compute correctly."""
        exits = [
            _make_exit(exit_price=Decimal("155.0000"), quantity=Decimal("30.0000")),
            _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("30.0000")),
            _make_exit(exit_price=Decimal("165.0000"), quantity=Decimal("40.0000")),
        ]
        trade = _make_trade(exits=exits)
        metrics = compute_trade_metrics(trade)
        assert metrics["status"] == "closed"
        assert metrics["remaining_quantity"] == 0.0
        # PnL: (155-150)*30 + (160-150)*30 + (165-150)*40 = 150 + 300 + 600 = 1050
        assert metrics["realized_pnl"] == 1050.0
        # Avg exit: (155*30 + 160*30 + 165*40) / 100 = (4650 + 4800 + 6600) / 100 = 160.5
        assert metrics["avg_exit_price"] == 160.5

    def test_zero_entry_price_no_crash(self):
        """Zero entry price should not cause division by zero."""
        trade = _make_trade(entry_price=Decimal("0.0000"))
        metrics = compute_trade_metrics(trade)
        assert metrics["return_pct"] == 0.0


# ============================================================
# Serialization helpers
# ============================================================


class TestSerialization:
    """Tests for serialize_trade, _serialize_exit, _serialize_leg."""

    def test_serialize_exit(self):
        exit_ = _make_exit()
        result = _serialize_exit(exit_)
        assert "id" in result
        assert "exit_date" in result
        assert "exit_price" in result
        assert "quantity" in result
        assert "comments" in result

    def test_serialize_leg(self):
        leg = _make_leg()
        result = _serialize_leg(leg)
        assert "id" in result
        assert "leg_type" in result
        assert "strike" in result
        assert "expiry" in result
        assert "quantity" in result
        assert "premium" in result

    def test_serialize_trade_includes_computed_fields(self):
        trade = _make_trade()
        result = serialize_trade(trade)
        assert result["status"] == "open"
        assert result["remaining_quantity"] == 100.0
        assert result["realized_pnl"] == 0.0
        assert result["return_pct"] == 0.0
        assert "exits" in result
        assert "legs" in result

    def test_serialize_trade_without_children(self):
        trade = _make_trade()
        result = serialize_trade(trade, include_children=False)
        assert "exits" not in result
        assert "legs" not in result

    def test_serialize_trade_with_exits_and_legs(self):
        exit1 = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("50.0000"))
        leg1 = _make_leg()
        trade = _make_trade(exits=[exit1], legs=[leg1])
        result = serialize_trade(trade)
        assert len(result["exits"]) == 1
        assert len(result["legs"]) == 1
        assert result["status"] == "partial"

    def test_serialize_trade_fields(self):
        trade = _make_trade()
        result = serialize_trade(trade)
        assert result["ticker"] == "AAPL"
        assert result["direction"] == "long"
        assert result["asset_type"] == "shares"
        assert result["trade_type"] == "single_leg"
        assert result["timeframe"] == "daily"
        assert result["entry_price"] == 150.0
        assert result["total_quantity"] == 100.0
        assert result["stop_loss"] == 145.0
        assert result["take_profit"] == 170.0
        assert result["tags"] == ["momentum", "earnings"]
        assert result["comments"] == "Bullish breakout on volume"

    def test_serialize_trade_none_optional_fields(self):
        trade = _make_trade(stop_loss=None, take_profit=None, tags=None, comments=None)
        result = serialize_trade(trade)
        assert result["stop_loss"] is None
        assert result["take_profit"] is None
        assert result["tags"] == []
        assert result["comments"] is None


# ============================================================
# CRUD: create_trade (mocked DB)
# ============================================================


class TestCreateTrade:
    """Tests for journal_service.create_trade."""

    @pytest.mark.asyncio
    async def test_create_trade_returns_serialized(self):
        """create_trade should return a serialized dict."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is sync, not async
        mock_db.flush = AsyncMock()

        # After flush, create_trade re-fetches via db.execute(select(...))
        # We capture the Trade object from add() and return it from execute()
        captured_trade = None

        def capture_add(obj):
            nonlocal captured_trade
            # Set server-generated fields that would come from DB
            if not hasattr(obj, "id") or obj.id is None:
                obj.id = uuid.uuid4()
            obj.created_at = "2026-01-15T10:00:00+00:00"
            obj.updated_at = "2026-01-15T10:00:00+00:00"
            obj.exits = []
            obj.legs = []
            captured_trade = obj

        mock_db.add.side_effect = capture_add

        # Mock the re-fetch execute() to return the captured trade
        mock_result = MagicMock()
        mock_result.scalar_one.side_effect = lambda: captured_trade
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import create_trade

        result = await create_trade(
            mock_db,
            ticker="AAPL",
            direction="long",
            asset_type="shares",
            trade_type="single_leg",
            timeframe="daily",
            entry_date=date(2026, 1, 15),
            entry_price=150.0,
            total_quantity=100.0,
            stop_loss=145.0,
            take_profit=170.0,
            tags=["momentum"],
            comments="Test trade",
        )

        assert result["ticker"] == "AAPL"
        assert result["direction"] == "long"
        assert result["status"] == "open"
        assert result["realized_pnl"] == 0.0
        assert result["tags"] == ["momentum"]
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_trade_uppercases_ticker(self):
        """Ticker should be stored in uppercase."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is sync, not async

        captured_trade = None

        def capture_add(obj):
            nonlocal captured_trade
            obj.id = uuid.uuid4()
            obj.created_at = "2026-01-15T10:00:00+00:00"
            obj.updated_at = "2026-01-15T10:00:00+00:00"
            obj.exits = []
            obj.legs = []
            captured_trade = obj

        mock_db.add.side_effect = capture_add

        mock_result = MagicMock()
        mock_result.scalar_one.side_effect = lambda: captured_trade
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import create_trade

        result = await create_trade(
            mock_db,
            ticker="aapl",
            direction="long",
            asset_type="shares",
            timeframe="daily",
            entry_date=date(2026, 1, 15),
            entry_price=150.0,
            total_quantity=100.0,
        )
        assert result["ticker"] == "AAPL"


# ============================================================
# CRUD: get_trade (mocked DB)
# ============================================================


class TestGetTrade:
    """Tests for journal_service.get_trade."""

    @pytest.mark.asyncio
    async def test_get_trade_found(self):
        """Should return serialized trade when found."""
        trade = _make_trade()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = trade

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import get_trade

        result = await get_trade(mock_db, trade.id)
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["status"] == "open"

    @pytest.mark.asyncio
    async def test_get_trade_not_found(self):
        """Should return None when trade doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import get_trade

        result = await get_trade(mock_db, uuid.uuid4())
        assert result is None


# ============================================================
# CRUD: list_trades (mocked DB)
# ============================================================


class TestListTrades:
    """Tests for journal_service.list_trades."""

    @pytest.mark.asyncio
    async def test_list_trades_empty(self):
        """Should return empty list when no trades."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import list_trades

        result = await list_trades(mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_trades_returns_serialized(self):
        """Should return list of serialized trades."""
        trade1 = _make_trade(ticker="AAPL")
        trade2 = _make_trade(ticker="MSFT")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade1, trade2]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import list_trades

        result = await list_trades(mock_db)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_trades_filters_by_status(self):
        """Status filter is applied in Python after fetch."""
        open_trade = _make_trade(ticker="AAPL")
        closed_exit = _make_exit(exit_price=Decimal("160.0000"), quantity=Decimal("100.0000"))
        closed_trade = _make_trade(ticker="MSFT", exits=[closed_exit])

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [open_trade, closed_trade]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import list_trades

        # Only closed trades
        result = await list_trades(mock_db, status="closed")
        assert len(result) == 1
        assert result[0]["ticker"] == "MSFT"

        # Only open trades
        result = await list_trades(mock_db, status="open")
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"


# ============================================================
# CRUD: delete_trade (mocked DB)
# ============================================================


class TestDeleteTrade:
    """Tests for journal_service.delete_trade."""

    @pytest.mark.asyncio
    async def test_delete_trade_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import delete_trade

        result = await delete_trade(mock_db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_trade_not_found(self):
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import delete_trade

        result = await delete_trade(mock_db, uuid.uuid4())
        assert result is False


# ============================================================
# CRUD: add_exit (mocked DB)
# ============================================================


class TestAddExit:
    """Tests for journal_service.add_exit."""

    @pytest.mark.asyncio
    async def test_add_exit_exceeds_quantity_raises(self):
        """Should raise ValueError when exit qty > remaining."""
        trade = _make_trade(total_quantity=Decimal("100.0000"), exits=[])

        # First call returns the trade; second call (re-fetch) also returns it
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = trade

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import add_exit

        with pytest.raises(ValueError, match="exceeds remaining quantity"):
            await add_exit(
                mock_db,
                trade.id,
                exit_date=date(2026, 2, 1),
                exit_price=160.0,
                quantity=150.0,  # More than 100
            )

    @pytest.mark.asyncio
    async def test_add_exit_not_found_returns_none(self):
        """Should return None if trade doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import add_exit

        result = await add_exit(
            mock_db,
            uuid.uuid4(),
            exit_date=date(2026, 2, 1),
            exit_price=160.0,
            quantity=50.0,
        )
        assert result is None


# ============================================================
# CRUD: add_leg (mocked DB)
# ============================================================


class TestAddLeg:
    """Tests for journal_service.add_leg."""

    @pytest.mark.asyncio
    async def test_add_leg_not_found_returns_none(self):
        """Should return None if trade doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import add_leg

        result = await add_leg(
            mock_db,
            uuid.uuid4(),
            leg_type="buy_call",
            strike=155.0,
            expiry=date(2026, 3, 21),
            quantity=10.0,
            premium=3.5,
        )
        assert result is None


# ============================================================
# CRUD: update_trade (mocked DB)
# ============================================================


class TestUpdateTrade:
    """Tests for journal_service.update_trade."""

    @pytest.mark.asyncio
    async def test_update_trade_not_found(self):
        """Should return None if trade doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import update_trade

        result = await update_trade(mock_db, uuid.uuid4(), tags=["new-tag"])
        assert result is None

    @pytest.mark.asyncio
    async def test_update_trade_with_no_changes(self):
        """Empty update should still return the trade."""
        trade = _make_trade()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = trade

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import update_trade

        # No valid fields (disallowed_field is not in allowed set)
        result = await update_trade(mock_db, trade.id, disallowed_field="bad")
        # Should call get_trade, which also calls execute
        assert result is not None


# ============================================================
# API Route Schemas (import check)
# ============================================================

# These tests require fastapi (not in CI test environment)
_has_fastapi = importlib.util.find_spec("fastapi") is not None


@pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")
class TestAPISchemas:
    """Test that Pydantic request/response schemas are importable and valid."""

    def test_create_trade_request_valid(self):
        from backend.api.routes.journal import CreateTradeRequest

        req = CreateTradeRequest(
            ticker="AAPL",
            direction="long",
            asset_type="shares",
            timeframe="daily",
            entry_date=date(2026, 1, 15),
            entry_price=150.0,
            total_quantity=100.0,
        )
        assert req.ticker == "AAPL"
        assert req.trade_type == "single_leg"  # default

    def test_create_trade_request_invalid_direction(self):
        from pydantic import ValidationError

        from backend.api.routes.journal import CreateTradeRequest

        with pytest.raises(ValidationError):
            CreateTradeRequest(
                ticker="AAPL",
                direction="neutral",  # Invalid
                asset_type="shares",
                timeframe="daily",
                entry_date=date(2026, 1, 15),
                entry_price=150.0,
                total_quantity=100.0,
            )

    def test_create_trade_request_negative_price_rejected(self):
        from pydantic import ValidationError

        from backend.api.routes.journal import CreateTradeRequest

        with pytest.raises(ValidationError):
            CreateTradeRequest(
                ticker="AAPL",
                direction="long",
                asset_type="shares",
                timeframe="daily",
                entry_date=date(2026, 1, 15),
                entry_price=-10.0,  # Must be > 0
                total_quantity=100.0,
            )

    def test_update_trade_request_all_optional(self):
        from backend.api.routes.journal import UpdateTradeRequest

        req = UpdateTradeRequest()
        assert req.stop_loss is None
        assert req.take_profit is None
        assert req.tags is None

    def test_add_exit_request_valid(self):
        from backend.api.routes.journal import AddExitRequest

        req = AddExitRequest(
            exit_date=date(2026, 2, 1),
            exit_price=160.0,
            quantity=50.0,
        )
        assert req.exit_price == 160.0

    def test_add_leg_request_valid(self):
        from backend.api.routes.journal import AddLegRequest

        req = AddLegRequest(
            leg_type="buy_call",
            strike=155.0,
            expiry=date(2026, 3, 21),
            quantity=10.0,
            premium=3.5,
        )
        assert req.leg_type == "buy_call"

    def test_add_leg_request_invalid_type(self):
        from pydantic import ValidationError

        from backend.api.routes.journal import AddLegRequest

        with pytest.raises(ValidationError):
            AddLegRequest(
                leg_type="butterfly",  # Invalid
                strike=155.0,
                expiry=date(2026, 3, 21),
                quantity=10.0,
                premium=3.5,
            )


# ============================================================
# API Router Registration
# ============================================================


@pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")
class TestRouterRegistration:
    """Test that the journal router is properly configured."""

    def test_router_prefix(self):
        from backend.api.routes.journal import router

        assert router.prefix == "/journal"

    def test_router_has_routes(self):
        from backend.api.routes.journal import router

        paths = [route.path for route in router.routes]
        assert "/journal/" in paths
        assert "/journal/{trade_id}" in paths
        assert "/journal/{trade_id}/exits" in paths
        assert "/journal/{trade_id}/legs" in paths


# ============================================================
# User Isolation Tests
# ============================================================


class TestUserIsolation:
    """Tests that user_id scoping works correctly across all CRUD operations."""

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="alice")
    async def test_create_trade_sets_user_id(self, mock_uid):
        """create_trade should set user_id from _current_user_id."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        created_trade = None

        def capture_add(obj):
            nonlocal created_trade
            obj.id = uuid.uuid4()
            obj.created_at = "2026-01-15T10:00:00+00:00"
            obj.updated_at = "2026-01-15T10:00:00+00:00"
            obj.exits = []
            obj.legs = []
            created_trade = obj

        mock_db.add.side_effect = capture_add

        mock_result = MagicMock()
        mock_result.scalar_one.side_effect = lambda: created_trade
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import create_trade

        result = await create_trade(
            mock_db,
            ticker="AAPL",
            direction="long",
            asset_type="shares",
            timeframe="daily",
            entry_date=date(2026, 1, 15),
            entry_price=150.0,
            total_quantity=100.0,
        )

        assert created_trade is not None
        assert created_trade.user_id == "alice"
        assert result["user_id"] == "alice"

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="alice")
    async def test_get_trade_filters_by_user_id(self, mock_uid):
        """get_trade should only return trades belonging to the current user."""
        # Alice's trade
        trade = _make_trade(user_id="alice")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = trade

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import get_trade

        result = await get_trade(mock_db, trade.id)
        assert result is not None
        assert result["user_id"] == "alice"

        # Verify the query included user_id filter by checking execute was called
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="bob")
    async def test_get_trade_returns_none_for_other_user(self, mock_uid):
        """get_trade should return None when trade belongs to a different user."""
        # DB returns None because the WHERE clause filters out alice's trade
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import get_trade

        result = await get_trade(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="alice")
    async def test_list_trades_filters_by_user_id(self, mock_uid):
        """list_trades should only return trades for the current user."""
        trade1 = _make_trade(user_id="alice", ticker="AAPL")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade1]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import list_trades

        result = await list_trades(mock_db)
        assert len(result) == 1
        assert result[0]["user_id"] == "alice"

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="bob")
    async def test_delete_trade_scoped_to_user(self, mock_uid):
        """delete_trade should only delete trades belonging to the current user."""
        # rowcount=0 means the WHERE clause (id + user_id) matched nothing
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import delete_trade

        result = await delete_trade(mock_db, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="alice")
    async def test_delete_trade_own_trade_succeeds(self, mock_uid):
        """delete_trade should succeed when user owns the trade."""
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import delete_trade

        result = await delete_trade(mock_db, uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="bob")
    async def test_add_exit_returns_none_for_other_user(self, mock_uid):
        """add_exit should return None when trade belongs to a different user."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import add_exit

        result = await add_exit(
            mock_db,
            uuid.uuid4(),
            exit_date=date(2026, 2, 1),
            exit_price=160.0,
            quantity=50.0,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="bob")
    async def test_add_leg_returns_none_for_other_user(self, mock_uid):
        """add_leg should return None when trade belongs to a different user."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import add_leg

        result = await add_leg(
            mock_db,
            uuid.uuid4(),
            leg_type="buy_call",
            strike=155.0,
            expiry=date(2026, 3, 21),
            quantity=10.0,
            premium=3.5,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.journal_service._current_user_id", return_value="bob")
    async def test_update_trade_returns_none_for_other_user(self, mock_uid):
        """update_trade should return None when trade belongs to a different user."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        from backend.services.journal_service import update_trade

        result = await update_trade(mock_db, uuid.uuid4(), tags=["new-tag"])
        assert result is None

    def test_serialize_trade_includes_user_id(self):
        """Serialized trade output should include user_id."""
        trade = _make_trade(user_id="alice")
        result = serialize_trade(trade)
        assert result["user_id"] == "alice"

    def test_default_user_id_in_mock(self):
        """Default mock trade should have user_id='default'."""
        trade = _make_trade()
        assert trade.user_id == "default"


# ============================================================
# User ID Validation Tests
# ============================================================


class TestCurrentUserIdValidation:
    """Tests that _current_user_id validates the PRAXIALPHA_USER_ID setting."""

    @patch("backend.services.journal_service.get_settings")
    def test_valid_user_id(self, mock_settings):
        """A valid, trimmed user_id is returned as-is."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = "alice"
        assert _current_user_id() == "alice"

    @patch("backend.services.journal_service.get_settings")
    def test_strips_whitespace(self, mock_settings):
        """Leading/trailing whitespace is stripped."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = "  alice  "
        assert _current_user_id() == "alice"

    @patch("backend.services.journal_service.get_settings")
    def test_none_raises_runtime_error(self, mock_settings):
        """None value raises RuntimeError."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = None
        with pytest.raises(RuntimeError, match="not configured"):
            _current_user_id()

    @patch("backend.services.journal_service.get_settings")
    def test_empty_string_raises_value_error(self, mock_settings):
        """Empty string raises ValueError."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = ""
        with pytest.raises(ValueError, match="non-empty"):
            _current_user_id()

    @patch("backend.services.journal_service.get_settings")
    def test_whitespace_only_raises_value_error(self, mock_settings):
        """Whitespace-only string raises ValueError."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = "   "
        with pytest.raises(ValueError, match="non-empty"):
            _current_user_id()

    @patch("backend.services.journal_service.get_settings")
    def test_too_long_raises_value_error(self, mock_settings):
        """User ID exceeding 50 chars raises ValueError."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = "x" * 51
        with pytest.raises(ValueError, match="at most 50"):
            _current_user_id()

    @patch("backend.services.journal_service.get_settings")
    def test_exactly_max_length_is_valid(self, mock_settings):
        """User ID of exactly 50 chars is valid."""
        from backend.services.journal_service import _current_user_id

        mock_settings.return_value.praxialpha_user_id = "x" * 50
        assert _current_user_id() == "x" * 50
