# High-Risk Insert Identity Conversion Plan (Phase 5B.9)

**Generated:** 2026-06-01  
**Status:** Planning only — no code conversions in this phase  
**Goal:** Convert remaining production `cursor.lastrowid` usage to portable helpers (`ensure_insert_sql_returning`, `get_inserted_id`) without changing SQLite business behavior.

**Companion inventory:** [lastrowid_portability_inventory.md](lastrowid_portability_inventory.md)

---

## Executive summary

| Metric | Value |
|--------|------:|
| Production `lastrowid` sites (app code, excl. helpers/tests/scripts) | **14** |
| High-risk functions to convert | **11** |
| Recommended implementation order | **A → B → C → D → E → F → G** |
| **Highest-risk blocker** | **`post_journal_entry`** — central ledger writer; every downstream phase depends on correct `entry_id` linkage |

**Phase G (journal posting) must be last.** Converting `post_journal_entry` before callers are validated multiplies regression blast radius.

---

## Portable conversion pattern (all phases)

```python
from database import ensure_insert_sql_returning, get_inserted_id

cursor = conn.execute(
    ensure_insert_sql_returning("INSERT INTO ... VALUES (...)"),
    params,
)
row_id = get_inserted_id(cursor)
```

- **SQLite:** SQL unchanged; `get_inserted_id` → `cursor.lastrowid`.
- **PostgreSQL:** `ensure_insert_sql_returning` appends `RETURNING id`; `get_inserted_id` reads returned row.
- **Rule:** Capture `row_id` immediately after `INSERT`, before any other statement on the same cursor (especially before nested `post_journal_entry`).

---

## Site-by-site analysis

### 1. `_insert_stock_movement_record`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `_insert_stock_movement_record` (~6873) |
| **INSERT table** | `stock_movements` |
| **lastrowid use** | Return movement row id to callers (`movement_id` in inventory UI) |
| **Downstream dependencies** | Optional journal posting when movement value > 0 (inventory UI ~9750+); receive-stock helper `_receive_stock_into_inventory` (~7018); audit/display only in most paths |
| **Transaction boundary** | Caller-owned `conn`; no commit inside helper |
| **Rollback** | Caller rolls back entire inventory adjustment if later step fails |
| **Accounting impact** | None inside helper; callers may post COGS/AP journal after movement |
| **Inventory impact** | **High** — movement row is audit trail for qty changes already applied via `UPDATE inventory` |
| **Branch impact** | `branch_id` stored on movement row |
| **Receipt/document numbering** | Uses caller `reference` string (e.g. `STK-{item_id}-{timestamp}`), not `lastrowid` |
| **Risk level** | **Medium-high** (inventory audit integrity) |
| **Conversion strategy** | Wrap INSERT with `ensure_insert_sql_returning`; `return get_inserted_id(movement_cursor)`. No other logic changes. |
| **Tests before conversion** | `test_inventory_movements.py`; new unit test: movement insert returns id matching DB row; rollback leaves no orphan movement |
| **Recommended phase** | **5B.10A (Phase A)** |

---

### 2. `show_accounts_payable_page`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_accounts_payable_page` (~8403) |
| **INSERT table** | `bills` |
| **lastrowid use** | `bill_id` → `post_journal_entry(..., source_id=bill_id)` when `posting_state == "Posted"` |
| **Downstream dependencies** | `build_purchase_journal_lines`, `post_journal_entry`, `log_system_event`, supplier via `_get_or_create_party` |
| **Transaction boundary** | Single UI `conn`; `conn.commit()` after bill (+ optional journal) |
| **Rollback** | No explicit rollback on posting failure mid-block; exceptions abort before commit |
| **Accounting impact** | **Yes** when Posted — AP/cash/expense/asset lines |
| **Inventory impact** | None (unless classification triggers asset register elsewhere) |
| **Branch impact** | `branch_id` passed to `post_journal_entry` |
| **Receipt/document numbering** | `bill_number = BILL-{timestamp}` pre-generated; not derived from `lastrowid` |
| **Risk level** | **High** (ledger + AP) |
| **Conversion strategy** | `bill_id = get_inserted_id(cursor)` after bill INSERT; pass `bill_id` to journal. Mirror `financials.py` bill pattern (5B.8). |
| **Tests before conversion** | AP/bill integration tests; journal balances; duplicate bill_number constraint; draft vs posted |
| **Recommended phase** | **5B.10B (Phase B)** |

---

