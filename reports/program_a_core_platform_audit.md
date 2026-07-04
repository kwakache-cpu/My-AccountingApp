# Program A — Core Platform Excellence Audit

**Date:** 2026-07-04  
**Scope:** Audit and mapping only — no production code changes  
**Governance:** AGENTS.md, DEVELOPER_RULES.md, REGRESSION_LOCKDOWN.md, EKA_CONSTITUTION.md  

---

## Executive Summary

EKA Enterprise Platform has a **mature accounting engine** with controlled source-document posting, strong regression coverage (706 tests), and deliberate performance deferrals on dashboard and financial reports. The core is **operationally complete** for SME daily use (POS, invoicing, payments, inventory, payroll, assets, reports) but has **linkage gaps** (customer/supplier IDs on payment rows, inventory receive without GL, taxation without view gate/tests, no notification engine) and **permission asymmetries** (POS posts without `post_accounting_document` when `user_role` is omitted).

**Strongest modules:** Accounting engine, POS sale identity, Financial Reports (Phase 1 lazy load), regression lockdown, dual-backend startup, subscription/Paystack flow.

**Weakest links:** Taxation (no tests, no view permission), payment subledger linkage, inventory receive → GL gap, notification/alert absence, Chart of Accounts view ungated.

---

## Module Audits (1–20)

### 1. Dashboard

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `modules.show_dashboard` (~17855), `_cached_dashboard_analytics_bundle`, `_cached_dashboard_receivable_payable_health`, `_fetch_dashboard_receivable_payable_health` |
| **Tables** | `journal_entries`, `journal_lines`, `inventory`, `pos_sales`, `invoices`, `customers`, `suppliers`, `payments` (via analytics helpers) |
| **Roles** | `view_dashboard` (Demo: static sample only) |
| **Business purpose** | Executive KPIs, sales/inventory analytics, on-demand AR/AP health, recent activity |
| **Accounting impact** | Read-only from ledger; legacy vs journal validation expander |
| **Inventory impact** | Low stock, fast/dead movers, expiry counts |
| **Cash/bank impact** | Cash/Bank balance KPI from trial balance |
| **Customer/supplier** | Deferred AR/AP aging, top debtors/creditors |
| **Tax impact** | None direct |
| **Audit trail** | Read-only activity display |
| **Reporting** | Feeds user into Financial Reports via Quick Actions |
| **Tests** | `test_dashboard_analytics.py`, `test_lv008_performance_autopsy.py`, `test_regression_lockdown.py`, `test_branch_session.py` |
| **Missing tests** | End-to-end dashboard render with mocked Streamlit; maintenance banner in current dashboard |
| **Missing links** | Maintenance status (`check_maintenance_status`) only in legacy dashboard, not `show_dashboard` |
| **Performance risks** | Main bundle cached 120s; AR/AP correctly deferred — **low risk if defer preserved** |
| **Security risks** | Low — read-only; branch scoping enforced |
| **UX gaps** | AR/AP requires explicit load button (intentional); Demo mode is static |
| **Recommended** | P2: surface maintenance notice on current dashboard; P1: document defer contract in UI caption |

---

