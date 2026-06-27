# Backup & Restore Rehearsal Steps

**Phase:** 5B.18D  
**Generated at:** 2026-06-27  
**Purpose:** Operator runbook for certifying Firebase, local, and Supabase backup/restore before go-live.

---

## Readiness Summary

| Area | Readiness % | Classification |
|---|---|---|
| Local SQLite backup | **85%** | PASS with warning |
| Firebase cloud backup | **80%** | PASS with warning — live rehearsal open |
| Restore validation | **78%** | PASS with warning |
| Restore diagnostics | **92%** | PASS |
| Supabase/PostgreSQL backup | **55%** | WARNING — operator-managed only |
| Rollback safety | **88%** | PASS with warning |
| Overall data safety | **82%** | WARNING until live rehearsal complete |

---

## Architecture Overview

**Backup unit:** SQLite file snapshot (`eka_enterprise_v3.db`)  
**Cloud vault:** Firebase Storage  
**Local paths:**
- Latest: `{EKA_DATA_DIR}/backups/latest/eka_enterprise_v3.db`
- History: `{EKA_DATA_DIR}/backups/history/eka_enterprise_v3_{timestamp}.db`
- Restore guard: `{EKA_DATA_DIR}/restore_guard.json`

**PostgreSQL:** No in-app backup/restore. Supabase platform backups are operator responsibility. Firebase SQLite restore is **blocked** when Postgres runtime is active.

---

## Safety Guards (Do Not Disable)

| Guard | Purpose |
|---|---|
| Upload guard | Blocks cloud upload if local company count < cloud backup count |
| Restore guard | Blocks cloud uploads immediately after restore until successful startup |
| Production readiness check | Snapshot must pass `production_ready` with `company_count >= 1` |
| Pre-restore safety copy | Current runtime copied to `eka_enterprise_v3_before_cloud_restore_{timestamp}.db` |
| Test mode block | Cloud backup skipped in test mode unless `EKA_ALLOW_TEST_CLOUD_BACKUP=1` |
| Postgres runtime block | Cloud SQLite restore returns `postgres_runtime_recovery_blocked` |
| Debounce | Same signature within `EKA_BACKUP_DEBOUNCE_SECONDS` (default 20s) skipped |

---

## Part A — Firebase Cloud Backup Rehearsal

### Prerequisites

- [ ] `FIREBASE_SERVICE_ACCOUNT` configured in Streamlit secrets
- [ ] `FIREBASE_STORAGE_BUCKET` and `FIREBASE_DB_BACKUP_OBJECT` verified
- [ ] Admin user with `export_backup` permission (System Admin or Master Admin)
- [ ] Pilot company with posted transactions exists

### Steps

1. **Verify diagnostics**
   - Open System Configuration → System Health
   - Confirm `get_recovery_source_diagnostics()` shows:
     - `credentials_loaded: true`
     - `credentials_source` (file/secrets/env)
     - `bucket_name`, `object_name` populated
   - Confirm no secrets appear in UI output

2. **Trigger backup**
   - Option A: Perform a write to a `BACKUP_TRIGGER_TABLE` (e.g., post a journal) — automatic post-commit backup
   - Option B: Admin → "Prepare Backup Export" button
   - Option C: `force_backup_after_company_creation()` after new company (not for rehearsal)

3. **Verify upload**
   - Check `latest_cloud_backup_status` in persistence diagnostics
   - Confirm Firebase Console shows object at `backups/eka_enterprise_v3.db`
   - Confirm history object at `backups/history/eka_enterprise_v3_{timestamp}.db`

4. **Record evidence**
   - Backup timestamp
   - Object path and size
   - Local company count at backup time
   - Operator name

---

## Part B — Local Backup Verification

Local backup runs automatically with every successful cloud backup attempt.

### Steps

1. Confirm local latest exists: `{EKA_DATA_DIR}/backups/latest/eka_enterprise_v3.db`
2. Run `get_local_backup_diagnostics()` — verify `production_ready: true`
3. Compare company count: runtime vs local latest vs cloud latest via `run_persistence_self_test()`
4. Record local backup mtime and company count

### Pre-Migration Backups

`db_upgrade_safety.create_timestamped_backup()` creates `{db_name}_{reason}_{timestamp}.db` before schema migrations. These are separate from cloud backup history.

---

## Part C — Cloud Restore Rehearsal (Isolated)

**WARNING:** Never restore directly over production without staging validation first.

### Prerequisites

- [ ] Isolated Streamlit app instance or local environment with empty/discardable DB
- [ ] Valid cloud backup object confirmed in Part A
- [ ] Rollback owner assigned

### Steps

1. **Export current state** (if restoring over existing DB)
   - Pre-restore safety copy is created automatically by the engine
   - Optionally run manual export via "Prepare Backup Export"

2. **Select restore target**
   - Staging: fresh `EKA_DATA_DIR` or isolated Streamlit deployment
   - Production: only after staging validation passes

