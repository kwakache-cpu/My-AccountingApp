# Live App Smoke Test Checklist — Phase 5B.18E

**Phase:** 5B.18E  
**Generated at:** 2026-06-27  
**Purpose:** Operator smoke test for production or pilot runtime after deployment.

## Smoke Test Objectives

- Confirm app startup and configuration loads correctly
- Confirm runtime backend and persistence behave as expected
- Confirm one end-to-end business write path succeeds
- Confirm audit logging and backup operations are triggered
- Confirm basic permission boundaries hold for production roles

---

## Smoke Test Pre-Conditions

- **STREAMLIT SECRET REQUIRED**: production secrets loaded securely
- **FIREBASE ACTION REQUIRED**: Firebase credentials validated and backup object path verified
- **DATABASE ACTION REQUIRED**: `DATABASE_URL` and backend settings validated
- **SUPABASE ACTION REQUIRED**: if using Postgres, Supabase backup/restore SOP must be documented and approved

---

## Startup Smoke Tests

- App startup
- [ ] Deploy latest approved app version to Streamlit Cloud or production host
- [ ] Confirm app launches without startup exception
- [ ] Confirm `ERP_PRODUCTION_MODE=1` or equivalent production environment flag
- [ ] Confirm `ERP_ENVIRONMENT=production` (or approved staging mode for cutover rehearsal)
- [ ] Confirm `get_deployment_readiness_diagnostics()` reports active backend, company count, and backup status
- [ ] Confirm no plaintext secrets appear in app diagnostics

---

## Authentication and Role Test

- Dashboard loads
- [ ] Owner / CEO can log in and reach Dashboard
- [ ] System Admin can log in and access system configuration only
- [ ] Cashier can log in and access POS only
- [ ] Accountant can log in and access journals, invoices, and reports
- [ ] Auditor / Read Only can log in and access reports and audit trail only

---

## Business Workflow Smoke Tests

- [ ] Perform a test sales transaction through POS and confirm inventory decrement and journal posting
- [ ] Enter a customer payment and confirm AR balance reduction
- [ ] Create and post a supplier bill and confirm AP balance
- [ ] Run a basic Trial Balance report and confirm it balances
- [ ] Confirm one journal entry posts and is visible in the audit trail
- [ ] Confirm backup upload event occurs after the write activity

---

## Persistence and Backup Smoke Tests

- [ ] Confirm cloud backup path exists and is writable
- [ ] Confirm last cloud backup timestamp is recent
- [ ] Confirm last local backup timestamp is recent if local backup is enabled
- [ ] Confirm `FIREBASE_DB_BACKUP_OBJECT` path or equivalent is correct
- [ ] Confirm `DATABASE_URL` is present when Postgres backend is active
- [ ] Confirm `DB_BACKEND=postgres` only when Postgres cutover is approved
- [ ] Confirm `ERP_ENABLE_POSTGRES_RUNTIME=1` only when Postgres runtime is active

---

## Observability and Logs

- [ ] Confirm runtime logs contain no startup errors
- [ ] Confirm audit trail logs test actions
- [ ] Confirm any failed permissions are explicit denial messages
- [ ] Confirm system health diagnostics are accessible to operator

---

## Smoke Test Sign-Off

| Tester | Role | Date | Pass/Fail | Notes |
|---|---|---|---|---|
|  |  |  |  |  |

---

## Notes

This checklist is intended as a lightweight production readiness verification for release candidate status. It does not replace the full role-based UAT or backup/restore rehearsal reports.
