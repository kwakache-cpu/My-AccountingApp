# ERP Remaining Blockers

**Phase:** 5B.18A  
**Generated at:** 2026-06-27 00:15 UTC  
**Purpose:** severity-ordered production blockers and warnings remaining after ERP production readiness certification.

## Severity-Ordered Blockers

| Severity | Blocker | Classification | Evidence | Required Resolution |
|---|---|---|---|---|
| 1 - Critical | Live cloud backup and restore rehearsal has not been proven in this certification run. | WARNING | Backup/recovery helpers and diagnostics exist, but local tests do not exercise real cloud credentials, bucket permissions, object restore, and post-restore accounting validation. | Run a full backup, restore to isolated environment, validate company/branch/user/accounting row counts, and record sign-off. |
| 2 - High | Manual browser UAT is not complete for every module/action/role. | WARNING | Automated tests cover core services and workflows, but Create/Edit/Delete/Approve/Reverse/Post for every UI page and role is not fully browser-certified. | Execute role-by-role UAT scripts for all modules before unrestricted go-live. |
| 3 - High | Production-size performance and concurrency are not certified. | WARNING | Tests prove correctness, not large-tenant latency, high cashier concurrency, report timing, or dashboard load. | Profile dashboard, POS, reports, and payment workflows under production-like data and concurrent users. |
| 4 - High | Full finance-owner sign-off is still needed for VAT/NHIL reports and statutory payroll outputs. | WARNING | VAT journal posting is certified; NHIL capture fields exist, but filing/report formats need finance validation. | Finance owner validates statutory report output against expected filings. |
| 5 - Medium | Fixed asset depreciation is certified but multi-period edge cases need UAT. | WARNING | Depreciation journal/book-value update is tested; multi-period schedules, disposals, revaluations, and partial-month policies are not fully certified. | Run asset lifecycle UAT across acquisition, depreciation, disposal, and reporting. |
| 6 - Medium | Banking/cash UI workflows need operational UAT. | WARNING | Journal-level bank transfer is tested and banking module exists, but reconciliation, transfer approvals, and cashier close procedures need manual proof. | Certify cash drawer close, bank transfers, reconciliation, and audit evidence. |
| 7 - Medium | Inventory import/adjustment workflows need production-like UAT. | WARNING | POS decrement and purchase increase are tested; bulk import, stock count adjustment, and valuation under real volumes need review. | Run inventory adjustment/import scenarios with rollback and audit checks. |
| 8 - Medium | External monitoring and alerting are not certified. | WARNING | In-app diagnostics exist; external uptime/error monitoring is outside this test run. | Configure and test monitoring, error alerts, and incident response ownership. |
| 9 - Low | Developer access remains intentionally powerful. | WARNING | Developer role has broad permissions by design. | Restrict developer credential handling, audit access, and emergency-use approval before production. |
| 10 - Low | Historical report files show evolving certification state. | WARNING | Prior reports remain intentionally preserved. | Treat latest certification report as current source while preserving history. |

## Non-Blocker PASS Items

- SQLite runtime: **PASS**
- PostgreSQL runtime: **PASS**
- Schema portability: **PASS**
- Read path certification: **PASS**
- Write path certification: **PASS**
- Transaction ownership: **PASS**
- Rollback certification: **PASS**
- PostgreSQL E2E certification: **PASS**
- Functional accounting certification: **PASS with warning**
- Migration cleanup: **PASS**
- Regression suite: **PASS**

## Highest-priority next phase

**PHASE 5B.18B — Production Pilot UAT, Backup/Restore Rehearsal, and Performance Certification**

This is the single highest-priority next phase because the remaining risk is operational proof, not PostgreSQL portability or accounting-engine redesign.