### 3. `show_create_bill_page`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_create_bill_page` (~8538) |
| **INSERT table** | `bills`, then `bill_lines` |
| **lastrowid use** | `bill_id` for line inserts and `post_journal_entry` source_id |
| **Downstream dependencies** | `bill_lines` FK to `bill_id`; purchase journal; permission gates |
| **Transaction boundary** | UI `conn`; `conn.rollback()` if posting permission denied |
| **Rollback** | Explicit rollback on permission failure before commit |
| **Accounting impact** | **Yes** when Posted |
| **Inventory impact** | None |
| **Branch impact** | `branch_id` on journal |
| **Receipt/document numbering** | `BILL-{timestamp}` |
| **Risk level** | **High** |
| **Conversion strategy** | Same as AP page: capture `bill_id` once, use for all `bill_lines` and journal |
| **Tests before conversion** | Bill lines persisted with correct `bill_id`; posted journal `source_id` matches |
| **Recommended phase** | **5B.10B (Phase B)** |

---

### 4. `show_sales_purchase` (Sales + Purchase branches)

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_sales_purchase` (~12800) |
| **INSERT tables** | `invoices` (Sales), `bills` (Purchase) |
| **lastrowid use** | `invoice_cursor.lastrowid` → `save_invoice_lines`, stock effects, journal `source_id`; `bill_cursor.lastrowid` → journal `source_id` |
| **Downstream dependencies** | `_register_customer` / `_get_or_create_party`; `save_invoice_lines`; `apply_invoice_stock_effects` (Sales Posted); `build_*_journal_lines`; `post_journal_entry`; `_ensure_counterparty`; `log_audit_action` |
| **Transaction boundary** | `try/except` with `conn.commit()` at end |
| **Rollback** | Exception → error UI; no commit |
| **Accounting impact** | **Yes** when Posted (both branches) |
| **Inventory impact** | **Yes** on Sales Posted — `apply_invoice_stock_effects` |
| **Branch impact** | `branch_id` on stock + journal |
| **Receipt/document numbering** | `tx_reference = SAL-/PUR-{timestamp}` (not lastrowid-based) |
| **Risk level** | **Very high** (combined AR/AP + optional stock) |
| **Conversion strategy** | Capture `invoice_id` / `bill_id` via `get_inserted_id` immediately after INSERT; replace all `*_cursor.lastrowid` references. **Do not** change stock or journal line builders. |
| **Tests before conversion** | Extend sales/purchase tests; invoice lines FK; stock qty after posted sale; journal balance |
| **Recommended phase** | **5B.10B (Phase B)** — execute **after** simpler AP pages; treat Sales branch as higher-risk sub-step within B |

---

### 5. `allocate_payment`

| Field | Detail |
|-------|--------|
| **File** | `accounting_engine.py` |
| **Function** | `allocate_payment` (~1545) |
| **INSERT table** | `payment_allocations` |
| **lastrowid use** | Return allocation id |
| **Downstream dependencies** | Outstanding balance checks on invoices/bills; optional caller commit |
| **Transaction boundary** | Owns connection when `conn=None`; commit/rollback in function |
| **Rollback** | Full rollback on exception when owns connection |
| **Accounting impact** | **Indirect** — allocation links payment to AR/AP documents; no journal in this function |
| **Inventory impact** | None |
| **Branch impact** | `branch_id` on allocation row |
| **Receipt/document numbering** | None |
| **Risk level** | **Medium-high** (payment integrity) |
| **Conversion strategy** | `ensure_insert_sql_returning` on INSERT; `return get_inserted_id(cursor)` |
| **Tests before conversion** | Allocation caps vs outstanding; duplicate allocation prevention |
| **Recommended phase** | **5B.10C (Phase C)** — with banking payment insert |

---

### 6. `show_banking` (payment recording)

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_banking` (~13062); identity at ~13321–13338 |
| **INSERT table** | `payments` |
| **lastrowid use** | `payment_id` for `document_reference`, `post_journal_entry` (`payment_id` + `source_id`), allocations, customer ledger |
| **Downstream dependencies** | Multiple `post_journal_entry` branches by `payment_type`; `allocate_payment` possible; balance checks; audit |
| **Transaction boundary** | `conn` with `conn.rollback()` on insufficient balance; commit on success |
| **Rollback** | Explicit rollback before return on validation failures |
| **Accounting impact** | **Yes** — all payment types post journals |
| **Inventory impact** | None |
| **Branch impact** | `branch_id` on journal |
| **Receipt/document numbering** | `document_reference = reference or f"BANK-{payment_id}"` — **uses payment id as fallback** |
| **Risk level** | **Very high** |
| **Conversion strategy** | `payment_id = get_inserted_id(payment_cursor)` immediately after INSERT; keep `BANK-{payment_id}` fallback logic identical |
| **Tests before conversion** | Banking regression; each payment type journal; reference string unchanged on SQLite |
| **Recommended phase** | **5B.10C (Phase C)** |

