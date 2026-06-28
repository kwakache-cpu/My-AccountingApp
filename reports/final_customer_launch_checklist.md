# Final Customer Launch Checklist — Phase 5B.18F

**Phase:** 5B.18F  
**Generated at:** 2026-06-28  
**Purpose:** Operator checklist for first live customer launch, onboarding, and handoff after production cutover.

## Launch Goals

- Onboard first pilot customer into approved production runtime
- Validate end-to-end customer workflows under live operation
- Confirm customer support, training, and escalation paths are active
- Preserve rollback safety and accounting integrity throughout launch

This checklist extends `reports/first_customer_onboarding_checklist.md` (5B.18E) with launch-day and post-cutover customer readiness.

---

## Launch Preconditions

- **STREAMLIT SECRET REQUIRED** — production secrets configured for customer-facing runtime
- **FIREBASE ACTION REQUIRED** — backup object path verified before customer data is written
- **DATABASE ACTION REQUIRED** — backend and `DATABASE_URL` validated for approved deployment mode
- **SUPABASE ACTION REQUIRED** — if Postgres backend is active, Supabase backup/restore SOP approved before customer launch

- [ ] `reports/final_launch_approval_checklist.md` approved
- [ ] `reports/production_cutover_runbook.md` cutover steps completed
- [ ] Rollback owner and support owner assigned
- [ ] Customer communication plan sent

---

## Customer Account Setup (Pre-Launch)

- [ ] Create pilot company record in production runtime
- [ ] Configure branch(es), warehouse, and POS locations as required
- [ ] Create master admin and operator users for customer
- [ ] Create accounting periods and chart of accounts
- [ ] Confirm default tax settings, currency, and exchange rates
- [ ] Confirm customer users assigned least-privilege production roles

---

## Launch-Day Customer Validation

- App startup
- Dashboard loads
- [ ] Customer admin can log in successfully
- [ ] Owner / CEO can reach Dashboard and key modules
- [ ] Cashier can access POS only (branch-scoped if applicable)
- [ ] Accountant can access journals, invoices, and reports
- [ ] Auditor / Read Only can access reports and audit trail only
- [ ] Confirm no permission escalation across customer users

---

## First Live Customer Workflows

- [ ] Execute first live sale or invoice (or agreed pilot transaction)
- [ ] Post customer payment and confirm AR balance reduction
- [ ] Enter supplier bill and confirm AP balance (if in pilot scope)
- [ ] Post journal entry and confirm Trial Balance remains balanced
- [ ] Confirm inventory movement updates correctly (if applicable)
- [ ] Confirm audit trail records each customer transaction
- [ ] Confirm cloud backup triggered after customer write activity

---

## Customer Training and Handoff

- [ ] Provide customer login credentials and support contact details securely
- [ ] Walk through primary workflow: sale, payment, invoice, report
- [ ] Explain backup and incident communication channels
- [ ] Confirm customer knows how to report critical issues immediately
- [ ] Confirm customer access limited to intended production roles
- [ ] Schedule follow-up support check-in within 24 hours

---

## Launch-Day Sign-Off

| Stakeholder | Role | Customer Launch Approved | Signature | Date |
|---|---|---|---|---|
|  | Operator | [ ] |  |  |
|  | Business Owner | [ ] |  |  |
|  | Support Owner | [ ] |  |  |
|  | Customer Representative | [ ] |  |  |

---

## Related Reports

- `reports/first_customer_onboarding_checklist.md`
- `reports/production_cutover_runbook.md`
- `reports/first_24_hour_monitoring_checklist.md`
- `reports/post_launch_support_checklist.md`
- `reports/final_launch_approval_checklist.md`
- `reports/phase_5b18f_launch_certification_summary.md`