### 2. POS

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_pos`, `process_pos_sale`, `_pos_checkout_write`, `_persist_pos_sale`, `_validate_pos_cart_at_checkout`, `_render_pos_suspended_sales_side_panel` |
| **Tables** | `pos_sales`, `pos_sale_lines`, `inventory`, `journal_entries`, `journal_lines`, `customer_transactions`, `counterparties`, `vouchers` (optional legacy) |
| **Roles** | `sell_pos`; discounts: `apply_pos_discount` / `approve_pos_discount`; returns: `process_pos_return` |
| **Business purpose** | Retail/service checkout, cash/credit/mobile money, suspended sales |
| **Accounting impact** | **Yes** — revenue + VAT + optional COGS via `post_accounting_impact`; `source_table=pos_sales` |
| **Inventory impact** | **Yes** — direct `inventory.qty` decrement |
| **Cash/bank** | Cash/Mobile Money → asset accounts |
| **Customer** | Credit sales → AR + `_record_customer_ledger_transaction` |
| **Tax impact** | VAT Payable on taxable lines |
| **Audit trail** | Checkout audit + controlled correction path |
| **Dashboard/reporting** | Feeds sales KPIs, payment method breakdown |
| **Tests** | `test_pos_sale_identity.py`, `test_erp_cross_module_workflows.py`, `test_controlled_corrections.py`, `test_inventory_enforcement.py`, `test_regression_lockdown.py`, +6 more |
| **Missing tests** | End-to-end cash POS journal line assertions in isolation; Mobile Money path |
| **Missing links** | No `stock_movements` row on POS decrement (inventory qty only) |
| **Performance risks** | Medium on large carts; scan feedback uses `components.html` (POS-only, not client dashboard) |
| **Security risks** | **Medium** — POS posting skips engine role check when `user_role` not passed; Cashier can post without `post_accounting_document` |
| **UX gaps** | Suspended sales side panel improved; credit customer selection required for On Credit |
| **Recommended** | P0: pass `user_role` to POS posting or document intentional Cashier exception; P1: optional `stock_movements` for POS |

---

### 3. Sales / Invoicing

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `financials.show_create_invoice_page`, `show_invoice_manager`, `show_sales_purchase` (modules), `apply_invoice_stock_effects`, `build_sales_tax_journal_lines` |
| **Tables** | `invoices`, `invoice_lines`, `inventory`, `stock_movements`, `journal_entries`, `journal_lines` |
| **Roles** | `create_invoice`; post: `post_accounting_document` |
| **Business purpose** | B2B sales invoicing, draft/submitted/posted states |
| **Accounting impact** | **Yes** when Posted — AR or Cash + revenue + VAT |
| **Inventory impact** | **Yes** — `apply_invoice_stock_effects` decrements stock + `stock_movements` |
| **Cash/bank** | If status Paid at post time |
| **Customer** | `customer_id` on invoice |
| **Tax impact** | VAT via journal lines |
| **Audit trail** | Posting + optional audit on actions |
| **Dashboard/reporting** | Sales journals, financial reports |
| **Tests** | `test_sales_invoice_identity.py`, `test_posting_workflow.py`, `test_erp_functional_certification.py`, `test_inventory_movements.py` |
| **Missing tests** | Draft→Posted state transition; partial payment allocation |
| **Missing links** | No automatic payment receipt link from invoice screen |
| **Performance risks** | Low |
| **Security risks** | Low — posting gated |
| **UX gaps** | Alternate tabbed UI in financials duplicates paths |
| **Recommended** | P2: consolidate invoice UI paths; P1: invoice → receive payment shortcut |

---

### 4. Purchases / Bills

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `modules.show_create_bill_page`, `build_purchase_journal_lines`, `show_sales_purchase(doc_type=Purchase)` |
| **Tables** | `bills`, `bill_lines`, `journal_entries`, `journal_lines` |
| **Roles** | `create_bill`; post: `post_accounting_document` |
| **Business purpose** | Supplier bill entry, expense/inventory/asset classification |
| **Accounting impact** | **Yes** when Posted — expense/inventory/asset + VAT Receivable; Cr AP or cash |
| **Inventory impact** | **No automatic stock receive** on bill post (classification only) |
| **Cash/bank** | If status Received (cash purchase) |
| **Supplier** | `supplier_id` on bill |
| **Tax impact** | VAT Receivable |
| **Audit trail** | On post |
| **Dashboard/reporting** | Purchase journals, AP aging |
| **Tests** | `test_ap_bills_identity.py`, `test_posting_workflow.py`, `test_erp_cross_module_workflows.py` |
| **Missing tests** | Bill → inventory receive workflow link |
| **Missing links** | **Bill does not increase inventory qty** — gap vs Purchase-to-Pay workflow |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | Users may expect bill to receive stock |
| **Recommended** | P1: document bill vs inventory receive distinction; P2: optional receive-on-post for inventory bills |

---

### 5. Inventory

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_inventory`, `_receive_inventory_stock`, `_insert_stock_movement_record`, `_post_inventory_import_opening_value`, import wizard helpers |
| **Tables** | `inventory`, `stock_movements`, `inventory_import_batches`, `suppliers`, `chart_of_accounts` |
| **Roles** | `view_inventory`, `manage_inventory`, `post_accounting_document` (import opening) |
| **Business purpose** | Item master, stock in/out, barcode, import, opening balances |
| **Accounting impact** | Opening stock, valued in/out, import opening — **not** on simple receive |
| **Inventory impact** | **Core** — qty, movements, expiry |
| **Cash/bank** | Indirect via offset accounts on valued movements |
| **Customer/supplier** | Supplier picklists |
| **Tax impact** | None direct |
| **Audit trail** | Movements + import batches |
| **Dashboard/reporting** | Inventory KPIs, low stock |
| **Tests** | `test_inventory_movements.py`, `test_inventory_enforcement.py`, `test_erp_cross_module_workflows.py` |
| **Missing tests** | Import opening post full flow; barcode scan regression |
| **Missing links** | **Receive stock without GL**; POS decrements qty without `stock_movements` |
| **Performance risks** | Medium on large catalogs (search cache exists) |
| **Security risks** | Low |
| **UX gaps** | Import wizard complex but functional |
| **Recommended** | P1: align receive vs bill/POS movement semantics; P2: unified movement ledger |

