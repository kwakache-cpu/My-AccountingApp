# PostgreSQL Write-Path Hardening

**Generated at:** 2026-06-25 13:55 UTC  
**Branch:** `phase-5b16b-postgres-write-path-hardening`  
**Baseline reports:** `reports/erp_current_state_assessment.md`, `reports/postgres_final_certification.md`

## Readiness Summary

**PostgreSQL readiness:** **92%**  
**Production readiness:** **78%**

This phase hardens the highest-risk write paths identified in final certification while preserving SQLite compatibility. The application is materially closer to PostgreSQL cutover, but production remains a controlled **NO-GO** until staged PostgreSQL write tests and remaining cleanup warnings are resolved or formally accepted.

## Unsafe Write Paths Fixed

| Area | Previous risk | Hardening applied |
|---|---|---|
| Journal posting transaction | Owned `post_journal_entry()` path could call `execute_write_transaction()` and reach SQLite `BEGIN IMMEDIATE`. | Routed owned journal transactions through `execute_db_write_transaction()`. |
| Branch/admin write transaction | Branch governance helper used direct `execute_write_transaction()`. | Routed through `execute_db_write_transaction()` while preserving SQLite lock-safe behavior. |
| Customer/supplier quick-add | Active financial UI paths used literal `INSERT OR IGNORE`. | Replaced with `db_insert_ignore_sql()` and `execute_portable_write()`. |
| Shared idempotent seeds | Branch catalog, branch grants, default branch user, system settings, maintenance settings, schema version used literal conflict SQL. | Replaced with `db_insert_ignore_sql()` and portable writes where helper infrastructure is available. |
| Local migration idempotent inserts | `erp_migrations.py` used literal `INSERT OR IGNORE`. | Replaced with select-then-insert logic to preserve idempotence without conflict-specific SQL. |
| Invoice line writes | `save_invoice_lines()` used raw delete/insert DML. | Routed delete and line insert through `execute_portable_write()`. |
| Invoice stock effects | Inventory update and stock movement insert used raw DML. | Routed both writes through `execute_portable_write()`. |
| POS checkout stock decrement | Checkout inventory decrement used raw update DML. | Routed through `execute_portable_write()`. |
| Payroll records | Payroll summary insert used raw DML. | Routed through `execute_portable_write()`. |
| Depreciation posting | Fixed asset depreciation update used raw update DML. | Routed through `execute_portable_write()`. |
| Fixed asset reversal | Asset reversal status update used raw update DML. | Routed through `execute_portable_write()`. |

## Critical Workflow Certification

| Workflow | Result | Notes |
|---|---|---|
| POS checkout | WARNING improved | Inventory decrement now uses portable write helper; sale identity and journal posting remain connected. Needs staged PostgreSQL checkout run. |
| Inventory adjustment | WARNING improved | Invoice stock movement writes are portable; broader inventory import/adjustment loops still need staged runtime coverage. |
| Customer invoice | WARNING improved | Invoice line writes and stock effects are portable; posted invoice journal/balance behavior remains unchanged. |
| Customer payment | WARNING | Existing payment identity and journal chain remain certified by prior tests; staged PostgreSQL payment run still required. |
| Supplier bill | WARNING | Existing bill identity and AP journal chain remain certified by prior tests; line/detail staging still required. |
| Supplier payment | WARNING | Existing supplier payment identity and AP/cash journal chain remain certified by prior tests; staged PostgreSQL run still required. |
| Payroll posting | WARNING improved | Payroll source-document linkage remains tested and payroll records insert is now portable. |
| Asset depreciation posting | WARNING improved | Depreciation fixed-asset update is now portable; journal linkage remains reference-based and should be staged. |
| User/admin maintenance | WARNING improved | Branch governance transactions and fixed-asset reversal update are hardened; company deletion/setup maintenance remains privileged and should be staged carefully. |

## Remaining Blockers

- Manual migration cleanup warnings still exist in baseline readiness reports: POS branch assignment, manager-user review, and payment reference review.
- Production cutover still requires real PostgreSQL staged write execution for every critical workflow listed above.
- PostgreSQL rollback behavior and audit-log persistence need final staged evidence for POS, invoices, bills, payments, payroll, fixed assets, and admin maintenance.

## Remaining Warnings

- `execute_write_transaction()` remains available for SQLite compatibility and SQLite concurrency tests; production callers should continue to prefer `execute_db_write_transaction()`.
- `db_insert_ignore_sql()` intentionally emits `INSERT OR IGNORE` for SQLite. Remaining literal matches outside helpers are tests, audit scripts, and local maintenance utilities.
- Some raw write paths remain in non-critical utilities, seed/reset scripts, and privileged cleanup/admin tooling; they are not certified for production PostgreSQL runtime.
- Fixed asset depreciation journals remain reference-traceable but are not yet source-linked with `source_table='fixed_assets'` for every depreciation run.
- Critical workflows still need staging against a real PostgreSQL database, not only SQLite-backed regression and source-contract tests.

## Tests Added or Updated

- Updated final certification tests to require `execute_db_write_transaction()` in journal and branch-admin transaction paths.
- Added Phase 5B.16B certification checks for portable insert-ignore replacement in active customer/supplier paths.
- Added source-contract checks for portable critical DML in POS checkout, invoice line save, invoice stock effects, payroll records, and depreciation updates.

## Go / No-Go Recommendation

**Recommendation:** **NO-GO for production PostgreSQL cutover; GO for staged PostgreSQL write certification.**

The unsafe high-priority write-path patterns are reduced, and the branch is ready for staged PostgreSQL workflow execution. Production approval should wait for green staged writes, audit verification, rollback checks, and cleanup warning disposition.
