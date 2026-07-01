# LV-009 — Complete Performance Forensic Audit

**Generated:** 2026-07-01  
**Mode:** Read-only investigation — **no production code modified**  
**Evidence sources:** Production live observations (LV-007), LV-008 profiler, `scripts/lv009_forensic_harness.py`, `scripts/run_financial_reports_show_profiler.py`, static code-path audit, `reports/lv009_forensic_measurements.json`

---

## Evidence Classification Key

| Tag | Meaning |
|-----|---------|
| **LIVE** | User-reported production measurement |
| **MEASURED** | Executed in this workspace (SQLite backend, 29 journal entries / company) |
| **STRUCTURAL** | Static code audit — call counts, SQL text, cache decorators |
| **REQUIRES-PG** | Needs production PostgreSQL + `EXPLAIN (ANALYZE, BUFFERS)` — not available in workspace (`has_database_url: false`) |

---

## Root Cause Summary

**The application is not uniformly slow.** Startup and System Health fast paths are now within target. Remaining pain is **concentrated in Financial Reports (~64s LIVE)** and **first-interaction cold paths** (first login after restart, first page load).

**Single biggest contributor (production Financial Reports cold load):**  
**`get_ledger_balances()` — full `journal_lines` → `journal_entries` → `chart_of_accounts` GROUP BY aggregation**, executed as part of eager `_cached_financial_reports_bundle()` on every cache miss, with a **second identical scan** when date filters include a start date.

**Why local measurement disagrees with production (64s vs ~100ms):**  
Local harness uses **SQLite with 29 journal entries / 64 lines** (`MEASURED`). Production uses **PostgreSQL over network** with **orders-of-magnitude more ledger data** (`REQUIRES-PG`). The same SQL template that takes **0.3–0.5ms MEASURED** scales linearly (or worse with seq scans) on large `journal_lines` tables.

**Secondary contributors (ranked):**
1. **Eager computation of all 6 financial statements** on page open (STRUCTURAL — confirmed in `show_financial_reports`)
2. **Eager rendering of all 6 tabs** including formatting + CSV byte preparation (STRUCTURAL)
3. **PostgreSQL connection cold handshake** on first authenticated interaction (STRUCTURAL + LIVE first-login symptom)
4. **Dashboard query fan-out** (25 SQL statements MEASURED per cache miss; gross-profit via separate `generate_income_statement` connection STRUCTURAL)
5. **Streamlit full-script rerun** on every interaction (STRUCTURAL — framework constraint)
6. **POS multi-connection cold load** (6 connections STRUCTURAL)

---

## Q1 — Contributor Ranking (Estimated Share)

**Scope:** Remaining user-visible latency after LV-007 fixes, weighted toward **Financial Reports cold load (~64s LIVE)** as the dominant complaint.

| Contributor | Estimated Share | Evidence |
|-------------|----------------:|----------|
| PostgreSQL queries (ledger GROUP BY, dashboard fan-out, POS) | **52%** | LIVE 64s reports; STRUCTURAL `get_ledger_balances` ×2; MEASURED dashboard 25 SQL / cache miss |
| Connection management (TCP+SSL, session pin misses, ephemeral opens) | **14%** | LIVE first-login slower; STRUCTURAL `NullPool`, `get_ledger_balances` always `get_connection()`+`close()`; LV-008 session pin only when Streamlit session exists |
| Python processing (report bundle formatters, KPI transforms) | **10%** | MEASURED equity_format 34ms / 65% of bundle on tiny data; STRUCTURAL all 6 reports computed eagerly |
| Streamlit reruns (full `main()` + page shell) | **8%** | LIVE login ~2s with MEASURED auth SQL 0.34ms — shell dominates |
| DataFrame rendering (`st.dataframe`, chart prep) | **5%** | MEASURED report_formatting_and_render 34ms / 34% of 101ms total (tiny data) |
| Charts (`st.bar_chart`, `st.line_chart`) | **3%** | STRUCTURAL dashboard 3 charts; not on Financial Reports hot path |
| Authentication SQL | **1%** | MEASURED 3 queries, 0.34ms total SQL |
| Startup pipeline | **<1%** | LIVE ~0.5ms |
| Network latency (browser ↔ Streamlit Cloud ↔ Supabase) | **5%** | LIVE warm paths faster; inferred from PG round-trip on each query phase |
| Streamlit Cloud hosting (cold worker, CPU throttle) | **2%** | LIVE first-after-restart slower; no isolated measurement |
| Other (sidebar currency/branch, audit log on login, metadata) | **2%** | STRUCTURAL `app._render_primary_sidebar` per rerun |

**Total ≈ 100%**

---

## Q2 — Primary Bottleneck Category

**Answer: Multiple causes — dominated by PostgreSQL query cost on Financial Reports, amplified by architecture (eager compute + Streamlit rerun).**

