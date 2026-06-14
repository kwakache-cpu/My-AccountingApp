# SQLite to PostgreSQL Row-Copy Engine Mock

Phase: 5B.15G

Mock-first row-copy engine structure only. No real data migration, PostgreSQL connection discovery, PostgreSQL write to staging/production, PostgreSQL runtime enablement, production deployment, or SQLite behavior change was attempted.

## Summary

- Engine module: `sqlite_postgres_rowcopy_engine.py`
- Focused tests: `tests/test_sqlite_postgres_rowcopy_engine.py`
- Source dry-run status: READY_FOR_DRY_RUN_COPY
- SQLite rows represented by dry-run: 527
- Dry-run mapping failures: 0
- Row-copy batches built from dry-run: 31
- Engine execution default: BLOCKED unless `allow_execution=True`
- Allowed execution target in this phase: injected mock PostgreSQL connection in tests only

## Mock Execution Behavior

- `build_row_copy_batches_from_dryrun()` derives batches from the Phase 5B.15F dry-run result.
- Batches preserve FK-safe migration order from the dry-run table plan.
- Empty tables do not produce executable batches.
- `execute_row_copy_batches_with_connection(..., allow_execution=False)` returns `RowCopyStatus.BLOCKED` before opening a cursor or executing inserts.
- `execute_row_copy_batches_with_connection(..., allow_execution=True)` reads SQLite rows and sends parameterized `INSERT INTO ... VALUES (%s, ...)` statements only to the injected `postgres_conn`.
- The engine commits only after all batches succeed.
- The engine rolls back on insert failure.
- The SQLite connection is read through `SELECT ... LIMIT ? OFFSET ?`; no SQLite writes are issued.

## Safety Controls

- The engine never discovers or creates a PostgreSQL connection.
- The engine never reads runtime environment configuration or database URLs.
- The engine never enables PostgreSQL runtime.
- The engine does not import PostgreSQL drivers.
- PostgreSQL writes are limited to whatever injected object is passed by tests.
- Real row-copy execution remains unauthorized.

## Test Evidence

- Blocked unless `allow_execution=True`: covered.
- Mock postgres receives INSERT statements: covered.
- Commit after success: covered.
- Rollback after failure: covered.
- Batch ordering follows FK-safe order: covered.
- SQLite source remains unchanged: covered.
- No database URL/runtime configuration usage: covered.
- No real PostgreSQL connection creation: covered.

Focused test command:

```powershell
python -m unittest discover tests -p test_sqlite_postgres_rowcopy_engine.py
```

Result:

```text
Ran 6 tests in 0.003s
OK
```

## Final Status

- MOCK_ROW_COPY_ENGINE_READY: the controlled row-copy engine structure is implemented and test-covered for injected mock connections.
- Real guarded row-copy can be implemented next, but must add explicit staging guards and must remain blocked until separately authorized.
