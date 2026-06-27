# ERP Pilot UAT Certification

**Phase:** 5B.18B  
**Generated at:** 2026-06-27 01:17 UTC  
**Scope:** production pilot user acceptance checklist for controlled business use.  
**Classification:** **WARNING** until browser UAT is signed off by business, finance, and operations owners.

## Readiness

- Current pilot UAT readiness %: **79%**
- Current accounting workflow readiness %: **91%**
- Current operational readiness %: **78%**
- Current role/branch readiness %: **90%**

## Pilot UAT Checklist

| Area | Classification | UAT Evidence Required |
|---|---|---|
| Login | PASS with warning | Confirm each role can log in and reaches only allowed pages. |
| Dashboard | WARNING | Confirm dashboard loads within accepted pilot latency and respects company/branch context. |
| POS sale | PASS with warning | Confirm cashier sale, receipt, inventory effect, journal, audit, and rollback behavior. |
| POS correction | WARNING | Controlled correction foundation exists for sale date/cashier metadata; confirm a clear UI workflow, branch scope, audit old/new values, and report updates before go-live. |
| Customer invoice | PASS with warning | Confirm create, approve/post, payment, AR balance, and journal. |
| Customer payment | PASS with warning | Confirm receipt date, method, allocation, AR reduction, journal, and audit. |
| Supplier bill | PASS with warning | Confirm bill date, approval/posting, AP balance, journal, and audit. |
| Supplier payment | PASS with warning | Confirm payment date, AP reduction, cash/bank reduction, journal, and audit. |
| Journal entry | PASS with warning | Confirm allowed posting dates, locked-period block, reversal/void, and audit trail. |
| Payroll posting | PASS with warning | Confirm payroll approval, expense/liability posting, and reports. |
| Fixed asset depreciation | PASS with warning | Confirm acquisition, register, depreciation journal, and depreciation report. |
| VAT/NHIL report | WARNING | Finance owner must verify statutory report format and filing totals. |
| Financial reports | PASS with warning | Confirm TB, GL, IS, BS, Cash Flow, AR/AP aging against journals. |
| Audit trail | PASS with warning | Confirm filters, old/new correction evidence, and export/sign-off path. |
| User permissions | PASS | Confirm restricted roles cannot bypass posting/correction/admin permissions. |
| Branch restrictions | PASS with warning | Confirm branch users see only allowed branch sales, users, inventory, and reports. |

## Pilot Exit Criteria

- Every checklist item is executed by the responsible role.
- Every defect is recorded with severity and owner.
- No critical accounting, permission, audit, or rollback issue remains open.
- Backup and restore rehearsal is complete.
- Performance certification is complete for pilot-size data.