| Category | Verdict | Why |
|----------|---------|-----|
| PostgreSQL | **Primary** | LIVE 64s on reports; ledger GROUP BY is the only stage that can reach tens of seconds at journal scale |
| Python | Secondary | MEASURED formatters significant only at small scale; not 64s-class alone |
| Streamlit | Secondary | LIVE login 2s vs MEASURED auth 0.44ms wall — rerun/render shell matters but not 64s |
| Rendering | Tertiary | MEASURED 34ms formatting on tiny dataset; scales with tab count (6 tabs always rendered) |
| Network | Contributing | PG hosted remotely; each query phase adds RTT |
| Hosting | Minor alone | LIVE cold-start symptom; startup itself is fast |

---

## Q3 — SQL Query Counts Per Page

### Methodology
- **MEASURED:** `scripts/lv009_forensic_harness.py` with SQL interception (`execute_portable_query` wrapper), cache cleared, company `ADMIN-PERFECTO-123`
- **STRUCTURAL:** Static audit for POS and System Health (Streamlit session required for full page simulation)

### Dashboard

| Metric | MEASURED (cache miss) | STRUCTURAL (full page + branch caption) |
|--------|----------------------:|----------------------------------------:|
| Total SQL statements | **25** | **26–27** |
| Unique SQL statements | **21** | **22** |
| Repeated SQL statements | **2** patterns | **4** (`sqlite_master` table checks) |
| Total SQL time | **2.69 ms** | N/A on PG |
| Average SQL time | **0.108 ms** | N/A on PG |
| `get_connection()` calls | **2** | **3** (branch name + bundle + `generate_income_statement`) |

### Financial Reports

| Metric | MEASURED (bundle cache miss) | STRUCTURAL (full `show_financial_reports`) |
|--------|-----------------------------:|-------------------------------------------:|
| Total SQL statements | **2** | **2–3** (+ integrity if button clicked) |
| Unique SQL statements | **2** | **2–3** |
| Repeated SQL statements | **0** (no start date) / **1** ledger template ×2 (with start date) | Same |
| Total SQL time | **0.64 ms** | N/A on PG |
| Average SQL time | **0.32 ms** | N/A on PG |
| `get_connection()` calls | **2** | **2–3** |

### POS

| Metric | STRUCTURAL (cold load, empty cart) |
|--------|-----------------------------------:|
| Total SQL statements | **~18–24** (schema checks + bootstrap + 4 side panels) |
| Unique SQL statements | **~14–18** |
| Repeated SQL statements | **4+** (`ensure_pos_sales_schema`, `ensure_cashier_closings_schema`) |
| Total SQL time | **REQUIRES-PG** |
| Average SQL time | **REQUIRES-PG** |
| `get_connection()` calls | **6** |

### System Health (fast path)

| Metric | LIVE | STRUCTURAL |
|--------|------|------------|
| Wall time | **337 ms** | — |
| Total SQL statements | **REQUIRES-PG** | **3–4** (deployment cache hit) / **8+** (cache miss) |
| Unique SQL statements | — | **6–8** |
| Repeated SQL statements | — | **2** (`COUNT companies`, company key probe) |
| Total SQL time | — | **REQUIRES-PG** |
| `get_connection()` calls | — | **3–4** |

---

## Q4 — SQL Executed More Than Once

### Dashboard (MEASURED)

| SQL (abbreviated) | Call Count | Caller | Reason | Can Merge? |
|-------------------|----------:|--------|--------|------------|
| `SELECT name FROM sqlite_master WHERE type='table' AND name=?` | **4** | `db_table_exists` via KPI/sales/inventory helpers | Per-feature table existence check | **YES** — session/process cache |
| Ledger balance by account pattern (AR/AP/cash) | **2** | `_dashboard_branch_ledger_balance` | Separate KPI queries | **YES** — single grouped query |

### Financial Reports (STRUCTURAL — when start_date set)

| SQL | Call Count | Caller | Reason | Can Merge? |
|-----|----------:|--------|--------|------------|
| `get_ledger_balances` GROUP BY journal | **2** | `_cached_financial_reports_bundle` cumulative + period | Period slice needs separate date filter | **PARTIAL** — window functions or materialized balances |
| Depreciation `fixed_assets` SELECT | **1** | bundle | — | — |

### POS (STRUCTURAL)

| SQL | Call Count | Caller | Reason | Can Merge? |
|-----|----------:|--------|--------|------------|
| `ensure_pos_sales_schema` / DDL checks | **4+** | bootstrap, suspended, recent tx, receipts | Each `get_connection()` block | **YES** — once per page conn |
| `pos_sales` recent list | **2** | recent receipts + reprint fallback | Separate UI sections | **YES** — shared query |

### System Health (STRUCTURAL)

| SQL | Call Count | Caller | Reason | Can Merge? |
|-----|----------:|--------|--------|------------|
| `SELECT key FROM companies ... LIMIT 1` | **2** | deployment diagnostics outer + inner | Cache miss path duplication | **YES** |
| `COUNT(*) FROM companies` | **2** | health snapshot + deployment | Overlapping probes | **YES** |

---

## Q5 — Slowest SQL Query

### MEASURED (SQLite, 29 journals — **not production representative**)

