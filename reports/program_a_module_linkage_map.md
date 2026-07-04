# Program A — Module Linkage Map

**Date:** 2026-07-04  
**Purpose:** Show how ERP modules connect through data, accounting, and workflows.

---

## Platform Layer Diagram

```
                    ┌─────────────────────────────────────┐
                    │           app.py (Shell)             │
                    │  login · routing · Gatekeeper Dev    │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────────┐
│  modules.py     │    │   financials.py     │    │ enterprise_      │
│  POS · Inventory│    │  Invoices · Payments│    │ services.py      │
│  Payroll · Assets│   │  Customers · Reports│    │ Health · Ops     │
│  Banking · Setup │    │  Suppliers · Ledger │    │ Console          │
└────────┬────────┘    └──────────┬──────────┘    └────────┬─────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  ▼
                    ┌─────────────────────────────┐
                    │    accounting_engine.py      │
                    │  post_accounting_impact      │
                    │  periods · COA · reports     │
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │       database.py            │
                    │  SQLite / PostgreSQL · startup │
                    └─────────────────────────────┘
```

---

## Controlled Source Document Map

The accounting engine treats these as authoritative posting sources:

| source_table | Modules | Journal source_type examples | Links to |
|--------------|---------|------------------------------|----------|
| `pos_sales` | POS | POS Sale, POS COGS | inventory, customers (credit), dashboard |
| `pos_returns` | POS returns | POS Return | inventory, pos_sales |
| `invoices` | Sales | Invoice | customers, inventory, stock_movements |
| `bills` | Purchases | Bill | suppliers, AP |
| `payments` | Banking, AR, AP | Customer Receipt, Supplier Payment, Tax Settlement, transfers | cash/bank accounts |
| `payroll` | Payroll | Payroll | tax liabilities |
| `fixed_assets` | Assets | Acquisition, Depreciation | suppliers, BS |
| `stock_movements` | Inventory | (via valued movements) | inventory |
| `vouchers` | Legacy optional | Voucher | transitional |
| `inventory_import_batches` | Inventory import | Opening | inventory, COA |

**Linkage rule:** Every posted document should set `posted_entry_id` (and related fields) on the source row via `_sync_source_document_posting`.

---

## Order to Cash Linkage

```
Customer Master (customers)
        │
        ├──► POS Credit ──► pos_sales ──► journal ──► AR / Revenue / VAT
        │         │              │
        │         │              └──► inventory.qty ↓
        │         └──► customer_transactions
        │
        ├──► POS Cash ──► pos_sales ──► journal ──► Cash / Revenue / VAT
        │
        ├──► Invoice ──► invoices ──► journal ──► AR / Revenue / VAT
        │         │           │
        │         │           └──► stock_movements + inventory ↓
        │         └──► invoice_lines
        │
        └──► Receive Payment ──► payments ──► journal ──► Cash / AR ↓
                    │
                    └──► [GAP: customer_id not always on payments row]

Dashboard ◄── journal_entries, pos_sales, invoices (cached analytics)
Financial Reports ◄── journal_lines + chart_of_accounts
```

---

## Purchase to Pay Linkage

```
Supplier Master (suppliers)
        │
        ├──► Bill ──► bills ──► journal ──► Expense/Inventory/Asset + VAT / AP
        │         │
        │         └──► bill_lines
        │         │
        │         └──► [GAP: no inventory qty ↑ on post]
        │
        ├──► Inventory Receive ──► stock_movements + inventory ↑
        │         │
        │         └──► [GAP: no automatic GL unless valued In/Out]
        │
        └──► Supplier Payment ──► payments ──► journal ──► AP ↓ / Cash ↓
                    │
                    └──► [GAP: supplier_id not always on payments row]

Dashboard ◄── AP aging (deferred)
Financial Reports ◄── AP in balance sheet, purchase journals
```

---

## Inventory Lifecycle Linkage

```
Item Master (inventory)
        │
        ├──► Receive Stock ──► qty ↑, stock_movements (no GL by default)
        ├──► Stock In/Out (valued) ──► journal + stock_movements
        ├──► Opening / Import ──► journal (Inventory vs offset)
        ├──► POS Sale ──► qty ↓ (no stock_movements)
        ├──► Invoice ──► qty ↓ + stock_movements
        └──► Return ──► pos_returns ──► journal + qty ↑

Dashboard ◄── inventory value, low stock, expiry, movement trends
Financial Reports ◄── inventory GL vs register (reporting trust checks)
```

