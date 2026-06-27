# ERP Go-Live Checklist

**Phase:** 5B.18A  
**Generated at:** 2026-06-27 00:15 UTC  
**Go/No-Go status:** **NO-GO for unrestricted production; GO for controlled pilot only after checklist sign-off.**

## Technical Readiness

- [x] SQLite runtime passes certification.
- [x] PostgreSQL runtime passes certification.
- [x] Schema portability passes certification.
- [x] Read paths pass certification.
- [x] Write paths pass certification.
- [x] Transaction ownership passes certification.
- [x] Rollback certification passes.
- [x] Regression suite passes.
- [ ] Production-sized performance run completed.
- [ ] POS concurrency run completed.
- [ ] Report latency run completed.
- [ ] External monitoring and alerting configured.

## Accounting Readiness

- [x] POS sale revenue posting certified.
- [x] POS inventory reduction and COGS posting certified.
- [x] Customer invoice and payment lifecycle certified.
- [x] Supplier bill and payment lifecycle certified.
- [x] General journal balance controls certified.
- [x] Payroll journal posting certified.
- [x] Fixed asset acquisition certified.
- [x] Depreciation journal and asset update certified.
- [x] VAT control journal certified.
- [x] Bank/cash journal movement certified.
- [ ] Finance owner signs off VAT/NHIL statutory report formats.
- [ ] Finance owner signs off payroll statutory outputs.
- [ ] Finance owner signs off fixed asset/depreciation schedules.

## Security Readiness

- [x] Developer role classified as privileged.
- [x] Master Admin permissions verified.
- [x] System Admin cannot post accounting documents.
- [x] Accountant can post/report but cannot manage users.
- [x] Cashier cannot view management reports.
- [x] Inventory Officer cannot post journals.
- [x] Payroll Officer cannot manage users.
- [x] Auditor cannot post journals.
- [x] Branch isolation helper certified.
- [ ] Role-by-role browser UAT completed for every module.
- [ ] Developer credential emergency-use policy signed off.

## Operational Readiness

- [ ] Backup completed immediately before go-live.
- [ ] Backup restore rehearsal completed into isolated environment.
- [ ] Restore row counts reconciled for companies, branches, users, inventory, journals, customers, suppliers, invoices, bills, payments, payroll, fixed assets, and audit logs.
- [ ] Rollback window approved.
- [ ] Rollback owner assigned.
- [ ] Customer support owner assigned.
- [ ] Finance sign-off captured.
- [ ] Business owner sign-off captured.
- [ ] Production secrets verified.
- [ ] Cloud Backup credentials verified.
- [ ] Recovery runbook reviewed.
- [ ] Incident response runbook reviewed.

## Module UAT Checklist

- [ ] Dashboard widgets load within accepted latency.
- [ ] Company Management create/edit/archive/reactivate/wipe controls verified.
- [ ] Branch Management create/edit/assign/disable controls verified.
- [ ] Point of Sale sale/return/discount/cashier close verified.
- [ ] Inventory create/edit/adjust/import/stock movement verified.
- [ ] Customers create/edit/delete/customer ledger verified.
- [ ] Suppliers create/edit/delete/supplier ledger verified.
- [ ] Sales invoice create/edit/approve/post/reverse verified.
- [ ] Purchasing bill create/edit/approve/post/reverse verified.
- [ ] Accounts Receivable payment/allocation/aging verified.
- [ ] Accounts Payable payment/allocation/aging verified.
- [ ] General Journal post/reverse/period-lock controls verified.
- [ ] Chart of Accounts create/edit/control-account restrictions verified.
- [ ] Banking transfer/reconciliation/cash movement verified.
- [ ] Payroll create/approve/post/report verified.
- [ ] Fixed Assets acquire/depreciate/dispose/report verified.
- [ ] VAT/NHIL reporting verified.
- [ ] Analytics pages verified.
- [ ] Audit Trail filter/export verified.
- [ ] User Management create/edit/disable/branch assignment verified.
- [ ] Developer Dashboard diagnostics verified.
- [ ] System Configuration settings and secrets handling verified.
- [ ] Cloud Backup and Recovery verified.

## Final Go/No-Go Gate

## Sign-off Requirements

Production may proceed only when:

- All critical and high blockers in `reports/erp_remaining_blockers.md` are resolved or formally accepted.
- Backup and restore are successfully rehearsed.
- Production-size performance is acceptable.
- Finance and business owners sign off.
- Rollback procedure has an assigned owner and approved execution window.