| Field | Value |
|-------|-------|
| **SQL** | `get_ledger_balances` GROUP BY on `journal_lines`/`journal_entries`/`chart_of_accounts` |
| **Elapsed** | **0.53 ms** (bundle), **0.34 ms** (direct) |
| **Rows** | **10** accounts |
| **Calls** | **1–2** per reports cache miss |
| **Execution plan** | N/A (SQLite) |
| **Index usage** | SQLite auto-index on small tables |
| **Recommendation** | **REQUIRES-PG** `EXPLAIN (ANALYZE, BUFFERS)` on production |

### STRUCTURAL (production inference — **must verify on PG**)

| Field | Value |
|-------|-------|
| **SQL** | Same `get_ledger_balances` template |
| **Elapsed** | **Estimated 40–55s of 64s LIVE** (majority stage) |
| **Rows** | All posted journal lines for company through end_date |
| **Calls** | 1–2 |
| **Execution plan** | **REQUIRES-PG** — expect `HashAggregate` or `Seq Scan` on `journal_lines` if stats/indexes suboptimal |
| **Index usage** | `idx_journal_entries_reporting (company_key, approval_status, is_voided, date)` exists in schema; **no dedicated `journal_lines(company_key)`** — filter applied via join |
| **Recommendation** | Run `EXPLAIN`; consider composite index `(company_key, date)` on `journal_entries` + covering strategy; materialized trial balance |

---

## Q6 — Largest Database Tables

### MEASURED (SQLite dev database)

| Table | Rows | Size | Indexes | Last ANALYZE | Last VACUUM |
|-------|-----:|------|---------|--------------|-------------|
| system_logs | 127 | ~N/A | audit indexes | N/A (SQLite) | N/A |
| audit_logs | 112 | ~N/A | yes | N/A | N/A |
| journal_lines | 66 | ~N/A | entry_id, account_id | N/A | N/A |
| journal_entries | 30 | ~N/A | reporting, source, customer, supplier | N/A | N/A |
| chart_of_accounts | 38 | ~N/A | parent, active | N/A | N/A |

### REQUIRES-PG (production)

Run on production:
```sql
SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid)),
       last_analyze, last_vacuum, last_autovacuum
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 20;
```

**Expected production leaders:** `journal_lines`, `journal_entries`, `audit_logs`, `pos_sale_lines`, `invoices`, `payments`.

---

## Q7 — Missing Indexes?

| Slow Query | Current Indexes (from `database.py` schema) | Potentially Missing | Est. Improvement |
|------------|---------------------------------------------|---------------------|------------------|
| `get_ledger_balances` | `idx_journal_entries_reporting`, `journal_lines(entry_id)`, `journal_lines(account_id)` | `(company_key, id)` on entries for join selectivity; partial index `WHERE is_voided=0 AND approval_status='Posted'` | **30–60%** on large ledgers **REQUIRES-PG verify** |
| AR aging per-customer loop | `idx_invoices_company_status`, `idx_payments_company_status` | Batch CTE index not applicable — algorithm is N+1 | Rewrite > index |
| Dashboard POS 30-day aggregates | pos_sales indexes (if present) | `(company_key, sale_date)` composite | **10–25%** dashboard |
| `db_table_exists` | — | Not SQL — cache metadata | **2–5%** dashboard |

---

## Q8 — PostgreSQL Scan Types

**REQUIRES-PG** — no production `EXPLAIN` output in workspace.

**STRUCTURAL expectation for `get_ledger_balances` at scale:**

| Scan Type | Expected Occurrence |
|-----------|---------------------|
| Sequential Scan | Possible on `journal_lines` if planner estimates full table read cheaper |
| Index Scan | Likely on `journal_entries` via `company_key` filter |
| Bitmap Scan | Possible hybrid on entries date range |
| Parallel Scan | Possible on large aggregates (PG 11+) |
| Hash Aggregate | **Highly likely** for GROUP BY account |

---

## Q9 — GROUP BY Delays

| Metric | MEASURED (SQLite) | REQUIRES-PG |
|--------|-------------------|-------------|
| Hash Aggregate | N/A | Expected primary node |
| Sort | ORDER BY account_code after aggregate | Minor vs aggregate |
| Disk spill | No | Possible at millions of lines |
| Memory | Trivial | `work_mem` bound |
| Elapsed | **0.3–0.5 ms** | **Estimated 40–55s** of 64s LIVE |

---

## Q10 — ORDER BY Disk Sort

**REQUIRES-PG.** ORDER BY on ~hundreds of accounts post-aggregate is unlikely to dominate; verify in `EXPLAIN`.

---

## Q11 — PostgreSQL Statistics Staleness

**REQUIRES-PG.** Workspace has no PostgreSQL connection.

**Checklist for production:**
- [ ] `last_analyze` on `journal_lines`, `journal_entries`
- [ ] `n_dead_tup` / bloat
- [ ] `autovacuum` running

---

## Q12 — Connection Pooling

