"""LV-008 offline performance autopsy harness (measurement only)."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _timed(label, fn, timings):
    started = time.perf_counter()
    result = fn()
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    timings.append({"label": label, "elapsed_ms": elapsed_ms})
    return result, elapsed_ms


def run_lv008_autopsy(*, company_key="SYSTEM", iterations=1):
    """Measure hot-path timings using the active runtime backend."""
    import database
    from financials import _cached_financial_reports_bundle

    database.clear_lv008_connection_stats()
    database.clear_postgres_query_timings()
    timings = []
    repeated = Counter()

    def _record(label, elapsed_ms):
        timings.append({"label": label, "elapsed_ms": elapsed_ms})
        repeated[label] += 1

    startup, startup_ms = _timed("startup.run_canonical_startup_pipeline", database.run_canonical_startup_pipeline, timings)
    _record("startup.run_canonical_startup_pipeline", startup_ms)

    for index in range(max(1, int(iterations))):
        label = f"financial_reports.bundle_iter_{index + 1}"
        started = time.perf_counter()
        try:
            bundle = _cached_financial_reports_bundle(
                company_key,
                "none",
                datetime.now().date().isoformat(),
                "none",
                "none",
                database.get_active_db_backend(),
            )
            _cached_financial_reports_bundle.clear()
            pipeline = bundle.get("pipeline_timings") or {}
            for stage, stage_ms in pipeline.items():
                if stage.endswith("_ms") or stage in {"total_ms", "slowest_elapsed_ms"}:
                    timings.append({"label": f"financial_reports.{stage}", "elapsed_ms": float(stage_ms or 0.0)})
        except Exception as exc:
            timings.append({"label": label, "elapsed_ms": 0.0, "error": str(exc)})
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        _record(label, elapsed_ms)

    conn_stats = database.get_lv008_connection_stats()
    postgres_queries = database.get_postgres_query_timings(limit=25)

    ranked_functions = sorted(timings, key=lambda row: row.get("elapsed_ms", 0.0), reverse=True)
    ranked_sql = sorted(postgres_queries, key=lambda row: row.get("elapsed_ms", 0.0), reverse=True)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "backend": database.get_active_db_backend(),
        "startup_ok": bool(startup.get("startup_ok")),
        "startup_elapsed_ms": startup.get("elapsed_ms"),
        "connection_stats": conn_stats,
        "top_functions": ranked_functions[:25],
        "top_sql": ranked_sql[:25],
        "repeated_functions": repeated.most_common(25),
        "financial_pipeline_slowest": (bundle.get("pipeline_timings") or {}).get("slowest_stage")
        if "bundle" in locals()
        else None,
    }


def main():
    report = run_lv008_autopsy()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
