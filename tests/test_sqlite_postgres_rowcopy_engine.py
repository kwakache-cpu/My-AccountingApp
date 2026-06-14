import sqlite3
import tempfile
import unittest
import io
from pathlib import Path
from unittest.mock import Mock, patch

from sqlite_postgres_rowcopy_dryrun import RowCopyDryRunResult, RowCopyDryRunStatus, TableRowCopyDryRun
from sqlite_postgres_rowcopy_engine import (
    ROW_COPY_ENABLE_ENV_VAR,
    RowCopyStatus,
    build_row_copy_batches_from_dryrun,
    execute_guarded_row_copy_to_staging,
    execute_row_copy_batches_with_connection,
    validate_row_copy_guard,
)
from postgres_staging_deployer import main


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

    def close(self):
        self.events.append(("connection_close",))


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
            "sqlite3.connect",
            "create_engine",
            "get_database_url",
            "ERP_ENABLE_POSTGRES_RUNTIME",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)

    def _valid_env(self):
        return {
            ROW_COPY_ENABLE_ENV_VAR: "1",
            "ERP_ENVIRONMENT": "staging",
            "DATABASE_URL": "postgresql://user:secret@example.test/app",
        }

    def test_all_guards_missing_blocks(self):
        guard = validate_row_copy_guard(copy_rows_flag=False, confirmation_flag=False, environ={}, driver_preference=("missing",))
        self.assertTrue(guard.blocked)
        self.assertEqual(guard.status, RowCopyStatus.BLOCKED)
        self.assertFalse(guard.guard_results[ROW_COPY_ENABLE_ENV_VAR])
        self.assertFalse(guard.guard_results["ERP_ENVIRONMENT_is_staging"])
        self.assertFalse(guard.guard_results["DATABASE_URL_present"])
        self.assertFalse(guard.guard_results["explicit_copy_rows_flag"])

    def test_missing_confirmation_blocks(self):
        guard = validate_row_copy_guard(
            copy_rows_flag=True,
            confirmation_flag=False,
            environ=self._valid_env(),
            driver_preference=("sqlite3",),
        )
        self.assertTrue(guard.blocked)
        self.assertFalse(guard.guard_results["explicit_confirm_row_copy_flag"])

    def test_non_staging_blocks(self):
        env = self._valid_env()
        env["ERP_ENVIRONMENT"] = "production"
        guard = validate_row_copy_guard(
            copy_rows_flag=True,
            confirmation_flag=True,
            environ=env,
            driver_preference=("sqlite3",),
        )
        self.assertTrue(guard.blocked)
        self.assertFalse(guard.guard_results["ERP_ENVIRONMENT_is_staging"])

    def test_missing_database_url_blocks(self):
        env = self._valid_env()
        env.pop("DATABASE_URL")
        guard = validate_row_copy_guard(
            copy_rows_flag=True,
            confirmation_flag=True,
            environ=env,
            driver_preference=("sqlite3",),
        )
        self.assertTrue(guard.blocked)
        self.assertFalse(guard.guard_results["DATABASE_URL_present"])

    def test_guarded_row_copy_opens_sqlite_through_readonly_factory_and_commits(self):
        sqlite_conn = self._sqlite_conn()
        postgres_conn = MockPostgresConnection()
        sqlite_factory = Mock(return_value=sqlite_conn)
        connector = Mock(return_value=postgres_conn)
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "rowcopy.md"
            result = execute_guarded_row_copy_to_staging(
                copy_rows_flag=True,
                confirmation_flag=True,
                sqlite_db_path=Path("source.db"),
                output_path=output_path,
                environ=self._valid_env(),
                connector=connector,
                sqlite_connection_factory=sqlite_factory,
                dryrun_builder=Mock(return_value=self._dryrun()),
            )
            report = output_path.read_text(encoding="utf-8")
        self.assertEqual(result.status, RowCopyStatus.COMPLETED)
        self.assertTrue(result.run_result.committed)
        self.assertEqual(result.run_result.rows_copied, 5)
        sqlite_factory.assert_called_once_with(Path("source.db"))
        connector.assert_called_once_with("postgresql://user:secret@example.test/app", result.guard.driver_name, 5)
        self.assertIn(("commit",), postgres_conn.events)
        self.assertIn(("connection_close",), postgres_conn.events)
        self.assertIn("Status: COMPLETED", report)
        self.assertNotIn("secret", report)

    def test_guarded_row_copy_failure_rolls_back_and_closes_connections(self):
        sqlite_conn = self._sqlite_conn()
        postgres_conn = MockPostgresConnection(fail_after=1)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = execute_guarded_row_copy_to_staging(
                copy_rows_flag=True,
                confirmation_flag=True,
                sqlite_db_path=Path("source.db"),
                output_path=Path(temp_dir) / "rowcopy.md",
                environ=self._valid_env(),
                connector=Mock(return_value=postgres_conn),
                sqlite_connection_factory=Mock(return_value=sqlite_conn),
                dryrun_builder=Mock(return_value=self._dryrun()),
            )
        self.assertEqual(result.status, RowCopyStatus.ROLLED_BACK)
        self.assertTrue(result.run_result.rolled_back)
        self.assertIn(("rollback",), postgres_conn.events)
        self.assertIn(("connection_close",), postgres_conn.events)
        self.assertNotIn(("commit",), postgres_conn.events)

    def test_cli_default_unaffected(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        self.assertIn("PostgreSQL staging deployment skeleton dry-run.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_runtime_not_enabled_by_row_copy_sources(self):
        deployer_source = Path("postgres_staging_deployer.py").read_text(encoding="utf-8")
        engine_source = Path("sqlite_postgres_rowcopy_engine.py").read_text(encoding="utf-8")
        for source in (deployer_source, engine_source):
            self.assertNotIn("DB_BACKEND", source)
            self.assertNotIn("ERP_ENABLE_POSTGRES_RUNTIME", source)
            self.assertNotIn("init_db", source)
            self.assertNotIn("get_connection", source)


if __name__ == "__main__":
    unittest.main()
