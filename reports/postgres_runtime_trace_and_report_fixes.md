# PostgreSQL Runtime Trace and Report Fixes (Phase 5B.15V)

**Completed:** 2026-06-16

## Live runtime symptoms addressed

| Page | Symptom | Classification |
|------|---------|----------------|
| Dashboard | `current transaction is aborted, commands ignored until end of transaction block` | Secondary error after first failed SELECT on shared connection |
| Financial Reports | `psycopg2.errors.UndefinedTable` in `_resolve_source_document_mismatches` | Primary error: `sqlite_master` queried under PostgreSQL |

## Root causes

### Dashboard transaction abort

**First failing query (root):** `_fetch_dashboard_kpi_snapshot()` attempted to read `pos_sales` after `ensure_pos_sales_schema()` returned early on PostgreSQL (runtime DDL blocked). When `pos_sales` was missing or the date predicate was incompatible, the SELECT failed and left the shared `PostgresManagedConnection` in an aborted transaction.

**Secondary error:** Subsequent dashboard reads on the same connection (`journal_entries` today-sales fallback, receivables/payables, inventory insights) surfaced `current transaction is aborted`.

Contributing factors:
- Swallowed exceptions in POS KPI try/except without connection rollback
- SQLite-style `date(column) = date(?)` predicates on text date columns
- No table-existence guard before optional POS reads under PostgreSQL

### Financial Reports UndefinedTable

**First failing query (root):**

```sql
SELECT name FROM sqlite_master WHERE type='table' AND name = ?
```

Called from `accounting_engine._resolve_source_document_mismatches()` for each controlled source document table. PostgreSQL has no `sqlite_master` relation, producing `UndefinedTable`.

## Fixes applied

### `database.py`

- `PostgresManagedConnection._execute_prepared()` — rollback on query exception before re-raising (prevents aborted-transaction poisoning on read paths)
- `sql_cast_as_date()`, `sql_date_equals()`, `sql_date_on_or_after()` — portable date predicates using `CAST(... AS date)`
- `sql_group_concat()` — PostgreSQL `string_agg` / SQLite `GROUP_CONCAT`

### `accounting_engine.py`

- `_resolve_source_document_mismatches()` — uses `db_table_exists()` and `execute_portable_query()`; skips missing optional source tables; no `sqlite_master` under PostgreSQL
- `_source_document_duplicate_postings()` — portable grouped ID aggregation via `sql_group_concat()`

### `modules.py`

- `_dashboard_pos_tables_ready()` — checks `db_table_exists(conn, "pos_sales")` before optional POS analytics
- Dashboard KPI/sales/inventory paths — portable date predicates; removed runtime `ensure_pos_sales_schema()` calls from read-only PostgreSQL dashboard bundle

## Tests added

`tests/test_postgres_runtime_trace_and_report_fixes.py`:

1. `_resolve_source_document_mismatches` does not query `sqlite_master` under PostgreSQL
2. Missing optional source-document tables do not crash Financial Reports integrity diagnostics
3. Dashboard failed SELECT rolls back and does not poison subsequent dashboard reads
4. PostgreSQL managed connection rolls back after query exception
5. SQLite `_resolve_source_document_mismatches` behavior unchanged
6. Portable date and group-concat helpers verified

## Validation

```text
python -m py_compile app.py database.py modules.py financials.py accounting_engine.py  → PASS
python tests/run_regression_tests.py                                                  → PASS (443/443)
git diff --check                                                                      → PASS
```

## Runtime page testing status

**READY_TO_RESUME** PostgreSQL runtime page testing for Dashboard and Financial Reports after validation passes. Login, sidebar, and POS page-load paths remain unchanged from prior phases.

## Out of scope (unchanged)

- No commits, pushes, SQLite data changes, backups deletion, data migration, or production deployment
- No sales/invoices/payments/accounting posts
- Remaining `sqlite_master` probes in `get_journal_dominance_diagnostics()` and other non-page-load paths deferred to follow-up phases
