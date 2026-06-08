import io
import inspect
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from postgres_schema_executor import (
    EXECUTION_BLOCKED_MESSAGE,
    SchemaExecutionAuditStatus,
    SchemaExecutionPlan,
    execute_schema_plan_with_connection,
)
from postgres_staging_deployer import main


class PostgresSchemaExecutionEngineTests(unittest.TestCase):
    def _plan(self):
        return SchemaExecutionPlan(
            source_path=Path("mock.sql"),
            statements=(
                "BEGIN;",
                "CREATE TABLE example (id BIGINT);",
                "COMMIT;",
            ),
        )

    def test_blocked_unless_allow_execution_true(self):
        connection = Mock()
        result = execute_schema_plan_with_connection(self._plan(), connection)
        self.assertFalse(result.ok)
        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.error_message, EXECUTION_BLOCKED_MESSAGE)
        connection.execute.assert_not_called()
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        self.assertEqual(result.audit_log.events[0].status, SchemaExecutionAuditStatus.BLOCKED)

    def test_mock_connection_receives_statements_in_order_and_commits(self):
        connection = Mock()
        plan = self._plan()
        result = execute_schema_plan_with_connection(plan, connection, allow_execution=True)
        self.assertTrue(result.ok)
        self.assertEqual(result.statements_executed, 3)
        self.assertEqual([call.args[0] for call in connection.execute.call_args_list], list(plan.statements))
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()

    def test_audit_events_for_successful_execution(self):
        connection = Mock()
        result = execute_schema_plan_with_connection(self._plan(), connection, allow_execution=True, deployment_id="deploy-ok")
        statuses = [event.status for event in result.audit_log.events]
        self.assertEqual(
            statuses,
            [
                SchemaExecutionAuditStatus.RUNNING,
                SchemaExecutionAuditStatus.COMPLETED,
                SchemaExecutionAuditStatus.RUNNING,
                SchemaExecutionAuditStatus.COMPLETED,
                SchemaExecutionAuditStatus.RUNNING,
                SchemaExecutionAuditStatus.COMPLETED,
            ],
        )
        self.assertTrue(all(event.deployment_id == "deploy-ok" for event in result.audit_log.events))
        self.assertFalse(any(event.rollback_required for event in result.audit_log.events))

    def test_rollback_after_statement_failure(self):
        connection = Mock()
        connection.execute.side_effect = [None, RuntimeError("boom")]
        result = execute_schema_plan_with_connection(self._plan(), connection, allow_execution=True)
        self.assertFalse(result.ok)
        self.assertEqual(result.statements_executed, 1)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        self.assertTrue(result.rollback_attempted)
        self.assertTrue(result.rollback_succeeded)
        self.assertIn("RuntimeError: boom", result.error_message)

    def test_audit_events_for_failure_and_rollback(self):
        connection = Mock()
        connection.execute.side_effect = [None, RuntimeError("boom")]
        result = execute_schema_plan_with_connection(self._plan(), connection, allow_execution=True)
        statuses = [event.status for event in result.audit_log.events]
        self.assertIn(SchemaExecutionAuditStatus.FAILED, statuses)
        self.assertEqual(statuses[-1], SchemaExecutionAuditStatus.ROLLED_BACK)
        failed_event = next(event for event in result.audit_log.events if event.status is SchemaExecutionAuditStatus.FAILED)
        self.assertTrue(failed_event.rollback_required)
        self.assertIn("RuntimeError: boom", failed_event.error_message)

    def test_cli_apply_still_blocked(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_schema_executor.execute_schema_plan_with_connection") as engine:
            exit_code = main(["--apply", "--confirm-schema-apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Status: BLOCKED", stderr.getvalue())
        self.assertIn("No SQL executed. No schema created. No migrations run.", stderr.getvalue())
        engine.assert_not_called()

    def test_engine_has_no_connection_discovery_database_url_or_driver_imports(self):
        source = inspect.getsource(execute_schema_plan_with_connection)
        forbidden_terms = [
            "DATABASE_URL",
            "os.environ",
            "psycopg",
            "supabase",
            "create_client",
            "create_engine",
            "urlsplit",
            "connect(",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)


if __name__ == "__main__":
    unittest.main()
