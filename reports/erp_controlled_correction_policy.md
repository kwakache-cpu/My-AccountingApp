# ERP Controlled Correction Policy

**Phase:** 5B.18C  
**Classification:** **PASS with warnings**

## Policy

Corrections must never silently delete or rewrite accounting history. Every operational correction must use a controlled workflow with:

- Permission required.
- Correction reason required.
- Original value recorded.
- New value recorded.
- Audit trail created.
- Branch/company scope enforced.
- Period-lock rules respected.
- Accounting impact verified.

## POS Correction Policy

| Correction Type | Status | Required Workflow |
|---|---|---|
| Sale date metadata | Supported with controls | Use controlled POS correction. Linked journal dates are synchronized when applicable. |
| Cashier/responsible-user metadata | Supported with controls | Use controlled POS correction. Cashier closings are not rewritten. |
| Dedicated salesman reassignment | Partial | Currently maps to responsible-user/cashier identity. Add a separate field only if the business requires it. |
| Sale totals | Not free-editable | Use return, reversal, void, or reposting workflow. |
| Line items / inventory quantities | Not free-editable | Use return/reversal/repost with inventory and journal verification. |
| Posted accounting amounts | Not free-editable | Use reversal/repost or approved accounting correction workflow. |

## Locked Period Policy

- Normal users cannot correct a POS sale into a locked period.
- Privileged users with reopen/period-control authority can override only with a reason.
- Locked-period overrides are audit logged through the controlled correction audit payload.
- Finance should review all backdated and locked-period correction reports before close.

## Manual Actions Required

- Finance owner must sign off whether responsible-user attribution is enough or a separate salesman field is required.
- Management must approve period-lock override policy before production go-live.
- UAT must verify accountants understand correction vs deletion.