3. **Execute restore**
   - Admin → "Restore Latest Cloud Backup" (requires `restore_backup` permission)
   - **Note:** If local DB is valid and populated, UI restore may be blocked unless explicit recovery mode is used. For rehearsal, use empty staging environment or documented explicit recovery path.

4. **Candidate selection** (automatic)
   - Engine tries latest Firebase object, then history blobs newest-first
   - Each candidate: download → `get_database_health_snapshot()` → must be `production_ready`

5. **Post-restore validation**
   - [ ] App starts without exception
   - [ ] `company_count > 0`
   - [ ] Restore guard clears after successful startup
   - [ ] Admin users can log in (or admin recovery panel appears if no admin users)

6. **Row-count reconciliation**

   | Table Group | Validate |
   |---|---|
   | Core | companies, branches, users |
   | Master data | customers, suppliers, inventory items |
   | Transactions | pos_sales, sales_invoices, ap_bills, payments |
   | Accounting | journal_entries, journal_lines, chart_of_accounts |
   | Payroll & assets | payroll_runs, fixed_assets |
   | Audit | audit_logs |

7. **Financial reconciliation**
   - Trial Balance balances
   - Balance Sheet vs prior backup
   - Income Statement for current period
   - General Ledger sample accounts
   - AR/AP aging totals
   - VAT/NHIL control accounts
   - Fixed asset register and depreciation

8. **Permission smoke test**
   - Log in as Owner, System Admin, Accountant, Cashier, Inventory Officer, HR/Payroll, Auditor, Branch Manager, Bookkeeper, Staff
   - Confirm sidebar shows only allowed modules per role

9. **Record sign-off**
   - Restore timestamp, source backup id, target environment
   - Validator name, row-count results, financial reconciliation result
   - Business owner, finance owner, technical owner signatures

---

## Part D — Local File Restore (API / Runbook)

No admin UI button exists. Use for emergency restore from a known-good `.db` file.

```
restore_runtime_database_from_local_file(source_path)
```

### Steps

1. Verify file is valid SQLite (`is_sqlite_file()`)
2. Engine creates pre-restore timestamped backup via `create_timestamped_backup()`
3. Replaces runtime DB and writes restore guard
4. Post-restore health snapshot required
5. Run same row-count and financial reconciliation as Part C

---

## Part E — Supabase / PostgreSQL Backup (Operator-Managed)

**No in-app implementation.** Required if `DB_BACKEND=postgres` is production backend.

### SUPABASE ACTION REQUIRED

1. Configure Supabase automated backups or schedule manual pg_dump
2. Export production-pilot database before go-live
3. Restore to isolated staging project/database
4. Update `DATABASE_URL` in staging Streamlit secrets
5. Start ERP against restored staging database
6. Run row-count and financial reconciliation (same as Part C steps 6–7)
7. **Never** paste connection strings into reports or commits

### Postgres Runtime Constraints

- `restore_latest_cloud_backup_to_local()` → `postgres_runtime_recovery_blocked`
- `attempt_production_database_recovery()` → `postgres_runtime_recovery_blocked`
- `get_db_diagnostics()` omits SQLite health under Postgres
- Recovery relies on Supabase platform tools (PITR, pg_dump restore)

---

## Integrity Verification Summary

| Check | When | Status |
|---|---|---|
| SQLite magic header | Local file restore | Implemented |
| `production_ready` structural check | Cloud restore candidate selection | Implemented |
| Company count >= 1 | Cloud restore candidate selection | Implemented |
| Upload guard (company count) | Before cloud upload | Implemented |
| Row-count snapshots on migration | Startup migrations | Implemented |
| `PRAGMA integrity_check` | Restore time | **Not implemented** — manual optional |
| Financial reconciliation | Restore rehearsal | **Manual required** |
| UUID/row-level parity | Self-test | Company count only |

---

## Restore Diagnostics Reference

| Function | Use |
|---|---|
| `get_recovery_source_diagnostics()` | Firebase credential/bucket/object readiness |
| `get_persistence_diagnostics()` | Runtime vs local vs cloud status |
| `get_local_backup_diagnostics()` | Local latest backup health |
| `get_cloud_backup_diagnostics()` | Cloud object validation |
| `run_persistence_self_test()` | Cross-check company counts |
| `get_startup_backend_diagnostics()` | Backend routing and cutover evidence |

---

## Rollback Plan

1. **Freeze writes** — announce maintenance window
2. **Export current state** — Firebase backup + Supabase dump if Postgres
3. **Restore to staging first** — never switch production without staging validation
4. **Validate** — row counts, trial balance, audit trail continuity
5. **Switch runtime** — update secrets or restore runtime DB
6. **Verify** — smoke test critical workflows
7. **Log** — operator, timestamp, source backup, target, validation results

---

## Evidence Checklist Before Go-Live

- [ ] Backup id/path and timestamp recorded
- [ ] Restore target environment documented
- [ ] Row-count reconciliation passed
- [ ] Financial reconciliation passed
- [ ] Permission smoke test passed
- [ ] Rollback owner assigned
- [ ] Business owner sign-off
- [ ] Finance owner sign-off
- [ ] Technical owner sign-off
