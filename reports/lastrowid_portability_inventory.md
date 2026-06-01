# lastrowid Portability Inventory

**Generated at:** 2026-06-01 14:35:29 UTC
**Total lastrowid references (app + tests, excl. .venv):** 32
**Application code references:** 19
**Test-only references:** 13
**Remaining raw lastrowid (application):** 18

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

**Count:** 18

| File | Function | Line | Table | Convert now? | Snippet |
|------|----------|-----:|-------|--------------|---------|
| `database.py` | `log_schema_manifest_diagnostics` | 647 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"lastrowid_usage": "lastrowid",` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 31 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"lastrowid": re.compile(r"\blastrowid\b"),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 290 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `q_count = sum(1 for v in sqlite_features.get("lastrowid", []) if "database.py" n` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 291 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `lastrowid_hits = len(sqlite_features.get("lastrowid", []))` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `_score_risks` | 297 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `blockers.append(f"Widespread cursor.lastrowid usage ({lastrowid_hits} references` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `render_write_paths_report` | 487 | `unknown` | done | `"- Replace `lastrowid` with `fetch_inserted_row_id()` after `insert_returning_id` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `render_readiness_report` | 532 | `unknown` | yes — use ensure_insert_sql_returning + get_inserted_id | `"2. Finish placeholder + `lastrowid` migration on critical write paths using exi` |
| `tests/test_ap_bills_identity.py` | `test_bill_insert_sqlite_matches_lastrowid` | 87 | `unknown` | done | `self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)` |
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

**Count:** 0

_None._

## High-risk — accounting / POS / payments / inventory

**Count:** 14

| File | Function | Line | Table | Convert now? | Snippet |
|------|----------|-----:|-------|--------------|---------|
| `accounting_engine.py` | `post_journal_entry` | 1307 | `inventory` | no — dedicated transaction testing required | `entry_id = int(cursor.lastrowid)` |
| `accounting_engine.py` | `allocate_payment` | 1587 | `unknown` | no — dedicated transaction testing required | `return int(cursor.lastrowid)` |
| `modules.py` | `_persist_pos_sale` | 5325 | `unknown` | no — dedicated transaction testing required | `pos_sale_id = int(cursor.lastrowid)` |
| `modules.py` | `_process_pos_return` | 5600 | `inventory` | no — dedicated transaction testing required | `pos_return_id = int(cursor.lastrowid)` |
| `modules.py` | `show_sales_purchase` | 12893 | `invoices` | no — dedicated transaction testing required | `save_invoice_lines(conn, int(invoice_cursor.lastrowid), invoice_items)` |
| `modules.py` | `show_sales_purchase` | 12934 | `invoices` | no — dedicated transaction testing required | `source_id=int(invoice_cursor.lastrowid),` |
| `modules.py` | `_journal_method_balance` | 13347 | `unknown` | no — dedicated transaction testing required | `payment_id = int(payment_cursor.lastrowid)` |
| `modules.py` | `show_payroll` | 14300 | `unknown` | no — dedicated transaction testing required | `payroll_id = int(payroll_cursor.lastrowid)` |
| `modules.py` | `show_fixed_assets` | 14852 | `unknown` | no — dedicated transaction testing required | `reference=f"FA-{int(asset_cursor.lastrowid)}",` |
| `modules.py` | `show_fixed_assets` | 14860 | `unknown` | no — dedicated transaction testing required | `source_id=int(asset_cursor.lastrowid),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 75 | `pos_sales` | no — dedicated transaction testing required | `(r"payment_cursor\.lastrowid", "modules.py"),` |
| `scripts/run_postgres_schema_compatibility_audit.py` | `<module>` | 88 | `payments` | no — dedicated transaction testing required | `(r"payroll_cursor\.lastrowid", "modules.py"),` |
| `tests/test_inventory_movements.py` | `test_insert_stock_movement_record_sqlite_matches_lastrowid` | 148 | `unknown` | done | `self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)` |
| `tests/test_migration_cleanup_ui.py` | `_create_pos_sale` | 53 | `unknown` | no — dedicated transaction testing required | `return int(cursor.lastrowid), receipt_number` |

## Phase 5B.7 Conversions (completed)

| Function | File |
|----------|------|
| `_create_legacy_voucher_if_enabled` | `modules.py` |
| `_get_or_create_party` | `modules.py` |
| `_register_customer` | `modules.py` |
| `_register_supplier` | `modules.py` |
| `get_or_create_account` | `accounting_engine.py` |
| `create_bank_account` | `accounting_engine.py` |

## Phase 5B.8 Conversions (completed)

| Function | File |
|----------|------|
| `_party_id` | `financials.py` |
| `show_invoice_manager` (invoice + bill saves) | `financials.py` |
| `show_create_invoice_page` | `financials.py` |
| `schedule_recurring_transaction` | `accounting_engine.py` |

## Phase 5B.9 — High-risk conversion plan

See [high_risk_identity_conversion_plan.md](high_risk_identity_conversion_plan.md) for phased conversion order (5B.10A–5B.10G).

## Phase 5B.10A Conversions (completed)

| Function | File |
|----------|------|
| `_insert_stock_movement_record` | `modules.py` |

## Phase 5B.10B Conversions (completed)

| Function | File |
|----------|------|
| `show_accounts_payable_page` | `modules.py` |
| `show_create_bill_page` | `modules.py` |
| `show_sales_purchase` (Purchase / bill branch only) | `modules.py` |