| Metric | MEASURED | STRUCTURAL |
|--------|----------|------------|
| Pooling model | N/A (SQLite) | **No pool** — `NullPool` SQLAlchemy engine; `psycopg2.connect` per ephemeral open |
| Session pin (LV-008) | `reuses: 0` in harness | `_get_postgres_session_connection()` when Streamlit session + user exists |
| Opens / Reuses / Closes | 0 / 0 / 0 (SQLite harness) | Track via `get_lv008_connection_stats()` in live session |
| Pool hits / misses | N/A | Session reuses increment `reuses`; new pins increment `session_pins` |

**Verdict:** Connection pooling is **partially working** via session pin (LV-008), **not** traditional pool. Functions that call `conn.close()` on proxy get no-op close but still invoke `get_connection()` each time.

---

## Q13 — New Connection Per Page?

| Page | MEASURED | STRUCTURAL (authenticated PG session) |
|------|----------|---------------------------------------|
| Dashboard | 2 conns (bundle uses 1; scale query adds 1) | **1 session reuse** if pinned; 3 opens on cache miss without sharing |
| Financial Reports | 2 | **2–3** `get_connection()` calls; **same session conn reused** via proxy |
| POS | Not measured | **6 separate** `get_connection()` blocks |
| Settings | Not measured | **1+** per settings interaction |
| Authentication | 1 (login button) | **1** new session pin on first post-login `get_connection()` |

**Every page does NOT create a new TCP connection** after session pin — but **every `get_connection()` call still runs validation path**.

---

## Q14 — Unnecessary Streamlit Reruns

| Function | Execution Count | Necessary? | Reason |
|----------|----------------:|------------|--------|
| `app.main()` | Every widget event | **Partial** | Framework requirement |
| `run_process_startup_warmup()` | Every rerun, **cached after 1st** | **Yes** (cached) | Process cache hit |
| `get_session_canonical_startup_result()` | Every rerun | **Yes** (cached) | Session cache |
| `_render_primary_sidebar()` | Every authenticated rerun | **Partial** | Branch list + currency SQL every rerun |
| `show_financial_reports()` full bundle | Every reports page rerun | **No** on cache hit within 60s | `st.cache_data` helps; filter change misses |
| `_cached_financial_reports_bundle()` | Cache miss only | **Yes** on miss | — |
| All 6 report tab renders | Every reports rerun | **No** | Tabs not visible still formatted |
| `generate_income_statement()` in dashboard KPI | Dashboard cache miss | **Partial** | Could derive from same ledger scan |
| POS historical panel SQL | Every POS rerun | **No** | Inside collapsed expander |

---

## Q15 — Caches That Never Hit

| Cache | Hits | Misses | Reason |
|-------|------|--------|--------|
| `_cached_financial_reports_bundle` | Warm within 60s TTL | **Every filter change**; **every cold session** | Key includes dates/branch/backend |
| `_cached_dashboard_analytics_bundle` | Warm 120s | **Daily period key** changes; branch change | `period_key = strftime today` |
| `_PROCESS_WARMUP_CACHE` | After 1st process request | First request after deploy/restart | By design |
| `_cached_trial_balance_report` etc. | **Never on reports page** | Always | **Dead code path** — bundle used directly |
| `lv003_page_access:*` session | After first page check | First navigation per page | By design |
| `diagnostics_ttl_cache` | Admin panels | Client pages | LV-007 removed client diagnostics |

---

## Q16 — Caches That Invalidate Too Often

| Cache | Invalidation Reason | Frequency |
|-------|---------------------|-----------|
| `_cached_dashboard_analytics_bundle` | `period_key` = current date string | **Daily** automatic miss |
| `_cached_financial_reports_bundle` | `end_key` = today when default end date used | **Daily** |
| `st.cache_data.clear()` | Logout / admin cache clear flag | Session end |
| `validate_postgres_runtime_enabled` TTL 30s | Time-based | Every 30s on validation path |

---

## Q17 — DataFrames Recreated Repeatedly

| DataFrame | Creation Count | Rows (MEASURED) | Caller |
|-----------|---------------:|----------------:|--------|
| `trial_balance_df` | Every reports rerun | 10 | bundle → tabs |
| `income_statement_df` | Every reports rerun | 6 | bundle → tabs |
| `balance_sheet_df` | Every reports rerun | 7 | bundle → tabs |
| `cash_flow_df` | Every reports rerun | 7 | bundle → tabs |
| `equity_df` | Every reports rerun | 5 | bundle → tabs |
| `depreciation_df` | Every reports rerun | 0 | bundle → tabs |
| `display_df` per tab | **6× per rerun** | same | `_convert_money_frame` + `_ifrs_account_display` |
| `daily_sales_df`, `top_items_df`, `payment_df` | Dashboard rerun | varies | `show_dashboard` |
| AR/AP aging frames | On button only (LV-007) | — | deferred |

---

## Q18 — Rendering Cost (MEASURED — offline profiler, no Streamlit server)

| Widget / Phase | Time (ms) | Notes |
|----------------|----------:|-------|
| `_convert_money_frame` + `_ifrs_account_display` (formatting) | **11.8** TB tab; **~32** total all tabs | Dominates rendering path |
| `to_dict(orient="records")` proxy for `st.dataframe` | **2.5** TB tab; **~6** total | Underestimates real Streamlit widget |
| `st.dataframe()` actual | **REQUIRES live** | Not measured in harness |
| `st.table()` | Not on hot path | — |
| `st.bar_chart()` / `st.line_chart()` | Not in reports profiler | Dashboard only |
| Plotly | Not on Financial Reports path | — |
| CSV `to_csv().encode()` via `_csv_button` | **STRUCTURAL** — 6 buttons per page | Prepared on render, not on click |

