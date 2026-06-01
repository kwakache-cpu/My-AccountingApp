# PostgreSQL Placeholder Inventory (Phase 5B.11)

**Audited at:** 2026-06-01 20:09:00 UTC
**Scope:** `database.py`, `modules.py`, `financials.py`, `accounting_engine.py`, `app.py`, `enterprise_services.py`, `erp_migrations.py`

## Executive Summary

| Metric | Count |
|--------|------:|
| Literal `?` placeholders (heuristic, excl. strings/logging) | **1032** |
| `db_param_placeholder()` / `db_placeholders()` call sites | **5** |
| Portable helper definitions | `database.py` only |

**Classification legend**

- **Already portable** — uses `db_param_placeholder()`, `db_placeholders()`, or Postgres `%s` in `db_table_exists` / `db_column_exists` branches
- **Needs helper conversion** — SQL uses literal `?`; will fail on psycopg2/psycopg without rewrite
- **SQLite-only** — path gated to SQLite runtime (backup, file paths, PRAGMA diagnostics)
- **Test/report only** — not in scoped production modules (noted when N/A here)

## Per-File Summary

| File | `?` count | Helper calls | Risk | Dominant pattern |
|------|----------:|---------------:|------|------------------|
| `database.py` | 162 | 5 | MEDIUM | literal `?` throughout |
| `modules.py` | 683 | 0 | HIGH | literal `?` throughout |
| `financials.py` | 41 | 0 | MEDIUM | literal `?` throughout |
| `accounting_engine.py` | 128 | 0 | HIGH | literal `?` throughout |
| `app.py` | 18 | 0 | MEDIUM | literal `?` throughout |
| `enterprise_services.py` | 0 | 0 | LOW | mixed helpers + literals |
| `erp_migrations.py` | 4 | 0 | MEDIUM | literal `?` + `INSERT OR IGNORE` |

## Detailed Findings by File

### `database.py`

**Already portable**
- `db_param_placeholder()` / `db_placeholders()` — central routing to `%s` on Postgres
- `db_table_exists()` / `db_column_exists()` — `%s` branch for information_schema
- `db_insert_ignore_sql()` — ON CONFLICT DO NOTHING on Postgres
- `insert_returning_id_sql()` — uses `db_placeholders()` internally

**Needs helper conversion**
- _Review remaining literals in hot paths._

**SQLite-only**
- Company/subscription CRUD — literal `?` (lines ~3379–3942)
- Backup/restore diagnostics — literal `?` + `sqlite_master`
- Schema deployment `_deploy_full_schema` — SQLite DDL only

**Top functions by `?` count**

| Function | `?` |
|----------|----:|
| `create_company_branch` | 20 |
| `update_company_branch` | 16 |
| `log_audit_action` | 16 |
| `(module)` | 12 |
| `create_company_record` | 9 |
| `_log_migration_event` | 9 |
| `update_company_staff_branch_assignment` | 9 |
| `assign_branch_manager` | 8 |

### `modules.py`

**Already portable**
- Critical write paths use `ensure_insert_sql_returning()` + `get_inserted_id()` (identity portable)

**Needs helper conversion**
- ~683 literal `?` in execute() SQL — **needs systematic `db_placeholders()` pass**

**SQLite-only**
- _N/A or see sqlite feature inventory._

**Top functions by `?` count**

| Function | `?` |
|----------|----:|
| `(module)` | 117 |
| `_import_validated_stock_rows` | 35 |
| `_import_inventory_from_excel` | 29 |
| `_process_pos_return` | 28 |
| `_persist_pos_sale` | 27 |
| `show_sales_purchase` | 27 |
| `_import_sales_from_excel` | 26 |
| `show_payroll` | 24 |

### `financials.py`

**Already portable**
- Critical write paths use `ensure_insert_sql_returning()` + `get_inserted_id()` (identity portable)

**Needs helper conversion**
- ~41 literal `?` in execute() SQL — **needs systematic `db_placeholders()` pass**

**SQLite-only**
- _N/A or see sqlite feature inventory._

**Top functions by `?` count**

| Function | `?` |
|----------|----:|
| `show_invoice_manager` | 27 |
| `show_create_invoice_page` | 11 |
| `_journal_df` | 1 |
| `get_depreciation_schedule` | 1 |
| `get_ledger_balances` | 1 |

### `accounting_engine.py`

**Already portable**
- Critical write paths use `ensure_insert_sql_returning()` + `get_inserted_id()` (identity portable)

**Needs helper conversion**
- ~128 literal `?` in execute() SQL — **needs systematic `db_placeholders()` pass**

**SQLite-only**
- _N/A or see sqlite feature inventory._

**Top functions by `?` count**

| Function | `?` |
|----------|----:|
| `post_journal_entry` | 26 |
| `get_or_create_account` | 25 |
| `_mirror_legacy_transactions` | 9 |
| `_legacy_voucher_insert` | 9 |
| `get_ap_aging_report` | 9 |
| `get_ar_aging_report` | 8 |
| `_resolve_source_document_mismatches` | 4 |
| `get_finance_integrity_diagnostics` | 4 |

### `app.py`

- Minimal SQL (`?` ≤ 1); UI delegates to modules/database.
**Already portable**
- _None beyond database.py helpers._

**Needs helper conversion**
- _Review remaining literals in hot paths._

**SQLite-only**
- _N/A or see sqlite feature inventory._

**Top functions by `?` count**

| Function | `?` |
|----------|----:|
| `_show_admin_recovery_panel` | 7 |
| `submit_payment_reference` | 4 |
| `(module)` | 3 |
| `login_ui` | 2 |
| `_show_legacy_dashboard` | 1 |
| `_show_local_dashboard` | 1 |

### `enterprise_services.py`

- No SQL placeholders detected in scan.

### `erp_migrations.py`

- No SQL placeholders detected in scan.

## Risk Matrix

| Area | Risk | Reason |
|------|------|--------|
| Placeholders in `modules.py` | **HIGH** | Largest app surface; almost all SQL is literal `?` |
| Placeholders in `accounting_engine.py` | **HIGH** | Reporting + posting queries use `?` |
| Placeholders in `database.py` schema ensure | **HIGH** | `ensure_schema` / `_deploy_full_schema` not dialect-aware |
| Helper infrastructure | **LOW** | `db_param_placeholder()` exists but rarely called from app code |
| Identity-related INSERTs | **LOW** | RETURNING appended via `ensure_insert_sql_returning()` |

## Recommendation

1. Introduce a thin SQL builder pass: wrap new SQL with `db_placeholders(n)`; migrate hot paths first (POS, payments, journal).
2. Do **not** enable Postgres runtime until `ensure_schema` and `erp_migrations` emit Postgres-compatible DDL/DML.
3. Identity paths are largely done; placeholder pass is now the primary SQL blocker.
