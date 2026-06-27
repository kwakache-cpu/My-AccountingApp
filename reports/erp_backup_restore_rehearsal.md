# ERP Backup Restore Rehearsal

**Phase:** 5B.18B  
**Generated at:** 2026-06-27 01:17 UTC  
**Scope:** backup/export, restore rehearsal, and rollback plan before production pilot.  
**Classification:** **WARNING**

## Readiness

- Current backup readiness %: **78%**
- Current restore readiness %: **70%**
- Current rollback readiness %: **84%**
- Current go-live data safety readiness %: **77%**

## Existing Mechanisms

| Area | Classification | Evidence |
|---|---|---|
| Local SQLite backup | PASS with warning | Runtime snapshot and local latest/history backup paths exist. |
| Cloud backup diagnostics | PASS with warning | Firebase recovery diagnostics expose credential, bucket, object, and database URL readiness without leaking secrets. |
| PostgreSQL backup/export path | WARNING | PostgreSQL runtime is certified, but Supabase export rehearsal must be done outside code. |
| Restore guard | PASS | Restore guard prevents unsafe overwrite immediately after local restore. |
| Rollback plan | WARNING | E2E rollback is certified; production operational rollback rehearsal still needs sign-off. |

## Restore Rehearsal Steps

1. Export PostgreSQL/Supabase backup from the approved production-pilot database.
2. Restore to an isolated staging database, never directly over production.
3. Start ERP against the restored staging database.
4. Validate row counts for companies, branches, users, inventory, journals, customers, suppliers, invoices, bills, payments, payroll, fixed assets, and audit logs.
5. Run financial report reconciliation: Trial Balance, Balance Sheet, Income Statement, General Ledger, AR/AP aging, VAT/NHIL, payroll, and fixed assets.
6. Run permission smoke tests for Developer, Master Admin, System Admin, Owner, Branch Manager, Accountant, Cashier, Sales Officer, Inventory Officer, Payroll Officer, Auditor, and Staff.
7. Record restore timestamp, source backup id, restored database id, validator, and sign-off.

## Manual Actions Required

### SUPABASE ACTION REQUIRED

- Create a production-pilot database backup/export from Supabase.
- Restore/export into an isolated staging project or database.
- Verify connection string is not pasted into reports or commits.

### STREAMLIT SECRET REQUIRED

- Configure production-pilot `DATABASE_URL`, `DB_BACKEND=postgres`, `ERP_ENABLE_POSTGRES_RUNTIME=1`, and environment settings in Streamlit secrets or deployment environment.
- Do not commit secrets to the repository.

### FIREBASE ACTION REQUIRED

- Verify Firebase service account, bucket name, backup object path, and restore object path.
- Confirm backup object retention and access policy.

### DATABASE ACTION REQUIRED

- Run post-restore row count reconciliation.
- Run finance report reconciliation.
- Confirm rollback owner and rollback window.

## Rollback Plan

- Freeze writes before rollback.
- Export current production-pilot state.
- Restore last known good backup into staging first.
- Validate accounting and audit tables before switching runtime.
- Keep a rollback log with operator, timestamp, source backup, target database, and validation results.

## Evidence Needed Before Go-Live

- Backup id/path.
- Restore target.
- Row-count reconciliation.
- Financial reconciliation.
- Permission smoke-test result.
- Business owner sign-off.
- Finance owner sign-off.
- Technical owner sign-off.
