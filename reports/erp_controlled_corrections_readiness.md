# ERP Controlled Corrections Readiness

**Phase:** 5B.18B  
**Generated at:** 2026-06-27 01:17 UTC  
**Scope:** controlled correction foundation readiness for POS sale date and cashier/user assignment, voucher/journal date controls, and report integrity.
**Classification:** **WARNING**

## Readiness

- Current controlled corrections readiness %: **78%**
- POS correction readiness %: **76%**
- Voucher/journal date control readiness %: **86%**
- Audit evidence readiness %: **92%**

## Certified Controls

| Control | Classification | Evidence |
|---|---|---|
| POS sales date filter | PASS | `fetch_pos_sales_for_correction()` filters POS sales by start/end date. |
| POS cashier filter | PASS | `fetch_pos_sales_for_correction()` filters by cashier/user and branch. |
| Dedicated salesman filter | NOT TESTED | No separate salesman field/workflow is implemented yet; current coverage treats the POS responsible user as `cashier`. |
| Historical POS sale lookup foundation | PASS with warning | Filter helper returns historical sale metadata without mutating sales; full sale-history UI is still pending. |
| Controlled POS date correction foundation | PASS with warning | `controlled_correct_pos_sale_metadata()` requires permission, reason, and audit evidence, but the operational UI/UAT is still pending. |
| Controlled POS cashier correction foundation | PASS with warning | Same helper updates cashier metadata and preserves sale/accounting rows; dedicated salesman assignment remains pending. |
| Unauthorized POS correction block | PASS | Roles without `correct_pos_sales` alias are denied and security event path is used. |
| Old/new audit evidence | PASS | Audit `before_after_summary` stores changed fields, old values, new values, reason, and sale reference. |
| Journal/report date consistency | PASS | Linked POS journal dates are synchronized when POS sale date is corrected. |
| Journal balance preservation | PASS | Correction does not alter journal lines or debit/credit equality. |
| Cashier closing preservation | PASS | Cashier assignment correction does not rewrite existing cashier closing records. |
| Voucher/journal date posting | PASS with warning | Posting dates are selectable by authorized posting roles; locked periods block posting. |
| Backdated/future date correction | WARNING | Controlled POS date correction foundation is implemented; broader posted voucher date correction should prefer reversal/repost workflow unless finance owner approves direct correction policy. |

## Clarification

- Controlled POS correction foundation added: service-layer date/cashier metadata correction with permission, reason, audit old/new values, branch/company scope, journal date synchronization, and journal balance preservation.
- Full operational POS correction UI/UAT still pending: users still need a clear browser workflow for finding historical sales and submitting controlled corrections.
- Salesman filtering is not separately implemented. Current filters use `pos_sales.cashier`, which represents the POS responsible user/cashier identity.
- Broad historical POS correction is not complete for all fields. Totals, line items, payment method, inventory effects, and posted accounting amounts are not freely editable and should use return/reversal/repost patterns.

## Controlled Correction Pattern

Every supported correction must include:

- Permission check.
- Correction reason.
- Audit trail.
- Original value.
- New value.
- Timestamp through audit log.
- Branch/company scope.
- Journal/report consistency check where accounting dates are affected.
- No silent deletion of accounting history.

## Remaining Blockers

1. Browser UI for POS correction still requires implementation/UAT sign-off for operational use.
2. Finance owner must decide whether posted voucher date corrections are allowed directly or only through reversal/repost.
3. Backdated/future correction policy must be documented in operating procedures.
