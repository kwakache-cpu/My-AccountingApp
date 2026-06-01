# lastrowid Portability Inventory

**Generated at:** 2026-06-01 12:56:38 UTC
**Total lastrowid references (app + tests, excl. .venv):** 46
**Application code references:** 35
**Test-only references:** 11
**Remaining raw lastrowid (application):** 34

## Recommended Helper Usage

```python
from database import ensure_insert_sql_returning, get_inserted_id

cursor = conn.execute(
    ensure_insert_sql_returning('INSERT INTO my_table (...) VALUES (...)'),
    params,
)
row_id = get_inserted_id(cursor)
```

PostgreSQL requires `RETURNING id` (appended by `ensure_insert_sql_returning`).
SQLite continues to use `cursor.lastrowid` via `get_inserted_id()`.

## Low-risk — setup / admin / contacts

**Count:** 22

| File | Function | Line | Table | Convert now? | Snippet |
|------|----------|-----:|-------|--------------|---------|
| `accounting_engine.py` | `allocate_payment` | 1587 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |
| `database.py` | `log_schema_manifest_diagnostics` | 647 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"lastrowid_usage": "lastrowid",` |
| `modules.py` | `show_accounts_payable_page` | 8478 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `bill_id = int(cursor.lastrowid)` |
| `modules.py` | `show_create_bill_page` | 8674 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `bill_id = int(cursor.lastrowid)` |
| `modules.py` | `show_fixed_assets` | 14843 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `reference=f"FA-{int(asset_cursor.lastrowid)}",` |
| `modules.py` | `show_fixed_assets` | 14851 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `source_id=int(asset_cursor.lastrowid),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 31 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"lastrowid": re.compile(r"\blastrowid\b"),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 290 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `q_count = sum(1 for v in sqlite_features.get("lastrowid", []) if "database.py" n` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 291 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `lastrowid_hits = len(sqlite_features.get("lastrowid", []))` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 297 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `blockers.append(f"Widespread cursor.lastrowid usage ({lastrowid_hits} references` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `render_write_paths_report` | 487 | `unknown` | done | `"- Replace `lastrowid` with `fetch_inserted_row_id()` after `insert_returning_id` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `render_readiness_report` | 532 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"2. Finish placeholder + `lastrowid` migration on critical write paths using exi` |
| `tests/test_branch_module_governance.py` | `test_staff_assignment_transfers_user_branch_id` | 84 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `).lastrowid` |
| `tests/test_insert_identity_portability.py` | `test_get_inserted_id_returns_sqlite_lastrowid` | 19 | `unknown` | done | `self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)` |
| `tests/test_insert_identity_portability.py` | `test_get_inserted_id_returns_sqlite_lastrowid` | 20 | `unknown` | done | `self.assertEqual(self.database.fetch_inserted_row_id(cursor, backend="sqlite"), ` |
| `tests/test_migration_cleanup_ui.py` | `test_payment_fix_refuses_without_confirmation` | 183 | `payments` | yes — use ensure_insert_sql_returning + get_inserted_id | `).lastrowid` |
| `tests/test_migration_cleanup_ui.py` | `test_payment_fix_updates_only_customer_id_and_reference` | 215 | `payments` | yes — use ensure_insert_sql_returning + get_inserted_id | `).lastrowid` |
| `tests/test_support.py` | `create_customer` | 109 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |
| `tests/test_support.py` | `create_supplier` | 120 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |
| `tests/test_support.py` | `create_invoice` | 145 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |
| `tests/test_support.py` | `create_bill` | 170 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |
| `tests/test_support.py` | `create_payment` | 207 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `return int(cursor.lastrowid)` |

## Medium-risk — CRUD / financials helpers

**Count:** 10

