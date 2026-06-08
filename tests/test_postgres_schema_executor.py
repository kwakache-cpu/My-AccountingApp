import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from postgres_deployment_executor import APPLY_NOT_IMPLEMENTED_MESSAGE
from postgres_schema_executor import (
    EXECUTION_BLOCKED_MESSAGE,
    SchemaExecutionPlan,
    build_schema_execution_plan,
    execute_schema_plan,
    split_sql_statements,
)
from postgres_staging_deployer import main


class PostgresSchemaExecutorTests(unittest.TestCase):
    def test_dry_run_parses_schema_statements(self):
        plan = build_schema_execution_plan()
        self.assertTrue(plan.dry_run)
        self.assertFalse(plan.execution_allowed)
        self.assertTrue(plan.rollback_modeled)
        self.assertGreater(len(plan.statements), 10)
        self.assertEqual(plan.statements[0], "BEGIN;")
        self.assertEqual(plan.statements[-1], "COMMIT;")
        self.assertTrue(any(statement.startswith("CREATE TABLE IF NOT EXISTS companies") for statement in plan.statements))

    def test_split_sql_statements_ignores_comments_and_keeps_quoted_semicolons(self):
        sql = """
-- comment with ; should not split
CREATE TABLE example (message TEXT DEFAULT 'a;b');
/* block ; comment */
CREATE TABLE second (name TEXT);
"""
        statements = split_sql_statements(sql)
        self.assertEqual(len(statements), 2)
        self.assertIn("'a;b'", statements[0])
        self.assertNotIn("comment", statements[0])
        self.assertTrue(statements[1].startswith("CREATE TABLE second"))

    def test_apply_remains_blocked(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        exit_code = main(["--apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(APPLY_NOT_IMPLEMENTED_MESSAGE, stderr.getvalue())

    def test_mock_execution_executes_statements_in_tests_only(self):
        plan = SchemaExecutionPlan(
            source_path=Path("mock.sql"),
            statements=("BEGIN;", "CREATE TABLE example (id BIGINT);", "COMMIT;"),
        )
        connection = Mock()
        result = execute_schema_plan(plan, connection, allow_mock_execution=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.statements_executed, 3)
        self.assertEqual(connection.execute.call_count, 3)
        connection.execute.assert_any_call("CREATE TABLE example (id BIGINT);")
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()

    def test_execution_is_blocked_without_mock_opt_in(self):
        plan = SchemaExecutionPlan(source_path=Path("mock.sql"), statements=("BEGIN;",))
        connection = Mock()
        result = execute_schema_plan(plan, connection)
        self.assertFalse(result.ok)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.error_message, EXECUTION_BLOCKED_MESSAGE)
        connection.execute.assert_not_called()

    def test_rollback_behavior_is_modeled_on_mock_failure(self):
        plan = SchemaExecutionPlan(
            source_path=Path("mock.sql"),
            statements=("BEGIN;", "CREATE TABLE example (id BIGINT);", "COMMIT;"),
        )
        connection = Mock()
        connection.execute.side_effect = [None, RuntimeError("boom")]
        result = execute_schema_plan(plan, connection, allow_mock_execution=True)
        self.assertFalse(result.ok)
        self.assertTrue(result.execution_allowed)
        self.assertEqual(result.statements_executed, 1)
        self.assertTrue(result.rollback_attempted)
        self.assertTrue(result.rollback_succeeded)
        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()
        self.assertIn("RuntimeError: boom", result.error_message)

    def test_no_database_url_or_supabase_used_by_executor(self):
        source = Path("postgres_schema_executor.py").read_text(encoding="utf-8")
        forbidden_terms = [
            "DATABASE_URL",
            "os.environ",
            "supabase",
            "create_client",
            "psycopg.connect",
            "psycopg2.connect",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)

    def test_plan_can_be_built_from_temp_schema_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; CREATE TABLE sample (id BIGINT); COMMIT;", encoding="utf-8")
            plan = build_schema_execution_plan(schema_path)
        self.assertEqual(len(plan.statements), 3)
        self.assertFalse(plan.execution_allowed)


if __name__ == "__main__":
    unittest.main()
