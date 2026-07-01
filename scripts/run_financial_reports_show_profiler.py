"""Run show_financial_reports profiler path without Streamlit UI."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def run_profiler_path(company_key):
    import financials

    financials._begin_show_financial_reports_profiler(company_key)
    profiler = financials._SHOW_FR_PROFILER
    start_date = None
    end_date = datetime.now().date()
    start_key = financials._financial_report_cache_date(start_date)
    end_key = financials._financial_report_cache_date(end_date)
    account_key = "none"
    branch_key = "none"
    backend_key = financials.get_active_db_backend()

    with financials._ShowFinancialReportsProfilerStage(profiler, "filter_controls"):
        pass

    bundle_stage = financials._ShowFinancialReportsProfilerStage(profiler, "reports_bundle_fetch")
    bundle_stage.__enter__()
    try:
        bundle = financials._cached_financial_reports_bundle(
            company_key,
            start_key,
            end_key,
            account_key,
            branch_key,
            backend_key,
        )
        financials._cached_financial_reports_bundle.clear()
        bundle_stage.metadata = {"bundle_pipeline_timings": bundle.get("pipeline_timings") or {}}
        report_defs = [
            ("Trial Balance", bundle["trial_balance"]),
            ("Statement of Profit or Loss", bundle["income_statement"]),
            ("Statement of Financial Position", bundle["balance_sheet"]),
            ("Statement of Cash Flows", bundle["cash_flow"]),
            ("Statement of Changes in Equity", bundle["equity"]),
            ("Depreciation Schedule", bundle["depreciation"]),
        ]
    finally:
        bundle_stage.__exit__(None, None, None)

    with financials._ShowFinancialReportsProfilerStage(profiler, "summary_metrics_render"):
        pass

    with financials._ShowFinancialReportsProfilerStage(profiler, "report_formatting_and_render"):
        for label, df in report_defs:
            tab_started = time.perf_counter()
            format_started = time.perf_counter()
            display_df = financials._ifrs_account_display(financials._convert_money_frame(financials._safe_dataframe(df, [])))
            format_ms = (time.perf_counter() - format_started) * 1000.0
            render_started = time.perf_counter()
            _ = display_df.to_dict(orient="records")
            render_ms = (time.perf_counter() - render_started) * 1000.0
            profiler.record_stage(
                f"report_tab:{label}",
                (time.perf_counter() - tab_started) * 1000.0,
                formatting_ms=round(format_ms, 2),
                rendering_ms=round(render_ms, 2),
                row_count=int(len(display_df)),
            )

    return financials._finalize_show_financial_reports_profiler()


def main():
    company_key = os.environ.get("LV008_COMPANY_KEY", "SYSTEM")
    for key in ("COMPANY_KEY", "EKA_COMPANY_KEY"):
        if os.environ.get(key):
            company_key = os.environ[key]
    report = run_profiler_path(company_key)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
