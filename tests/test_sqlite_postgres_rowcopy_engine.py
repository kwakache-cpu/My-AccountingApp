import sqlite3
import tempfile
import unittest
from pathlib import Path

from sqlite_postgres_rowcopy_dryrun import RowCopyDryRunResult, RowCopyDryRunStatus, TableRowCopyDryRun
from sqlite_postgres_rowcopy_engine import (
    RowCopyStatus,
    build_row_copy_batches_from_dryrun,
    execute_row_copy_batches_with_connection,
)


class MockCursor:
    def __init__(self, events, fail_after=None):
        self.events = events
        self.fail_after = fail_after
        self.execute_count = 0

    def execute(self, sql, params):
        self.execute_count += 1
        if self.fail_after is not None and self.execute_count > self.fail_after:
            raise RuntimeError("mock insert failed")
        self.events.append(("execute", sql, params))

    def close(self):
        self.events.append(("close",))


class MockPostgresConnection:
    def __init__(self, fail_after=None):
        self.events = []
        self.fail_after = fail_after
        self.cursor_instance = MockCursor(self.events, fail_after=fail_after)

    def cursor(self):
        self.events.append(("cursor",))
        return self.cursor_instance

    def commit(self):
        self.events.append(("commit",))

    def rollback(self):
        self.events.append(("rollback",))


class SQLitePostgresRowCopyEngineTests(unittest.TestCase):
    def _sqlite_conn(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE companies (key TEXT PRIMARY KEY, name TEXT)")
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, company_key TEXT, full_name TEXT)")
        connection.executemany(
            "INSERT INTO companies (key, name) VALUES (?, ?)",
            [("c1", "One"), ("c2", "Two")],
        )
        connection.executemany(
            "INSERT INTO users (id, company_key, full_name) VALUES (?, ?, ?)",
            [(1, "c1", "Ada"), (2, "c1", "Grace"), (3, "c2", "Linus")],
        )
        connection.commit()
        return connection

    def _dryrun(self):
        company_table = TableRowCopyDryRun(
            table_name="companies",
            source_row_count=2,
            rows_evaluated=2,
            rows_mappable=2,
            rows_unmappable=0,
            source_columns=["key", "name"],
            destination_columns=["key", "name"],
            mapped_columns=["key", "name"],
            nullable_fields=["name"],
            required_fields=["key"],
            defaulted_fields=[],
            migration_order=1,
            batch_size=100,
            batch_count=1,
        )
        user_table = TableRowCopyDryRun(
            table_name="users",
            source_row_count=3,
            rows_evaluated=3,
            rows_mappable=3,
            rows_unmappable=0,
            source_columns=["company_key", "full_name", "id"],
            destination_columns=["company_key", "full_name", "id"],
            mapped_columns=["company_key", "full_name", "id"],
            nullable_fields=["full_name"],
            required_fields=["company_key", "id"],
            defaulted_fields=[],
            migration_order=2,
            dependencies=["companies"],
            batch_size=2,
            batch_count=2,
        )
        return RowCopyDryRunResult(
            status=RowCopyDryRunStatus.READY_FOR_DRY_RUN_COPY,
            tables_evaluated=2,
            rows_evaluated=5,
            rows_mappable=5,
            rows_unmappable=0,
            estimated_batches=3,
            fk_dependency_order=["companies", "users"],
            table_results=[user_table, company_table],
            column_mapping_issues=[],
            blockers=[],
        )

    def test_blocked_unless_allow_execution_true(self):
        batches = build_row_copy_batches_from_dryrun(self._dryrun())
        sqlite_conn = self._sqlite_conn()
        postgres_conn = MockPostgresConnection()
        try:
            result = execute_row_copy_batches_with_connection(batches, sqlite_conn, postgres_conn)
        finally:
            sqlite_conn.close()
        self.assertEqual(result.status, RowCopyStatus.BLOCKED)
        self.assertEqual(postgres_conn.events, [])
        self.assertEqual(result.batches_planned, 3)
        self.assertEqual(result.rows_planned, 5)

    def test_mock_postgres_receives_insert_statements_and_commits_after_success(self):
        batches = build_row_copy_batches_from_dryrun(self._dryrun())
        sqlite_conn = self._sqlite_conn()
        postgres_conn = MockPostgresConnection()
        try:
            result = execute_row_copy_batches_with_connection(
                batches,
                sqlite_conn,
                postgres_conn,
                allow_execution=True,
            )
        finally:
            sqlite_conn.close()
        execute_events = [event for event in postgres_conn.events if event[0] == "execute"]
        self.assertEqual(result.status, RowCopyStatus.COMPLETED)
        self.assertEqual(result.rows_copied, 5)
        self.assertEqual(len(execute_events), 5)
        self.assertEqual(postgres_conn.events[-2:], [("commit",), ("close",)])
        self.assertIn('INSERT INTO "companies"', execute_events[0][1])
        self.assertIn('INSERT INTO "users"', execute_events[-1][1])

    def test_rollback_after_failure(self):
        batches = build_row_copy_batches_from_dryrun(self._dryrun())
        sqlite_conn = self._sqlite_conn()
        postgres_conn = MockPostgresConnection(fail_after=2)
        try:
            result = execute_row_copy_batches_with_connection(
                batches,
                sqlite_conn,
                postgres_conn,
                allow_execution=True,
            )
        finally:
            sqlite_conn.close()
        self.assertEqual(result.status, RowCopyStatus.ROLLED_BACK)
        self.assertIn(("rollback",), postgres_conn.events)
        self.assertNotIn(("commit",), postgres_conn.events)
        self.assertIn("mock insert failed", result.error_message)

    def test_batch_ordering_follows_fk_safe_order(self):
        batches = build_row_copy_batches_from_dryrun(self._dryrun())
        self.assertEqual([batch.table_name for batch in batches], ["companies", "users", "users"])
        self.assertEqual([batch.batch_number for batch in batches], [1, 1, 2])

    def test_sqlite_source_remains_unchanged(self):
        batches = build_row_copy_batches_from_dryrun(self._dryrun())
        sqlite_conn = self._sqlite_conn()
        before = sqlite_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        postgres_conn = MockPostgresConnection()
        try:
            execute_row_copy_batches_with_connection(
                batches,
                sqlite_conn,
                postgres_conn,
                allow_execution=True,
            )
            after = sqlite_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            sqlite_conn.close()
        self.assertEqual(before, after)

    def test_no_real_connection_or_runtime_configuration_usage(self):
        source = Path("sqlite_postgres_rowcopy_engine.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "DATABASE_URL",
            "os.environ",
            "sqlite3.connect",
            "psycopg",
            "create_engine",
            "get_database_url",
            "ERP_ENABLE_POSTGRES_RUNTIME",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
