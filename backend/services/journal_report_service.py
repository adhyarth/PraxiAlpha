"""
PraxiAlpha — Trading Journal PDF Report Service

Generates PDF reports for the trading journal:
- Query closed trades by date range
- Build annotated Plotly candlestick charts per trade (entry/exit markers,
  stop-loss/take-profit lines)
- Export to PDF with trade summary table + embedded charts

Dependencies: fpdf2 (PDF generation), kaleido (Plotly → static image).
Both are optional — guarded by importlib checks so CI can run without them.
"""

from __future__ import annotations

import io
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fpdf import FPDF

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lookback periods for chart context around a trade
# ---------------------------------------------------------------------------

_TIMEFRAME_LOOKBACK_DAYS: dict[str, int] = {
    "daily": 365,  # 1 year of daily candles
    "weekly": 730,  # 2 years of weekly candles
    "monthly": 1825,  # 5 years of monthly candles
    "quarterly": 3650,  # 10 years of quarterly candles
}


# ---------------------------------------------------------------------------
# Chart builder — annotated candlestick for a single trade
# ---------------------------------------------------------------------------


def build_trade_chart(
    candles: list[dict[str, Any]],
    trade: dict[str, Any],
    *,
    width: int = 900,
    height: int = 500,
) -> bytes | None:
    """
    Build a Plotly candlestick chart annotated with trade markers.

    Returns PNG image bytes, or None if plotly/kaleido is unavailable.

    Annotations:
    - Green triangle-up marker at entry date/price
    - Red triangle-down marker(s) at each exit date/price
    - Dashed green line for stop-loss level
    - Dashed blue line for take-profit level
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError:
        logger.warning("plotly not available — skipping chart generation")
        return None

    if not candles:
        return None

    dates = [c["date"] for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    fig = go.Figure()

    # Candlestick trace
    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        )
    )

    # Entry marker
    fig.add_trace(
        go.Scatter(
            x=[trade["entry_date"]],
            y=[trade["entry_price"]],
            mode="markers",
            marker=dict(symbol="triangle-up", size=14, color="#00e676"),
            name=f"Entry ${trade['entry_price']:.2f}",
        )
    )

    # Exit markers
    for exit_ in trade.get("exits", []):
        fig.add_trace(
            go.Scatter(
                x=[exit_["exit_date"]],
                y=[exit_["exit_price"]],
                mode="markers",
                marker=dict(symbol="triangle-down", size=14, color="#ff1744"),
                name=f"Exit ${exit_['exit_price']:.2f}",
            )
        )

    # Stop-loss line
    if trade.get("stop_loss") is not None:
        fig.add_hline(
            y=trade["stop_loss"],
            line_dash="dash",
            line_color="#ff9800",
            line_width=1,
            annotation_text=f"SL ${trade['stop_loss']:.2f}",
            annotation_position="top right",
        )

    # Take-profit line
    if trade.get("take_profit") is not None:
        fig.add_hline(
            y=trade["take_profit"],
            line_dash="dash",
            line_color="#2196f3",
            line_width=1,
            annotation_text=f"TP ${trade['take_profit']:.2f}",
            annotation_position="top right",
        )

    # Layout
    direction_label = trade["direction"].upper()
    status_label = trade.get("status", "unknown").upper()
    fig.update_layout(
        title=f"{trade['ticker']} — {direction_label} ({trade['timeframe']}) — {status_label}",
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        width=width,
        height=height,
        margin=dict(l=60, r=30, t=50, b=40),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    # Export to PNG bytes
    try:
        img_bytes: bytes = fig.to_image(format="png", engine="kaleido")
        return img_bytes
    except Exception:
        logger.warning("kaleido export failed — skipping chart image", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Trade summary helpers
# ---------------------------------------------------------------------------


def format_pnl(value: float | None) -> str:
    """Format a PnL value with sign and 2 decimal places."""
    if value is None:
        return "N/A"
    if value >= 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def format_pct(value: float | None) -> str:
    """Format a percentage value with sign and 2 decimal places."""
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def get_lookback_start(trade: dict[str, Any]) -> date:
    """
    Calculate the chart lookback start date based on trade timeframe.

    Returns a date that provides enough context to see the trade
    in the context of the broader trend.
    """
    timeframe = trade.get("timeframe", "daily")
    lookback_days = _TIMEFRAME_LOOKBACK_DAYS.get(timeframe, 365)
    entry = trade["entry_date"]
    if isinstance(entry, str):
        entry = date.fromisoformat(entry)
    result: date = entry - timedelta(days=lookback_days)
    return result


def get_chart_end_date(trade: dict[str, Any]) -> date:
    """
    Calculate the chart end date — includes some space after the last exit.

    For closed trades, extends 30 days past the last exit.
    For open trades, uses today.
    """
    exits = trade.get("exits", [])
    if exits:
        last_exit_date = max(
            date.fromisoformat(e["exit_date"])
            if isinstance(e["exit_date"], str)
            else e["exit_date"]
            for e in exits
        )
        return last_exit_date + timedelta(days=30)
    return date.today()


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------


def generate_report_pdf(
    trades: list[dict[str, Any]],
    chart_images: dict[str, bytes],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> bytes:
    """
    Generate a PDF report with trade summaries and embedded charts.

    Args:
        trades: List of serialized trade dicts (from journal_service).
        chart_images: Mapping of trade_id → PNG image bytes.
        start_date: Report period start (for the title page).
        end_date: Report period end (for the title page).

    Returns:
        PDF file as bytes.
    """
    from fpdf import FPDF  # noqa: PLC0415

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    # ---- Title page ----
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, "PraxiAlpha", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 16)
    pdf.cell(0, 10, "Trading Journal Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    # Date range
    pdf.set_font("Helvetica", "", 12)
    if start_date and end_date:
        pdf.cell(
            0,
            8,
            f"Period: {start_date.isoformat()} to {end_date.isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )
    elif start_date:
        pdf.cell(
            0,
            8,
            f"From: {start_date.isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )
    elif end_date:
        pdf.cell(
            0,
            8,
            f"Up to: {end_date.isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
            align="C",
        )

    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(
        0,
        8,
        f"Total trades: {len(trades)}",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )

    # ---- Aggregate summary ----
    _add_aggregate_summary(pdf, trades)

    # ---- Per-trade pages ----
    for trade in trades:
        _add_trade_page(pdf, trade, chart_images.get(trade["id"]))

    return bytes(pdf.output())


def _add_aggregate_summary(pdf: FPDF, trades: list[dict[str, Any]]) -> None:
    """Add an aggregate summary section to the PDF."""
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "Summary", new_x="LMARGIN", new_y="NEXT")

    if not trades:
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, "No trades in the selected period.", new_x="LMARGIN", new_y="NEXT")
        return

    # Compute aggregates
    total_pnl = sum(t.get("realized_pnl", 0) or 0 for t in trades)
    winners = [t for t in trades if (t.get("realized_pnl") or 0) > 0]
    losers = [t for t in trades if (t.get("realized_pnl") or 0) < 0]
    breakeven = [t for t in trades if (t.get("realized_pnl") or 0) == 0]
    win_rate = (len(winners) / len(trades) * 100) if trades else 0

    avg_win = sum(t.get("realized_pnl", 0) or 0 for t in winners) / len(winners) if winners else 0
    avg_loss = sum(t.get("realized_pnl", 0) or 0 for t in losers) / len(losers) if losers else 0

    # Profit factor
    gross_profit = sum(t.get("realized_pnl", 0) or 0 for t in winners)
    gross_loss = abs(sum(t.get("realized_pnl", 0) or 0 for t in losers))
    profit_factor = (
        (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
    )

    # Summary table
    pdf.set_font("Helvetica", "", 10)
    summary_rows = [
        ("Total P&L", format_pnl(total_pnl)),
        ("Win Rate", f"{win_rate:.1f}%"),
        ("Winners / Losers / Breakeven", f"{len(winners)} / {len(losers)} / {len(breakeven)}"),
        ("Avg Winner", format_pnl(avg_win)),
        ("Avg Loser", format_pnl(avg_loss)),
        ("Profit Factor", f"{profit_factor:.2f}" if profit_factor != float("inf") else "Inf"),
    ]

    col_w1 = 80
    col_w2 = 80
    for label, value in summary_rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(col_w1, 7, label, border=1)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(col_w2, 7, value, border=1, new_x="LMARGIN", new_y="NEXT")


def _add_trade_page(
    pdf: FPDF,
    trade: dict[str, Any],
    chart_img: bytes | None,
) -> None:
    """Add a page for a single trade with details and chart."""
    pdf.add_page()

    # Trade header
    direction_label = trade["direction"].upper()
    status_label = trade.get("status", "unknown").upper()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        f"{trade['ticker']} - {direction_label} ({trade['timeframe']})",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Status: {status_label}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Trade details table
    detail_rows = [
        ("Entry Date", str(trade.get("entry_date", ""))),
        ("Entry Price", f"${trade['entry_price']:.2f}"),
        ("Quantity", f"{trade['total_quantity']:.4g}"),
        ("Stop Loss", f"${trade['stop_loss']:.2f}" if trade.get("stop_loss") else "-"),
        ("Take Profit", f"${trade['take_profit']:.2f}" if trade.get("take_profit") else "-"),
        ("Realized P&L", format_pnl(trade.get("realized_pnl"))),
        ("Return %", format_pct(trade.get("return_pct"))),
        (
            "R-Multiple",
            f"{trade['r_multiple']:.2f}" if trade.get("r_multiple") is not None else "-",
        ),
        (
            "Avg Exit Price",
            f"${trade['avg_exit_price']:.2f}" if trade.get("avg_exit_price") else "-",
        ),
    ]

    col_w1 = 55
    col_w2 = 65
    pdf.set_font("Helvetica", "", 9)
    for label, value in detail_rows:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_w1, 6, label, border=1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_w2, 6, value, border=1, new_x="LMARGIN", new_y="NEXT")

    # Exits
    exits = trade.get("exits", [])
    if exits:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Exits", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for i, exit_ in enumerate(exits, 1):
            pdf.cell(
                0,
                6,
                f"  {i}. {exit_['exit_date']} - "
                f"{exit_['quantity']:.4g} @ ${exit_['exit_price']:.2f}",
                new_x="LMARGIN",
                new_y="NEXT",
            )

    # Tags and comments
    tags = trade.get("tags", [])
    if tags:
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 6, f"Tags: {', '.join(tags)}", new_x="LMARGIN", new_y="NEXT")

    comments = trade.get("comments")
    if comments:
        pdf.ln(2)
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, f"Notes: {comments}")

    # Chart image
    if chart_img:
        pdf.ln(5)
        # Write image bytes to a temporary buffer for fpdf2
        img_stream = io.BytesIO(chart_img)
        img_stream.name = "chart.png"
        # Fit to page width minus margins
        available_width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.image(img_stream, w=available_width)
