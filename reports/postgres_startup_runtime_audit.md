# PostgreSQL Startup Runtime Audit

Scope: startup/runtime backend selection paths only:

- `database.py`: `startup_database()`, `get_connection()`, backend selectors, runtime enablement checks, SQLite/PostgreSQL openers, lightweight integrity/startup call points.
- `app.py`: database startup and initialization calls in `main()`.

Runtime code was not changed.

## Key Findings

| Area | Finding | Risk |
|---|---|---|
| Backend selection | `get_active_db_backend()` returns `postgres` only when configured backend is PostgreSQL, runtime flag is enabled, and `DATABASE_URL` exists. Otherwise it silently returns `sqlite`. | MEDIUM |
| Connection factory | `get_connection()` is backend-aware and can call `_open_postgres_connection()` when PostgreSQL is fully enabled. | LOW |
| App startup order | `app.py` calls `ensure_schema()` before `startup_database()`. `ensure_schema()` opens SQLite directly and runs SQLite PRAGMA/ALTER/schema integrity logic. | CRITICAL |
| Canonical startup | `startup_database()` is SQLite-file first: it calls `_ensure_local_db_file()`, validates `DB_PATH`, opens `_open_sqlite_connection()`, runs SQLite readiness checks, and later opens SQLite again for migrations. | CRITICAL |
| Readiness reporting | `get_database_health_snapshot()` and `is_database_ready_for_production()` are SQLite database-file readiness checks, not backend-neutral health checks. | CRITICAL |
| PostgreSQL connection | `_open_postgres_connection()` can create a wrapped psycopg/psycopg2 connection and enforce `sslmode=require`. It is not used by `startup_database()`. | HIGH |
| Lightweight checks | `_run_lightweight_integrity_checks()` calls SQLite DDL/bootstrap helpers, including `ensure_schema_integrity()`, `_ensure_database_identity_table()`, `_ensure_app_compatibility_tables()`, and schema manifest diagnostics. | CRITICAL |

## 1. What Happens Today When DB_BACKEND=sqlite?

`get_configured_db_backend()` normalizes `DB_BACKEND=sqlite` to `sqlite`, and `get_active_db_backend()` returns `sqlite`.

In `app.py`, `main()` first calls `ensure_schema()`. That function opens `_open_sqlite_connection()`, runs `PRAGMA table_info(companies)`, may run `ALTER TABLE companies ...`, then calls `ensure_schema_integrity()`.

`main()` then calls `startup_database()`, which:

1. Calls `_ensure_local_db_file()`.
2. Uses SQLite file readiness through `is_database_valid()` and `get_database_health_snapshot()`.
3. May open `_open_sqlite_connection()` for preflight and run `_run_lightweight_integrity_checks()`.
4. Opens `_open_sqlite_connection()` for startup migrations and validation.
5. Returns a startup result such as `bootstrap_mode`, `fallback_complete`, `startup_complete`, or failure metadata.

Risk: LOW for the current SQLite runtime because this is the designed path.

## 2. What Happens Today When DB_BACKEND=postgres But Runtime Flag Is Off?

`get_configured_db_backend()` returns `postgres`, but `is_postgres_runtime_enabled()` returns false unless `ERP_ENABLE_POSTGRES_RUNTIME` is explicitly one of `1`, `true`, `yes`, or `on`.

Because the runtime flag is off, `get_active_db_backend()` returns `sqlite`. `validate_postgres_runtime_enabled()` would report `postgres_blocked=True` and include the reason `ERP_ENABLE_POSTGRES_RUNTIME is not enabled.`

Startup still follows the same SQLite path as `DB_BACKEND=sqlite`, including `app.py` `ensure_schema()` and `startup_database()` SQLite file validation.

Risk: MEDIUM. The fallback is intentional as a safety gate, but it can mask misconfiguration because `DB_BACKEND=postgres` does not make startup exercise PostgreSQL.

## 3. What Happens Today When DB_BACKEND=postgres, DATABASE_URL Is Set, And ERP_ENABLE_POSTGRES_RUNTIME=1?

Backend selection becomes PostgreSQL-aware:

- `get_active_db_backend()` returns `postgres`.
- `validate_postgres_runtime_enabled()` can return `ok=True` if a PostgreSQL driver is installed.
- Direct calls to `get_connection()` can use `_open_postgres_connection()`.

However, application startup does not become PostgreSQL-safe:

1. `app.py` calls `ensure_schema()` before `startup_database()`.
2. `ensure_schema()` ignores `get_connection()` and calls `_open_sqlite_connection()` directly.
3. `startup_database()` also ignores active backend selection and starts by calling `_ensure_local_db_file()`, `is_database_valid(DB_PATH)`, `get_database_health_snapshot(DB_PATH)`, and later `_open_sqlite_connection()`.
4. Health/readiness remains based on the local SQLite file at `DB_PATH`, not `DATABASE_URL`.
5. If startup proceeds into lightweight checks, `_run_lightweight_integrity_checks()` executes SQLite DDL/PRAGMA/bootstrap helpers.

Risk: CRITICAL. PostgreSQL may be active for later `get_connection()` calls, but the startup path still requires and mutates a SQLite runtime database file.

## 4. SQLite-Only Hard Blockers

