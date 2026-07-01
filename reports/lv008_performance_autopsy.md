# LV-008 Performance Autopsy — Ranked Root-Cause Report

**Generated:** 2026-07-03  
**Evidence sources:** LV-007 live measurements, code-path audit, SQLite harness (`scripts/lv008_performance_autopsy.py`), PostgreSQL query timing hooks (`record_postgres_query_timing`), LV-003 hot-path recorder.

---

## Verified Live Baseline (pre-LV-008 fixes)

| Surface | Measured | Source |
|---|---|---|
| Canonical startup | ~0.5 ms | LV-007 live |
| System Health (fast) | ~337 ms | LV-007 live |
| Login | ~1.9 s | LV-007 live |
| Financial Reports | ~64 s | LV-007 live |
| Dashboard | >3 s (target miss) | LV-007 live symptom |
| Later navigation | Much faster | Session + Streamlit cache warm |

---

## PART B — Ranked Bottlenecks

### Top Functions (by measured + structural evidence)

| Rank | Function / Stage | Est. share | Evidence |
|---|---|---|---|
| 1 | `get_ar_aging_report` + `get_ap_aging_report` (dashboard) | 25–45% of dashboard | Per-customer/per-supplier N+1 SQL loops (`accounting_engine.py`) |
| 2 | `get_connection` → `_open_postgres_connection` (no pool) | 20–35% cold paths | New TCP+SSL per call; `NullPool` in SQLAlchemy engine |
| 3 | `get_ledger_balances` ×2 (financial reports) | 15–30% of reports | Two full journal GROUP BY scans per cache miss |
| 4 | `app.main()` Streamlit rerun shell | 10–20% every interaction | Full Python rerun per widget event |
| 5 | Dashboard chart/DataFrame construction | 5–12% | 10+ `pd.DataFrame` transforms + `st.line_chart`/`st.bar_chart` |
| 6 | `get_finance_integrity_diagnostics` (pre-LV-007) | Was on hot path | Deferred in LV-007 |
| 7 | `validate_postgres_runtime_enabled` | <1% per call | Already TTL-cached 30s |
| 8 | `information_schema` via `db_table_exists` | 2–5% when uncached | Per-call unless column cache hit |
| 9 | `run_process_startup_warmup` | Cold only, <100ms after LV-007 | Process cache |
| 10 | Authentication `authenticate_access_key_read_path` | 5–10% of login | Single conn; acceptable |

### Top SQL Patterns

| Rank | Query pattern | Calls per page | Evidence |
|---|---|---|---|
| 1 | AR aging: invoices + payment subqueries per customer | O(customers) | `get_ar_aging_report` loop |
| 2 | AP aging: bills + payment subqueries per supplier | O(suppliers) | `get_ap_aging_report` loop |
| 3 | Ledger balances GROUP BY (cumulative) | 1 per reports cache miss | `financials.get_ledger_balances` |
| 4 | Ledger balances GROUP BY (period) | 1 per reports cache miss | same |
| 5 | Dashboard POS aggregates (30-day windows) | 3 per dashboard cache miss | `_fetch_dashboard_sales_analytics` |
| 6 | Dashboard KPI inventory scan | 2 per dashboard cache miss | `_fetch_dashboard_kpi_snapshot` |
| 7 | `SELECT 1` connection ping | 1 per new PG connection | `build_fast_runtime_ping` / connect |
| 8 | `information_schema.tables` | sporadic | `db_table_exists` |
| 9 | Depreciation schedule full table read | 1 per reports bundle | `get_depreciation_schedule` |
| 10 | Recent journal activity LIMIT 10 | 1 per dashboard | `get_recent_accounting_activity` |

### Cold-start-only operations

- `run_process_startup_warmup()` (first process request)
- `import app` for menu metadata during warmup
- First `st.cache_data` population per session
- First PostgreSQL session connection (TCP+SSL handshake to Supabase)

---

## PART C — Bottleneck Disposition

| Bottleneck | Action | Rationale |
|---|---|---|
| PG connection per `get_connection()` | **CACHE / REUSE** | Session-pinned connection; `close()` no-op on proxy |
| AR/AP on dashboard hot path | **DEFER** | On-demand button + separate 300s cache |
| Duplicate ledger GROUP BY | **CACHE** (LV-007 bundle) | Already combined; session conn reduces overhead |
| Streamlit full rerun | **KEEP** | Framework constraint; mitigate with cache/defer |
| Finance integrity on reports | **DEFER** (LV-007) | Button-triggered only |
| Client LV diagnostics | **REMOVE** (LV-007) | Done |
| N+1 AR/AP algorithm | **REWRITE** (future) | Accounting-path change; deferred pending batch design |

