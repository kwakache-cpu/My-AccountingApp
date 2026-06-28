# Production Rollback Checklist — Phase 5B.18E

**Phase:** 5B.18E  
**Generated at:** 2026-06-27  
**Purpose:** Operator runbook for safe rollback from a failed production deployment or cutover.

## Rollback Preconditions

- Rollback must be triggered only when a confirmed production failure exists
- Rollback owner must be assigned and communication must be opened to stakeholders
- A known-good backup or snapshot must exist before rollback begins
- **STREAMLIT SECRET REQUIRED**: production secrets loaded securely
- **SUPABASE ACTION REQUIRED**: if using Postgres, Supabase backup/restore SOP must be documented and approved
- **FIREBASE ACTION REQUIRED**: Firebase credentials validated and backup object path verified
- **DATABASE ACTION REQUIRED**: verify recovery source and target backup before writing any production state

---

## Trigger Conditions

- Unbalanced Trial Balance after deployment
- Critical accounting or permission failure
- Production startup failure not fixable during rollback window
- Data corruption detected in company runtime
- Backup restore attempt fails or is incomplete

---

## Rollback Decision

- [ ] Confirm failure condition with technical owner, finance, and business owner
- [ ] Freeze writes and notify affected users
- [ ] Record current production state with forensic export
- [ ] Confirm the most recent good backup and restore target
- [ ] Verify the rollback window is still open

---

## Rollback Steps

1. **Announce freeze**
   - [ ] Stop all user write activity immediately
   - [ ] Communicate rollback plan to support and business stakeholders

2. **Preserve current production state**
   - [ ] Export current runtime metadata and diagnostics
   - [ ] Archive current backup object names and timestamps
   - [ ] Do not overwrite the last known good backup

3. **Restore to staging first**
   - [ ] Restore backup into an isolated staging environment
   - [ ] Validate row counts for critical tables
   - [ ] Validate trial balance balances and key financial reports
   - [ ] Validate admin login and runtime startup
   - [ ] Confirm persistence diagnostics are healthy

4. **Switch production runtime**
   - [ ] If SQLite pilot, replace runtime database file with approved backup
   - [ ] If Postgres, restore Supabase snapshot or follow platform restore SOP
   - [ ] Update `DATABASE_URL` / backend settings if required
   - [ ] Confirm `ERP_ENABLE_POSTGRES_RUNTIME` and `ERP_ENVIRONMENT` values remain correct

5. **Verify rollback success**
   - [ ] Login as Owner and System Admin
   - [ ] Confirm dashboard loads
   - [ ] Perform one smoke write and confirm audit trail
   - [ ] Confirm trial balance remains balanced
   - [ ] Confirm no new startup errors

6. **Document rollback**
   - [ ] Record rollback owner and timestamp
   - [ ] Record source backup ID and restore target
   - [ ] Document validation results and any issues
   - [ ] Identify root cause and required follow-up actions

---

## Rollback Safeguards

- Confirm `restore_runtime_database_from_local_file()` exists before manual SQLite restore
- Confirm `restore_latest_cloud_backup_to_local()` is blocked under Postgres runtime and that the operator uses the approved restore path
- Confirm backup object path is versioned and retrievable
- Confirm `DATABASE_URL` is not leaked in shared reports

---

## Rollback Sign-Off

| Stakeholder | Role | Approved | Signature | Date |
|---|---|---|---|---|
| Technical owner |  | [ ] |  |  |
| Business owner |  | [ ] |  |  |
| Finance owner |  | [ ] |  |  |
| Operator |  | [ ] |  |  |

---

## Related Reports

- `reports/backup_restore_rehearsal_steps.md`
- `reports/deployment_secrets_checklist.md`
- `reports/final_go_live_blockers.md`
- `reports/phase_5b18e_release_candidate_summary.md`
