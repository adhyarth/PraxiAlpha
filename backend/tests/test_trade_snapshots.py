"""
PraxiAlpha — Trade Snapshot Tests

Tests for:
- TradeSnapshot model structure
- PnL computation (long, short, edge cases)
- Snapshot service CRUD (list, what-if summary)
- Snapshot service user isolation (user scoping)
- Celery task (eligible trade finder)
- API endpoints (/snapshots, /what-if)

All tests mock the database — no real Postgres needed in CI.
"""

import importlib.util
import uuid
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Optional dependencies — not installed in CI test environment
_has_celery = importlib.util.find_spec("celery") is not None
_has_fastapi = importlib.util.find_spec("fastapi") is not None

# ============================================================
# Model Tests
# ============================================================


class TestTradeSnapshotModel:
    """Tests for TradeSnapshot ORM model structure."""

    def test_model_can_be_imported(self):
        from backend.models.trade_snapshot import TradeSnapshot

        assert TradeSnapshot.__tablename__ == "trade_snapshots"

    def test_model_columns(self):
        from backend.models.trade_snapshot import TradeSnapshot

        columns = {c.name for c in TradeSnapshot.__table__.columns}
        expected = {
            "id",
            "trade_id",
            "snapshot_date",
            "close_price",
            "hypothetical_pnl",
            "hypothetical_pnl_pct",
            "created_at",
        }
        assert expected == columns

    def test_unique_constraint_exists(self):
        from backend.models.trade_snapshot import TradeSnapshot

        constraints = TradeSnapshot.__table__.constraints
        unique_names = {c.name for c in constraints if hasattr(c, "name") and c.name}
        assert "uq_trade_snapshot_date" in unique_names

    def test_model_repr(self):
        from backend.models.trade_snapshot import TradeSnapshot

        snap = TradeSnapshot(
            id=uuid.uuid4(),
            trade_id=uuid.uuid4(),
            snapshot_date=date(2026, 3, 20),
            close_price=155.00,
            hypothetical_pnl=500.00,
            hypothetical_pnl_pct=5.0,
        )
        repr_str = repr(snap)
        assert "TradeSnapshot" in repr_str
        assert "500" in repr_str

    def test_registered_in_models_init(self):
        from backend.models import TradeSnapshot

        assert TradeSnapshot.__tablename__ == "trade_snapshots"


# ============================================================
# PnL Computation Tests
# ============================================================


class TestComputeHypotheticalPnl:
    """Tests for compute_hypothetical_pnl helper."""

    def test_long_trade_profit(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=100.0,
            close_price=110.0,
            total_quantity=50.0,
            direction="long",
        )
        assert pnl == 500.0  # (110 - 100) * 50
        assert pnl_pct == 10.0  # 500 / (100*50) * 100

    def test_long_trade_loss(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=100.0,
            close_price=90.0,
            total_quantity=50.0,
            direction="long",
        )
        assert pnl == -500.0
        assert pnl_pct == -10.0

    def test_short_trade_profit(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=100.0,
            close_price=90.0,
            total_quantity=50.0,
            direction="short",
        )
        assert pnl == 500.0  # (100 - 90) * 50
        assert pnl_pct == 10.0

    def test_short_trade_loss(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=100.0,
            close_price=110.0,
            total_quantity=50.0,
            direction="short",
        )
        assert pnl == -500.0
        assert pnl_pct == -10.0

    def test_zero_movement(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=100.0,
            close_price=100.0,
            total_quantity=50.0,
            direction="long",
        )
        assert pnl == 0.0
        assert pnl_pct == 0.0

    def test_decimal_precision(self):
        """Verify no float drift with precise values."""
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=10.01,
            close_price=10.03,
            total_quantity=100.0,
            direction="long",
        )
        assert pnl == 2.0  # (10.03 - 10.01) * 100 = 2.0000
        assert abs(pnl_pct - 0.1998) < 0.001

    def test_fractional_quantity(self):
        from backend.services.trade_snapshot_service import compute_hypothetical_pnl

        pnl, pnl_pct = compute_hypothetical_pnl(
            entry_price=50.0,
            close_price=60.0,
            total_quantity=0.5,
            direction="long",
        )
        assert pnl == 5.0  # (60 - 50) * 0.5
        assert pnl_pct == 20.0


