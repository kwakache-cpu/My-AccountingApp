# Launch Blocker Tracker — Authoritative Register

**Sprint:** Launch Validation Sprint 1  
**Generated at:** 2026-06-28  
**Purpose:** Single authoritative tracker for all launch blockers, live UAT defects, and launch blocking decisions.

**Classification:** This document supersedes scattered blocker lists for **live validation tracking**. Source reports (`final_go_live_blockers.md`, `phase_5b18f_launch_certification_summary.md`) remain historical reference.

---

## Tracker Summary

| Metric | Value |
|---|---|
| Launch validation readiness | **91%** |
| Development certification | **92%** (complete) |
| Live browser UAT execution | **0%** (Sprint 1 in progress) |
| Open launch blockers | **5** |
| Open live defects | **1** (DEF-002 **Open** — LV-007 cold-start warmup + client diagnostics removal + Financial Reports optimization; live timing: first login <3s, dashboard <3s, Financial Reports <5s, no client diagnostics) |
| Last updated | 2026-07-01 |

---

## LV-009 Phase 1 — Financial Reports Lazy Load (2026-07-01)

| Item | Detail |
|---|---|
| Problem | Financial Reports still ~64s LIVE — eager 6-report bundle, eager CSV bytes, repeated connections |
| Fix | Lazy per-report cache `_cached_financial_report_by_type(..., report_type_key)`; shell + summary first; `st.radio` selector (only active report computed); `_lazy_csv_button` (CSV on Export click only); `_fetch_ledger_balance_snapshot` shared connection |
| Cache keys | `company_key`, `branch_key`, `start_date`, `end_date`, `account_key`, `backend_key`, `report_type_key` |
| Preserved | `_cached_financial_reports_bundle()` for legacy/admin/tests; accounting formatters unchanged |
| Targets | Financial Reports first paint **<5s** LIVE (DEF-002 remains **Open** until confirmed) |
| Evidence | `tests/test_lv009_phase1_financial_reports_speed.py`, `reports/lv009_performance_forensic_audit.md` |

---

## LV-008 Performance Autopsy (2026-07-03)

| Item | Detail |
|---|---|
| Report | `reports/lv008_performance_autopsy.md` |
| Harness | `scripts/lv008_performance_autopsy.py` |
| Root cause | PG connection churn (no session reuse) + dashboard AR/AP N+1 aging |
| Fixes | Session-pinned PG connection; AR/AP deferred on dashboard |
| Evidence | `tests/test_lv008_performance_autopsy.py` |

---

## Severity Definitions

| Severity | Definition |
|---|---|
| **Critical** | Data loss, accounting integrity failure, security breach, or unrecoverable production failure |
| **High** | Major workflow broken, permission escalation, or missing capability required for approved launch scope |
| **Medium** | Degraded workflow, workaround exists, or limited pilot impact |
| **Low** | Cosmetic, documentation, or non-blocking operational gap |

---

## Status Definitions

| Status | Definition |
|---|---|
| **Open** | Not started or under investigation |
| **Fixed** | Code or configuration change applied; pending live verification |
| **Verified** | Fix confirmed in live browser or operational rehearsal |

---

## Launch Blocker Register