**Linkage gap:** Three different inventory decrement patterns (POS direct, invoice movement, receive without GL).

---

## Payroll & Asset Linkage

```
Payroll Register (payroll)
        └──► journal ──► Salary Expense / PAYE / SSNIT / Payable-Cash
                └──► Financial Reports (P&L)

Fixed Assets (fixed_assets)
        ├──► Acquisition ──► journal ──► Asset / Cash-AP
        └──► Depreciation Run ──► journal ──► Depreciation Exp / Accum Dep
                └──► Financial Reports (depreciation schedule)
                └──► [PARTIAL: source linkage certification]
```

---

## Tax Linkage

```
Sales (POS + Invoices) ──► VAT Payable accounts (journal)
Purchases (Bills) ──► VAT Receivable accounts (journal)
        │
        └──► show_taxation ──► reads tax control account balances
                    └──► Tax Settlement ──► payments/journal ──► Cash ↓, liability ↓

[GAP: no dedicated tests; no view permission gate]
```

---

## Platform & Governance Linkage

```
Registration (show_onboarding_payment)
        └──► companies + trial subscription
                └──► Paystack verify ──► activate subscription ──► ERP access

Login (authenticate_access_key)
        └──► users / companies / branches
                └──► session + permissions
                        └──► all module gates

System Configuration (show_company_setup)
        └──► companies, branches, users (no DDL on render)

Dev Gatekeeper (app.py)
        └──► enterprise_services ops snapshot
                └──► render_runtime_admin_diagnostics_suite (admin only)
                        └──► migration cleanup (lazy)

Client pages ──X──► admin diagnostics (blocked by surface gating)
```

---

## Dashboard & Reporting Linkage

```
show_dashboard
        ├──► _cached_dashboard_analytics_bundle (120s TTL)
        │         ├── KPIs from pos_sales, journal, inventory
        │         ├── Sales charts
        │         └── Inventory charts
        └──► _cached_dashboard_receivable_payable_health (on-demand, 300s TTL)
                  └── AR/AP aging, top debtors/creditors

show_financial_reports
        ├──► _cached_ledger_balance_snapshot (shared connection)
        └──► _cached_financial_report_by_type (lazy per report)
                  ├── Trial Balance
                  ├── Income Statement
                  ├── Balance Sheet
                  ├── Cash Flow
                  ├── Changes in Equity
                  └── Depreciation Schedule
```

---

## Permission Linkage Chain

```
ENTERPRISE_ROLE_PERMISSIONS
        └──► user_has_permission(role, permission)
                └──► require_permission() ──► module entry gates
                └──► post_accounting_impact(user_role=...) ──► posting gates
                        └──► [EXCEPTION: POS may omit user_role]

Branch module grants (branch_module_grants)
        └──► Additional POS/inventory scoping per branch
```

---

## Audit Trail Linkage

```
log_audit_action (platform-wide)
        └──► audit_logs ◄── show_audit_trail (view_audit_trail)

Controlled corrections (POS metadata)
        └──► audit_logs + pos_sales update (no delete)

Permission denials
        └──► system_logs + audit_logs
```

---

## Test Coverage Linkage

```
tests/test_regression_lockdown.py ──► 18 protected workflows
tests/run_regression_tests.py ──► 706 tests across modules
        │
        ├── Accounting: test_accounting_core, test_posting_workflow, test_erp_accounting_integrity
        ├── POS: test_pos_sale_identity, test_controlled_corrections
        ├── Reports: test_lv009_phase1_financial_reports_speed
        ├── Startup: test_startup_backend_gate, test_lv004
        ├── Subscription: test_subscription_billing
        └── Permissions: test_permission_security, test_branch_module_governance

[GAP: no test → module link for taxation]
```

---

## Broken or Weak Links (Summary)

| From | To | Issue | Severity |
|------|-----|-------|----------|
| Customer receipt | payments.customer_id | Not persisted | High |
| Supplier payment | payments.supplier_id | Not persisted | High |
| Supplier bill | inventory.qty | No receive on post | High |
| Inventory receive | journal | No GL on simple receive | Medium |
| POS sale | stock_movements | Qty only | Medium |
| Taxation | tests | No coverage | High |
| POS checkout | post_accounting_impact | user_role omitted | Medium |
| Depreciation | source_table linkage | Certification gap | Medium |
| Notifications | all modules | No engine | Low (Phase 2) |

---

*Program A Module Linkage Map — audit only.*
