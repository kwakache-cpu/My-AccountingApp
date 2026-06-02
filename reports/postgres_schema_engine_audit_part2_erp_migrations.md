# PostgreSQL Schema Engine Audit Part 2: ERP Migrations

Scope: `erp_migrations.py` only. Runtime code was not changed.

## Inventory

| Line | Function | Occurrence | Category | PostgreSQL Risk |
|---:|---|---|---|---|
| 6 | `_table_exists` | `sqlite_master` | SQLite catalog introspection | CRITICAL |
| 6 | `_table_exists` | `? placeholders` | SQLite/DB-API placeholder style | HIGH |
| 15 | `_column_exists` | `PRAGMA` | SQLite schema introspection | CRITICAL |
| 21 | `_ensure_column` | `ALTER TABLE` | Runtime migration DDL | HIGH |
| 26 | `_ensure_setting_defaults` | `INSERT OR IGNORE` | SQLite conflict handling | HIGH |
| 42 | `_ensure_migration_history_table` | `CREATE TABLE` | Runtime migration DDL | MEDIUM |
| 54 | `_migration_applied` | `? placeholders` | SQLite/DB-API placeholder style | HIGH |
| 62 | `_record_migration` | `INSERT OR IGNORE` | SQLite conflict handling | HIGH |
| 62 | `_record_migration` | `? placeholders` | SQLite/DB-API placeholder style | HIGH |
| 62 | `_record_migration` | `? placeholders` | SQLite/DB-API placeholder style | HIGH |

No occurrences found for `sqlite_sequence`, `AUTOINCREMENT`, `BEGIN IMMEDIATE`, `WAL`, `busy_timeout`, `journal_mode`, `synchronous`, `foreign_keys`, `sqlite3.Row`, or `row_factory`.

## Count By Category

| Category | Count |
|---|---:|
| Runtime migration DDL | 2 |
| SQLite catalog introspection | 1 |
| SQLite conflict handling | 2 |
| SQLite schema introspection | 1 |
| SQLite/DB-API placeholder style | 4 |

### Count By Occurrence Type

| Occurrence | Count |
|---|---:|
| `PRAGMA` | 1 |
| `sqlite_master` | 1 |
| `sqlite_sequence` | 0 |
| `AUTOINCREMENT` | 0 |
| `INSERT OR IGNORE` | 2 |
| `CREATE TABLE` | 1 |
| `ALTER TABLE` | 1 |
| `BEGIN IMMEDIATE` | 0 |
| `WAL` | 0 |
| `busy_timeout` | 0 |
| `journal_mode` | 0 |
| `synchronous` | 0 |
| `foreign_keys` | 0 |
| `sqlite3.Row` | 0 |
| `row_factory` | 0 |
| `? placeholders` | 4 |

## Migration Engine Blockers

| Blocker | Risk | Impact |
|---|---|---|
| `_table_exists` reads `sqlite_master` and uses `?` placeholders. | CRITICAL | PostgreSQL has no `sqlite_master`; table existence must use `information_schema` or `pg_catalog`, and parameters must use the active PostgreSQL driver's placeholder style. |
| `_column_exists` uses `PRAGMA table_info(...)`. | CRITICAL | PostgreSQL cannot execute PRAGMA; column checks must use `information_schema.columns` or `pg_catalog`. |
| `_ensure_column` emits runtime `ALTER TABLE ... ADD COLUMN ...` with direct identifier interpolation. | HIGH | PostgreSQL can add columns, but identifiers and type/default fragments need PostgreSQL-safe quoting and migration ownership. |
| `_ensure_setting_defaults` uses `INSERT OR IGNORE`. | HIGH | PostgreSQL requires `ON CONFLICT DO NOTHING` with an explicit unique or primary-key target. |
| `_record_migration` uses `INSERT OR IGNORE` and two `?` placeholders. | HIGH | Migration history recording would fail on PostgreSQL before the migration can be marked applied. |
| `_migration_applied` uses a `?` placeholder. | HIGH | PostgreSQL drivers used by this app expect `%s`-style parameters, so the applied-check query would fail. |

## What Would Fail If DB_BACKEND=postgres Today

1. The first table-existence check would fail because `_table_exists` queries `sqlite_master`.
2. Column-existence checks would fail because `_column_exists` runs `PRAGMA table_info`.
3. Migration history reads and writes would fail because `_migration_applied` and `_record_migration` use `?` placeholders.
4. Idempotent inserts would fail because PostgreSQL does not support `INSERT OR IGNORE`.
5. Additive column migrations could fail or become unsafe because `_ensure_column` interpolates identifiers and SQLite-oriented type/default fragments directly into `ALTER TABLE`.
6. `run_foundation_migrations` would not reliably complete, because both migration gating and migration recording depend on SQLite-specific SQL.

## Recommended Phase 5B.13A-3 Scope

1. Add backend-aware table and column introspection for migration code, using PostgreSQL `information_schema` or `pg_catalog` when the active backend is PostgreSQL.
2. Replace migration SQL placeholders through the existing portable query/write layer, or introduce a migration-local placeholder adapter that emits `%s` for PostgreSQL and `?` for SQLite.
3. Convert `INSERT OR IGNORE` migration writes to backend-aware conflict SQL, using `ON CONFLICT (id) DO NOTHING` for `system_settings` and `ON CONFLICT (migration_id) DO NOTHING` for `migration_history`.
4. Harden `_ensure_column` with backend-specific identifier handling and PostgreSQL-compatible type/default fragments before allowing runtime migrations against PostgreSQL.
5. Decide whether `erp_migrations.py` remains a dual-backend runtime migration engine or becomes SQLite-only while PostgreSQL migrations move to explicit migration files.

## Validation

- Passed: `python -m py_compile erp_migrations.py`
