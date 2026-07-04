# Program A — Workflow Trace Matrix

**Date:** 2026-07-04  
**Legend:** ✅ Yes / ⚠️ Partial / ❌ No / — N/A  
**Status:** **Complete** = end-to-end with tests | **Partial** = works with gaps | **Missing** = not implemented

---

## Summary Matrix

| # | Workflow | Journal | Ledgers | Fin Reports | Inventory | Cust/Supp Bal | Dashboard | Audit | Permissions | Tests | Status |
|---|----------|---------|---------|-------------|-----------|---------------|-----------|-------|-------------|-------|--------|
| 1 | POS cash sale | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ | ⚠️ | ✅ | **Complete** |
| 2 | POS credit sale | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | **Complete** |
| 3 | Customer invoice | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | **Complete** |
| 4 | Customer receipt | ✅ | ✅ | ✅ | — | ⚠️ | ✅ | ✅ | ✅ | ✅ | **Partial** |
| 5 | Supplier bill | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ⚠️ | ✅ | ✅ | **Partial** |
| 6 | Supplier payment | ✅ | ✅ | ✅ | — | ⚠️ | ✅ | ✅ | ✅ | ✅ | **Partial** |
| 7 | Inventory purchase | ⚠️ | ⚠️ | ⚠️ | ✅ | — | ✅ | ✅ | ✅ | ⚠️ | **Partial** |
| 8 | Inventory sale | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ✅ | **Complete** |
| 9 | Journal entry | ✅ | ✅ | ✅ | — | — | ✅ | ⚠️ | ✅ | ✅ | **Complete** |
| 10 | Payroll posting | ✅ | ✅ | ✅ | — | — | ✅ | ✅ | ✅ | ⚠️ | **Complete** |
| 11 | Asset acquisition | ✅ | ✅ | ✅ | — | ⚠️ | — | ✅ | ✅ | ⚠️ | **Complete** |
| 12 | Depreciation run | ✅ | ✅ | ✅ | — | — | — | ⚠️ | ✅ | ⚠️ | **Partial** |
| 13 | VAT/NHIL reporting | ⚠️ | ✅ | ⚠️ | — | — | — | ⚠️ | ⚠️ | ❌ | **Partial** |
| 14 | Bank/cash movement | ✅ | ✅ | ✅ | — | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | **Complete** |
| 15 | User / role assignment | — | — | — | — | — | — | ✅ | ✅ | ✅ | **Complete** |
| 16 | Company onboarding / subscription | — | — | — | — | — | — | ⚠️ | ✅ | ✅ | **Complete** |

---

## Detailed Workflow Traces

### 1. POS Cash Sale

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Revenue (+ VAT, optional COGS) — `source_table=pos_sales`, `source_type=POS Sale` / `POS COGS` |
| Updates ledgers? | ✅ Cash Dr, Revenue/VAT Cr; COGS/Inventory if cost tracked |
| Affects financial reports? | ✅ P&L, TB, cash flow via ledger |
| Affects inventory? | ✅ Direct `inventory.qty` decrement (no `stock_movements` row) |
| Customer/supplier balances? | — Cash path, no AR |
| Affects dashboard? | ✅ Sales KPIs, payment method chart |
| Audit trail? | ✅ Checkout + optional audit log |
| Permissions? | ⚠️ `sell_pos` only; engine role check skipped if `user_role` omitted |
| Tests? | ✅ `test_pos_sale_identity`, `test_erp_cross_module_workflows`, `test_regression_lockdown` |
| **Status** | **Complete** (permission note) |

**Path:** `show_pos` → `process_pos_sale` → `_pos_checkout_write` → `_persist_pos_sale` → `post_journal_entry`

---

### 2. POS Credit Sale

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Same as cash; AR Dr instead of Cash |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ |
| Affects inventory? | ✅ |
| Customer/supplier balances? | ✅ `_record_customer_ledger_transaction` + counterparty |
| Affects dashboard? | ✅ |
| Audit trail? | ✅ |
| Permissions? | ⚠️ Same as cash + credit customer required in UI |
| Tests? | ✅ `test_erp_cross_module_workflows`, `test_erp_functional_certification` |
| **Status** | **Complete** |

---