---

### 7. `show_payroll`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_payroll` (~14198) |
| **INSERT tables** | `payroll`, `payroll_records` |
| **lastrowid use** | `payroll_id` → `post_journal_entry(..., source_table='payroll', source_id=payroll_id)` |
| **Downstream dependencies** | `_build_payroll_journal_lines`; `post_journal_entry`; audit log |
| **Transaction boundary** | `try/except`; `conn.commit()` on success |
| **Rollback** | Exception path — no commit |
| **Accounting impact** | **Yes** — payroll accrual/payment lines |
| **Inventory impact** | None |
| **Branch impact** | `active_branch_id` on journal |
| **Receipt/document numbering** | `PAY-{emp}-{month}-{year}` reference (not lastrowid) |
| **Risk level** | **High** |
| **Conversion strategy** | `payroll_id = get_inserted_id(payroll_cursor)`; journal unchanged |
| **Tests before conversion** | Payroll calculation + journal balance tests |
| **Recommended phase** | **5B.10D (Phase D)** |

---

### 8. `show_fixed_assets`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `show_fixed_assets` (~14684) |
| **INSERT table** | `fixed_assets` |
| **lastrowid use** | `asset_cursor.lastrowid` in journal `reference=f"FA-{id}"` and `source_id` |
| **Downstream dependencies** | `_build_fixed_asset_acquisition_lines`; `post_journal_entry`; audit |
| **Transaction boundary** | `try/except`; `conn.commit()` |
| **Rollback** | Exception — no commit |
| **Accounting impact** | **Yes** — asset acquisition journal |
| **Inventory impact** | None |
| **Branch impact** | `active_branch_id` on journal |
| **Receipt/document numbering** | **FA-{asset_id}** reference tied to inserted id |
| **Risk level** | **High** |
| **Conversion strategy** | `asset_id = get_inserted_id(asset_cursor)`; use for FA reference and source_id |
| **Tests before conversion** | Fixed asset acquisition journals; credit vs cash paths |
| **Recommended phase** | **5B.10D (Phase D)** |

---

### 9. `_process_pos_return`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `_process_pos_return` (~5460) |
| **INSERT tables** | `stock_movements` (inline, per line), `pos_returns` |
| **lastrowid use** | `pos_return_id` → `post_journal_entry`, `UPDATE pos_returns SET posted_entry_id` |
| **Downstream dependencies** | Inventory qty restock; inline `stock_movements` INSERT (separate from helper); refund journals; store credit ledger |
| **Transaction boundary** | Caller (`return_conn`) commits after function returns (~12382) |
| **Rollback** | Caller must rollback on exception (verify `except` path) |
| **Accounting impact** | **Yes** — per-line refund journal |
| **Inventory impact** | **Yes** — restock + movement rows |
| **Branch impact** | `branch_id` on movements, returns, journal |
| **Receipt/document numbering** | `return_reference` caller-generated; not lastrowid |
| **Risk level** | **Very high** |
| **Conversion strategy** | Convert `pos_returns` INSERT only in Phase E; consider converting inline `stock_movements` INSERT to `_insert_stock_movement_record` + portable id in same phase (optional refactor, separate PR) |
| **Tests before conversion** | POS return tests; refundable qty; journal + inventory reversal |
| **Recommended phase** | **5B.10E (Phase E)** |

---

### 10. `_persist_pos_sale`

