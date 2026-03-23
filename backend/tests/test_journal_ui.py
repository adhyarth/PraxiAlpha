"""
PraxiAlpha — Trading Journal Streamlit UI Tests

Tests for:
- journal_api.py — HTTP client functions (mocked httpx)
- journal_trade_form.py — form rendering helpers
- journal_trade_detail.py — detail view formatting helpers
- journal page routing and view logic

All tests mock httpx and Streamlit — no real backend or browser needed in CI.
"""

import importlib.util
from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# Test: journal_trade_detail.py — formatting helpers
# ===========================================================================


class TestDetailFormatters:
    """Test the formatting helper functions in journal_trade_detail."""

    def test_fmt_pnl_positive(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pnl

        assert _fmt_pnl(1234.56) == "+$1,234.56"

    def test_fmt_pnl_negative(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pnl

        assert _fmt_pnl(-500.0) == "-$500.00"

    def test_fmt_pnl_zero(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pnl

        assert _fmt_pnl(0) == "$0.00"

    def test_fmt_pnl_none(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pnl

        assert _fmt_pnl(None) == "—"

    def test_fmt_pct_positive(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pct

        assert _fmt_pct(12.34) == "+12.34%"

    def test_fmt_pct_negative(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pct

        assert _fmt_pct(-5.67) == "-5.67%"

    def test_fmt_pct_zero(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pct

        assert _fmt_pct(0) == "0.00%"

    def test_fmt_pct_none(self):
        from streamlit_app.components.journal_trade_detail import _fmt_pct

        assert _fmt_pct(None) == "—"

    def test_fmt_price(self):
        from streamlit_app.components.journal_trade_detail import _fmt_price

        assert _fmt_price(150.0) == "$150.00"
        assert _fmt_price(None) == "—"
        assert _fmt_price(1234567.89) == "$1,234,567.89"

    def test_fmt_r_positive(self):
        from streamlit_app.components.journal_trade_detail import _fmt_r

        assert _fmt_r(2.5) == "+2.50R"

    def test_fmt_r_negative(self):
        from streamlit_app.components.journal_trade_detail import _fmt_r

        assert _fmt_r(-1.2) == "-1.20R"

    def test_fmt_r_none(self):
        from streamlit_app.components.journal_trade_detail import _fmt_r

        assert _fmt_r(None) == "—"


# ===========================================================================
# Test: journal_api.py — HTTP client functions
# ===========================================================================


class TestJournalApi:
    """Test the journal API client functions with mocked httpx."""

    def _mock_response(self, status_code: int = 200, json_data: Any = None,
                       content: bytes = b"", headers: dict | None = None):
        """Create a mock httpx response."""
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.content = content
        resp.text = str(json_data)
        resp.headers = headers or {}
        return resp

    @patch("httpx.get")
    def test_list_trades_success(self, mock_get):
        from streamlit_app.components.journal_api import list_trades

        mock_get.return_value = self._mock_response(
            json_data={"count": 1, "trades": [{"id": "abc", "ticker": "AAPL"}]}
        )
        result = list_trades(ticker="AAPL", limit=10)
        assert result is not None
        assert result["count"] == 1
        mock_get.assert_called_once()

    @patch("httpx.get")
    def test_list_trades_with_filters(self, mock_get):
        from streamlit_app.components.journal_api import list_trades

        mock_get.return_value = self._mock_response(
            json_data={"count": 0, "trades": []}
        )
        result = list_trades(
            ticker="TSLA",
            status="closed",
            direction="long",
            timeframe="daily",
            tags="swing,earnings",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1),
        )
        assert result is not None
        # Verify params were passed
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert params["ticker"] == "TSLA"
        assert params["status"] == "closed"

    @patch("httpx.get", side_effect=Exception("connection refused"))
    def test_list_trades_backend_down(self, mock_get):
        from streamlit_app.components.journal_api import list_trades

        result = list_trades()
        assert result is None

    @patch("httpx.get")
    def test_get_trade_success(self, mock_get):
        from streamlit_app.components.journal_api import get_trade

        mock_get.return_value = self._mock_response(
            json_data={"id": "abc", "ticker": "AAPL", "status": "open"}
        )
        result = get_trade("abc")
        assert result is not None
        assert result["ticker"] == "AAPL"

    @patch("httpx.get")
    def test_get_trade_not_found(self, mock_get):
        from streamlit_app.components.journal_api import get_trade

        mock_get.return_value = self._mock_response(status_code=404)
        result = get_trade("nonexistent")
        assert result is None

    @patch("httpx.post")
    def test_create_trade_success(self, mock_post):
        from streamlit_app.components.journal_api import create_trade

        mock_post.return_value = self._mock_response(
            status_code=201,
            json_data={"id": "new-id", "ticker": "AAPL"},
        )
        result = create_trade({"ticker": "AAPL", "direction": "long"})
        assert result is not None
        assert result["id"] == "new-id"

    @patch("httpx.post")
    def test_create_trade_validation_error(self, mock_post):
        from streamlit_app.components.journal_api import create_trade

        mock_post.return_value = self._mock_response(status_code=422)
        result = create_trade({"ticker": ""})
        assert result is None

    @patch("httpx.put")
    def test_update_trade_success(self, mock_put):
        from streamlit_app.components.journal_api import update_trade

        mock_put.return_value = self._mock_response(
            json_data={"id": "abc", "stop_loss": 140.0}
        )
        result = update_trade("abc", {"stop_loss": 140.0})
        assert result is not None

    @patch("httpx.delete")
    def test_delete_trade_success(self, mock_delete):
        from streamlit_app.components.journal_api import delete_trade

        mock_delete.return_value = self._mock_response(status_code=204)
        assert delete_trade("abc") is True

    @patch("httpx.delete")
    def test_delete_trade_not_found(self, mock_delete):
        from streamlit_app.components.journal_api import delete_trade

        mock_delete.return_value = self._mock_response(status_code=404)
        assert delete_trade("nonexistent") is False

    @patch("httpx.post")
    def test_add_exit_success(self, mock_post):
        from streamlit_app.components.journal_api import add_exit

        mock_post.return_value = self._mock_response(
            json_data={"id": "abc", "exits": [{"exit_price": 160.0}]}
        )
        result = add_exit("abc", {"exit_date": "2026-03-01", "exit_price": 160.0, "quantity": 50})
        assert result is not None

    @patch("httpx.post")
    def test_add_leg_success(self, mock_post):
        from streamlit_app.components.journal_api import add_leg

        mock_post.return_value = self._mock_response(
            json_data={"id": "abc", "legs": [{"leg_type": "buy_call"}]}
        )
        result = add_leg("abc", {"leg_type": "buy_call", "strike": 150, "expiry": "2026-06-01",
                                  "quantity": 1, "premium": 5.0})
        assert result is not None

    @patch("httpx.get")
    def test_list_snapshots_success(self, mock_get):
        from streamlit_app.components.journal_api import list_snapshots

        mock_get.return_value = self._mock_response(
            json_data={"count": 2, "snapshots": [{"snapshot_date": "2026-03-01"}]}
        )
        result = list_snapshots("abc")
        assert result is not None
        assert result["count"] == 2

    @patch("httpx.get")
    def test_get_whatif_summary_success(self, mock_get):
        from streamlit_app.components.journal_api import get_whatif_summary

        mock_get.return_value = self._mock_response(
            json_data={"trade_id": "abc", "actual_pnl": 500.0}
        )
        result = get_whatif_summary("abc")
        assert result is not None
        assert result["actual_pnl"] == 500.0

    @patch("httpx.get")
    def test_download_report_success(self, mock_get):
        from streamlit_app.components.journal_api import download_report

        mock_get.return_value = self._mock_response(
            content=b"%PDF-1.4 fake",
            headers={"content-disposition": 'attachment; filename="journal_report_2026-01-01.pdf"'},
        )
        pdf_bytes, filename = download_report(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1),
        )
        assert pdf_bytes == b"%PDF-1.4 fake"
        assert filename == "journal_report_2026-01-01.pdf"

    @patch("httpx.get")
    def test_download_report_no_content_disposition(self, mock_get):
        from streamlit_app.components.journal_api import download_report

        mock_get.return_value = self._mock_response(content=b"%PDF", headers={})
        pdf_bytes, filename = download_report()
        assert pdf_bytes == b"%PDF"
        assert filename == "journal_report.pdf"  # fallback

    @patch("httpx.get")
    def test_download_report_failure(self, mock_get):
        from streamlit_app.components.journal_api import download_report

        mock_get.return_value = self._mock_response(status_code=500)
        pdf_bytes, filename = download_report()
        assert pdf_bytes is None

    @patch("httpx.get", side_effect=Exception("timeout"))
    def test_download_report_network_error(self, mock_get):
        from streamlit_app.components.journal_api import download_report

        pdf_bytes, filename = download_report()
        assert pdf_bytes is None


# ===========================================================================
# Test: journal_api.py — URL construction
# ===========================================================================


class TestJournalApiUrls:
    """Test URL construction in the API client."""

    def test_journal_url_default(self):
        from streamlit_app.components.journal_api import _journal_url

        url = _journal_url("/report")
        assert url.endswith("/api/v1/journal/report")

    def test_journal_url_root(self):
        from streamlit_app.components.journal_api import _journal_url

        url = _journal_url("/")
        assert url.endswith("/api/v1/journal/")

    def test_journal_url_with_trade_id(self):
        from streamlit_app.components.journal_api import _journal_url

        url = _journal_url("/abc-123")
        assert url.endswith("/api/v1/journal/abc-123")


# ===========================================================================
# Test: journal_trade_detail.py — rendering (mocked st calls)
# ===========================================================================


@pytest.fixture()
def _sample_trade() -> dict[str, Any]:
    """Return a sample trade dict for rendering tests."""
    return {
        "id": "test-trade-id",
        "user_id": "default",
        "ticker": "AAPL",
        "direction": "long",
        "asset_type": "shares",
        "trade_type": "single_leg",
        "timeframe": "daily",
        "entry_date": "2026-01-15",
        "entry_price": 150.0,
        "total_quantity": 100.0,
        "stop_loss": 145.0,
        "take_profit": 170.0,
        "tags": ["momentum", "earnings"],
        "comments": "Bullish breakout",
        "status": "partial",
        "remaining_quantity": 50.0,
        "realized_pnl": 500.0,
        "return_pct": 3.33,
        "avg_exit_price": 160.0,
        "r_multiple": 1.0,
        "exits": [
            {
                "id": "exit-1",
                "trade_id": "test-trade-id",
                "exit_date": "2026-02-01",
                "exit_price": 160.0,
                "quantity": 50.0,
                "comments": "Partial take profit",
            }
        ],
        "legs": [],
    }


class TestRenderTradeInfo:
    """Test render_trade_info calls st functions correctly."""

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_renders_header(self, mock_st, _sample_trade):
        from streamlit_app.components.journal_trade_detail import render_trade_info

        render_trade_info(_sample_trade)
        # Verify markdown was called (for header)
        assert mock_st.markdown.called

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_renders_metrics(self, mock_st, _sample_trade):
        from streamlit_app.components.journal_trade_detail import render_trade_info

        # Mock columns
        mock_col = MagicMock()
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)

        render_trade_info(_sample_trade)
        assert mock_st.columns.called


class TestRenderExitsTable:
    """Test the exits table rendering."""

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_renders_exits(self, mock_st, _sample_trade):
        from streamlit_app.components.journal_trade_detail import render_exits_table

        render_exits_table(_sample_trade)
        assert mock_st.dataframe.called

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_no_exits_message(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_exits_table

        render_exits_table({"exits": []})
        mock_st.caption.assert_called_with("No exits recorded yet.")

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_none_exits(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_exits_table

        render_exits_table({"exits": None})
        mock_st.caption.assert_called_with("No exits recorded yet.")


class TestRenderLegsTable:
    """Test the legs table rendering."""

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_no_legs_message(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_legs_table

        render_legs_table({"legs": []})
        mock_st.caption.assert_called_with("No option legs recorded.")

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_renders_legs(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_legs_table

        trade = {
            "legs": [
                {
                    "leg_type": "buy_call",
                    "strike": 150.0,
                    "expiry": "2026-06-01",
                    "quantity": 1.0,
                    "premium": 5.0,
                }
            ]
        }
        render_legs_table(trade)
        assert mock_st.dataframe.called


class TestRenderWhatifSummary:
    """Test the what-if summary rendering."""

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_none_summary(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_whatif_summary

        render_whatif_summary(None)
        mock_st.caption.assert_called()

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_no_snapshots(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_whatif_summary

        render_whatif_summary({"total_snapshots": 0})
        assert mock_st.caption.called

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_with_snapshots(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_whatif_summary

        mock_col = MagicMock()
        mock_st.columns.return_value = [mock_col, mock_col, mock_col]
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)

        summary = {
            "total_snapshots": 5,
            "actual_pnl": 500.0,
            "actual_pnl_pct": 3.33,
            "best_hypothetical": {
                "hypothetical_pnl": 1000.0,
                "hypothetical_pnl_pct": 6.67,
                "snapshot_date": "2026-02-15",
                "close_price": 165.0,
            },
            "worst_hypothetical": {
                "hypothetical_pnl": -200.0,
                "hypothetical_pnl_pct": -1.33,
                "snapshot_date": "2026-02-01",
                "close_price": 148.0,
            },
            "latest_snapshot": {
                "snapshot_date": "2026-02-20",
                "close_price": 162.0,
                "hypothetical_pnl": 800.0,
            },
        }
        render_whatif_summary(summary)
        assert mock_st.columns.called


class TestRenderSnapshotTable:
    """Test the snapshot history table rendering."""

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_none_data(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_snapshot_table

        render_snapshot_table(None)
        mock_st.caption.assert_called_with("Could not load snapshot data.")

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_empty_snapshots(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_snapshot_table

        render_snapshot_table({"snapshots": []})
        mock_st.caption.assert_called_with("No snapshots recorded.")

    @patch("streamlit_app.components.journal_trade_detail.st")
    def test_renders_snapshots(self, mock_st):
        from streamlit_app.components.journal_trade_detail import render_snapshot_table

        render_snapshot_table({
            "snapshots": [
                {
                    "snapshot_date": "2026-03-01",
                    "close_price": 155.0,
                    "hypothetical_pnl": 500.0,
                    "hypothetical_pnl_pct": 3.33,
                }
            ]
        })
        assert mock_st.dataframe.called


# ===========================================================================
# Test: journal page — PnL display helpers
# ===========================================================================


class TestPagePnlHelpers:
    """Test the PnL display helpers in the journal page module."""

    def test_pnl_display_positive(self):
        from streamlit_app.pages.journal import _pnl_display

        assert _pnl_display(1000.0) == "+$1,000.00"

    def test_pnl_display_negative(self):
        from streamlit_app.pages.journal import _pnl_display

        assert _pnl_display(-250.0) == "-$250.00"

    def test_pnl_display_zero(self):
        from streamlit_app.pages.journal import _pnl_display

        assert _pnl_display(0) == "$0.00"

    def test_pnl_display_none(self):
        from streamlit_app.pages.journal import _pnl_display

        assert _pnl_display(None) == "—"

    def test_pct_display_positive(self):
        from streamlit_app.pages.journal import _pct_display

        assert _pct_display(5.5) == "+5.50%"

    def test_pct_display_negative(self):
        from streamlit_app.pages.journal import _pct_display

        assert _pct_display(-2.1) == "-2.10%"

    def test_pct_display_none(self):
        from streamlit_app.pages.journal import _pct_display

        assert _pct_display(None) == "—"


# ===========================================================================
# Test: status badges
# ===========================================================================


class TestStatusBadges:
    """Test the status badge mapping."""

    def test_all_statuses_mapped(self):
        from streamlit_app.pages.journal import _STATUS_BADGES

        assert "open" in _STATUS_BADGES
        assert "partial" in _STATUS_BADGES
        assert "closed" in _STATUS_BADGES

    def test_badges_contain_emoji(self):
        from streamlit_app.pages.journal import _STATUS_BADGES

        for badge in _STATUS_BADGES.values():
            assert len(badge) > 2  # emoji + text
