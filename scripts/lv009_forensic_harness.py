"""LV-009 read-only forensic measurement harness (no production behavior changes)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SQLTracer:
    def __init__(self):
        self.queries: list[dict] = []
        self.conn_opens = 0

    def wrap(self, database):
        orig_get = database.get_connection
        orig_exec = database.execute_portable_query
        tracer = self

        def get_connection():
            tracer.conn_opens += 1
            return orig_get()

        def execute_portable_query(conn, sql, params=(), **kwargs):
            started = time.perf_counter()
            result = orig_exec(conn, sql, params, **kwargs)
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
            tracer.queries.append(
                {
                    "sql": " ".join(str(sql).split())[:500],
                    "elapsed_ms": elapsed_ms,
                    "params_len": len(params) if params else 0,
                }
            )
            return result

        database.get_connection = get_connection
        database.execute_portable_query = execute_portable_query
        return database


def summarize_queries(queries, label):
    sql_counter = Counter(row["sql"] for row in queries)
    total_sql_ms = round(sum(row["elapsed_ms"] for row in queries), 2)
    return {
        "label": label,
        "total_statements": len(queries),
        "unique_statements": len(sql_counter),
        "repeated_statements": sum(1 for count in sql_counter.values() if count > 1),
        "total_sql_ms": total_sql_ms,
        "avg_sql_ms": round(total_sql_ms / len(queries), 3) if queries else 0.0,
        "top_repeated": [
            {"sql": sql[:220], "count": count}
            for sql, count in sql_counter.most_common(8)
            if count > 1
        ],
        "slowest": sorted(queries, key=lambda row: row["elapsed_ms"], reverse=True)[:5],
    }


def sqlite_table_stats(db_path):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]
    stats = []
    for table in tables:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{table}"')
            rows = int(cur.fetchone()[0])
            stats.append({"table": table, "rows": rows})
        except Exception as exc:
            stats.append({"table": table, "error": str(exc)})
    conn.close()
    stats.sort(key=lambda row: row.get("rows", 0), reverse=True)
    return stats


def run_forensic(company_key="ADMIN-PERFECTO-123"):
    import database

    tracer = SQLTracer()
    database = tracer.wrap(database)

    results = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "backend": database.get_active_db_backend(),
        "has_database_url": bool(os.environ.get("DATABASE_URL") or os.environ.get("EKA_DATABASE_URL")),
        "company_key": company_key,
    }

    db_path = os.path.join(ROOT, "data", "eka_enterprise_v3.db")
    results["sqlite_table_stats_top20"] = sqlite_table_stats(db_path)[:20]

    from financials import _cached_financial_reports_bundle, get_ledger_balances

    _cached_financial_reports_bundle.clear()
    started = time.perf_counter()
    bundle = _cached_financial_reports_bundle(
        company_key,
        "none",
        datetime.now().date().isoformat(),
        "none",
        "none",
        database.get_active_db_backend(),
    )
    fr_wall_ms = round((time.perf_counter() - started) * 1000.0, 2)
    fr_queries = list(tracer.queries)
    fr_conns = tracer.conn_opens
    tracer.queries.clear()
    tracer.conn_opens = 0

    from modules import _cached_dashboard_analytics_bundle

    _cached_dashboard_analytics_bundle.clear()
    started = time.perf_counter()
    _cached_dashboard_analytics_bundle(company_key, "none", "30d")
    dash_wall_ms = round((time.perf_counter() - started) * 1000.0, 2)
    dash_queries = list(tracer.queries)
    dash_conns = tracer.conn_opens
    tracer.queries.clear()
    tracer.conn_opens = 0

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT login_key FROM users WHERE company_key = ? LIMIT 1", (company_key,))
    row = cur.fetchone()
    auth_key = row[0] if row else ""
    started = time.perf_counter()
    auth_queries_before = len(tracer.queries)
    if auth_key:
        database.execute_portable_query(
            conn,
            "SELECT key, name, COALESCE(status, 'Active') FROM companies WHERE key = ?",
            (auth_key,),
        ).fetchone()
        database.execute_portable_query(
            conn,
            """
            SELECT b.branch_id, b.company_key, b.branch_name, b.branch_access_key, c.name
            FROM branches b
            JOIN companies c ON c.key = b.company_key
            WHERE b.branch_access_key = ?
              AND COALESCE(c.status, 'Active') = 'Active'
            LIMIT 1
            """,
            (auth_key,),
        ).fetchone()
        user_login = database.execute_portable_query(
            conn,
            """
            SELECT u.company_key, c.name, u.role, u.full_name, u.branch_id
            FROM users u
            JOIN companies c ON c.key = u.company_key
            WHERE u.login_key = ?
              AND COALESCE(u.status, 'Active') = 'Active'
              AND COALESCE(c.status, 'Active') = 'Active'
            """,
            (auth_key,),
        ).fetchone()
        auth_matched = bool(user_login)
    else:
        auth_matched = False
    auth_wall_ms = round((time.perf_counter() - started) * 1000.0, 2)
    auth_queries = tracer.queries[auth_queries_before:]
    tracer.queries.clear()
    tracer.conn_opens = 0

    started = time.perf_counter()
    ledger_balances = get_ledger_balances(company_key, end_date=datetime.now().date())
    lb_wall_ms = round((time.perf_counter() - started) * 1000.0, 2)
    lb_queries = list(tracer.queries)

    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM journal_entries WHERE company_key = ?", (company_key,))
    journal_entries = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM journal_lines jl
        JOIN journal_entries je ON je.id = jl.entry_id
        WHERE je.company_key = ?
        """,
        (company_key,),
    )
    journal_lines = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM customers WHERE company_key = ?", (company_key,))
    customers = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM suppliers WHERE company_key = ?", (company_key,))
    suppliers = int(cur.fetchone()[0])
    conn.close()

    results["company_scale"] = {
        "journal_entries": journal_entries,
        "journal_lines": journal_lines,
        "customers": customers,
        "suppliers": suppliers,
    }
    results["financial_reports"] = {
        **summarize_queries(fr_queries, "financial_reports"),
        "wall_ms": fr_wall_ms,
        "connections": fr_conns,
        "pipeline_timings": bundle.get("pipeline_timings"),
    }
    results["dashboard"] = {
        **summarize_queries(dash_queries, "dashboard"),
        "wall_ms": dash_wall_ms,
        "connections": dash_conns,
    }
    results["authentication"] = {
        **summarize_queries(auth_queries, "authentication"),
        "wall_ms": auth_wall_ms,
        "matched": auth_matched,
    }
    results["ledger_balances"] = {
        **summarize_queries(lb_queries, "ledger_balances"),
        "wall_ms": lb_wall_ms,
        "account_count": len(ledger_balances),
    }
    results["connection_stats"] = database.get_lv008_connection_stats()
    return results


def main():
    company_key = os.environ.get("LV009_COMPANY_KEY", "ADMIN-PERFECTO-123")
    print(json.dumps(run_forensic(company_key), indent=2))


if __name__ == "__main__":
    main()
