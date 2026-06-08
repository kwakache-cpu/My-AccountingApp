import io
import unittest
from pathlib import Path
from unittest.mock import patch

from postgres_schema_executor import (
    SchemaApplyStatus,
    SchemaExecutionAuditStatus,
    SchemaExecutionPlan,
    build_blocked_schema_apply_audit_log,
    build_schema_apply_guard_diagnostics,
    build_schema_execution_audit_log,
    build_statement_preview,
)
from postgres_staging_deployer import main


class PostgresSchemaExecutionAuditTests(unittest.TestCase):
    def test_dry_run_audit_events_generated(self):
        plan = SchemaExecutionPlan(
            source_path=Path("schema.sql"),
            statements=(
                "BEGIN;",
                "CREATE TABLE example (id BIGINT);",
                "COMMIT;",
            ),
        )
        audit_log = build_schema_execution_audit_log(plan, deployment_id="deploy-123", phase_id="phase-test")
        self.assertEqual(audit_log.deployment_id, "deploy-123")
        self.assertEqual(audit_log.phase_id, "phase-test")
        self.assertEqual(len(audit_log.events), 3)
        self.assertTrue(all(event.status is SchemaExecutionAuditStatus.PLANNED for event in audit_log.events))
        self.assertEqual(audit_log.events[1].statement_index, 2)
        self.assertEqual(audit_log.events[1].statement_preview, "CREATE TABLE example (id BIGINT);")
        self.assertFalse(any(event.rollback_required for event in audit_log.events))

    def test_apply_blocked_audit_event_generated(self):
        diagnostics = build_schema_apply_guard_diagnostics(
            apply_flag=True,
            confirmation_flag=False,
            environ={},
            statements_planned=3,
        )
        audit_log = build_blocked_schema_apply_audit_log(diagnostics, deployment_id="blocked-1")
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertEqual(len(audit_log.events), 1)
        event = audit_log.events[0]
        self.assertEqual(event.deployment_id, "blocked-1")
        self.assertEqual(event.statement_index, 0)
        self.assertEqual(event.status, SchemaExecutionAuditStatus.BLOCKED)
        self.assertIn("blocked before SQL execution", event.statement_preview)
        self.assertFalse(event.rollback_required)
        self.assertEqual(event.duration_ms, 0)
        self.assertEqual(event.error_message, diagnostics.message)

    def test_cli_dry_run_reports_planned_audit_events(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        self.assertIn("Audit events planned:", stdout.getvalue())
        self.assertIn("No SQL executed. No database connection attempted.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_apply_reports_blocked_audit_event_without_execution(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_staging_deployer.execute_schema_plan", create=True) as execute:
            with patch.dict("os.environ", {}, clear=True):
                exit_code = main(["--apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        output = stderr.getvalue()
        self.assertIn("Audit log:", output)
        self.assertIn("event_status: BLOCKED", output)
        self.assertIn("rollback_required: False", output)
        self.assertIn("No SQL executed. No schema created. No migrations run.", output)
        execute.assert_not_called()

    def test_statement_previews_are_truncated_and_redacted(self):
        statement = (
            "CREATE TABLE credentials (id BIGINT, password = 'super-secret-value', "
            "token = \"another-secret-value\", notes TEXT DEFAULT '"
            + ("x" * 250)
            + "');"
        )
        preview = build_statement_preview(statement, max_chars=120)
        self.assertLessEqual(len(preview), 120)
        self.assertTrue(preview.endswith("..."))
        self.assertNotIn("super-secret-value", preview)
        self.assertNotIn("another-secret-value", preview)
        self.assertIn("password = '***'", preview)
        self.assertIn('token = \"***\"', preview)

    def test_no_sql_execution_or_db_connection_added(self):
        executor_source = Path("postgres_schema_executor.py").read_text(encoding="utf-8")
        deployer_source = Path("postgres_staging_deployer.py").read_text(encoding="utf-8")
        forbidden_executor_terms = [
            "psycopg.connect",
            "psycopg2.connect",
            "create_engine",
            "supabase",
            "create_client",
        ]
        for term in forbidden_executor_terms:
            self.assertNotIn(term, executor_source)
        self.assertNotIn("execute_schema_plan(", deployer_source)


if __name__ == "__main__":
    unittest.main()
