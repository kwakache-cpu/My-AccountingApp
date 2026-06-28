# Post-Launch Support Checklist — Phase 5B.18F

**Phase:** 5B.18F  
**Generated at:** 2026-06-28  
**Purpose:** Operator and support team checklist for sustained production support after first live customer launch.

## Support Scope

This checklist covers support readiness from T+24 hours through the first week of controlled production operation.
It complements the first-24-hour monitoring checklist and preserves rollback safety.

---

## Support Preconditions

- **STREAMLIT SECRET REQUIRED** — support team knows how to verify production secrets without exposing values
- **FIREBASE ACTION REQUIRED** — support team can locate backup object path and last backup timestamp
- **DATABASE ACTION REQUIRED** — support team understands active backend and escalation path for database issues
- **SUPABASE ACTION REQUIRED** — if Postgres backend is active, support team has Supabase escalation contacts and restore SOP

**Support owner:** _______________________  
**Support hours (pilot):** _______________________  
**Escalation contact (technical):** _______________________  
**Escalation contact (finance):** _______________________

---

## Day 1 (T+24 to T+48 Hours)

- [ ] Review 24-hour monitoring sign-off and open defects
- [ ] Confirm pilot customer can log in and complete primary workflows
- [ ] Confirm support channel response SLA communicated to customer
- [ ] Triage any permission, reporting, or transaction issues by severity
- [ ] Confirm backup uploads continue after daily business activity
- [ ] Confirm audit trail captures support-related administrative actions
- [ ] Update defect log with owner and target resolution date

---

## Days 2–3 (Early Stabilization)

- [ ] Execute role spot-checks for critical pilot roles (Owner, Cashier, Accountant)
- [ ] Confirm POS, AR, AP, and journal workflows remain stable under live use
- [ ] Review performance complaints against targets in `erp_performance_certification.md`
- [ ] Confirm no unresolved **BLOCKS LAUNCH** defects remain open without waiver
- [ ] Schedule finance review of live Trial Balance and statutory reports
- [ ] Confirm rollback owner remains available during approved support window

---

## Days 4–7 (First Week Completion)

- [ ] Complete or schedule remaining browser UAT items from `reports/live_uat_checklist.md`
- [ ] Capture performance timings for dashboard, POS, TB/GL, and audit trail
- [ ] Confirm banking/cash drawer and inventory adjustment workflows if in pilot scope
- [ ] Confirm external monitoring alerts tested (if configured)
- [ ] Conduct support retrospective: incidents, root causes, runbook gaps
- [ ] Prepare first-week support summary for business and finance owners

---

## Incident Response

For each production incident, record:

- [ ] Incident ID and timestamp
- [ ] Affected module (POS, journals, reports, permissions, backup, etc.)
- [ ] Severity: Critical / High / Medium / Low
- [ ] User impact and business impact
- [ ] Immediate mitigation taken
- [ ] Rollback considered? [ ] Yes [ ] No — reason: __________
- [ ] Root cause (if known) and follow-up owner

**Critical incidents** (unbalanced TB, data corruption, permission escalation, backup failure) must escalate to rollback owner and finance owner immediately.

---

## Support Communication

- [ ] Daily status update to business owner during first week (or agreed cadence)
- [ ] Customer-facing status updates for any user-impacting incidents
- [ ] Document any pilot waivers for finance/statutory sign-off or monitoring gaps
- [ ] Confirm post-launch improvement items logged for backlog review

---

## First-Week Support Sign-Off

| Stakeholder | Role | Support Readiness Complete | Signature | Date |
|---|---|---|---|---|
|  | Support Owner | [ ] |  |  |
|  | Technical Owner | [ ] |  |  |
|  | Business Owner | [ ] |  |  |

---

## Related Reports

- `reports/first_24_hour_monitoring_checklist.md`
- `reports/production_rollback_checklist.md`
- `reports/live_uat_checklist.md`
- `reports/final_customer_launch_checklist.md`
- `reports/phase_5b18f_launch_certification_summary.md`