---

## PART E — Architectural Root Cause (mandatory)

### 1. Single biggest contributor

**Repeated PostgreSQL connection acquisition without session reuse**, compounded on dashboard by **AR/AP N+1 aging queries**.

### 2. Primary cause checkboxes

☑ **PostgreSQL/database queries** (ledger GROUP BY, AR/AP N+1)  
☑ **Connection pooling** (absent — `NullPool`, new `psycopg2.connect` per call)  
☑ **Streamlit rerun architecture** (full `main()` each interaction)  
☑ **DataFrame creation/processing** (dashboard charts)  
☑ **Caching strategy** (partial — gaps on AR/AP and connections)  
☑ **Deployment/hosting (Streamlit Cloud)** (network latency on each new PG connection)  
☑ **Multiple causes** — ranked below

### 3. Estimated percentage contribution (remaining latency, post-LV-007)

| Cause | % |
|---|---|
| PostgreSQL queries (ledger + AR/AP N+1) | 30% |
| Connection acquisition (no session reuse) | 25% |
| Streamlit rerun architecture | 20% |
| DataFrame + chart rendering | 12% |
| Network / Streamlit Cloud hosting | 8% |
| Authentication / session setup | 3% |
| Other (metadata, misc) | 2% |

### 4. Moving off Streamlit Cloud (same code + PostgreSQL)

**Expected improvement: 10–20%** on warm paths, **up to 30%** on cold paths.  
Connection reuse (LV-008) removes most per-request TLS handshake cost; hosting change alone does not fix N+1 SQL or rerun model.

### 5. Fundamentally architectural?

**YES** — synchronous Streamlit rerun + per-call database connections + monolithic page functions that bundle unrelated query phases (dashboard AR/AP inside main analytics bundle).

### 6. Single component >20%?

**YES — `get_connection()` / `_open_postgres_connection()`** on PostgreSQL before LV-008 session pin.  
**Mitigation:** session-pinned proxy (implemented LV-008).  
**YES — `get_ar_aging_report`/`get_ap_aging_report`** when on dashboard hot path (>20% of dashboard).  
**Mitigation:** deferred on-demand load (implemented LV-008).

### 7. Approaching Streamlit performance limit?

**PARTIALLY** — measured evidence: startup deterministic at ~0.5ms proves backend is fast; 64s reports and 1.9s login implicate page-level query fan-out and connection churn, not Streamlit script overhead alone.

### 8. Five highest-impact changes remaining

| # | Change | Gain | Complexity | Risk | Priority |
|---|---|---|---|---|---|
| 1 | Session PG connection reuse | 20–30% | Medium | Low | **P0** (LV-008) |
| 2 | Defer AR/AP dashboard aging | 25–40% dashboard | Low | Low | **P0** (LV-008) |
| 3 | Batch AR/AP aging SQL (single query) | 30–50% when loaded | High | Medium | P1 |
| 4 | Materialized/reporting views for ledger balances | 40–60% reports | High | Medium | P1 |
| 5 | API layer outside Streamlit for reports | 50–70% reports | High | High | P2 |

### 9. Final architect recommendation

**B + C** — Continue targeted optimization (**session connection reuse**, **defer N+1 phases**) **and** plan migration of Financial Reports aggregation to a non-Streamlit worker or materialized SQL view. Current architecture is acceptable for admin/ops after LV-008 on warm paths; not acceptable for 64s reports at enterprise scale without query redesign (P1/P2).

---

## LV-008 Implemented Fixes

1. **PostgreSQL session connection pin** — `database.get_connection()` reuses one connection per authenticated Streamlit session; logout closes it.
2. **Dashboard AR/AP deferred** — removed from `_cached_dashboard_analytics_bundle`; on-demand button + `_cached_dashboard_receivable_payable_health` (300s TTL).
3. **Autopsy harness** — `scripts/lv008_performance_autopsy.py` + `tests/test_lv008_performance_autopsy.py`.

---

## Remaining (requires live re-measurement)

- Financial Reports <5s — **unverified live** (structural fixes in LV-007 + LV-008 connection reuse should help; ledger GROUP BY may still dominate large tenants).
- Dashboard <3s — **unverified live** (AR/AP defer should help significantly).
- First login <3s — **unverified live** (warmup + session conn should reduce second-phase cost).