---

## Q19 — Financial Reports: What Is Computed on Open?

| Report | Computed on Open? | Evidence |
|--------|-------------------|----------|
| Trial Balance | **YES** | `_cached_financial_reports_bundle` |
| Income Statement | **YES** | `_income_statement_from_balances` |
| Balance Sheet | **YES** | `_balance_sheet_from_trial_balance` |
| Cash Flow | **YES** | `_cash_flow_from_reports` |
| Equity | **YES** | `_equity_from_reports` |
| Depreciation | **YES** | `get_depreciation_schedule` |
| Analytics | **NO** | Not on this page |
| Finance Integrity | **NO** | Button-triggered only (LV-007) |
| Consolidated (Master Admin) | **Only if toggled** | Separate path |

---

## Q20 — Exports Before User Clicks?

| Format | Pre-generated? | When | Necessary? |
|--------|----------------|------|------------|
| CSV | **YES** | Each tab render — `dataframe.to_csv().encode()` in `_csv_button` | **NO** — lazy on click preferred |
| Excel | **NO** | — | — |
| PDF | **NO** | — | — |

---

## Q21 — Authentication Measurement

| Metric | MEASURED | LIVE |
|--------|----------|------|
| SQL count | **3** | — |
| SQL elapsed | **0.34 ms** | — |
| Wall time (auth queries only) | **0.44 ms** | — |
| Full login wall | — | **~1.9–2.0 s** |
| Cache usage | None for auth | Session created post-rerun |
| Repeated work | 3 sequential lookups (company → branch → user) | Worst-case 3 queries even when user login would suffice on first hit |

**Login 2s breakdown (inferred from LIVE − MEASURED):** ~**2% SQL**, ~**40% post-login rerun + dashboard shell**, ~**25% first PG session pin + TLS**, ~**20% Streamlit render**, ~**13% network/hosting**.

---

## Q22 — Company Switching Timings

**REQUIRES live session instrumentation.** STRUCTURAL call map:

| Phase | Functions | Expected Cost |
|-------|-----------|---------------|
| Company lookup | `companies` SELECT | Low |
| Permissions | `require_permission`, `lv003_page_access` cache miss | Low–medium |
| Currency | `_render_currency_sidebar_controls` → `system_settings` | Low |
| Settings | `system_settings` read/write | Low |
| Tax | module-specific | Medium |
| Branch | `branches` SELECT + session update | Low |

**Not measured in this audit** — recommend LV-003 hot-path recorder on company switch.

---

## Q23 — Functions That Should NEVER Run During Normal Navigation

| Function | Reason | Current Caller |
|----------|--------|----------------|
| `get_finance_integrity_diagnostics` | Heavy reconciliation | Only on button (fixed LV-007) |
| `run_canonical_startup_pipeline` | Startup only | Cached after warmup |
| `get_ar_aging_report` / `get_ap_aging_report` | N+1 | Deferred button (LV-007) — **must not regress** |
| `render_runtime_admin_diagnostics_suite` | Dev-only | Dev pages only (LV-007) |
| `_cached_trial_balance_report` (orphan) | Dead duplicate | Unused — should not invoke |
| `import app` inside warmup | Cold cost | `run_process_startup_warmup` once/process |
| POS `_render_pos_historical_sales_control` SQL | Hidden panel | Every POS rerun |

---

## Q24 — Streamlit Cloud Contribution

| Factor | Estimated Share of LIVE Pain | Evidence |
|--------|------------------------------|----------|
| Cold boot (worker spin-up) | **5–10%** first request after sleep | LIVE first-after-restart slower |
| Network (browser ↔ app ↔ DB) | **5–8%** | Remote Supabase + Streamlit Cloud |
| Hosting (CPU/RAM limits) | **2–5%** | Not isolatable |
| Application code | **80–88%** | 64s reports >> plausible network overhead |

**Moving off Streamlit Cloud alone: 10–20%** warm path, **up to 30%** cold path — **will not fix 64s reports**.

---

## Q25 — Can Financial Reports Be Incremental?

| Approach | Feasible? | Recommendation |
|----------|-----------|----------------|
| Reuse Trial Balance | **YES** | Single ledger scan → all statements (already LV-007); extend TTL / persist |
| Cached balances | **YES** | `company_key+branch+as_of_date` balance table, updated on post |
| Materialized summaries | **YES** | PG materialized view refreshed on schedule |
| Lazy per-tab load | **YES** | Highest UX impact — see Q28 |

---

## Q26 — Five Functions to Rewrite

