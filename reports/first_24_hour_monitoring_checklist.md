# First 24-Hour Monitoring Checklist — Phase 5B.18F

**Phase:** 5B.18F  
**Generated at:** 2026-06-28  
**Purpose:** Operator monitoring plan for the first 24 hours after production cutover and first live customer launch.

## Monitoring Objectives

- Detect startup, persistence, and permission failures immediately after cutover
- Confirm accounting integrity remains intact during first live transactions
- Confirm backup and audit logging continue operating under production load
- Escalate incidents according to rollback and support runbooks

---

## Monitoring Preconditions

- **STREAMLIT SECRET REQUIRED** — production secrets loaded and validated
- **FIREBASE ACTION REQUIRED** — Firebase backup path and credentials verified
- **DATABASE ACTION REQUIRED** — active backend and `DATABASE_URL` confirmed for production runtime
- **SUPABASE ACTION REQUIRED** — if Postgres backend is active, Supabase monitoring and backup SOP must be in place

**Monitoring owner:** _______________________  
**Cutover timestamp (T-0):** _______________________  
**Rollback owner on standby:** _______________________

---

## Hour 0–1 (Immediate Post-Cutover)

- [ ] Confirm App startup completed without exception
- [ ] Confirm Dashboard loads for Owner / CEO
- [ ] Review System Health diagnostics — no critical failures
- [ ] Confirm persistence self-test passes
- [ ] Confirm no unbalanced journals after cutover smoke write
- [ ] Confirm cloud backup upload occurred after first write
- [ ] Review Streamlit runtime logs for startup errors
- [ ] Confirm support channel is active and acknowledged by pilot customer

---

## Hour 1–4 (Early Production Activity)

- [ ] Monitor first live customer transactions (sale, payment, invoice, or journal as applicable)
- [ ] Confirm audit trail records each live transaction
- [ ] Confirm inventory updates (if POS/inventory used) match expected quantities
- [ ] Confirm Trial Balance remains balanced after live activity
- [ ] Confirm no permission escalation observed across pilot roles
- [ ] Confirm branch isolation holds for branch-scoped users
- [ ] Check backup timestamp remains recent after business writes

---

## Hour 4–12 (Sustained Operations)

- [ ] Monitor dashboard and report load times against pilot targets
- [ ] Confirm POS checkout and finalization remain within acceptable latency (if POS in use)
- [ ] Confirm AR/AP balances update correctly after customer/supplier transactions
- [ ] Review audit trail filter performance under live logging volume
- [ ] Confirm no duplicate journal postings or failed transaction wrappers
- [ ] Confirm external monitoring alerts (if configured) are receiving heartbeat/status

---

## Hour 12–24 (Stabilization)

- [ ] Re-run Trial Balance, Balance Sheet, and Income Statement for pilot company
- [ ] Confirm cloud and local backup timestamps are current
- [ ] Confirm company count and critical table row counts match expected baseline
- [ ] Review any operator or customer-reported defects and classify severity
- [ ] Confirm rollback plan remains valid if critical failure detected
- [ ] Prepare 24-hour monitoring summary for business and finance owners

---

## Escalation Triggers

Escalate immediately to rollback owner and technical owner if any of the following occur:

- Unbalanced Trial Balance after live transactions
- Data corruption or missing company records
- Critical permission escalation
- Startup failure or persistence self-test failure
- Backup upload failure persisting beyond recovery window
- Accounting integrity failure confirmed by finance owner

Follow `reports/production_rollback_checklist.md` if rollback is triggered.

---

## 24-Hour Monitoring Sign-Off

| Check | Owner | Pass/Fail | Notes | Time |
|---|---|---|---|---|
| Startup and dashboard |  |  |  |  |
| Live transaction integrity |  |  |  |  |
| Backup and audit logging |  |  |  |  |
| Permission boundaries |  |  |  |  |
| Financial report reconciliation |  |  |  |  |

| Stakeholder | Role | 24-Hour Monitoring Complete | Signature | Date |
|---|---|---|---|---|
|  | Monitoring Owner | [ ] |  |  |
|  | Technical Owner | [ ] |  |  |
|  | Operator | [ ] |  |  |

---

## Related Reports

- `reports/production_cutover_runbook.md`
- `reports/production_rollback_checklist.md`
- `reports/post_launch_support_checklist.md`
- `reports/final_launch_approval_checklist.md`
- `reports/phase_5b18f_launch_certification_summary.md`
