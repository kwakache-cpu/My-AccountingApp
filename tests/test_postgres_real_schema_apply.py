import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from postgres_connection_probe import ProbeStatus
from postgres_schema_executor import (
    SchemaApplyStatus,
    SchemaExecutionPlan,
    execute_schema_plan_with_database_url,
    validate_schema_apply_guard,
)
from postgres_staging_deployer import main


class PostgresRealSchemaApplyTests(unittest.TestCase):
    def _valid_env(self):
        return {
            "ERP_ENABLE_POSTGRES_SCHEMA_APPLY": "1",
            "ERP_ENVIRONMENT": "staging",
            "ERP_ENABLE_POSTGRES_PROBE": "1",
            "DATABASE_URL": "postgresql://user:secret@example.test/app",
        }

    def _probe_success(self):
        return Mock(
            status=ProbeStatus.PROBE_SUCCEEDED,
            error_message="",
            diagnostics={
                "driver_name": "psycopg",
                "database_url_redacted": "postgresql://user:***@example.test/app",
            },
        )

    def test_all_guards_missing_blocks(self):
        diagnostics = validate_schema_apply_guard(
            apply_flag=True,
            confirmation_flag=False,
            environ={},
            statements_planned=0,
        )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertTrue(diagnostics.blocked)
        self.assertFalse(diagnostics.all_guards_passed)
        self.assertFalse(diagnostics.guard_results["ERP_ENABLE_POSTGRES_SCHEMA_APPLY"])
        self.assertFalse(diagnostics.guard_results["ERP_ENABLE_POSTGRES_PROBE"])

    def test_missing_confirmation_blocks(self):
        diagnostics = validate_schema_apply_guard(
            apply_flag=True,
            confirmation_flag=False,
            environ=self._valid_env(),
            statements_planned=1,
        )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard_results["explicit_confirm_schema_apply_flag"])

    def test_non_staging_blocks(self):
        env = self._valid_env()
        env["ERP_ENVIRONMENT"] = "production"
        diagnostics = validate_schema_apply_guard(
            apply_flag=True,
            confirmation_flag=True,
            environ=env,
            statements_planned=1,
        )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard_results["ERP_ENVIRONMENT_is_staging"])

    def test_missing_database_url_blocks(self):
        env = self._valid_env()
        env.pop("DATABASE_URL")
        diagnostics = validate_schema_apply_guard(
            apply_flag=True,
            confirmation_flag=True,
            environ=env,
            statements_planned=1,
        )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard_results["DATABASE_URL_present"])

    def test_mock_connection_successful_apply_commits(self):
        plan = SchemaExecutionPlan(
            source_path=Path("mock.sql"),
            statements=("BEGIN;", "CREATE TABLE example (id BIGINT);", "COMMIT;"),
        )
        connection = Mock()
        connector = Mock(return_value=connection)
        result = execute_schema_plan_with_database_url(
            plan,
            database_url="postgresql://user:secret@example.test/app",
            driver_name="psycopg",
            connector=connector,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.statements_executed, 3)
        connector.assert_called_once_with("postgresql://user:secret@example.test/app", "psycopg", 5)
        self.assertEqual([call.args[0] for call in connection.execute.call_args_list], list(plan.statements))
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()
        connection.close.assert_called_once_with()

    def test_mock_connection_failure_rolls_back(self):
        plan = SchemaExecutionPlan(
            source_path=Path("mock.sql"),
            statements=("BEGIN;", "CREATE TABLE example (id BIGINT);", "COMMIT;"),
        )
        connection = Mock()
        connection.execute.side_effect = [None, RuntimeError("boom")]
        connector = Mock(return_value=connection)
        result = execute_schema_plan_with_database_url(
            plan,
            database_url="postgresql://user:secret@example.test/app",
            driver_name="psycopg",
            connector=connector,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.statements_executed, 1)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        connection.close.assert_called_once_with()
        self.assertTrue(result.rollback_attempted)
        self.assertTrue(result.rollback_succeeded)

    def test_cli_dry_run_unaffected(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        self.assertIn("PostgreSQL staging deployment skeleton dry-run.", stdout.getvalue())
        self.assertIn("No SQL executed. No database connection attempted.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_apply_calls_execution_only_when_guards_pass(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        execution_result = Mock(
            ok=True,
            audit_log=Mock(deployment_id="deploy-1", events=()),
            statements_executed=3,
            statements_planned=3,
            rollback_attempted=False,
            rollback_succeeded=False,
            error_message="",
        )
        with patch("postgres_staging_deployer.run_safe_connection_probe", return_value=self._probe_success()) as probe:
            with patch("postgres_staging_deployer.execute_schema_plan_with_database_url", return_value=execution_result) as execute:
                with patch.dict("os.environ", self._valid_env(), clear=True):
                    exit_code = main(
                        ["--apply", "--confirm-schema-apply"],
                        output_stream=stdout,
                        error_stream=stderr,
                    )
        self.assertEqual(exit_code, 0)
        probe.assert_called_once_with()
        execute.assert_called_once()
        kwargs = execute.call_args.kwargs
        self.assertEqual(kwargs["database_url"], "postgresql://user:secret@example.test/app")
        self.assertEqual(kwargs["driver_name"], "psycopg")
        self.assertIn("Schema apply completed for staging", stderr.getvalue())
        self.assertNotIn("secret", stderr.getvalue())

    def test_cli_apply_does_not_execute_when_guards_fail(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_staging_deployer.run_safe_connection_probe") as probe:
            with patch("postgres_staging_deployer.execute_schema_plan_with_database_url") as execute:
                with patch.dict("os.environ", {}, clear=True):
                    exit_code = main(["--apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        probe.assert_not_called()
        execute.assert_not_called()
        self.assertIn("Status: BLOCKED", stderr.getvalue())

    def test_no_app_startup_or_runtime_change(self):
        deployer_source = Path("postgres_staging_deployer.py").read_text(encoding="utf-8")
        executor_source = Path("postgres_schema_executor.py").read_text(encoding="utf-8")
        for source in (deployer_source, executor_source):
            self.assertNotIn("DB_BACKEND", source)
            self.assertNotIn("ERP_ENABLE_POSTGRES_RUNTIME", source)
            self.assertNotIn("init_db", source)
            self.assertNotIn("get_connection", source)


if __name__ == "__main__":
    unittest.main()
