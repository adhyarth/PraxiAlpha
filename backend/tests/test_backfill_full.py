"""
PraxiAlpha — Full Backfill Tests

Tests for the production backfill script:
  - Ticker filtering logic
  - Progress tracker (checkpoint read/write)
  - Incremental date calculation
  - Backfill result handling
"""

import asyncio
import importlib.util
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts.backfill_full import (
    ALLOWED_ASSET_TYPES,
    BackfillProgressTracker,
    filter_backfill_tickers,
    load_checkpoint,
)


# ============================================================
# Helpers — mock Stock objects
# ============================================================
def _make_stock(
    ticker: str,
    asset_type: str = "Common Stock",
    is_active: bool = True,
    is_delisted: bool = False,
    name: str | None = "Test Corp",
    latest_date: date | None = None,
) -> MagicMock:
    """Create a mock Stock object for testing."""
    stock = MagicMock()
    stock.ticker = ticker
    stock.asset_type = asset_type
    stock.is_active = is_active
    stock.is_delisted = is_delisted
    stock.name = name
    stock.latest_date = latest_date
    stock.id = hash(ticker) % 100000
    return stock


# ============================================================
# Ticker Filtering Tests
# ============================================================
class TestFilterBackfillTickers:
    """Tests for the ticker filtering logic."""

    def test_filter_keeps_common_stock(self):
        """Common Stock tickers should be kept."""
        stocks = [_make_stock("AAPL", asset_type="Common Stock")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 1
        assert result[0].ticker == "AAPL"

    def test_filter_keeps_etf(self):
        """ETF tickers should be kept."""
        stocks = [_make_stock("SPY", asset_type="ETF")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 1

    def test_filter_removes_preferred_stock(self):
        """Preferred Stock tickers should be filtered out."""
        stocks = [_make_stock("BAC-PL", asset_type="Preferred Stock")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_warrant(self):
        """Warrant tickers should be filtered out."""
        stocks = [_make_stock("SPAK-WT", asset_type="Warrant")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_unit(self):
        """Unit tickers should be filtered out."""
        stocks = [_make_stock("UNIT-UN", asset_type="Unit")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_empty_asset_type(self):
        """Tickers with empty asset type should be filtered out."""
        stocks = [_make_stock("JUNK", asset_type="")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_none_asset_type(self):
        """Tickers with None asset type should be filtered out."""
        stocks = [_make_stock("JUNK", asset_type=None)]
        # asset_type=None → (None or "").strip() = "" → not in ALLOWED
        stock = stocks[0]
        stock.asset_type = None
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_inactive(self):
        """Inactive tickers should be filtered out."""
        stocks = [_make_stock("OLD", is_active=False)]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_delisted(self):
        """Delisted tickers should be filtered out."""
        stocks = [_make_stock("DEAD", is_delisted=True)]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_no_name(self):
        """Tickers with no name (junk entries) should be filtered out."""
        stocks = [_make_stock("JUNK", name=None)]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_removes_empty_name(self):
        """Tickers with empty name should be filtered out."""
        stocks = [_make_stock("JUNK", name="")]
        result = filter_backfill_tickers(stocks)
        assert len(result) == 0

    def test_filter_mixed_input(self):
        """Should correctly filter a mix of valid and invalid tickers."""
        stocks = [
            _make_stock("AAPL", asset_type="Common Stock"),
            _make_stock("SPY", asset_type="ETF"),
            _make_stock("BAC-PL", asset_type="Preferred Stock"),
            _make_stock("SPAK-WT", asset_type="Warrant"),
            _make_stock("OLD", asset_type="Common Stock", is_active=False),
            _make_stock("DEAD", asset_type="ETF", is_delisted=True),
            _make_stock("JUNK", asset_type="Common Stock", name=None),
            _make_stock("MSFT", asset_type="Common Stock"),
        ]
        result = filter_backfill_tickers(stocks)
        tickers = [s.ticker for s in result]
        assert tickers == ["AAPL", "SPY", "MSFT"]

    def test_filter_custom_asset_types(self):
        """Should respect custom allowed_types."""
        stocks = [
            _make_stock("AAPL", asset_type="Common Stock"),
            _make_stock("SPY", asset_type="ETF"),
        ]
        # Only ETFs
        result = filter_backfill_tickers(stocks, allowed_types={"ETF"})
        assert len(result) == 1
        assert result[0].ticker == "SPY"

    def test_filter_empty_input(self):
        """Empty input should return empty output."""
        result = filter_backfill_tickers([])
        assert len(result) == 0

    def test_allowed_asset_types_constant(self):
        """ALLOWED_ASSET_TYPES should contain Common Stock and ETF."""
        assert {"Common Stock", "ETF"} == ALLOWED_ASSET_TYPES


# ============================================================
# Progress Tracker Tests
# ============================================================
class TestBackfillProgressTracker:
    """Tests for the BackfillProgressTracker."""

    def _make_tracker(
        self, total: int = 100, resume_from: dict[str, Any] | None = None
    ) -> tuple[BackfillProgressTracker, Path, Path]:
        """Create a tracker with temp files."""
        tmp_dir = Path(tempfile.mkdtemp())
        progress_file = tmp_dir / "progress.json"
        live_log_file = tmp_dir / "live.log"
        tracker = BackfillProgressTracker(
            total_tickers=total,
            progress_file=progress_file,
            live_log_file=live_log_file,
            resume_from=resume_from,
        )
        return tracker, progress_file, live_log_file

    def test_initial_state(self):
        """Fresh tracker should start at 0."""
        tracker, _, _ = self._make_tracker(total=100)
        assert tracker.completed_count == 0
        assert tracker.failed_count == 0
        assert tracker.total_records == 0
        assert tracker.total_tickers == 100

    def test_record_success(self):
        """Recording a success should update counters."""
        tracker, progress_file, live_log_file = self._make_tracker(total=10)
        asyncio.run(tracker.record_success("AAPL", records=9000, splits=4, dividends=79))
        assert tracker.completed_count == 1
        assert tracker.total_records == 9000
        assert tracker.total_splits == 4
        assert tracker.total_dividends == 79
        assert "AAPL" in tracker.completed

        # Check progress file was written
        assert progress_file.exists()
        data = json.loads(progress_file.read_text())
        assert data["completed"] == 1
        assert data["records_inserted"] == 9000

        # Check live log was written
        log_text = live_log_file.read_text()
        assert "AAPL" in log_text
        assert "✅" in log_text

    def test_record_failure(self):
        """Recording a failure should update the failed dict."""
        tracker, progress_file, live_log_file = self._make_tracker(total=10)
        asyncio.run(tracker.record_failure("BADTICKER", "404 Not Found"))
        assert tracker.failed_count == 1
        assert "BADTICKER" in tracker.failed
        assert tracker.failed["BADTICKER"] == "404 Not Found"

        # Check live log
        log_text = live_log_file.read_text()
        assert "BADTICKER" in log_text
        assert "❌" in log_text

    def test_multiple_successes(self):
        """Multiple successes should accumulate."""
        tracker, _, _ = self._make_tracker(total=10)
        asyncio.run(tracker.record_success("AAPL", records=9000))
        asyncio.run(tracker.record_success("MSFT", records=9000))
        asyncio.run(tracker.record_success("GOOGL", records=5000))
        assert tracker.completed_count == 3
        assert tracker.total_records == 23000

    def test_completed_set(self):
        """completed_set should provide O(1) lookup."""
        tracker, _, _ = self._make_tracker(total=10)
        asyncio.run(tracker.record_success("AAPL", records=100))
        asyncio.run(tracker.record_success("MSFT", records=200))
        assert "AAPL" in tracker.completed_set
        assert "MSFT" in tracker.completed_set
        assert "GOOGL" not in tracker.completed_set

    def test_progress_percentage(self):
        """Progress JSON should have correct percentage."""
        tracker, progress_file, _ = self._make_tracker(total=4)
        asyncio.run(tracker.record_success("A", records=100))
        asyncio.run(tracker.record_success("B", records=100))
        data = json.loads(progress_file.read_text())
        assert data["progress_pct"] == 50.0

    def test_resume_from_checkpoint(self):
        """Resuming should restore previous state."""
        checkpoint = {
            "tickers_completed": ["AAPL", "MSFT"],
            "tickers_failed": {"BAD": "404"},
            "records_inserted": 18000,
            "splits_inserted": 12,
            "dividends_inserted": 170,
            "started_at": "2026-03-16T10:00:00+00:00",
        }
        tracker, _, live_log_file = self._make_tracker(total=100, resume_from=checkpoint)
        assert tracker.completed_count == 2
        assert tracker.failed_count == 1
        assert tracker.total_records == 18000
        assert tracker.total_splits == 12
        assert tracker.total_dividends == 170

        # Live log should mention resume
        log_text = live_log_file.read_text()
        assert "RESUMED" in log_text

    def test_write_summary(self):
        """write_summary should output a final report."""
        tracker, _, live_log_file = self._make_tracker(total=3)
        asyncio.run(tracker.record_success("AAPL", records=9000))
        asyncio.run(tracker.record_failure("BAD", "timeout"))
        asyncio.run(tracker.record_success("MSFT", records=9000))
        tracker.write_summary()

        log_text = live_log_file.read_text()
        assert "BACKFILL COMPLETE" in log_text
        assert "18,000" in log_text  # total records formatted
        assert "BAD" in log_text  # failed ticker listed

    def test_eta_calculation(self):
        """ETA should be > 0 after processing some tickers."""
        tracker, _, _ = self._make_tracker(total=100)
        asyncio.run(tracker.record_success("AAPL", records=100))
        # After processing 1/100, ETA should be positive
        assert tracker.eta_seconds > 0

    def test_eta_zero_when_no_progress(self):
        """ETA should be 0 when no tickers have been processed."""
        tracker, _, _ = self._make_tracker(total=100)
        assert tracker.eta_seconds == 0.0

    def test_atomic_write(self):
        """Progress file should be written atomically (via temp + rename)."""
        tracker, progress_file, _ = self._make_tracker(total=10)
        asyncio.run(tracker.record_success("AAPL", records=100))
        # The .tmp file should not exist after write (it was renamed)
        assert not progress_file.with_suffix(".tmp").exists()
        # The progress file should exist and be valid JSON
        assert progress_file.exists()
        data = json.loads(progress_file.read_text())
        assert data["completed"] == 1


# ============================================================
# Checkpoint Load Tests
# ============================================================
class TestLoadCheckpoint:
    """Tests for checkpoint loading."""

    def test_load_nonexistent(self):
        """Should return None if checkpoint file doesn't exist."""
        result = load_checkpoint(Path("/tmp/nonexistent_backfill_progress.json"))
        assert result is None

    def test_load_valid_checkpoint(self):
        """Should load a valid checkpoint."""
        tmp = Path(tempfile.mktemp(suffix=".json"))
        data = {
            "tickers_completed": ["AAPL", "MSFT"],
            "tickers_failed": {},
            "records_inserted": 18000,
            "completed": 2,
            "total_tickers": 100,
        }
        tmp.write_text(json.dumps(data))
        result = load_checkpoint(tmp)
        assert result is not None
        assert result["completed"] == 2
        assert result["tickers_completed"] == ["AAPL", "MSFT"]
        tmp.unlink()

    def test_load_corrupt_checkpoint(self):
        """Should return None for corrupt JSON."""
        tmp = Path(tempfile.mktemp(suffix=".json"))
        tmp.write_text("this is not json {{{")
        result = load_checkpoint(tmp)
        assert result is None
        tmp.unlink()


# ============================================================
# Incremental Date Calculation Tests
# ============================================================
class TestIncrementalDateLogic:
    """Tests for the incremental start date calculation in backfill_single_stock."""

    def test_no_existing_data_uses_default_start(self):
        """When stock.latest_date is None, should use the default start date."""
        stock = _make_stock("AAPL", latest_date=None)
        default_start = "1990-01-01"
        # Simulate the logic from backfill_single_stock
        effective_start = default_start
        if stock.latest_date:
            overlap_start = stock.latest_date - timedelta(days=5)
            effective_start = max(overlap_start.isoformat(), default_start)
        assert effective_start == "1990-01-01"

    def test_existing_data_uses_overlap_start(self):
        """When stock has data, should start from latest_date - 5 days."""
        stock = _make_stock("AAPL", latest_date=date(2026, 3, 10))
        default_start = "1990-01-01"
        effective_start = default_start
        if stock.latest_date:
            overlap_start = stock.latest_date - timedelta(days=5)
            effective_start = max(overlap_start.isoformat(), default_start)
        assert effective_start == "2026-03-05"

    def test_overlap_does_not_go_before_default_start(self):
        """If latest_date - 5 days is before default start, use default start."""
        stock = _make_stock("AAPL", latest_date=date(1990, 1, 3))
        default_start = "1990-01-01"
        effective_start = default_start
        if stock.latest_date:
            overlap_start = stock.latest_date - timedelta(days=5)
            effective_start = max(overlap_start.isoformat(), default_start)
        # 1990-01-03 - 5 days = 1989-12-29, but max with 1990-01-01 → 1990-01-01
        assert effective_start == "1990-01-01"

    def test_recent_data_only_fetches_last_few_days(self):
        """Stock updated yesterday should only fetch ~6 days of data."""
        stock = _make_stock("AAPL", latest_date=date(2026, 3, 15))
        default_start = "1990-01-01"
        effective_start = default_start
        if stock.latest_date:
            overlap_start = stock.latest_date - timedelta(days=5)
            effective_start = max(overlap_start.isoformat(), default_start)
        assert effective_start == "2026-03-10"


# ============================================================
# Celery Task Registration Tests
# ============================================================
class TestCeleryTaskRegistration:
    """Verify Celery tasks are importable and registered (skip if celery not installed)."""

    @pytest.mark.skipif(
        importlib.util.find_spec("celery") is None,
        reason="celery not installed in CI",
    )
    def test_daily_ohlcv_update_is_registered(self):
        from backend.tasks.data_tasks import daily_ohlcv_update

        assert callable(daily_ohlcv_update)

    @pytest.mark.skipif(
        importlib.util.find_spec("celery") is None,
        reason="celery not installed in CI",
    )
    def test_daily_macro_update_is_registered(self):
        from backend.tasks.data_tasks import daily_macro_update

        assert callable(daily_macro_update)

    @pytest.mark.skipif(
        importlib.util.find_spec("celery") is None,
        reason="celery not installed in CI",
    )
    def test_backfill_all_stocks_is_registered(self):
        from backend.tasks.data_tasks import backfill_all_stocks

        assert callable(backfill_all_stocks)