| Field | Detail |
|-------|--------|
| **File** | `modules.py` |
| **Function** | `_persist_pos_sale` (~5290) |
| **INSERT tables** | `pos_sales`, `pos_sale_lines` |
| **lastrowid use** | `pos_sale_id` for line FKs; caller passes to `post_journal_entry(..., source_id=pos_sale_id)` |
| **Downstream dependencies** | Idempotent lookup by `sale_reference`; POS UI `process_pos_sale` (~11908); stock deduction before persist; journal after persist |
| **Transaction boundary** | Caller `conn`; commit in POS finalize flow |
| **Rollback** | Whole POS transaction rolls back on failure |
| **Accounting impact** | **Yes** (via caller journal) |
| **Inventory impact** | **Yes** (stock reduced before/at sale in caller) |
| **Branch impact** | `branch_id` on sale header/lines |
| **Receipt/document numbering** | `receipt_number` / `sale_reference` pre-set (`POS-{legacy_id or timestamp}`) — **not** from lastrowid |
| **Risk level** | **Critical** |
| **Conversion strategy** | `pos_sale_id = get_inserted_id(cursor)` after `pos_sales` INSERT; early-return idempotent path unchanged |
| **Tests before conversion** | POS sale persistence tests; duplicate `sale_reference`; line FK integrity |
| **Recommended phase** | **5B.10F (Phase F)** |

**Note:** `process_pos_sale` has no direct `lastrowid`; it orchestrates stock, `_persist_pos_sale`, and `post_journal_entry`. Do not modify finalize orchestration in identity-only PRs.

---

### 11. `post_journal_entry`

| Field | Detail |
|-------|--------|
| **File** | `accounting_engine.py` |
| **Function** | `post_journal_entry` (~1170+) |
| **INSERT tables** | `journal_entries`, then `journal_lines` |
| **lastrowid use** | `entry_id` → line inserts, document sync, legacy mirrors, return value |
| **Downstream dependencies** | `_sync_source_document_posting`; `_mirror_legacy_transactions`; `_legacy_voucher_insert`; duplicate posting guards; period lock |
| **Transaction boundary** | Optional `execute_write_transaction` wrapper; `with_retry_on_lock(conn.commit)` when owns connection |
| **Rollback** | `conn.rollback()` on exception when owns connection |
| **Accounting impact** | **Core ledger** — all modules depend on correct `entry_id` |
| **Inventory impact** | Only via source document sync metadata |
| **Branch impact** | `branch_id` on header; duplicate check includes branch |
| **Receipt/document numbering** | `reference` param; post-insert UPDATE sets `document_number` from reference |
| **Risk level** | **Critical / highest** |
| **Conversion strategy** | `entry_id = get_inserted_id(cursor)` after header INSERT; verify PostgreSQL `fetchone` not consumed elsewhere on cursor. Run full regression + journal integrity suite. |
| **Tests before conversion** | All journal tests; trial balance; duplicate source posting rejection; period lock |
| **Recommended phase** | **5B.10G (Phase G) — LAST** |

---

## Phased conversion roadmap

### Phase A — Stock movement identity (5B.10A)

**Scope:** `_insert_stock_movement_record` only.

| Item | Detail |
|------|--------|
| Sites | 1 function, 1 INSERT |
| Rationale | Isolated helper; many callers but no direct journal inside helper |
| Blockers | None |

### Phase B — Accounts payable / bills (5B.10B)

**Scope:** `show_accounts_payable_page`, `show_create_bill_page`, `show_sales_purchase` (bill + invoice branches).

| Item | Detail |
|------|--------|
| Sites | 3 functions, 4+ INSERT identity captures |
| Rationale | Document-first flows; journal already uses explicit `source_id` |
| Order within B | AP page → create bill → sales_purchase (purchase) → sales_purchase (sales) |

### Phase C — Payments (5B.10C)

**Scope:** `show_banking` payment INSERT, `allocate_payment`.

| Item | Detail |
|------|--------|
| Sites | 2 functions |
| Rationale | Payment reference fallback uses `payment_id`; test carefully |

### Phase D — Payroll & fixed assets (5B.10D)

**Scope:** `show_payroll`, `show_fixed_assets`.

| Item | Detail |
|------|--------|
| Sites | 2 functions |
| Rationale | HR/asset modules; journal linked via `source_id` |

### Phase E — POS return (5B.10E)

**Scope:** `_process_pos_return` (`pos_returns` INSERT; optional inline `stock_movements` alignment).

| Item | Detail |
|------|--------|
| Sites | 1 function (+ optional inline movement refactor) |
| Rationale | Multi-line loop with inventory + journal per line |

### Phase F — POS sale persistence (5B.10F)

**Scope:** `_persist_pos_sale` only (not `process_pos_sale` orchestration).

| Item | Detail |
|------|--------|
| Sites | 1 function |
| Rationale | POS lines FK; idempotent sale_reference guard must remain |

### Phase G — Journal posting (5B.10G)

**Scope:** `post_journal_entry` header INSERT identity.