---

### 6. Customers / Receivables

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `financials.show_customers_page`, `show_accounts_receivable`, `show_aging(Receivable)`, `get_customer_balances`, `_record_customer_ledger_transaction` |
| **Tables** | `customers`, `customer_transactions`, `counterparties`, `invoices`, `payments`, `pos_sales` |
| **Roles** | `create_customer`, `receive_customer_payment`, `view_reports` (aging) |
| **Business purpose** | Customer master, balances, aging, receipts |
| **Accounting impact** | Via invoices, POS credit, payments — not standalone on customer CRUD |
| **Inventory impact** | None |
| **Cash/bank** | Via receive payment |
| **Customer** | **Core** |
| **Tax impact** | Indirect via invoices |
| **Audit trail** | Customer CRUD + payment audit |
| **Dashboard/reporting** | AR KPIs (deferred), aging reports |
| **Tests** | `test_erp_functional_certification.py` (AR lifecycle), `test_posting_workflow.py` |
| **Missing tests** | Dedicated customer page tests; `customer_transactions` integrity |
| **Missing links** | **Payment row may omit `customer_id`** (only on journal) |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | AR aging on dashboard is on-demand |
| **Recommended** | P0: persist `customer_id` on `payments` INSERT; P1: customer balance drill-down from dashboard |

---

### 7. Suppliers / Payables

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `financials.show_suppliers_page`, `show_accounts_payable`, `show_aging(Payable)` |
| **Tables** | `suppliers`, `bills`, `payments` |
| **Roles** | `create_supplier`, `make_supplier_payment`, `create_bill` |
| **Business purpose** | Supplier master, AP, payments |
| **Accounting impact** | Via bills and supplier payments |
| **Inventory impact** | Indirect (supplier on receive) |
| **Cash/bank** | Supplier payments |
| **Supplier** | **Core** |
| **Tax impact** | Via bills (VAT Receivable) |
| **Audit trail** | On payments and bills |
| **Dashboard/reporting** | AP deferred load |
| **Tests** | `test_ap_bills_identity.py`, `test_posting_workflow.py` |
| **Missing tests** | Supplier page dedicated tests |
| **Missing links** | **Payment row may omit `supplier_id`** |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | Similar to AR |
| **Recommended** | P0: persist `supplier_id` on supplier payments; P1: AP drill-down |

---