| File | Function | Line | Table | Convert now? | Snippet |
|------|----------|-----:|-------|--------------|---------|
| `accounting_engine.py` | `schedule_recurring_transaction` | 1693 | `unknown` | later phase | `return int(cursor.lastrowid)` |
| `financials.py` | `_party_id` | 186 | `unknown` | later phase | `return int(cursor.lastrowid)` |
| `financials.py` | `show_invoice_manager` | 652 | `unknown` | later phase | `invoice_reference=f"INV-{cursor.lastrowid}",` |
| `financials.py` | `show_invoice_manager` | 679 | `inventory` | later phase | `reference=f"INV-{cursor.lastrowid}",` |
| `financials.py` | `show_invoice_manager` | 687 | `invoices` | later phase | `source_id=int(cursor.lastrowid),` |
| `financials.py` | `show_invoice_manager` | 778 | `unknown` | later phase | `reference=f"BILL-{cursor.lastrowid}",` |
| `financials.py` | `show_invoice_manager` | 786 | `bills` | later phase | `source_id=int(cursor.lastrowid),` |
| `financials.py` | `show_create_invoice_page` | 1052 | `unknown` | later phase | `invoice_reference=f"INV-{cursor.lastrowid}",` |
| `financials.py` | `show_create_invoice_page` | 1079 | `inventory` | later phase | `reference=f"INV-{cursor.lastrowid}",` |
| `financials.py` | `show_create_invoice_page` | 1087 | `invoices` | later phase | `source_id=int(cursor.lastrowid),` |

## High-risk — accounting / POS / payments / inventory

**Count:** 14

| File | Function | Line | Table | Convert now? | Snippet |
|------|----------|-----:|-------|--------------|---------|
| `accounting_engine.py` | `post_journal_entry` | 1307 | `inventory` | no — dedicated transaction testing required | `entry_id = int(cursor.lastrowid)` |
| `financials.py` | `show_invoice_manager` | 647 | `invoices` | no — dedicated transaction testing required | `save_invoice_lines(conn, int(cursor.lastrowid), invoice_items)` |
| `financials.py` | `show_create_invoice_page` | 1037 | `unknown` | no — dedicated transaction testing required | `save_invoice_lines(conn, int(cursor.lastrowid), invoice_items)` |
| `modules.py` | `_persist_pos_sale` | 5325 | `unknown` | no — dedicated transaction testing required | `pos_sale_id = int(cursor.lastrowid)` |
| `modules.py` | `_process_pos_return` | 5600 | `inventory` | no — dedicated transaction testing required | `pos_return_id = int(cursor.lastrowid)` |
| `modules.py` | `_insert_stock_movement_record` | 6913 | `inventory` | no — dedicated transaction testing required | `return int(movement_cursor.lastrowid)` |
| `modules.py` | `show_sales_purchase` | 12887 | `invoices` | no — dedicated transaction testing required | `save_invoice_lines(conn, int(invoice_cursor.lastrowid), invoice_items)` |
| `modules.py` | `show_sales_purchase` | 12928 | `invoices` | no — dedicated transaction testing required | `source_id=int(invoice_cursor.lastrowid),` |
| `modules.py` | `show_sales_purchase` | 12986 | `bills` | no — dedicated transaction testing required | `source_id=int(bill_cursor.lastrowid),` |
| `modules.py` | `_journal_method_balance` | 13338 | `unknown` | no — dedicated transaction testing required | `payment_id = int(payment_cursor.lastrowid)` |
| `modules.py` | `show_payroll` | 14291 | `unknown` | no — dedicated transaction testing required | `payroll_id = int(payroll_cursor.lastrowid)` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 75 | `pos_sales` | no — dedicated transaction testing required | `(r"payment_cursor\.lastrowid", "modules.py"),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 88 | `payments` | no — dedicated transaction testing required | `(r"payroll_cursor\.lastrowid", "modules.py"),` |
| `tests/test_migration_cleanup_ui.py` | `_create_pos_sale` | 53 | `unknown` | no — dedicated transaction testing required | `return int(cursor.lastrowid), receipt_number` |

## Phase 5B.7 Conversions (this patch)

| Function | File |
|----------|------|
| `_create_legacy_voucher_if_enabled` | `modules.py` |
| `_get_or_create_party` | `modules.py` |
| `_register_customer` | `modules.py` |
| `_register_supplier` | `modules.py` |
| `get_or_create_account` | `accounting_engine.py` |
| `create_bank_account` | `accounting_engine.py` |