| Function | Reason | Est. Improvement | Complexity | Risk |
|----------|--------|------------------|------------|------|
| `get_ledger_balances` | Full scan per call | **40–60%** reports | Medium | Medium — accounting accuracy |
| `get_ar_aging_report` | N+1 per customer | **30–50%** when loaded | High | Medium |
| `get_ap_aging_report` | N+1 per supplier | **30–50%** when loaded | High | Medium |
| `show_financial_reports` | Eager 6-tab pipeline | **50–70%** perceived | Medium | Low |
| `_cached_dashboard_analytics_bundle` + KPI | 25 SQL, duplicate ledger | **30–40%** dashboard | Medium | Low |

---

## Q27 — Architecture Redesign

| Area | Current | Proposed | Benefit |
|------|---------|----------|---------|
| Reports compute | Streamlit sync Python GROUP BY | PG materialized view + API | Sub-second reports at scale |
| DB connections | Session-pinned psycopg2 | PgBouncer + SQLAlchemy pool | Lower connection latency |
| UI framework | Streamlit monolith | Streamlit shell + FastAPI data layer | Decouple rerun from SQL |
| Caching | `st.cache_data` 60–120s | Redis/process ledger cache keyed by company | Cross-session reuse |
| Dashboard AR/AP | On-demand button | Pre-aggregated aging table | Instant when needed |
| Deploy | Streamlit Cloud | Container + CDN | 10–20% latency |

---

## Q28 — Lazy-Load Financial Reports?

**Current:** Open → bundle (all SQL) → format all → render all 6 tabs.

**Proposed:** Open → shell + Trial Balance tab only → load tab on select → cache per tab.

| Metric | Estimate |
|--------|----------|
| Improvement (first paint) | **60–80%** of 64s → **<5s target achievable** if ledger scan remains |
| Improvement (if ledger scan deferred to TB tab only) | **Additional 20–40%** on initial paint |
| With materialized ledger | **90%+** → sub-second |

---

## Q29 — Materialized Views?

| View | Recommended? | Rationale |
|------|--------------|-----------|
| Trial Balance | **YES — P1** | Directly targets slowest query |
| Income Statement | **YES** — derived from TB | Simple rollup |
| Balance Sheet | **YES** — derived from TB | Simple rollup |
| Cash Flow | **PARTIAL** | Indirect method needs period movement |
| Dashboard KPIs | **YES** | High read frequency |
| AR/AP aging | **YES** | Eliminates N+1 |
| Inventory | **PARTIAL** | POS-driven updates |
| Payroll | **LATER** | Lower traffic |

---

## Q30 — Single File for Maximum Gain

| Field | Value |
|-------|-------|
| **File** | `financials.py` |
| **Why** | Contains `get_ledger_balances`, `_cached_financial_reports_bundle`, `show_financial_reports` — the LIVE 64s path |
| **Est. improvement** | **40–70%** on reports via lazy tabs + conn reuse inside bundle + optional balance cache |
| **Why other files less impactful** | `database.py` connection pin already done (LV-008); `modules.py` dashboard already deferred AR/AP; `app.py` startup already fast |

---

## Q31 — Remaining Bottlenecks (Ordered)

| P | File | Function | Measured Cost | Est. Fix Gain | Complexity | Risk |
|---|------|----------|---------------|---------------|------------|------|
| P0 | `financials.py` | `get_ledger_balances` | **64s LIVE** (PG) | 40–55% | Medium | Medium |
| P0 | `financials.py` | `show_financial_reports` eager 6-tab | STRUCTURAL | 15–25% | Low | Low |
| P1 | `financials.py` | `_cached_financial_reports_bundle` ×2 scan | 2 calls w/ start date | 15–30% | Medium | Low |
| P1 | `accounting_engine.py` | `get_ar_aging_report` | N+1 | 30–50% on load | High | Medium |
| P1 | `modules.py` | `_fetch_dashboard_kpi_snapshot` → `generate_income_statement` | +1 conn + scan | 10–15% dashboard | Low | Low |
| P2 | `modules.py` | `show_pos` 6 connections | STRUCTURAL | 10–20% POS | Medium | Low |
| P2 | `app.py` | `_render_primary_sidebar` per-rerun SQL | STRUCTURAL | 5–10% | Low | Low |
| P2 | `database.py` | True connection pool (PgBouncer) | STRUCTURAL | 10–20% cold | Medium | Medium |
| P3 | `financials.py` | `_csv_button` eager CSV bytes | STRUCTURAL | 2–5% | Low | Low |
| P3 | `modules.py` | POS historical panel always runs | STRUCTURAL | 3–5% POS | Low | Low |

---

## Q32 — Do NOT Optimize (Not the Bottleneck)

| Area | Why |
|------|-----|
| Canonical startup pipeline | LIVE **0.5 ms** — done |
| `validate_postgres_runtime_enabled` | TTL 30s cached |
| System Health fast snapshot | LIVE **337 ms** — acceptable |
| Client LV diagnostics | Removed LV-007 |
| `ensure_schema` on SQLite startup | Not on PG hot path |
| Finance integrity on reports | Already deferred |
| Accounting logic correctness checks | Risk >> reward |
| Removing SQLite/PostgreSQL dual support | Out of scope |
| Weakening cutover/startup safety | Out of scope |

---

