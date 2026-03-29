"""
PraxiAlpha — Data Validation Page

Streamlit page for manually triggering OHLCV data validation
against TradingView Premium. Compares 20 tickers (10 fixed +
10 random) across all timeframes (daily, weekly, monthly, quarterly).

Shows results in a table with match percentages, mismatch details,
and failure persistence for re-checking on the next run.
"""

from __future__ import annotations

import asyncio
import time

import pandas as pd
import streamlit as st

from backend.services.tv_validation_service import (
    ALL_TIMEFRAMES,
    FIXED_TICKERS,
    TIMEFRAME_BARS,
    TV_AVAILABLE,
    ValidationResult,
    compare_candles,
    compute_summary,
    fetch_our_candles,
    fetch_tv_candles,
    get_retry_tickers_from_failures,
    get_tv_client,
    load_previous_failures,
    sample_random_tickers,
    save_failures,
)

# ============================================================
# Page config
# ============================================================

st.header("🔍 Data Validation")
st.markdown(
    "Compare OHLCV data in PraxiAlpha's database against "
    "**TradingView Premium** — the gold standard for split-adjusted prices."
)

# ============================================================
# Previous failures banner
# ============================================================

prev_failures = load_previous_failures()
if prev_failures:
    n_fail = len(prev_failures.get("failures", []))
    ts = prev_failures.get("timestamp", "unknown")
    st.warning(
        f"⚠️ **Previous run** ({ts}) had **{n_fail} failure(s)**. "
        "Those tickers will be automatically re-checked in this run."
    )
    with st.expander("Show previous failures"):
        fail_df = pd.DataFrame(prev_failures["failures"])
        st.dataframe(fail_df, use_container_width=True, hide_index=True)

# ============================================================
# Ticker info
# ============================================================

with st.expander("ℹ️ What gets validated?"):
    st.markdown(f"""
**20 tickers** across **4 timeframes** = up to **80 comparisons**

**Group A — Fixed (10 split/dividend stress-test tickers):**
{", ".join(f"`{t}`" for t in FIXED_TICKERS)}

**Group B — Random (10 tickers sampled from your DB each run):**
3 NYSE large caps, 3 NASDAQ, 2 AMEX, 2 ETFs — different every run
for broad spot-check coverage across your 23K+ ticker universe.

**Timeframes:** Daily ({TIMEFRAME_BARS["daily"]} bars), Weekly ({TIMEFRAME_BARS["weekly"]}),
Monthly ({TIMEFRAME_BARS["monthly"]}), Quarterly ({TIMEFRAME_BARS["quarterly"]})

**Tolerances:** Price: 1%, Volume: 5%

*Quarterly data is derived by aggregating TradingView monthly → quarterly in pandas.*
    """)

# ============================================================
# Run validation button
# ============================================================

if not TV_AVAILABLE:
    st.error(
        '❌ **tvdatafeed is not installed.** Install with: `pip install "praxialpha[tv-validate]"`'
    )
    st.stop()


def _run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