### 8. Banking / Cash

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_banking`, `engine_get_trial_balance`, owner equity/loan/transfer posting blocks |
| **Tables** | `payments`, `journal_entries`, `journal_lines`, `chart_of_accounts`, `customers`, `suppliers` |
| **Roles** | `view_banking`, `post_accounting_document`, `manage_owner_equity_transactions`, `manage_loan_transactions`, `manage_cash_bank_transfers`, `void_or_reverse_document` |
| **Business purpose** | Cash/bank balances, receipts, payments, transfers, equity, loans |
| **Accounting impact** | **Yes** — all types post to journal; `source_table=payments` |
| **Inventory impact** | None |
| **Cash/bank** | **Core** |
| **Customer/supplier** | Pickers for receipt/payment types |
| **Tax impact** | None direct |
| **Audit trail** | Yes + reversal panel |
| **Dashboard/reporting** | Cash book, trial balance, cash KPI |
| **Tests** | `test_payments_identity.py`, `test_permission_security.py` |
| **Missing tests** | Transfer/equity/loan journal line tests |
| **Missing links** | Duplicates dedicated receive/supplier payment pages |
| **Performance risks** | Low |
| **Security risks** | Low — well permissioned |
| **UX gaps** | Many transaction types on one page |
| **Recommended** | P2: workflow wizards per banking transaction type |

---

### 9. General Journal

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_journal_entries`, manual entry via `post_journal_entry`, `post_transaction`, `create_journal_entry` |
| **Tables** | `journal_entries`, `journal_lines`, `chart_of_accounts` |
| **Roles** | `view_reports`, `post_accounting_document` (manual) |
| **Business purpose** | Read ledger; manual adjusting entries with Suspense offset |
| **Accounting impact** | **Yes** — manual posts |
| **Inventory impact** | None |
| **Cash/bank** | Via line accounts |
| **Customer/supplier** | Optional on lines |
| **Tax impact** | Manual only |
| **Audit trail** | Engine + period controls |
| **Dashboard/reporting** | General ledger reports |
| **Tests** | `test_journal_entry_identity.py`, `test_accounting_core.py`, `test_period_locking_controls.py` |
| **Missing tests** | Manual journal UI flow |
| **Missing links** | Suspense offset pattern may confuse bookkeepers |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | Read-only emphasis good; manual entry buried |
| **Recommended** | P2: guided adjusting entry templates |

---