## Q33 — Streamlit Architectural Limits

**Yes — partial ceiling exists:**

1. **Full script rerun** on every widget interaction — cannot eliminate without framework change
2. **Synchronous request model** — long SQL blocks entire page
3. **`st.cache_data` is per-process** — cold worker = cold cache
4. **No true lazy tab rendering** — all tab bodies execute even when hidden

**Mitigations that still work:** aggressive caching, defer SQL, session connection pin, move heavy compute off rerun path.

---

## Q34 — Moving Off Streamlit Cloud Alone?

| Scenario | Improvement |
|----------|-------------|
| Same code, dedicated hosting | **10–20%** |
| Cold start reduction | **+5–10%** first request |
| **Will NOT fix** | 64s ledger GROUP BY |

---

## Q35 — Optimizations That Succeeded

| Optimization | Est. Gain | Evidence |
|--------------|-----------|----------|
| Deterministic startup pipeline | Startup **→ 0.5 ms** | LIVE |
| Process warmup `run_process_startup_warmup` | First interaction faster | LIVE first-login pattern |
| Diagnostics off client pages | Removed seconds of JSON/render | LV-007 |
| `_cached_financial_reports_bundle` | 2 scans max vs 6+ | STRUCTURAL |
| Finance integrity deferred | Removed multi-second reports path | LV-007 |
| AR/AP deferred on dashboard | 25–45% dashboard (estimated) | LV-007/008 |
| Session PG connection pin | 20–30% cold PG paths (estimated) | LV-008 |
| System Health fast snapshot | **337 ms** | LIVE |
| `st.cache_data` on dashboard/reports | Warm navigation much faster | LIVE |

---

## Q36 — Optimizations With Little Measurable Gain

| Optimization | Why Low Impact |
|--------------|----------------|
| Orphan `_cached_trial_balance_report` wrappers | Never called from `show_financial_reports` |
| Micro-optimizing Python formatters | **<1s** even at 64s scale |
| More `st.cache_data` without key fix | Daily date keys still miss |
| SQLite-side tuning | Production is PostgreSQL |

---

## Q37 — Financial Reports Timing Tree

### LIVE (production, user-reported)

```
Financial Reports total ≈ 64,000 ms (LIVE)
├── reports_bundle_fetch ≈ 52,000–58,000 ms (81–90%) — INFERRED from LV-008 stage model + LIVE
│   ├── ledger_balances_cumulative_ms ≈ 40,000–50,000 ms — INFERRED dominant PG scan
│   ├── ledger_balances_period_ms ≈ 0–40,000 ms — only if start_date set
│   ├── depreciation_schedule_ms ≈ 500–2,000 ms
│   └── formatters (TB/IS/BS/CF/EQ) ≈ 500–3,000 ms
├── report_formatting_and_render ≈ 4,000–8,000 ms (6–12%)
│   └── 6 tabs × (format + dataframe + CSV prep)
├── ui_styles_header_permission ≈ 200–500 ms
├── summary_metrics_render ≈ 100–300 ms
└── tabs_create ≈ 50–200 ms
```

### MEASURED (SQLite, ADMIN-PERFECTO-123, profiler harness)

```
Financial Reports total = 100.81 ms
├── reports_bundle_fetch = 66.27 ms (65.7%) [1 call]
│   ├── ledger_balances_cumulative_ms = 6.93 ms (10.7% of bundle)
│   ├── ledger_balances_period_ms = 0.0 ms
│   ├── equity_format_ms = 34.15 ms (52.7% of bundle) ← Python at tiny scale
│   ├── depreciation_schedule_ms = 7.22 ms
│   ├── cash_flow_format_ms = 7.58 ms
│   ├── trial_balance_format_ms = 4.61 ms
│   └── other formatters = 5.44 ms
├── report_formatting_and_render = 34.39 ms (34.1%) [6 tabs]
│   ├── Trial Balance tab = 14.33 ms
│   ├── Cash Flow tab = 9.87 ms
│   └── other 4 tabs = 10.19 ms
├── filter_controls = 0.0 ms
└── summary_metrics_render = 0.0 ms

SQL calls: get_ledger_balances ×1 (0.39 ms SQL), get_depreciation_schedule ×1 (1.32 ms SQL)
```

---

## Q38 — Dashboard Timing Tree

### MEASURED (SQLite, cache miss)

```
Dashboard bundle wall = 25.26 ms
├── SQL total = 2.69 ms (25 statements, 21 unique)
│   ├── POS today sales SUM = 0.16 ms (slowest in one run; 75 ms in another run — variance)
│   ├── journal activity fetch = 0.24 ms
│   └── 22 other KPI/sales/inventory queries
├── Python/chart DataFrame prep = ~15–20 ms (estimated remainder)
└── generate_income_statement (STRUCTURAL, separate conn) = not in bundle timer

Full page STRUCTURAL adds:
├── branch_name query = 1 SQL
├── 3× st.line_chart/bar_chart render = REQUIRES live
└── sidebar SQL (app.py) = 2+ per rerun
```

### LIVE