# ============================================================
# Snapshot Serialization Tests
# ============================================================


class TestSerializeSnapshot:
    """Tests for _serialize_snapshot helper."""

    def test_serializes_all_fields(self):
        from backend.services.trade_snapshot_service import _serialize_snapshot

        snap = MagicMock()
        snap.id = uuid.uuid4()
        snap.trade_id = uuid.uuid4()
        snap.snapshot_date = date(2026, 3, 20)
        snap.close_price = Decimal("155.50")
        snap.hypothetical_pnl = Decimal("500.00")
        snap.hypothetical_pnl_pct = Decimal("10.00")
        snap.created_at = datetime(2026, 3, 20, 19, 0, 0)

        result = _serialize_snapshot(snap)
        assert result["snapshot_date"] == "2026-03-20"
        assert result["close_price"] == 155.50
        assert result["hypothetical_pnl"] == 500.00
        assert result["hypothetical_pnl_pct"] == 10.00
        assert result["id"] == str(snap.id)
        assert result["trade_id"] == str(snap.trade_id)
        assert result["created_at"] is not None

    def test_serializes_none_created_at(self):
        from backend.services.trade_snapshot_service import _serialize_snapshot

        snap = MagicMock()
        snap.id = uuid.uuid4()
        snap.trade_id = uuid.uuid4()
        snap.snapshot_date = date(2026, 3, 20)
        snap.close_price = Decimal("100.00")
        snap.hypothetical_pnl = Decimal("0.00")
        snap.hypothetical_pnl_pct = Decimal("0.00")
        snap.created_at = None

        result = _serialize_snapshot(snap)
        assert result["created_at"] is None


# ============================================================
# Snapshot Service CRUD Tests
# ============================================================


def _make_mock_trade(**overrides):
    """Create a mock Trade with sensible defaults for snapshot tests."""
    from backend.models.journal import Timeframe, TradeDirection

    defaults = {
        "id": uuid.uuid4(),
        "user_id": "default",
        "ticker": "AAPL",
        "direction": TradeDirection.LONG,
        "entry_price": Decimal("150.00"),
        "total_quantity": Decimal("100"),
        "timeframe": Timeframe.DAILY,
        "stop_loss": None,
        "exits": [],
    }
    defaults.update(overrides)
    trade = MagicMock(**defaults)
    # Ensure attribute access returns the mock values
    for k, v in defaults.items():
        setattr(trade, k, v)
    return trade


def _make_mock_exit(exit_date, exit_price, quantity):
    """Create a mock TradeExit."""
    ex = MagicMock()
    ex.exit_date = exit_date
    ex.exit_price = Decimal(str(exit_price))
    ex.quantity = Decimal(str(quantity))
    return ex


def _make_mock_snapshot(**overrides):
    """Create a mock TradeSnapshot."""
    defaults = {
        "id": uuid.uuid4(),
        "trade_id": uuid.uuid4(),
        "snapshot_date": date(2026, 3, 20),
        "close_price": Decimal("155.00"),
        "hypothetical_pnl": Decimal("500.00"),
        "hypothetical_pnl_pct": Decimal("3.3333"),
        "created_at": datetime(2026, 3, 20, 19, 0, 0),
    }
    defaults.update(overrides)
    snap = MagicMock(**defaults)
    for k, v in defaults.items():
        setattr(snap, k, v)
    return snap