if st.button("🚀 Run Validation", type="primary", use_container_width=True):
    results: list[ValidationResult] = []

    # --- Phase 1: Build ticker list ---
    status = st.status("Building ticker list...", expanded=True)

    # Fixed tickers
    all_tickers_with_group: list[tuple[str, str]] = [(t, "fixed") for t in FIXED_TICKERS]

    # Random tickers
    try:
        random_tickers = _run_async(sample_random_tickers(10))
        all_tickers_with_group.extend((t, "random") for t in random_tickers)
        status.write(
            f"✅ Sampled {len(random_tickers)} random tickers: {', '.join(random_tickers)}"
        )
    except Exception as e:
        random_tickers = []
        status.write(f"⚠️ Could not sample random tickers (DB unavailable?): {e}")

    # Retry tickers from previous failures
    retry_pairs = get_retry_tickers_from_failures()
    retry_tickers_set = set()
    for ticker, _tf in retry_pairs:
        # Only add if not already in the ticker list
        if ticker not in {t for t, _ in all_tickers_with_group}:
            retry_tickers_set.add(ticker)
    for t in retry_tickers_set:
        all_tickers_with_group.append((t, "retry"))

    if retry_pairs:
        status.write(f"🔄 Re-checking {len(retry_pairs)} previously failed combination(s)")

    # Build the full job list: (ticker, timeframe, group)
    jobs: list[tuple[str, str, str]] = []
    existing_tickers = {t for t, _ in all_tickers_with_group}

    for ticker, group in all_tickers_with_group:
        for tf in ALL_TIMEFRAMES:
            jobs.append((ticker, tf, group))

    # Also add specific retry pairs that might be for tickers already in the list
    # but we want to make sure those specific timeframes are marked as retry
    retry_set = {(t, tf) for t, tf in retry_pairs}

    total_jobs = len(jobs)
    status.write(
        f"📋 Total: {len(set(t for t, _, _ in jobs))} tickers × {len(ALL_TIMEFRAMES)} timeframes = {total_jobs} checks"
    )
    status.update(label="Connecting to TradingView...", state="running")

    # --- Phase 2: Connect to TradingView ---
    try:
        tv = get_tv_client()
        status.write("✅ Connected to TradingView")
    except Exception as e:
        status.update(label="Connection failed", state="error")
        st.error(f"❌ Could not connect to TradingView: {e}")
        st.stop()

    # --- Phase 3: Run comparisons ---
    status.update(label="Running validation...", state="running")
    progress_bar = st.progress(0, text="Starting...")

    for idx, (ticker, tf, group) in enumerate(jobs):
        progress_pct = (idx + 1) / total_jobs
        progress_bar.progress(progress_pct, text=f"[{idx + 1}/{total_jobs}] {ticker} ({tf})...")

        try:
            # Fetch our data
            our_df = _run_async(fetch_our_candles(ticker, tf, TIMEFRAME_BARS.get(tf, 252)))

            if our_df is None or our_df.empty:
                results.append(
                    ValidationResult(
                        ticker=ticker,
                        timeframe=tf,
                        our_bar_count=0,
                        tv_bar_count=0,
                        overlapping_bars=0,
                        group=group,
                        error="No data in our DB",
                    )
                )
                continue

            # Fetch TV data
            tv_df = fetch_tv_candles(tv, ticker, tf, TIMEFRAME_BARS.get(tf, 252))

            if tv_df is None or tv_df.empty:
                results.append(
                    ValidationResult(
                        ticker=ticker,
                        timeframe=tf,
                        our_bar_count=len(our_df),
                        tv_bar_count=0,
                        overlapping_bars=0,
                        group=group,
                        error="Not found on TradingView",
                    )
                )
                continue

            # Compare
            result = compare_candles(ticker, tf, our_df, tv_df, group=group)
            results.append(result)

        except Exception as e:
            results.append(
                ValidationResult(
                    ticker=ticker,
                    timeframe=tf,
                    our_bar_count=0,
                    tv_bar_count=0,
                    overlapping_bars=0,
                    group=group,
                    error=str(e),
                )
            )

        # Rate limit (skip on last item)
        if idx < total_jobs - 1:
            time.sleep(1.5)

    progress_bar.progress(1.0, text="✅ Validation complete!")
    status.update(label="Validation complete!", state="complete")

    # --- Phase 4: Save failures ---
    save_failures(results, random_tickers)

    # --- Phase 5: Display results ---
    st.divider()

    # Summary metrics
    summary = compute_summary(results)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Checks", summary["total_combinations"])
    col2.metric("✅ Passed", summary["passed"])
    col3.metric("⚠️ Mismatches", summary["failed"])
    col4.metric("Overall Match", f"{summary['overall_match_pct']:.1f}%")

    if summary["errors"] > 0:
        st.warning(
            f"❗ {summary['errors']} check(s) had errors (ticker not found, TV unavailable, etc.)"
        )

    if summary["failed"] == 0 and summary["errors"] == 0:
        st.success("🎉 **All data matches TradingView within tolerance!**")
    elif summary["failed"] > 0:
        st.warning(
            f"⚠️ **{summary['total_mismatches']} field mismatch(es)** found across "
            f"{summary['failed']} ticker/timeframe combination(s). "
            "Failures have been saved and will be re-checked next run."
        )

    # Results table
    st.subheader("📊 Results")

    table_data = []
    for r in results:
        table_data.append(
            {
                "Status": r.status,
                "Ticker": r.ticker,
                "Group": r.group.title(),
                "Timeframe": r.timeframe.title(),
                "Our Bars": r.our_bar_count,
                "TV Bars": r.tv_bar_count,
                "Overlap": r.overlapping_bars,
                "Match %": f"{r.match_pct:.1f}%" if not r.error else "—",
                "Mismatches": r.mismatch_count if not r.error else "—",
                "Worst Diff": r.worst_diff if not r.error else r.error,
            }
        )

    results_df = pd.DataFrame(table_data)
    st.dataframe(
        results_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(width="small"),
            "Match %": st.column_config.TextColumn(width="small"),
        },
    )

    # Detailed mismatches (expandable)
    mismatched_results = [r for r in results if r.mismatch_count > 0]
    if mismatched_results:
        st.subheader("🔎 Mismatch Details")
        for r in mismatched_results:
            with st.expander(f"{r.ticker} / {r.timeframe} — {r.mismatch_count} mismatch(es)"):
                mismatch_data = []
                for m in sorted(r.mismatches, key=lambda x: abs(x.pct_diff), reverse=True):
                    if m.is_significant:
                        mismatch_data.append(
                            {
                                "Date": m.date,
                                "Field": m.field,
                                "Our Value": f"{m.our_value:.4f}",
                                "TV Value": f"{m.tv_value:.4f}",
                                "Diff %": f"{m.pct_diff:+.2f}%",
                            }
                        )
                if mismatch_data:
                    st.dataframe(
                        pd.DataFrame(mismatch_data),
                        use_container_width=True,
                        hide_index=True,
                    )

    # CSV download
    if results:
        csv_rows = []
        for r in results:
            if r.mismatches:
                for m in r.mismatches:
                    csv_rows.append(
                        {
                            "ticker": m.ticker,
                            "timeframe": m.timeframe,
                            "date": m.date,
                            "field": m.field,
                            "our_value": m.our_value,
                            "tv_value": m.tv_value,
                            "pct_diff": m.pct_diff,
                            "significant": m.is_significant,
                            "group": r.group,
                        }
                    )
            else:
                csv_rows.append(
                    {
                        "ticker": r.ticker,
                        "timeframe": r.timeframe,
                        "date": "—",
                        "field": "ALL OK" if not r.error else "ERROR",
                        "our_value": r.our_bar_count,
                        "tv_value": r.tv_bar_count,
                        "pct_diff": 0,
                        "significant": False,
                        "group": r.group,
                    }
                )

        csv_df = pd.DataFrame(csv_rows)
        st.download_button(
            "📥 Download Full Report (CSV)",
            csv_df.to_csv(index=False),
            file_name="tv_validation_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