| ID | Severity | Title | Module | Role | Owner | Status | Launch blocking decision | Evidence | Screenshot |
|---|---|---|---|---|---|---|---|---|---|
| BL-01 | Critical | Live Firebase backup/restore not rehearsed | Backup / Restore | Operator | __________ | Open | **BLOCKS LAUNCH** for unrestricted go-live; recommended before first-customer launch | `backup_restore_rehearsal_steps.md` | |
| BL-02 | Critical | Supabase/Postgres backup SOP not rehearsed | Database / Backup | Operator | __________ | Open | **BLOCKS LAUNCH** if Postgres is production backend | `deployment_secrets_checklist.md` | |
| BL-03 | High | Browser UAT incomplete for all 10 production roles | Permissions / UAT | All roles | __________ | Open | **BLOCKS LAUNCH** for unrestricted go-live | `live_browser_uat_sprint_1.md` | |
| BL-04 | High | Finance VAT/NHIL statutory report sign-off not obtained | Financial Reports | Finance Owner | __________ | Open | **BLOCKS LAUNCH** for tax-compliant statutory go-live | `final_accounting_signoff.md` | |
| BL-05 | High | External monitoring and alerting not configured | Operations | Technical Owner | __________ | Open | **BLOCKS LAUNCH** for 24/7 SLA production | `first_24_hour_monitoring_checklist.md` | |
| BL-06 | High | Production-size performance not measured | Performance | Technical Owner | __________ | Open | **BLOCKS LAUNCH** for high-volume tenants only | `erp_performance_certification.md` | |
| DNL-01 | Medium | Admin cloud restore requires explicit recovery mode | Backup / Restore | System Admin | __________ | Open | **DOES NOT BLOCK LAUNCH** — runbook exists | `production_rollback_checklist.md` | |
| DNL-02 | Low | Local file restore API has no admin UI | Backup / Restore | Operator | __________ | Open | **DOES NOT BLOCK LAUNCH** — documented API path | `production_rollback_checklist.md` | |
| DNL-03 | Medium | Developer role retains superuser permissions | Permissions | Developer | __________ | Open | **DOES NOT BLOCK LAUNCH** if Dev credentials restricted | `final_security_review.md` | |
| PLI-01 | Medium | Fixed asset multi-period depreciation edge cases | Assets | Accountant | __________ | Open | **POST-LAUNCH IMPROVEMENT** | `final_go_live_blockers.md` | |
| PLI-02 | Medium | Production-size report timing not captured | Financial Reports | Operator | __________ | Open | **POST-LAUNCH IMPROVEMENT** | `erp_performance_certification.md` | |

---

## Live Defect Register (Sprint 1)

Use `reports/live_defect_intake_template.md` for new entries. Copy verified rows here.

| Defect ID | Severity | Module | Role | Title | Owner | Status | Launch blocking decision | Evidence | Screenshot |
|---|---|---|---|---|---|---|---|---|---|
| DEF-001 | High | Dashboard / Financial Reports | Owner / CEO | Slow login load; empty dashboard charts; empty financial reports despite posted journals | Technical Owner | Fixed | **DOES NOT BLOCK LAUNCH** until live retest verified | Root cause: (1) PostgreSQL `date()` filter mismatch returned empty ledger/report rows; (2) Trial Balance incorrectly applied period `start_date` to cumulative balances; (3) Dashboard charts were POS-only with no journal fallback; (4) Dashboard deferred heavy legacy/journal compare to expander. Evidence: `tests/test_live_defect_lv001_dashboard_reports.py`; LV-001 diagnostics expander on Dashboard and Financial Reports | |
| DEF-002 | High | System Health / PostgreSQL Runtime / Client UX | Dev / System Admin / All roles | App slow on first login after restart; LV diagnostics visible on client pages; Financial Reports ~64s | Technical Owner | **Open** | **DOES NOT BLOCK LAUNCH** until live retest confirms first login <3s, dashboard <3s, Financial Reports <5s, no diagnostics on client pages | LV-002–006 improved caching/fast paths. **LV-007**: process warmup, client diagnostics removal, unified bundle cache. **LV-009 Phase 1**: lazy per-report fetch (`report_type` cache key), lazy CSV export, shared ledger connection in bundle path. **Open** until live timing confirmed. Evidence: `tests/test_lv007_performance_and_client_visibility.py`, `tests/test_lv009_phase1_financial_reports_speed.py`, `tests/test_lv00*.py` | |
| DEF-003 | | | | | | Open | | | |
| DEF-004 | Critical | Startup / PostgreSQL Cutover | Dev / System Admin | Streamlit Cloud PostgreSQL selected but startup blocked at `postgres_runtime_cutover_guard`; error referenced SQLite `/data/eka_enterprise_v3.db` | Technical Owner | **Fixed** (pending live retest) | **BLOCKS LAUNCH** until Streamlit Cloud confirms PostgreSQL startup | **LV-004**: Root cause — `startup_database()` required cutover evidence report files before allowing postgres runtime, failing even when runtime config + connection were valid; error UI showed SQLite DB path. Fix: route `postgres_runtime` validates runtime config + connection probe only; skips SQLite file startup/recovery; cutover evidence remains advisory; admin startup diagnostics added. Evidence: `tests/test_lv004_streamlit_postgres_cutover_startup.py` | |

---

## LV-007 Cold-Start Warmup + Client Diagnostics Removal + Financial Reports (2026-07-03)