### 10. Chart of Accounts

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_chart_of_accounts`, `show_chart_of_accounts_page`, `engine_get_or_create_account`, `get_chart_of_accounts_diagnostics` |
| **Tables** | `chart_of_accounts` |
| **Roles** | View: **ungated**; add: `manage_chart_of_accounts` |
| **Business purpose** | Account structure, add accounts |
| **Accounting impact** | Indirect — accounts used by all posting |
| **Inventory impact** | Inventory account definitions |
| **Cash/bank** | Cash/Bank account types |
| **Customer/supplier** | AR/AP accounts |
| **Tax impact** | Tax control accounts via `ensure_tax_control_accounts` |
| **Audit trail** | Minimal on add |
| **Dashboard/reporting** | Underpins all reports |
| **Tests** | `test_insert_identity_portability.py`, `test_postgres_e2e_write_execution_guard.py` |
| **Missing tests** | COA diagnostics; view permission |
| **Missing links** | None critical |
| **Performance risks** | Low |
| **Security risks** | **Medium** — view ungated (read-only but exposes structure) |
| **UX gaps** | Diagnostics admin-oriented |
| **Recommended** | P1: add `view_chart_of_accounts` permission; P2: account usage hints |

---

### 11. Financial Reports

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `financials.show_financial_reports`, `_cached_financial_report_by_type`, `_cached_ledger_balance_snapshot`, `_lazy_csv_button`, `get_ledger_balances` |
| **Tables** | `journal_entries`, `journal_lines`, `chart_of_accounts`, `fixed_assets` (depreciation schedule) |
| **Roles** | `view_reports` |
| **Business purpose** | Trial balance, P&L, balance sheet, cash flow, equity, depreciation, journals |
| **Accounting impact** | Read-only aggregation |
| **Inventory impact** | None direct |
| **Cash/bank** | Cash flow, cash book |
| **Customer/supplier** | AR/AP in balance sheet / aging inputs |
| **Tax impact** | Via P&L/BS accounts |
| **Audit trail** | None on read |
| **Dashboard/reporting** | **Core reporting hub** |
| **Tests** | `test_lv009_phase1_financial_reports_speed.py` (10 tests), `test_reporting_integrity.py`, `test_regression_lockdown.py` |
| **Missing tests** | Report total parity under PostgreSQL at scale |
| **Missing links** | None critical post-Phase 1 |
| **Performance risks** | **Was critical** — mitigated by lazy load; PG large ledger still hot |
| **Security risks** | Low |
| **UX gaps** | Lazy radio vs tabs — acceptable tradeoff |
| **Recommended** | P2: PG benchmark harness in CI; preserve Phase 1 patterns |

---

### 12. Tax / VAT / NHIL

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_taxation`, `ensure_tax_control_accounts`, `_tax_control_balance`, tax settlement post |
| **Tables** | `chart_of_accounts`, `journal_entries`, `journal_lines` (read); settlement → `payments`/journal |
| **Roles** | **No view gate**; post: `post_accounting_document` |
| **Business purpose** | Ghana VAT/NHIL/GETFund report + settlement |
| **Accounting impact** | Settlement posts Dr tax liability / Cr cash |
| **Inventory impact** | None |
| **Cash/bank** | Settlement payment |
| **Customer/supplier** | None |
| **Tax impact** | **Core module purpose** |
| **Audit trail** | On settlement post |
| **Dashboard/reporting** | Reconciliation vs sales revenue |
| **Tests** | **None dedicated** |
| **Missing tests** | **All taxation flows** |
| **Missing links** | NHIL/GETFund depend on correct COA balances |
| **Performance risks** | Low |
| **Security risks** | **Medium** — ungated view |
| **UX gaps** | Technical account names |
| **Recommended** | P0: add tests + view permission; P1: plain-language tax summary |

---

### 13. Payroll

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_payroll`, `_calculate_payroll_values`, `_build_payroll_journal_lines`, payslip HTML |
| **Tables** | `payroll`, `payroll_records`, `journal_entries` |
| **Roles** | `view_payroll`, `manage_payroll`, `void_or_reverse_document` |
| **Business purpose** | Ghana payroll (SSNIT, PAYE), accrual posting, void/reverse |
| **Accounting impact** | **Yes** — `source_table=payroll` |
| **Inventory impact** | None |
| **Cash/bank** | Payment account mapping |
| **Customer/supplier** | None |
| **Tax impact** | PAYE/SSNIT liabilities |
| **Audit trail** | Void/reverse audited |
| **Dashboard/reporting** | Expense in P&L |
| **Tests** | `test_payroll_fixed_assets_identity.py`, `test_postgres_final_certification.py` |
| **Missing tests** | PAYE band calculations; payslip generation |
| **Missing links** | None critical |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | Print preview uses HTML |
| **Recommended** | P1: payroll calculation unit tests; P2: employee master linkage |

---

### 14. Assets

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_fixed_assets`, `run_straight_line_depreciation`, `_build_fixed_asset_acquisition_lines` |
| **Tables** | `fixed_assets`, `suppliers`, `journal_entries` |
| **Roles** | `view_fixed_assets`, `manage_fixed_assets`, `void_or_reverse_document` |
| **Business purpose** | Asset register, acquisition post, depreciation run |
| **Accounting impact** | **Yes** — acquisition + depreciation journals |
| **Inventory impact** | None (distinct from inventory) |
| **Cash/bank** | Acquisition payment types |
| **Customer/supplier** | Supplier on credit purchase |
| **Tax impact** | None direct |
| **Audit trail** | Reverse acquisition |
| **Dashboard/reporting** | Depreciation schedule in Financial Reports |
| **Tests** | `test_payroll_fixed_assets_identity.py`, `test_postgres_final_certification.py` (source link certification note) |
| **Missing tests** | Full depreciation run integration |
| **Missing links** | Depreciation source linkage flagged in certification tests |
| **Performance risks** | Low |
| **Security risks** | Low |
| **UX gaps** | Legacy alternate UI exists |
| **Recommended** | P1: certify depreciation `source_table` linkage; P2: asset disposal workflow |

