# PostgreSQL Migration Scorecard (Phase 5B.11 + 5B.12A + 5B.12B)

**Audited at:** 2026-06-01 21:15:36 UTC
**5B.12B:** 11 additional `database.py` read helpers on `execute_portable_query` / `db_table_exists`.

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Identity portability | **GREEN** | Production paths use get_inserted_id / ensure_insert_sql_returning; zero raw lastrowid in app modules |
| Placeholder portability | **RED** | ~1035 scoped literal `?`; **foundation + ~20 portable reads in database.py**; modules/accounting_engine untouched |
| Schema introspection portability | **RED** | PRAGMA / sqlite_master dominate outside small db_* helpers |
| Transaction portability | **YELLOW** | db_begin/commit OK; BEGIN IMMEDIATE SQLite-only in lock wrapper |
| Accounting portability | **YELLOW** | Journal identity GREEN; SQL dialect and strftime filters RED/YELLOW |
| POS portability | **YELLOW** | Sale identity converted; placeholders + inventory PRAGMA remain |
| Inventory portability | **YELLOW** | Stock movement identity OK; schema probes SQLite-specific |
| Branch governance portability | **YELLOW** | Branch catalog/license reads partially portable; user/login SQL and writes remain SQLite-specific |
| Auth portability | **YELLOW** | Straightforward queries but ? placeholders and schema ensure blocker |
| Reporting portability | **RED** | accounting_engine heavy ? + strftime in SQL |
| Data readiness | **GREEN** | FK orphans 0 on SQLite snapshot; cleanup phases documented |
| Overall staging readiness | **RED** | NO-GO for ERP_ENABLE_POSTGRES_RUNTIME=1 until placeholders + DDL |

## Phase 5B.12 placeholder foundation

- Helpers: `db_placeholder`, `execute_portable_query`, `convert_placeholders_for_backend`, `sql_for_backend`
- Tests: `tests/test_placeholder_portability.py`, `tests/test_database_read_placeholder_conversion.py`
- Safe read coverage growing in `database.py` only; no write-path or `modules.py` changes yet

## Phase 5B.10 identity work (reflected)

- `post_journal_entry` — converted (5B.10G)
- POS, payments, bills, invoices, payroll, fixed assets, stock movements — `get_inserted_id` pattern
- Remaining `lastrowid` — tests, `database.py` helper implementation, audit scripts only

## Overall recommendation

**NO-GO** for Postgres runtime switch. Continue on SQLite. Next engineering priority: **placeholder + DDL portability**, not identity.