| Startup Call | Why It Blocks PostgreSQL | Risk |
|---|---|---|
| `app.py` `ensure_schema()` before `startup_database()` | Directly opens `_open_sqlite_connection()` and runs SQLite schema repair. | CRITICAL |
| `startup_database()` `_ensure_local_db_file()` | Ensures/manages a local SQLite DB path before any PostgreSQL startup branch. | CRITICAL |
| `startup_database()` `is_database_valid(DB_PATH)` | Requires `DB_PATH` to exist and be a valid SQLite file; uses `sqlite_master` and PRAGMA metadata. | CRITICAL |
| `startup_database()` `get_database_health_snapshot(DB_PATH)` | Delegates to SQLite production readiness reporting and returns SQLite-specific health fields. | CRITICAL |
| `startup_database()` `_open_sqlite_connection()` | Used for preflight, migration, and final validation regardless of active backend. | CRITICAL |
| `_run_lightweight_integrity_checks()` | Calls SQLite schema metadata/DDL paths, including `ensure_schema_integrity()`. | CRITICAL |
| `_ensure_migration_metadata_tables()` | Creates SQLite-flavored tables, including `AUTOINCREMENT` in `migration_logs`. | HIGH |
| `_ensure_database_identity_table()` | Uses `PRAGMA table_info`, `ALTER TABLE`, and `?` placeholder writes. | HIGH |
| `_record_schema_version()` | Uses `INSERT OR IGNORE` and `?` placeholders. | HIGH |
| `_log_migration_event()` | Uses `?` placeholders; relies on portable write conversion, but its target table is created by SQLite DDL. | MEDIUM |
| `_open_sqlite_connection()` | Sets `sqlite3.Row`, `PRAGMA foreign_keys`, `busy_timeout`, `journal_mode=WAL`, and `synchronous=NORMAL`. | CRITICAL |

## 5. Safe Or Already Backend-Aware Calls

| Call | Status | Risk |
|---|---|---|
| `get_configured_db_backend()` / `get_db_backend()` | Normalizes `DB_BACKEND` without opening a connection. | LOW |
| `is_postgres_runtime_enabled()` | Reads an explicit runtime flag from secrets/env. | LOW |
| `get_active_db_backend()` | Correctly gates PostgreSQL behind backend, runtime flag, and `DATABASE_URL`. | LOW |
| `validate_postgres_runtime_enabled()` | Checks configured backend, URL, runtime flag, and driver availability without connecting. | LOW |
| `_ensure_postgres_database_url()` | Adds `sslmode=require` when missing. | LOW |
| `_open_postgres_connection()` | Opens psycopg2/psycopg and wraps it in `PostgresManagedConnection`. | MEDIUM |
| `get_connection()` | Routes to PostgreSQL only when the active backend is PostgreSQL; otherwise falls back to SQLite. | MEDIUM |
| `execute_portable_query()` / `execute_portable_write()` | Convert `?` placeholders to `%s` for PostgreSQL where safe. | MEDIUM |
| `db_table_exists()` / `db_column_exists()` | Have PostgreSQL branches using `information_schema`; startup paths do not consistently use them. | MEDIUM |

## 6. What Would Fail First In A Real PostgreSQL Staging Run?

The first failure depends on whether a local SQLite `DB_PATH` already exists.

If `DB_PATH` is missing in production mode, the earliest hard blocker is `app.py` `main()` calling `ensure_schema()`. `ensure_schema()` checks `DB_PATH`, logs that schema safety is skipped if missing, then `startup_database()` calls `_ensure_local_db_file()` and `get_database_health_snapshot(DB_PATH)`. The PostgreSQL database is not used for readiness. In production this can lead startup to recovery/failure logic based on the missing SQLite file, not the PostgreSQL URL.

If a local SQLite `DB_PATH` exists, `ensure_schema()` will open and mutate SQLite before PostgreSQL startup. Then `startup_database()` will continue with SQLite preflight and readiness. PostgreSQL may not fail immediately because it is not the startup database. The first PostgreSQL-specific failure would likely happen after startup, when app code calls `get_connection()` and receives a PostgreSQL connection but then executes SQLite-style SQL, such as the `app.py` currency sync query with `?` placeholders.

Most likely first real staging blocker: CRITICAL, the startup gate is still SQLite-file based and does not bootstrap/validate PostgreSQL at all.

## 7. Recommended Next Phase

1. Add an explicit PostgreSQL branch at the start of `startup_database()` when `get_active_db_backend() == "postgres"`.
2. Move `app.py` away from unconditional `ensure_schema()` before `startup_database()`; make schema startup backend-aware.
3. Create PostgreSQL startup health checks that validate `DATABASE_URL`, driver availability, connectivity, required tables, migration version, and company count without touching `DB_PATH`.
4. Replace SQLite startup metadata helpers with backend-aware versions, especially migration metadata, database identity, schema version, and production readiness.
5. Route lightweight integrity checks through backend-aware table/column helpers, or keep SQLite self-heal checks strictly on SQLite paths.
6. After startup is PostgreSQL-safe, audit the first post-startup `get_connection()` call sites in `app.py` for SQLite placeholders and SQLite-specific SQL.

## Validation

- Passed: `python -m py_compile app.py database.py`
