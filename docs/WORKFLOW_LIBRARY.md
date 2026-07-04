# Workflow Library

Major business workflows supported by EKA Enterprise Platform.  
EKA is organized around **flows**, not feature menus.

For module locations, see `EKA_ARCHITECTURE_MANUAL.md`.  
For engineering constraints, see `DEVELOPER_RULES.md`.

---

## Workflow Map

```
Order to Cash ──────► Customer Journey
       │
       ▼
Inventory Lifecycle ◄──── Purchase to Pay ──────► Supplier Journey

Payroll Lifecycle ──► Expense / Liability posting
Asset Lifecycle ────► Depreciation / GL reconciliation
Year-End Closing ───► Period lock / final reports
```

---

## 1. Order to Cash

**Purpose:** Convert commercial activity into collected cash with correct revenue recognition.

### Stages

| Stage | Description | EKA surfaces |
|-------|-------------|--------------|
| Capture | Sale at POS or invoice creation | POS, Sales/Invoicing |
| Fulfill | Stock reduction, receipt/document | Inventory, POS lines |
| Post | Revenue, tax, COGS, cash/AR | Accounting engine |
| Collect | Payment receipt, allocation | Payments, customer balance |
| Reconcile | AR aging vs GL | Dashboard (on-demand), Financial Reports |

### Rules

- POS sales post through controlled source linkage (`pos_sales` → journal)
- Corrections use **controlled correction**, not silent delete
- Period locks block casual backdating

### Protected by regression lockdown

- POS sale (`test_pos_sale_identity.py`, `test_regression_lockdown.py`)
- Controlled correction (`test_controlled_corrections.py`)

---

## 2. Purchase to Pay

**Purpose:** Acquire goods/services and pay suppliers with correct expense/AP accounting.

### Stages

| Stage | Description | EKA surfaces |
|-------|-------------|--------------|
| Order | Purchase intent / bill entry | Purchases, Bills |
| Receive | Inventory or expense recognition | Inventory receive |
| Post | AP, expense, inventory asset | Accounting engine |
| Pay | Supplier payment | Payments |
| Reconcile | AP aging vs GL | Financial Reports, dashboard defer |

### Rules

- Bills and payments maintain source linkage
- Inventory receive updates stock before/as GL reflects movement

---

## 3. Inventory Lifecycle

**Purpose:** Track items from creation through sale, adjustment, and valuation.

### Stages

| Stage | Description |
|-------|-------------|
| Item master | SKU, barcode, unit, cost |
| Receive | Stock in (purchase, opening, adjustment) |
| Move | Branch transfer, adjustment |
| Sell | POS or invoice line consumption |
| Review | Low stock, expiry, valuation vs GL |

### Rules

- Inventory GL must reconcile with register (reporting trust checks)
- Barcode modes: keyboard, camera, physical scanner (company setting)

---

## 4. Customer Journey

**Purpose:** Manage customer relationship from first sale through collection.

### Stages

| Stage | Description |
|-------|-------------|
| Onboard | Customer master creation |
| Transact | POS or invoice |
| Credit | Balance tracking, aging |
| Collect | Payment, allocation |
| Review | Top debtors, overdue alerts |

### Platform note

New **company** registration (trial/Paystack) is a separate platform onboarding flow — see Registration workflow in `REGRESSION_LOCKDOWN.md`.

---

## 5. Supplier Journey

**Purpose:** Manage supplier master, purchases, and payments.

### Stages

| Stage | Description |
|-------|-------------|
| Onboard | Supplier master |
| Purchase | Bill / purchase entry |
| Pay | Payment run |
| Review | Top creditors, AP aging |

---

## 6. Payroll Lifecycle

**Purpose:** Process payroll with correct expense and liability posting.

### Stages

| Stage | Description |
|-------|-------------|
| Setup | Employees, salary structure |
| Run | Payroll period processing |
| Post | Expense + liability journals |
| Pay | Settlement / clearance |
| Report | Payroll summaries |

### Rules

- Posting through accounting engine with audit trail
- Period controls apply to payroll dates

---

## 7. Asset Lifecycle

**Purpose:** Track fixed assets from acquisition through depreciation.

### Stages

| Stage | Description |
|-------|-------------|
| Acquire | Asset register entry |
| Depreciate | Scheduled depreciation posting |
| Reconcile | Fixed assets GL vs register |
| Dispose | Controlled removal / write-off |

### Reports

- Depreciation schedule (Financial Reports — lazy loaded)

---

## 8. Year-End Closing

**Purpose:** Close accounting periods with integrity and produce final reports.

### Stages

| Stage | Description |
|-------|-------------|
| Prepare | Reconcile AR, AP, inventory, cash, fixed assets |
| Review | Trial balance, balance sheet balance |
| Lock | Period status controls |
| Report | P&L, balance sheet, tax/audit exports |
| Archive | Audit trail preserved |

### Rules

- Locked periods block casual corrections
- Reporting trust checks must pass before sign-off

---

## Platform Workflows (cross-cutting)

These are not industry flows but are essential to the platform:

| Workflow | Document |
|----------|----------|
| Login / secure logout | `REGRESSION_LOCKDOWN.md` |
| PostgreSQL / SQLite startup | `REGRESSION_LOCKDOWN.md` |
| Company registration & trial | `REGRESSION_LOCKDOWN.md` |
| Paystack subscription | `REGRESSION_LOCKDOWN.md` |
| System Configuration | `REGRESSION_LOCKDOWN.md` |
| Staff & roles | `REGRESSION_LOCKDOWN.md` |
| Admin diagnostics | `REGRESSION_LOCKDOWN.md` |

---

## Workflow Improvement Checklist

Before shipping a feature, confirm:

- [ ] Which workflow(s) does it improve?
- [ ] Does it save time, prevent mistakes, improve decisions, or increase security?
- [ ] Does it preserve accounting integrity and audit trail?
- [ ] Does it stay off client diagnostic surfaces?
- [ ] Is it covered or referenced in regression lockdown?

---

*Workflow Library — canonical business flows for EKA Enterprise Platform.*