---

### 15. Audit Trail

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_audit_trail`, `_build_audit_trail_query`, `log_audit_action` (platform-wide) |
| **Tables** | `audit_logs` |
| **Roles** | `view_audit_trail` |
| **Business purpose** | Forensic review, export |
| **Accounting impact** | None (observes) |
| **Inventory impact** | None |
| **Cash/bank** | None |
| **Customer/supplier** | None |
| **Tax impact** | None |
| **Audit trail** | **Core** |
| **Dashboard/reporting** | None |
| **Tests** | `test_permission_security.py`, `test_postgres_display_performance_sweep.py` |
| **Missing tests** | Branch-scoped audit filtering |
| **Missing links** | Not all modules log equally (consistent `log_audit_action` coverage varies) |
| **Performance risks** | Medium on large audit tables |
| **Security risks** | Low — gated |
| **UX gaps** | Export useful; filters basic |
| **Recommended** | P2: standardize audit logging on all write paths |

---

### 16. Roles / Permissions

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `ENTERPRISE_ROLE_PERMISSIONS`, `user_has_permission`, `require_permission`, `_record_permission_security_event` |
| **Tables** | `users`, `audit_logs`, `system_logs` |
| **Roles** | 15+ enterprise roles (Dev, Master Admin, System Admin, Owner, Accountant, Cashier, …) |
| **Business purpose** | Least-privilege access control |
| **Accounting impact** | Gates posting, period controls, void/reverse |
| **Inventory impact** | Gates manage_inventory |
| **Cash/bank** | Banking permission granularity |
| **Customer/supplier** | create_customer, create_supplier |
| **Tax impact** | post_accounting_document |
| **Audit trail** | Permission denials logged |
| **Dashboard/reporting** | view_dashboard, view_reports |
| **Tests** | `test_permission_security.py`, `test_erp_production_readiness.py`, `test_final_go_live_contracts.py`, `test_branch_module_governance.py` |
| **Missing tests** | POS posting role bypass (document or fix) |
| **Missing links** | System Admin narrow vs Master Admin — documented in matrix |
| **Performance risks** | None |
| **Security risks** | **Medium** — POS posting asymmetry |
| **UX gaps** | Permission errors user-friendly |
| **Recommended** | P0: resolve POS `user_role` posting gate; P1: permission matrix doc for clients |

---

### 17. System Configuration

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_company_setup`, branch deployment, staff creation forms |
| **Tables** | `companies`, `branches`, `users`, `branch_module_grants` |
| **Roles** | `manage_company`, `manage_branches`, `manage_users` |
| **Business purpose** | Company profile, barcode mode, branches, staff |
| **Accounting impact** | None direct (no DDL on render — **fixed**) |
| **Inventory impact** | Barcode input mode setting |
| **Cash/bank** | None |
| **Customer/supplier** | None |
| **Tax impact** | None |
| **Audit trail** | Settings updates logged |
| **Dashboard/reporting** | None |
| **Tests** | `test_urgent_system_config_and_migration_visibility.py`, `test_regression_lockdown.py` |
| **Missing tests** | Staff creation UI flow |
| **Missing links** | Staff limited to Bookkeeper/Staff roles in form |
| **Performance risks** | Low |
| **Security risks** | Low — DDL removed from render |
| **UX gaps** | Cannot create all role types from company setup |
| **Recommended** | P2: role template picker for admins |

---