| Item | Detail |
|---|---|
| Problem | First client request after restart still slow; LV diagnostics leaked to Dashboard/Financial Reports/POS; Financial Reports ~64s |
| Cold-start fix | `run_process_startup_warmup()` once per process — backend config, canonical startup, PG connection, role/menu/permissions metadata, fast health snapshot |
| Skipped warmup | cloud backup, Firebase, subscription billing, SQLite recovery/health, migration/schema scans, financial reports, full health audit |
| Client diagnostics | Removed from all business workflow pages; retained only in Dev Gatekeeper, System Health, System Administration |
| Financial Reports | `_cached_financial_reports_bundle()` — single cumulative + period ledger fetch; cache key `(company_key, branch_id, start_date, end_date, backend)` TTL 60s; integrity check on demand only |
| Admin panel | LV-007 Warmup Diagnostics + **Run startup warmup now** (admin only) |
| Targets | first login <3s, dashboard <3s, Financial Reports <5s, zero LV panels on client pages |
| Evidence | `tests/test_lv007_performance_and_client_visibility.py` |

---

## LV-006 Startup Pipeline Consolidation (2026-07-02)

| Item | Detail |
|---|---|
| Problem | Fragmented startup guards/diagnostics; repeated work on every Streamlit rerun |
| Fix | `run_canonical_startup_pipeline()` — single config load, route resolve, validate, execute; session-cached |
| Fast health | Cached startup result + `build_fast_runtime_ping()` only; no cloud/subscription/migration scans |
| Targets | login <3s, dashboard <5s, system health <3s (after first load) |
| Before (live, pre-LV-006) | login ~1.5–2.1s; system health ~7s fast snapshot; fragmented guards per rerun |
| After (expected) | startup once/session; fast health uses cached startup + ping only; no cloud/SQLite scans on hot path |
| Admin panel | LV-006 Startup Pipeline (Dev/Master Admin/System Admin only) |

---

## LV-004 Streamlit Cloud PostgreSQL Cutover Startup (2026-07-02)

| Item | Detail |
|---|---|
| Symptom | `Stage: postgres_runtime_cutover_guard` with SQLite path in error on Streamlit Cloud |
| Root cause | Active PostgreSQL runtime blocked on static cutover report files instead of runtime validation |
| Fix | `startup_route=postgres_runtime` → validate config + connection; skip SQLite startup/recovery |
| Admin diagnostics | `get_database_startup_diagnostics()` — configured/active backend, startup_route, sqlite_startup_skipped |
| Retest | Deploy to Streamlit Cloud with PostgreSQL secrets; confirm app loads without SQLite path error |

---

## Sprint 1 Burndown

| Workstream | Prior % | Current % | Status |
|---|---|---|---|
| Authoritative blocker tracker | 0% | **100%** | Complete |
| Browser UAT checklist | 85% | **95%** | Checklist ready; execution open |
| Role-based live UAT matrix | 85% | **95%** | Matrix ready; execution open |
| Defect intake process | 0% | **100%** | Template ready |
| Live browser UAT execution | 0% | **0%** | Pending manual testing |
| Live defect verification | 0% | **0%** | Pending |

---

## Launch Blocking Decision Key

| Decision | Meaning |
|---|---|
| **BLOCKS LAUNCH** | Must be Verified or explicitly waived with stakeholder sign-off before approved launch |
| **DOES NOT BLOCK LAUNCH** | Acknowledged; may proceed with controlled pilot |
| **POST-LAUNCH IMPROVEMENT** | Tracked for backlog; does not stop controlled pilot |

---

## Manual Live Actions Required

- [ ] Execute `reports/live_browser_uat_sprint_1.md` in live production or approved pilot runtime
- [ ] Complete `reports/role_based_live_uat_matrix.md` for all 10 roles
- [ ] Log defects using `reports/live_defect_intake_template.md`
- [ ] Update this tracker with defect IDs, Owner, Status, Evidence, and Screenshot links
- [ ] Re-evaluate **Launch blocking decision** after each Critical or High defect is Verified

---

## Related Reports

- `reports/live_browser_uat_sprint_1.md`
- `reports/role_based_live_uat_matrix.md`
- `reports/live_defect_intake_template.md`
- `reports/live_uat_checklist.md`
- `reports/final_go_live_blockers.md`
- `reports/phase_5b18f_launch_certification_summary.md`