```
Dashboard > 3s target miss (LIVE LV-007)
├── Likely PG dashboard SQL fan-out (25 queries × RTT) — INFERRED
├── First cache miss on _cached_dashboard_analytics_bundle — INFERRED
└── Streamlit chart render — INFERRED
```

---

## Q39 — Login Timing Tree

### LIVE

```
Login total ≈ 1,900–2,000 ms
├── get_connection (first PG session pin) ≈ 400–800 ms — INFERRED
├── authenticate_access_key_read_path ≈ 50–200 ms PG — INFERRED (MEASURED SQL 0.34ms SQLite)
├── log_audit_action ≈ 50–150 ms — INFERRED
├── st.rerun → full main() ≈ 600–900 ms — INFERRED
│   ├── run_process_startup_warmup (cached) ≈ 0 ms
│   ├── get_session_canonical_startup_result ≈ 0 ms cached
│   └── initial dashboard/shell render ≈ 400–700 ms
└── network/browser ≈ 100–300 ms
```

### MEASURED (auth SQL only)

```
Auth SQL wall = 0.44 ms (3 queries, 0.34 ms SQL)
```

---

## Q40 — Top 10 Pre-Launch Changes (Thousands of Companies, Millions of JEs)

| Rank | Change | Perf Impact | Risk | Complexity | Priority |
|------|--------|------------|------|------------|----------|
| 1 | Materialized trial balance / ledger balances per company | **Critical** | Medium | High | **P0** |
| 2 | Lazy-load Financial Reports tabs | **Very High** | Low | Medium | **P0** |
| 3 | Batch AR/AP aging (eliminate N+1) | **High** | Medium | High | **P1** |
| 4 | PgBouncer + connection pool in front of PG | **High** | Medium | Medium | **P1** |
| 5 | `EXPLAIN`-driven indexes on `journal_entries`/`journal_lines` | **High** | Low | Low | **P1** |
| 6 | FastAPI reporting service (off Streamlit rerun) | **Very High** | High | High | **P2** |
| 7 | Redis/process ledger cache (cross-session) | **High** | Medium | Medium | **P1** |
| 8 | Dashboard: single conn + drop duplicate `generate_income_statement` | **Medium** | Low | Low | **P1** |
| 9 | POS: consolidate 6 connections → 1 | **Medium** | Low | Medium | **P2** |
| 10 | Autovacuum/ANALYZE monitoring + bloat alerts | **Medium** (sustained) | Low | Low | **P1** |

---

## Final Recommended Roadmap

### Phase 0 — Verify on Production PG (before any fix)

1. Run `get_financial_reports_show_timing_breakdown()` log line `FINANCIAL_REPORTS_SHOW_TIMING` on production
2. `EXPLAIN (ANALYZE, BUFFERS)` on `get_ledger_balances` SQL
3. `pg_stat_user_tables` for row counts and analyze age
4. `get_lv008_connection_stats()` after Dashboard / Reports / Login

### Phase 1 — Low Risk (target: Reports < 5s)

| # | Action | Est. Improvement |
|---|--------|-----------------|
| 1 | Lazy tab loading in `show_financial_reports` | **50–70%** first paint |
| 2 | Pass shared `conn` through bundle (stop double `get_connection`) | **5–10%** |
| 3 | Lazy CSV generation (on click only) | **2–5%** |
| 4 | Dashboard: derive gross profit from bundle conn | **10–15%** dashboard |

### Phase 2 — Medium Risk (target: Reports < 2s at scale)

| # | Action | Est. Improvement |
|---|--------|-----------------|
| 5 | Composite/partial indexes per EXPLAIN | **20–40%** |
| 6 | Materialized view `mv_trial_balance(company_key, branch_id, as_of_date)` | **60–80%** |
| 7 | Batch AR/AP aging rewrite | **30–50%** when loaded |

### Phase 3 — Architectural (enterprise scale)

| # | Action | Est. Improvement |
|---|--------|-----------------|
| 8 | Reporting worker outside Streamlit | **70–90%** |
| 9 | PgBouncer + dedicated hosting | **15–25%** |
| 10 | Incremental balance maintenance on journal post | **80–95%** reads |

---

## Artifacts Produced (No Production Code Changed)

| Artifact | Path |
|----------|------|
| Forensic harness | `scripts/lv009_forensic_harness.py` |
| Raw measurements JSON | `reports/lv009_forensic_measurements.json` |
| LV-008 profiler harness | `scripts/run_financial_reports_show_profiler.py` |
| This report | `reports/lv009_performance_forensic_audit.md` |

---

## Honest Gaps (Require Production Access)

The following **cannot be answered with measured evidence** until production PostgreSQL instrumentation runs:

- Exact `EXPLAIN` scan types (Q8)
- GROUP BY disk spill metrics (Q9)
- ORDER BY sort method (Q10)
- Statistics staleness / autovacuum (Q11)
- Live connection pool hit rate in Streamlit session (Q12)
- Company switching timings (Q22)
- Production table sizes (Q6 PG rows)
- Exact % split of 64s reports tree (Q37 LIVE nodes)

**No code fixes applied. No commit. No push. No PR.**
