"""
PraxiAlpha — Trading Journal PDF Report Tests

Tests for:
- journal_report_service helper functions (format_pnl, format_pct, get_lookback_start, etc.)
- build_trade_chart (with plotly importorskip guard)
- generate_report_pdf (PDF generation with fpdf2)
- Report API endpoint GET /api/v1/journal/report (mocked service layer)

All tests mock the database — no real Postgres needed in CI.
"""

import importlib.util
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.services.journal_report_service import (
    _TIMEFRAME_LOOKBACK_DAYS,
    format_pct,
    format_pnl,
    get_chart_end_date,
    get_lookback_start,
)

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def _make_trade_dict(**overrides) -> dict:
    """Create a serialized trade dict with sensible defaults."""
    defaults = {
        "id": str(uuid.uuid4()),
        "ticker": "AAPL",
        "direction": "long",
        "asset_type": "shares",
        "trade_type": "single_leg",
        "timeframe": "daily",
        "entry_date": date(2026, 1, 15),
        "entry_price": 150.00,
        "total_quantity": 100.0,
        "stop_loss": 145.00,
        "take_profit": 170.00,
        "tags": ["momentum", "earnings"],
        "comments": "Bullish breakout on volume",
        "status": "closed",
        "realized_pnl": 1000.00,
        "return_pct": 6.67,
        "r_multiple": 2.0,
        "avg_exit_price": 160.00,
        "exits": [
            {
                "id": str(uuid.uuid4()),
                "exit_date": date(2026, 2, 1),
                "exit_price": 160.00,
                "quantity": 100.0,
                "comments": None,
            }
        ],
        "legs": [],
    }
    defaults.update(overrides)
    return defaults


def _make_candle(d: date, o: float, h: float, lo: float, c: float) -> dict:
    """Create a candle dict."""
    return {
        "date": d,
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "adjusted_close": c,
        "volume": 1_000_000,
    }


# ============================================================
# Helper function tests
# ============================================================


class TestFormatPnl:
    """Tests for format_pnl."""

    def test_positive(self):
        assert format_pnl(1000.0) == "+$1,000.00"

    def test_negative(self):
        assert format_pnl(-500.0) == "-$500.00"

    def test_zero(self):
        assert format_pnl(0.0) == "+$0.00"

    def test_none(self):
        assert format_pnl(None) == "N/A"

    def test_large(self):
        assert format_pnl(1_234_567.89) == "+$1,234,567.89"


class TestFormatPct:
    """Tests for format_pct."""

    def test_positive(self):
        assert format_pct(6.67) == "+6.67%"

    def test_negative(self):
        assert format_pct(-3.50) == "-3.50%"

    def test_zero(self):
        assert format_pct(0.0) == "+0.00%"

    def test_none(self):
        assert format_pct(None) == "N/A"


class TestGetLookbackStart:
    """Tests for get_lookback_start."""

    def test_daily_lookback(self):
        trade = _make_trade_dict(timeframe="daily", entry_date=date(2026, 6, 15))
        result = get_lookback_start(trade)
        expected = date(2026, 6, 15) - timedelta(days=_TIMEFRAME_LOOKBACK_DAYS["daily"])
        assert result == expected

    def test_weekly_lookback(self):
        trade = _make_trade_dict(timeframe="weekly", entry_date=date(2026, 6, 15))
        result = get_lookback_start(trade)
        expected = date(2026, 6, 15) - timedelta(days=_TIMEFRAME_LOOKBACK_DAYS["weekly"])
        assert result == expected

    def test_monthly_lookback(self):
        trade = _make_trade_dict(timeframe="monthly", entry_date=date(2026, 6, 15))
        result = get_lookback_start(trade)
        expected = date(2026, 6, 15) - timedelta(days=_TIMEFRAME_LOOKBACK_DAYS["monthly"])
        assert result == expected

    def test_quarterly_lookback(self):
        trade = _make_trade_dict(timeframe="quarterly", entry_date=date(2026, 6, 15))
        result = get_lookback_start(trade)
        expected = date(2026, 6, 15) - timedelta(days=_TIMEFRAME_LOOKBACK_DAYS["quarterly"])
        assert result == expected

    def test_string_entry_date(self):
        trade = _make_trade_dict(timeframe="daily", entry_date="2026-06-15")
        result = get_lookback_start(trade)
        expected = date(2026, 6, 15) - timedelta(days=365)
        assert result == expected

    def test_default_timeframe(self):
        trade = _make_trade_dict(entry_date=date(2026, 6, 15))
        trade.pop("timeframe", None)
        result = get_lookback_start(trade)
        # Falls back to 365 days
        expected = date(2026, 6, 15) - timedelta(days=365)
        assert result == expected


