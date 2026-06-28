# First Customer Onboarding Checklist — Phase 5B.18E

**Phase:** 5B.18E  
**Generated at:** 2026-06-27  
**Purpose:** Document the operator and customer onboarding steps for the first production pilot customer.

## Onboarding Goals

- Configure first pilot customer company and branch(es)
- Verify end-to-end transactional workflow
- Confirm customer support and training handoff
- Confirm production backups and rollback plan are in place

---

## Pre-Onboarding Preparation

- **STREAMLIT SECRET REQUIRED** — production secrets configured and validated for pilot deployment
- **FIREBASE ACTION REQUIRED** — Firebase credentials and backup object paths verified
- **DATABASE ACTION REQUIRED** — backend selection and `DATABASE_URL` validated for pilot runtime
- **SUPABASE ACTION REQUIRED** — if using Postgres, Supabase backup/restore SOP documented and approved before onboarding

- [ ] Confirm pilot company has no production-critical data in the staging environment
- [ ] Confirm Streamlit secrets are configured for production mode
- [ ] Confirm Firebase credentials and backup object paths are valid
- [ ] Confirm database backend is set appropriately for pilot deployment
- [ ] Confirm rollback checklist and operator sign-off checklist are available

---

## Customer Account Setup

- [ ] Create the pilot company record in the production runtime
- [ ] Configure branch(es), warehouse, and POS locations as required
- [ ] Create the first master admin and operator users
- [ ] Create required accounting periods and chart of accounts
- [ ] Confirm default tax settings, currency, and exchange rates if applicable

---

## Pilot Business Workflow Validation

- [ ] Enter an initial customer sale or invoice
- [ ] Post a customer payment and confirm AR carries through
- [ ] Enter a supplier bill and confirm AP carries through
- [ ] Post a general ledger journal and confirm Trial Balance
- [ ] Confirm inventory movement or POS sale updates stock correctly
- [ ] Confirm audit trail records each onboarding transaction

---

## Customer Training and Handoff

- [ ] Provide customer with login and support contact details
- [ ] Walk through the first customer workflow: sale, payment, invoice, report
- [ ] Confirm customer understands backup and rollback communication channels
- [ ] Confirm customer knows how to report critical issues immediately
- [ ] Confirm pilot customer access is limited to intended production roles

---

## First Customer Readiness Sign-Off

| Role | Name | Approval | Signature | Date |
|---|---|---|---|---|
| Technical Owner |  | [ ] |  |  |
| Business Owner |  | [ ] |  |  |
| Finance Owner |  | [ ] |  |  |
| Operator |  | [ ] |  |  |

---

## Related Reports

- `reports/release_candidate_checklist.md`
- `reports/live_app_smoke_test_checklist.md`
- `reports/production_rollback_checklist.md`
- `reports/operator_signoff_checklist.md`
- `reports/deployment_secrets_checklist.md`