| Item | Detail |
|------|--------|
| Sites | 1 function |
| Rationale | **Last** — affects every accounting path |

---

## Recommended phase order (summary)

```
A → B → C → D → E → F → G
```

| Phase | ID | Functions | Relative risk |
|-------|-----|-----------|---------------|
| A | 5B.10A | `_insert_stock_movement_record` | Medium-high |
| B | 5B.10B | AP / create bill / sales_purchase | High |
| C | 5B.10C | `show_banking`, `allocate_payment` | Very high |
| D | 5B.10D | `show_payroll`, `show_fixed_assets` | High |
| E | 5B.10E | `_process_pos_return` | Very high |
| F | 5B.10F | `_persist_pos_sale` | Critical |
| G | 5B.10G | `post_journal_entry` | **Highest** |

---

## Highest-risk blocker

**`post_journal_entry`** is the single largest PostgreSQL migration blocker:

- Used by POS, banking, payroll, bills, invoices, returns, and fixed assets.
- Inserts `journal_entries` then multiple `journal_lines` using `entry_id`.
- Updates source documents via `_sync_source_document_posting`.
- Wrong identity breaks GL, audit trails, and duplicate-posting guards.

**Mitigation:** Complete Phases A–F with SQLite parity tests first; convert journal header identity only after all callers use `get_inserted_id` for their own inserts.

---

## Per-phase test plan

### All phases (mandatory)

| Test area | Assertion |
|-----------|-----------|
| SQLite behavior unchanged | Same ids, row counts, and balances before/after |
| Returned id correct | `SELECT id FROM <table> WHERE id = ?` matches inserted row |
| Transaction rollback safe | Failed mid-flow leaves no partial header/lines |
| Duplicate prevention preserved | Unique constraints / app guards still fire |
| Journal still balances | `SUM(debit) = SUM(credit)` per entry |
| Inventory qty | Unchanged except expected deltas |
| `branch_id` preserved | Header/child rows match session branch |
| Document numbers | `bill_number`, `invoice_number`, `tx_reference`, `FA-*` unchanged |
| Receipt numbers | POS `receipt_number` / `sale_reference` not derived from lastrowid — verify unchanged |
| Audit log preserved | `log_audit_action` / `log_system_event` entries still written |

### Phase A — Stock movement

- Movement row links to correct `inventory_item_id` and qty snapshot.
- Inventory UI journal branch (if movement_value > 0) still posts.
- Receive-stock path returns same reference string.

### Phase B — Bills / sales_purchase

- `bill_lines.invoice_lines` FK to parent id.
- Posted bill journal `source_id` matches bill row.
- Sales posted path: stock effects + COGS journal unchanged.
- Draft posting: no journal, id still valid for lines.

### Phase C — Payments

- `BANK-{payment_id}` fallback reference unchanged when user reference empty.
- Each payment type journal still posts.
- Allocation outstanding math unchanged.

### Phase D — Payroll / fixed assets

- `payroll_records` sibling row still inserted.
- `FA-{asset_id}` journal reference matches asset row.

### Phase E — POS return

- `pos_returns.posted_entry_id` matches journal entry.
- Per-line refund totals; store credit ledger when applicable.
- Return reference idempotency guard still works.

### Phase F — POS sale

- Duplicate `sale_reference` returns existing id without new INSERT.
- All `pos_sale_lines.pos_sale_id` FKs correct.
- Journal `source_id` matches persisted sale.

### Phase G — Journal

- `journal_lines.entry_id` FK integrity.
- Source document reverse links (`posted_entry_id` etc.).
- Legacy mirror tables unchanged.
- `execute_write_transaction` retry path still commits.

---

## Out of scope (this plan)

| Item | Reason |
|------|--------|
| `process_pos_sale` orchestration | No `lastrowid`; excluded from identity-only work |
| Receipt numbering algorithms | Must not change |
| `DB_BACKEND` switch / migration | Separate program phase |
| Test helper `lastrowid` in `tests/test_support.py` | Convert in test-harness phase or leave until Postgres E2E |
| `database.py` helper implementations | Already portable |

---

## Files created/updated (Phase 5B.9)

| File | Action |
|------|--------|
| `reports/high_risk_identity_conversion_plan.md` | **Created** (this document) |
| `reports/lastrowid_portability_inventory.md` | **Regenerated** |
| `scripts/generate_lastrowid_inventory.py` | **Updated** — high-risk hints, 5B.8 section, plan link |

**No application code modified.**