### 3. Customer Invoice

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ When Posted — `source_table=invoices`, `source_type=Invoice` |
| Updates ledgers? | ✅ AR or Cash + Revenue + VAT |
| Affects financial reports? | ✅ |
| Affects inventory? | ✅ `apply_invoice_stock_effects` + `stock_movements` |
| Customer/supplier balances? | ✅ `customer_id` on invoice |
| Affects dashboard? | ✅ Sales metrics |
| Audit trail? | ⚠️ On post; draft saves no GL |
| Permissions? | ✅ `create_invoice` + `post_accounting_document` |
| Tests? | ✅ `test_sales_invoice_identity`, `test_posting_workflow`, `test_erp_functional_certification` |
| **Status** | **Complete** |

**Path:** `show_create_invoice_page` → INSERT invoice → optional stock → `post_journal_entry`

---

### 4. Customer Receipt / Payment

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Dr Cash/Bank/Mobile, Cr AR — `source_table=payments` |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ Cash book, AR reduction |
| Affects inventory? | — |
| Customer/supplier balances? | ⚠️ Journal has customer; **payments row may omit customer_id** |
| Affects dashboard? | ✅ Cash KPI, deferred AR |
| Audit trail? | ✅ `log_audit_action` on post |
| Permissions? | ✅ `receive_customer_payment` + `post_accounting_document` |
| Tests? | ✅ `test_payments_identity`, `test_posting_workflow`, `test_erp_functional_certification` |
| **Status** | **Partial** — subledger persistence gap |

**Path:** `show_receive_payment_page` OR `show_banking` (Customer Receipt)

---

### 5. Supplier Bill

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Expense/Inventory/Asset + VAT Receivable; Cr AP or Cash |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ AP, P&L |
| Affects inventory? | ❌ **No qty increase on post** — classification only |
| Customer/supplier balances? | ✅ `supplier_id` on bill |
| Affects dashboard? | ✅ AP (deferred) |
| Audit trail? | ⚠️ On post |
| Permissions? | ✅ `create_bill` + `post_accounting_document` |
| Tests? | ✅ `test_ap_bills_identity`, `test_posting_workflow` |
| **Status** | **Partial** — Purchase-to-Pay inventory gap |

**Path:** `show_create_bill_page` → INSERT bill → `post_journal_entry`

---

### 6. Supplier Payment

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Dr AP, Cr Cash/Bank — `source_table=payments` |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ |
| Affects inventory? | — |
| Customer/supplier balances? | ⚠️ Journal has supplier; **payments row may omit supplier_id** |
| Affects dashboard? | ✅ |
| Audit trail? | ✅ |
| Permissions? | ✅ `make_supplier_payment` + `post_accounting_document` |
| Tests? | ✅ `test_payments_identity`, `test_posting_workflow` |
| **Status** | **Partial** — subledger persistence gap |

---

### 7. Inventory Purchase (receive stock)

| Question | Answer |
|----------|--------|
| Posts to journal? | ⚠️ Only on **valued** Stock In/Out or opening balance — not simple receive |
| Updates ledgers? | ⚠️ When valued movement posted |
| Affects financial reports? | ⚠️ When posted |
| Affects inventory? | ✅ `_receive_inventory_stock` updates qty + `stock_movements` |
| Customer/supplier balances? | — |
| Affects dashboard? | ✅ Inventory value KPI |
| Audit trail? | ✅ Movement records |
| Permissions? | ✅ `manage_inventory` |
| Tests? | ⚠️ `test_inventory_movements` (receive only, no GL) |
| **Status** | **Partial** — receive without automatic GL; bill not linked |

**Gap:** Bill post + inventory receive are separate steps with no enforced link.

---

### 8. Inventory Sale (via invoice or POS)

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Via parent sale document |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ COGS when applicable |
| Affects inventory? | ✅ POS: qty only; Invoice: qty + stock_movements |
| Customer/supplier balances? | ⚠️ Credit paths only |
| Affects dashboard? | ✅ |
| Audit trail? | ✅ |
| Permissions? | ✅ |
| Tests? | ✅ Multiple POS + invoice tests |
| **Status** | **Complete** (movement record inconsistency) |

---

### 9. Journal Entry (manual)

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Manual entry with Suspense offset |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ All reports |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | ✅ Recent activity |
| Audit trail? | ⚠️ Engine level; manual entry logging varies |
| Permissions? | ✅ `view_reports` + `post_accounting_document` |
| Tests? | ✅ `test_accounting_core`, `test_journal_entry_identity` |
| **Status** | **Complete** |

---

