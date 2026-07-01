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
| Open live defects | **1** (LV-001 fixed pending retest; **DEF-002 Open** — LV-002D/LV-003 hot-path audit; verify `system_health_load_ms` < 3s) |
| Last updated | 2026-07-02 |

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
| DEF-002 | High | System Health / PostgreSQL Runtime | Dev / System Admin | App incredibly slow on active PostgreSQL; readiness score 0/100 with 291 blockers; misleading "switch not enabled" message | Technical Owner | **Open** | **DOES NOT BLOCK LAUNCH** until live retest confirms `system_health_load_ms` < 3s | LV-002/002B improved readiness and caching. LV-002C–D: fast snapshot reduced from ~33s to ~7s by removing subscription billing deep check, runtime ping persistence, and on-demand full audit. **LV-003**: Streamlit hot-path audit — per-rerun call tree (admin-only), session-cache startup guard/subscription checks, defer Dev gatekeeper ops snapshot + billing to session/refresh button, sidebar/page-access cache, currency DB sync only on change. **Open** until live confirms system health < 3s. Evidence: `tests/test_lv002_postgres_performance_and_readiness.py`, `tests/test_lv003_streamlit_hot_path_performance.py` | |
| DEF-003 | | | | | | Open | | | |

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
