# PostgreSQL Migration Scorecard (Phase 5B.11 + 5B.12A)

**Audited at:** 2026-06-01 20:46:58 UTC
**5B.12A:** Placeholder foundation helpers shipped; 6 read-only call sites use `execute_portable_query` in `database.py`.

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Identity portability | **GREEN** | Production paths use get_inserted_id / ensure_insert_sql_returning; zero raw lastrowid in app modules |
| Placeholder portability | **RED** | ~1035 literal `?` in scoped modules (source scan); **foundation helpers added** (`db_placeholder`, `execute_portable_query`, etc.); 6 read paths converted in `database.py` only |
| Schema introspection portability | **RED** | PRAGMA / sqlite_master dominate outside small db_* helpers |
| Transaction portability | **YELLOW** | db_begin/commit OK; BEGIN IMMEDIATE SQLite-only in lock wrapper |
| Accounting portability | **YELLOW** | Journal identity GREEN; SQL dialect and strftime filters RED/YELLOW |
| POS portability | **YELLOW** | Sale identity converted; placeholders + inventory PRAGMA remain |
| Inventory portability | **YELLOW** | Stock movement identity OK; schema probes SQLite-specific |
| Branch governance portability | **YELLOW** | Business logic present; introspection/SQL not Postgres-ready |
| Auth portability | **YELLOW** | Straightforward queries but ? placeholders and schema ensure blocker |
| Reporting portability | **RED** | accounting_engine heavy ? + strftime in SQL |
| Data readiness | **GREEN** | FK orphans 0 on SQLite snapshot; cleanup phases documented |
| Overall staging readiness | **RED** | NO-GO for ERP_ENABLE_POSTGRES_RUNTIME=1 until placeholders + DDL |

## Phase 5B.12A placeholder foundation

- `db_placeholder`, `db_placeholders`, `sql_for_backend`, `convert_placeholders_for_backend`, `execute_portable_query`
- `PlaceholderConversionError` when SQL has only quoted `?` characters (unsafe auto-convert)
- Tests: `tests/test_placeholder_portability.py` (10 cases)

## Phase 5B.10 identity work (reflected)

- `post_journal_entry` — converted (5B.10G)
- POS, payments, bills, invoices, payroll, fixed assets, stock movements — `get_inserted_id` pattern
- Remaining `lastrowid` — tests, `database.py` helper implementation, audit scripts only

## Overall recommendation

**NO-GO** for Postgres runtime switch. Continue on SQLite. Next engineering priority: **placeholder + DDL portability**, not identity.