### 10. Payroll Posting

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Salary expense, PAYE, SSNIT, net payable/cash |
| Updates ledgers? | ✅ `source_table=payroll` |
| Affects financial reports? | ✅ P&L expense |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | — Direct KPI limited |
| Audit trail? | ✅ Void/reverse audited |
| Permissions? | ✅ `manage_payroll`, `void_or_reverse_document` |
| Tests? | ⚠️ Identity + certification; limited calculation tests |
| **Status** | **Complete** |

---

### 11. Asset Acquisition

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ `_build_fixed_asset_acquisition_lines` |
| Updates ledgers? | ✅ Fixed asset + cash/AP |
| Affects financial reports? | ✅ Balance sheet |
| Affects inventory? | — |
| Customer/supplier balances? | ⚠️ Supplier on credit acquisition |
| Affects dashboard? | — |
| Audit trail? | ✅ Reverse path |
| Permissions? | ✅ `manage_fixed_assets` |
| Tests? | ⚠️ Identity tests; acquisition flow partial |
| **Status** | **Complete** |

---

### 12. Depreciation Run

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ Depreciation expense / accumulated depreciation |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ Depreciation schedule report |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | — |
| Audit trail? | ⚠️ Source linkage certification flagged in tests |
| Permissions? | ✅ `manage_fixed_assets` |
| Tests? | ⚠️ `test_postgres_final_certification` notes source link gap |
| **Status** | **Partial** |

---

### 13. VAT / NHIL Reporting

| Question | Answer |
|----------|--------|
| Posts to journal? | ⚠️ Report is read-only; settlement posts payment |
| Updates ledgers? | ✅ Settlement reduces tax liability |
| Affects financial reports? | ⚠️ Via tax control accounts in TB |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | — |
| Audit trail? | ⚠️ On settlement only |
| Permissions? | ⚠️ **No view gate**; post requires `post_accounting_document` |
| Tests? | ❌ **None** |
| **Status** | **Partial** |

---

### 14. Bank / Cash Movement

| Question | Answer |
|----------|--------|
| Posts to journal? | ✅ All banking types via `show_banking` |
| Updates ledgers? | ✅ |
| Affects financial reports? | ✅ Cash book, TB |
| Affects inventory? | — |
| Customer/supplier balances? | ⚠️ Via receipt/payment types |
| Affects dashboard? | ✅ Cash/Bank KPI |
| Audit trail? | ✅ + reversal panel |
| Permissions? | ✅ Granular banking permissions |
| Tests? | ⚠️ `test_payments_identity` — not all transaction types |
| **Status** | **Complete** |

---

### 15. User Creation / Role Assignment

| Question | Answer |
|----------|--------|
| Posts to journal? | — |
| Updates ledgers? | — |
| Affects financial reports? | — |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | — Access only |
| Audit trail? | ✅ User create/update logged |
| Permissions? | ✅ `manage_users`, branch assignment tests |
| Tests? | ✅ `test_branch_module_governance`, `test_permission_security`, `test_regression_lockdown` |
| **Status** | **Complete** |

**Paths:** `show_company_setup` staff form; `show_branch_management`; admin recovery panel

---

### 16. Company Onboarding / Subscription

| Question | Answer |
|----------|--------|
| Posts to journal? | — Client GL unaffected |
| Updates ledgers? | — |
| Affects financial reports? | — |
| Affects inventory? | — |
| Customer/supplier balances? | — |
| Affects dashboard? | — Until licensed |
| Audit trail? | ⚠️ Subscription events; platform audit |
| Permissions? | ✅ Renewal blocks ERP until active |
| Tests? | ✅ `test_subscription_billing`, `test_regression_lockdown`, `test_company_subscription_dml_portability` |
| **Status** | **Complete** |

**Path:** `show_onboarding_payment` → trial → Paystack → `verify_paystack_payment` → `activate_company_subscription`

---

## Workflow Completeness Summary

| Status | Count | Workflows |
|--------|-------|-----------|
| **Complete** | 10 | POS cash/credit, invoice, journal, payroll, asset acq, bank/cash, inventory sale, user/role, onboarding |
| **Partial** | 6 | Customer receipt, supplier bill, supplier payment, inventory purchase, depreciation, VAT/NHIL |
| **Missing** | 0 | — |

---

## Highest-Impact Trace Gaps

1. **Payment subledger IDs** — workflows 4 & 6
2. **Bill → inventory receive** — workflows 5 & 7
3. **Taxation test coverage** — workflow 13
4. **POS permission/posting gate** — workflows 1 & 2
5. **Depreciation source linkage certification** — workflow 12

---

*Program A Workflow Trace Matrix — audit only.*