class TestListSnapshots:
    """Tests for list_snapshots service function."""

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_none_for_nonexistent_trade(self, mock_uid):
        from backend.services.trade_snapshot_service import list_snapshots

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await list_snapshots(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_empty_list_for_no_snapshots(self, mock_uid):
        from backend.services.trade_snapshot_service import list_snapshots

        trade = _make_mock_trade(user_id="alice")
        mock_db = AsyncMock()

        # First call: _get_user_trade (trade exists)
        trade_result = MagicMock()
        trade_result.scalar_one_or_none.return_value = trade
        # Second call: list snapshots (empty)
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [trade_result, snap_result]

        result = await list_snapshots(mock_db, trade.id)
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_snapshots_ordered_by_date(self, mock_uid):
        from backend.services.trade_snapshot_service import list_snapshots

        trade = _make_mock_trade(user_id="alice")
        snap1 = _make_mock_snapshot(trade_id=trade.id, snapshot_date=date(2026, 3, 18))
        snap2 = _make_mock_snapshot(trade_id=trade.id, snapshot_date=date(2026, 3, 19))

        mock_db = AsyncMock()
        trade_result = MagicMock()
        trade_result.scalar_one_or_none.return_value = trade
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = [snap1, snap2]
        mock_db.execute.side_effect = [trade_result, snap_result]

        result = await list_snapshots(mock_db, trade.id)
        assert len(result) == 2
        assert result[0]["snapshot_date"] == "2026-03-18"
        assert result[1]["snapshot_date"] == "2026-03-19"


class TestGetWhatifSummary:
    """Tests for get_whatif_summary service function."""

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_none_for_nonexistent_trade(self, mock_uid):
        from backend.services.trade_snapshot_service import get_whatif_summary

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_whatif_summary(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_none_for_open_trade(self, mock_uid):
        from backend.services.trade_snapshot_service import get_whatif_summary

        trade = _make_mock_trade(user_id="alice", exits=[])
        mock_db = AsyncMock()
        trade_result = MagicMock()
        trade_result.scalar_one_or_none.return_value = trade
        mock_db.execute.return_value = trade_result

        result = await get_whatif_summary(mock_db, trade.id)
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_summary_with_no_snapshots(self, mock_uid):
        from backend.services.trade_snapshot_service import get_whatif_summary

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(user_id="alice", exits=exits)

        mock_db = AsyncMock()
        trade_result = MagicMock()
        trade_result.scalar_one_or_none.return_value = trade
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [trade_result, snap_result]

        result = await get_whatif_summary(mock_db, trade.id)
        assert result is not None
        assert result["total_snapshots"] == 0
        assert result["best_hypothetical"] is None
        assert result["worst_hypothetical"] is None

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_best_worst_latest(self, mock_uid):
        from backend.services.trade_snapshot_service import get_whatif_summary

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(user_id="alice", exits=exits)

        snap_low = _make_mock_snapshot(
            trade_id=trade.id,
            snapshot_date=date(2026, 3, 16),
            hypothetical_pnl=Decimal("-200.00"),
        )
        snap_high = _make_mock_snapshot(
            trade_id=trade.id,
            snapshot_date=date(2026, 3, 17),
            hypothetical_pnl=Decimal("800.00"),
        )
        snap_mid = _make_mock_snapshot(
            trade_id=trade.id,
            snapshot_date=date(2026, 3, 18),
            hypothetical_pnl=Decimal("300.00"),
        )

        mock_db = AsyncMock()
        trade_result = MagicMock()
        trade_result.scalar_one_or_none.return_value = trade
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = [snap_low, snap_high, snap_mid]
        mock_db.execute.side_effect = [trade_result, snap_result]

        result = await get_whatif_summary(mock_db, trade.id)
        assert result["total_snapshots"] == 3
        assert result["best_hypothetical"]["hypothetical_pnl"] == 800.0
        assert result["worst_hypothetical"]["hypothetical_pnl"] == -200.0
        assert result["latest_snapshot"]["snapshot_date"] == "2026-03-18"
        assert result["ticker"] == "AAPL"


# ============================================================
# User Isolation Tests
# ============================================================


class TestSnapshotUserIsolation:
    """Tests that snapshot operations respect user_id scoping."""

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="bob")
    async def test_list_snapshots_returns_none_for_other_user(self, mock_uid):
        """Bob can't list snapshots for Alice's trade."""
        from backend.services.trade_snapshot_service import list_snapshots

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # trade not found for bob
        mock_db.execute.return_value = mock_result

        result = await list_snapshots(mock_db, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="bob")
    async def test_whatif_returns_none_for_other_user(self, mock_uid):
        """Bob can't get what-if summary for Alice's trade."""
        from backend.services.trade_snapshot_service import get_whatif_summary

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_whatif_summary(mock_db, uuid.uuid4())
        assert result is None


# ============================================================
# Max Tracking Duration Tests
# ============================================================


class TestMaxTrackingDurations:
    """Tests for MAX_TRACKING_DAYS constants."""

    def test_daily_tracking_30_days(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import MAX_TRACKING_DAYS

        assert MAX_TRACKING_DAYS[Timeframe.DAILY] == 30

    def test_weekly_tracking_112_days(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import MAX_TRACKING_DAYS

        assert MAX_TRACKING_DAYS[Timeframe.WEEKLY] == 112

    def test_monthly_tracking_540_days(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import MAX_TRACKING_DAYS

        assert MAX_TRACKING_DAYS[Timeframe.MONTHLY] == 540

    def test_quarterly_tracking_540_days(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import MAX_TRACKING_DAYS

        assert MAX_TRACKING_DAYS[Timeframe.QUARTERLY] == 540


# ============================================================
# Celery Task Tests
# ============================================================


@pytest.mark.skipif(not _has_celery, reason="celery not installed")
class TestGenerateSnapshotsTask:
    """Tests for the generate_snapshots Celery task."""

    def test_task_is_registered(self):
        """The task should be importable and have the correct name."""
        spec = importlib.util.find_spec("backend.tasks.trade_snapshot_task")
        assert spec is not None

    def test_celery_beat_schedule_includes_snapshots(self):
        from backend.tasks.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "daily-trade-snapshots" in schedule
        task_config = schedule["daily-trade-snapshots"]
        assert task_config["task"] == "backend.tasks.trade_snapshot_task.generate_snapshots"


# ============================================================
# API Route Tests
# ============================================================


@pytest.mark.skipif(not _has_fastapi, reason="fastapi not installed")
class TestSnapshotAPIRoutes:
    """Tests for snapshot API endpoint registration."""

    def test_journal_router_has_snapshot_routes(self):
        from backend.api.routes.journal import router

        paths = [route.path for route in router.routes]
        assert "/journal/{trade_id}/snapshots" in paths
        assert "/journal/{trade_id}/what-if" in paths

    def test_snapshot_endpoint_is_get(self):
        from backend.api.routes.journal import router

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/journal/{trade_id}/snapshots":
                assert "GET" in route.methods
                break
        else:
            pytest.fail("snapshot route not found")

    def test_whatif_endpoint_is_get(self):
        from backend.api.routes.journal import router

        for route in router.routes:
            if hasattr(route, "path") and route.path == "/journal/{trade_id}/what-if":
                assert "GET" in route.methods
                break
        else:
            pytest.fail("what-if route not found")


# ============================================================
# Create Snapshot Tests
# ============================================================


class TestCreateSnapshot:
    """Tests for create_snapshot service function."""

    @pytest.mark.asyncio
    async def test_creates_and_returns_snapshot(self):
        from backend.services.trade_snapshot_service import create_snapshot

        trade_id = uuid.uuid4()
        mock_db = AsyncMock()

        # After flush+refresh, the snapshot should have an id and created_at
        async def mock_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime(2026, 3, 20, 19, 0, 0)

        mock_db.refresh = mock_refresh

        result = await create_snapshot(
            mock_db,
            trade_id=trade_id,
            snapshot_date=date(2026, 3, 20),
            close_price=155.0,
            hypothetical_pnl=500.0,
            hypothetical_pnl_pct=3.33,
        )
        assert result["trade_id"] == str(trade_id)
        assert result["close_price"] == 155.0
        assert result["hypothetical_pnl"] == 500.0
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()


# ============================================================
# Eligible Trade Finder Tests
# ============================================================


class TestGetClosedTradesNeedingSnapshots:
    """Tests for get_closed_trades_needing_snapshots."""

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_empty_for_open_trades(self, mock_uid):
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        trade = _make_mock_trade(user_id="alice", exits=[])
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade]
        mock_db.execute.return_value = mock_result

        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 20))
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_skips_trade_past_max_tracking(self, mock_uid):
        """A daily trade closed 31+ days ago should be skipped."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 1, 1), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.DAILY,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade]
        mock_db.execute.return_value = mock_result

        # Reference date is 60 days after close (past 30-day limit)
        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 2))
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_returns_eligible_closed_trade(self, mock_uid):
        """A daily trade closed 5 days ago should be eligible."""
        from backend.models.journal import Timeframe, TradeDirection
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.DAILY,
            direction=TradeDirection.LONG,
        )

        mock_db = AsyncMock()
        # First call: list trades
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [trade]
        # Second call: batch check existing snapshots (none found)
        existing_result = MagicMock()
        existing_result.all.return_value = []
        mock_db.execute.side_effect = [trades_result, existing_result]

        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 20))
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_skips_trade_with_existing_snapshot(self, mock_uid):
        """A trade that already has a snapshot for this date is skipped."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.DAILY,
        )

        mock_db = AsyncMock()
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [trade]
        # Batch check: existing snapshot found for this trade
        existing_result = MagicMock()
        existing_result.all.return_value = [(trade.id,)]
        mock_db.execute.side_effect = [trades_result, existing_result]

        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 20))
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_weekly_trade_skipped_on_non_cadence_day(self, mock_uid):
        """A weekly trade should only get snapshots every 7 days after exit."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.WEEKLY,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade]
        mock_db.execute.return_value = mock_result

        # 3 days after exit — not a multiple of 7, should be skipped
        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 18))
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_weekly_trade_eligible_on_cadence_day(self, mock_uid):
        """A weekly trade should get a snapshot exactly 7 days after exit."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 3, 15), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.WEEKLY,
        )

        mock_db = AsyncMock()
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [trade]
        existing_result = MagicMock()
        existing_result.all.return_value = []
        mock_db.execute.side_effect = [trades_result, existing_result]

        # 7 days after exit — cadence aligned
        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 3, 22))
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_monthly_trade_skipped_on_non_cadence_day(self, mock_uid):
        """A monthly trade should only get snapshots every 30 days after exit."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 1, 1), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.MONTHLY,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [trade]
        mock_db.execute.return_value = mock_result

        # 15 days after exit — not a multiple of 30
        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 1, 16))
        assert result == []

    @pytest.mark.asyncio
    @patch("backend.services.trade_snapshot_service._current_user_id", return_value="alice")
    async def test_monthly_trade_eligible_on_cadence_day(self, mock_uid):
        """A monthly trade should get a snapshot exactly 30 days after exit."""
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import (
            get_closed_trades_needing_snapshots,
        )

        exits = [_make_mock_exit(date(2026, 1, 1), 160.0, 100)]
        trade = _make_mock_trade(
            user_id="alice",
            exits=exits,
            timeframe=Timeframe.MONTHLY,
        )

        mock_db = AsyncMock()
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [trade]
        existing_result = MagicMock()
        existing_result.all.return_value = []
        mock_db.execute.side_effect = [trades_result, existing_result]

        # 30 days after exit — cadence aligned
        result = await get_closed_trades_needing_snapshots(mock_db, date(2026, 1, 31))
        assert len(result) == 1


# ============================================================
# Snapshot Cadence Constants Tests
# ============================================================


class TestSnapshotCadence:
    """Tests for SNAPSHOT_CADENCE_DAYS constants."""

    def test_daily_cadence(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import SNAPSHOT_CADENCE_DAYS

        assert SNAPSHOT_CADENCE_DAYS[Timeframe.DAILY] == 1

    def test_weekly_cadence(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import SNAPSHOT_CADENCE_DAYS

        assert SNAPSHOT_CADENCE_DAYS[Timeframe.WEEKLY] == 7

    def test_monthly_cadence(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import SNAPSHOT_CADENCE_DAYS

        assert SNAPSHOT_CADENCE_DAYS[Timeframe.MONTHLY] == 30

    def test_quarterly_cadence(self):
        from backend.models.journal import Timeframe
        from backend.services.trade_snapshot_service import SNAPSHOT_CADENCE_DAYS

        assert SNAPSHOT_CADENCE_DAYS[Timeframe.QUARTERLY] == 30