### 18. Gatekeeper / AI Assistant

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | Dev block in `app.py` (~2651); `show_ai_assistant`; `render_runtime_admin_diagnostics_suite`; `request_ai_chat_completion` |
| **Tables** | Platform-wide: `companies`, `audit_logs`, `subscriptions`, backup metadata |
| **Roles** | Dev: all; client AI: `use_ai_assistant` |
| **Business purpose** | Platform ops (Dev); client decision support (AI) |
| **Accounting impact** | Read-only context for AI (invoices, expenses, payroll snapshot) |
| **Inventory impact** | None in AI snapshot |
| **Cash/bank** | None direct |
| **Customer/supplier** | None direct |
| **Tax impact** | None |
| **Audit trail** | Dev actions logged |
| **Dashboard/reporting** | Dev metrics separate from client dashboard |
| **Tests** | `test_regression_lockdown.py`, `test_lv006/007` admin gating |
| **Missing tests** | AI assistant page; Dev gatekeeper render |
| **Missing links** | **tab3 "Manual Deployment" declared but empty** (content in tab1) |
| **Performance risks** | Dev overview heavy — migration cleanup now lazy |
| **Security risks** | Low if diagnostics stay gated |
| **UX gaps** | "Gatekeeper Admin" AI page name vs Dev dashboard confusion |
| **Recommended** | P1: rename client AI page; P2: wire tab3 or remove label |

---

### 19. Notifications / Alerts

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | **No dedicated module** — scattered `st.warning`, `st.info`, `check_license_expiry_with_grace`, `check_maintenance_status` |
| **Tables** | `maintenance_settings` (legacy dashboard only) |
| **Roles** | N/A |
| **Business purpose** | Subscription expiry, permission denials, health warnings |
| **Accounting impact** | None |
| **Inventory impact** | Low stock on dashboard only — not proactive |
| **Cash/bank** | None |
| **Customer/supplier** | None |
| **Tax impact** | None |
| **Audit trail** | None for notifications |
| **Dashboard/reporting** | Inline warnings only |
| **Tests** | `test_subscription_billing.py` (renewal block) |
| **Missing tests** | All notification paths |
| **Missing links** | **Entire notification engine absent** |
| **Performance risks** | N/A |
| **Security risks** | Low |
| **UX gaps** | No in-app notification center, email queue, or alerts |
| **Recommended** | P2: notification engine design; P1: subscription expiry UX consistency |

---

### 20. Onboarding / Subscription / Paystack

| Dimension | Finding |
|-----------|---------|
| **Main files/functions** | `show_onboarding_payment`, `initialize_paystack_payment`, `verify_paystack_payment`, `show_subscription_renewal_page`, `ensure_company_trial_subscription`, `activate_company_subscription` |
| **Tables** | `companies`, `subscriptions`, `subscription_payments` |
| **Roles** | Public registration; renewal blocks non-Dev until paid |
| **Business purpose** | Trial signup, Paystack checkout, license activation |
| **Accounting impact** | Platform revenue tracking (admin), not client GL |
| **Inventory impact** | None |
| **Cash/bank** | Paystack external |
| **Customer/supplier** | Company as tenant |
| **Tax impact** | None client-side |
| **Audit trail** | Subscription events |
| **Dashboard/reporting** | Dev billing snapshot |
| **Tests** | `test_subscription_billing.py`, `test_regression_lockdown.py`, `test_company_subscription_dml_portability.py` |
| **Missing tests** | Webhook handler integration |
| **Missing links** | None critical |
| **Performance risks** | Low |
| **Security risks** | Low — secrets from env |
| **UX gaps** | Markdown checkout link (intentional hardening) |
| **Recommended** | P2: webhook test harness; P1: post-registration welcome path |

---

## Cross-Cutting Findings

### Accounting Engine (strength)

- Controlled source tables with duplicate-post blocking
- Period lock integration
- Source document sync (`posted_entry_id`)
- Reversal/void discipline

### Regression Lockdown (strength)

- 706 tests; 18 protected workflows
- Phase 1 financial reports and dashboard defer preserved

### Systemic Gaps

1. Payment rows missing `customer_id` / `supplier_id` persistence
2. Inventory movement semantics inconsistent (POS vs invoice vs receive)
3. Taxation untested and ungated
4. No notification engine
5. POS posting role bypass
6. Bill post does not receive inventory

---

*Program A Core Platform Audit — mapping only, no code changes.*