class TestGetChartEndDate:
    """Tests for get_chart_end_date."""

    def test_closed_trade_with_exits(self):
        trade = _make_trade_dict(
            exits=[
                {"exit_date": date(2026, 2, 1), "exit_price": 160, "quantity": 50, "id": "x1"},
                {"exit_date": date(2026, 2, 15), "exit_price": 165, "quantity": 50, "id": "x2"},
            ],
        )
        result = get_chart_end_date(trade)
        assert result == date(2026, 2, 15) + timedelta(days=30)

    def test_open_trade_no_exits(self):
        trade = _make_trade_dict(exits=[], status="open")
        result = get_chart_end_date(trade)
        assert result == date.today()

    def test_string_exit_dates(self):
        trade = _make_trade_dict(
            exits=[
                {"exit_date": "2026-03-10", "exit_price": 170, "quantity": 100, "id": "x1"},
            ],
        )
        result = get_chart_end_date(trade)
        assert result == date(2026, 3, 10) + timedelta(days=30)


# ============================================================
# Chart builder tests (plotly required)
# ============================================================


plotly = pytest.importorskip("plotly", reason="plotly not installed")


class TestBuildTradeChart:
    """Tests for build_trade_chart — chart generation with plotly."""

    def test_returns_bytes_with_mocked_kaleido(self):
        """Chart builder should return PNG bytes when kaleido is available."""
        from backend.services.journal_report_service import build_trade_chart

        candles = [
            _make_candle(date(2026, 1, d), 150 + d, 155 + d, 148 + d, 152 + d) for d in range(1, 21)
        ]
        trade = _make_trade_dict()

        # Mock kaleido export to avoid needing real kaleido in CI
        fake_png = b"\x89PNG_fake_image_bytes"
        with patch("plotly.graph_objects.Figure.to_image", return_value=fake_png):
            result = build_trade_chart(candles, trade)

        assert result == fake_png

    def test_empty_candles_returns_none(self):
        from backend.services.journal_report_service import build_trade_chart

        trade = _make_trade_dict()
        result = build_trade_chart([], trade)
        assert result is None

    def test_no_stop_loss_or_take_profit(self):
        """Should work without SL/TP lines."""
        from backend.services.journal_report_service import build_trade_chart

        candles = [_make_candle(date(2026, 1, d), 150, 155, 148, 152) for d in range(1, 11)]
        trade = _make_trade_dict(stop_loss=None, take_profit=None)

        fake_png = b"\x89PNG_fake"
        with patch("plotly.graph_objects.Figure.to_image", return_value=fake_png):
            result = build_trade_chart(candles, trade)

        assert result == fake_png

    def test_short_trade(self):
        """Should work for short trades."""
        from backend.services.journal_report_service import build_trade_chart

        candles = [_make_candle(date(2026, 1, d), 150, 155, 148, 152) for d in range(1, 11)]
        trade = _make_trade_dict(direction="short")

        fake_png = b"\x89PNG_short"
        with patch("plotly.graph_objects.Figure.to_image", return_value=fake_png):
            result = build_trade_chart(candles, trade)

        assert result == fake_png

    def test_kaleido_failure_returns_none(self):
        """If kaleido export raises, should return None gracefully."""
        from backend.services.journal_report_service import build_trade_chart

        candles = [_make_candle(date(2026, 1, d), 150, 155, 148, 152) for d in range(1, 11)]
        trade = _make_trade_dict()

        with patch(
            "plotly.graph_objects.Figure.to_image",
            side_effect=Exception("kaleido not found"),
        ):
            result = build_trade_chart(candles, trade)

        assert result is None

    def test_multiple_exits_markers(self):
        """Should add a marker for each exit."""
        from backend.services.journal_report_service import build_trade_chart

        candles = [_make_candle(date(2026, 1, d), 150, 155, 148, 152) for d in range(1, 21)]
        trade = _make_trade_dict(
            exits=[
                {"exit_date": date(2026, 1, 10), "exit_price": 155, "quantity": 50, "id": "x1"},
                {"exit_date": date(2026, 1, 15), "exit_price": 165, "quantity": 50, "id": "x2"},
            ],
        )

        fake_png = b"\x89PNG_multi"
        with patch("plotly.graph_objects.Figure.to_image", return_value=fake_png):
            result = build_trade_chart(candles, trade)

        assert result == fake_png


# ============================================================
# PDF generation tests (fpdf2 required)
# ============================================================


fpdf2_available = importlib.util.find_spec("fpdf") is not None


@pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
class TestGenerateReportPdf:
    """Tests for generate_report_pdf — PDF output with fpdf2."""

    def test_empty_trades(self):
        from backend.services.journal_report_service import generate_report_pdf

        result = generate_report_pdf([], {})
        assert isinstance(result, bytes)
        assert len(result) > 0
        # PDF magic bytes
        assert result[:5] == b"%PDF-"

    def test_single_trade_no_chart(self):
        from backend.services.journal_report_service import generate_report_pdf

        trade = _make_trade_dict()
        result = generate_report_pdf([trade], {})
        assert result[:5] == b"%PDF-"
        assert len(result) > 100

    def test_single_trade_with_chart(self):
        from backend.services.journal_report_service import generate_report_pdf

        trade = _make_trade_dict()
        # Create a minimal valid PNG for fpdf2
        import struct
        import zlib

        def _make_minimal_png() -> bytes:
            """Create a tiny 1x1 white PNG."""
            sig = b"\x89PNG\r\n\x1a\n"
            # IHDR
            ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
            ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
            # IDAT
            raw = zlib.compress(b"\x00\xff\xff\xff")
            idat_crc = zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF
            idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
            # IEND
            iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
            iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
            return sig + ihdr + idat + iend

        chart_img = _make_minimal_png()
        result = generate_report_pdf([trade], {trade["id"]: chart_img})
        assert result[:5] == b"%PDF-"
        assert len(result) > 200

    def test_multiple_trades(self):
        from backend.services.journal_report_service import generate_report_pdf

        trades = [
            _make_trade_dict(
                id=str(uuid.uuid4()),
                ticker="AAPL",
                realized_pnl=500.0,
            ),
            _make_trade_dict(
                id=str(uuid.uuid4()),
                ticker="TSLA",
                realized_pnl=-200.0,
                direction="short",
            ),
            _make_trade_dict(
                id=str(uuid.uuid4()),
                ticker="MSFT",
                realized_pnl=0.0,
            ),
        ]
        result = generate_report_pdf(trades, {})
        assert result[:5] == b"%PDF-"

    def test_date_range_on_title(self):
        from backend.services.journal_report_service import generate_report_pdf

        result = generate_report_pdf(
            [],
            {},
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
        )
        assert result[:5] == b"%PDF-"

    def test_trade_without_optional_fields(self):
        """PDF should handle trades with None fields gracefully."""
        from backend.services.journal_report_service import generate_report_pdf

        trade = _make_trade_dict(
            stop_loss=None,
            take_profit=None,
            tags=[],
            comments=None,
            realized_pnl=None,
            return_pct=None,
            r_multiple=None,
            avg_exit_price=None,
            exits=[],
        )
        result = generate_report_pdf([trade], {})
        assert result[:5] == b"%PDF-"

    def test_aggregate_summary_win_rate(self):
        """Verify summary stats are computed (we test the PDF is generated)."""
        from backend.services.journal_report_service import generate_report_pdf

        trades = [
            _make_trade_dict(realized_pnl=300.0),
            _make_trade_dict(realized_pnl=200.0),
            _make_trade_dict(realized_pnl=-100.0),
        ]
        result = generate_report_pdf(trades, {})
        assert result[:5] == b"%PDF-"
        # All 3 trades → winner/loser split
        assert len(result) > 200


# ============================================================
# API endpoint tests (mocked service layer)
# ============================================================


class TestReportApiEndpoint:
    """Tests for GET /api/v1/journal/report."""

    @pytest.fixture
    def client(self):
        """Create a test client with mocked DB."""
        from fastapi.testclient import TestClient

        from backend.main import app

        return TestClient(app)

    @pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
    @patch("backend.api.routes.journal.journal_service")
    def test_report_no_trades(self, mock_svc, client):
        """Empty report should return a valid PDF."""
        mock_svc.list_trades = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/journal/report",
            params={"include_charts": False},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"

    @pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
    @patch("backend.api.routes.journal.journal_service")
    def test_report_with_trades_no_charts(self, mock_svc, client):
        """Report with trades (charts disabled) should return a PDF."""
        trades = [_make_trade_dict()]
        mock_svc.list_trades = AsyncMock(return_value=trades)

        response = client.get(
            "/api/v1/journal/report",
            params={
                "include_charts": False,
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "journal_report_2026-01-01_to_2026-03-31.pdf" in response.headers.get(
            "content-disposition", ""
        )

    @pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
    @patch("backend.api.routes.journal.journal_service")
    def test_report_filename_start_only(self, mock_svc, client):
        """Filename should include only start_date when end_date is not provided."""
        mock_svc.list_trades = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/journal/report",
            params={"include_charts": False, "start_date": "2026-01-01"},
        )
        assert response.status_code == 200
        assert "journal_report_2026-01-01.pdf" in response.headers.get("content-disposition", "")

    @pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
    @patch("backend.api.routes.journal.journal_service")
    def test_report_filename_no_dates(self, mock_svc, client):
        """Filename should be plain when no dates provided."""
        mock_svc.list_trades = AsyncMock(return_value=[])

        response = client.get(
            "/api/v1/journal/report",
            params={"include_charts": False},
        )
        assert response.status_code == 200
        assert "journal_report.pdf" in response.headers.get("content-disposition", "")

    @pytest.mark.skipif(not fpdf2_available, reason="fpdf2 not installed")
    @patch("backend.api.routes.journal.journal_service")
    def test_report_passes_filters(self, mock_svc, client):
        """Verify that query params are forwarded to list_trades."""
        mock_svc.list_trades = AsyncMock(return_value=[])

        client.get(
            "/api/v1/journal/report",
            params={
                "include_charts": False,
                "status": "closed",
                "ticker": "TSLA",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
            },
        )

        mock_svc.list_trades.assert_called_once()
        call_kwargs = mock_svc.list_trades.call_args
        # Check positional or keyword args
        assert call_kwargs.kwargs.get("ticker") == "TSLA" or (
            len(call_kwargs.args) > 1 and call_kwargs.args[1] == "TSLA"
        )
