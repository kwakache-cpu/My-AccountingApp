import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from postgres_schema_executor import (
    SCHEMA_APPLY_BLOCKED_MESSAGE,
    SCHEMA_APPLY_ENABLE_ENV_VAR,
    SchemaApplyStatus,
    build_schema_apply_guard_diagnostics,
    validate_schema_apply_guard,
)
from postgres_staging_deployer import main


class PostgresSchemaApplyGuardTests(unittest.TestCase):
    def _valid_env(self):
        return {
            SCHEMA_APPLY_ENABLE_ENV_VAR: "1",
            "ERP_ENVIRONMENT": "staging",
            "DATABASE_URL": "postgresql://user:secret@example.test/app",
        }

    def test_apply_blocked_if_any_guard_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; COMMIT;", encoding="utf-8")
            diagnostics = validate_schema_apply_guard(
                apply_flag=True,
                confirmation_flag=True,
                schema_path=schema_path,
                environ={"ERP_ENVIRONMENT": "staging", "DATABASE_URL": "postgresql://example/app"},
                statements_planned=2,
            )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertTrue(diagnostics.blocked)
        self.assertFalse(diagnostics.guard_results[SCHEMA_APPLY_ENABLE_ENV_VAR])
        self.assertEqual(diagnostics.message, SCHEMA_APPLY_BLOCKED_MESSAGE)

    def test_apply_blocked_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; COMMIT;", encoding="utf-8")
            diagnostics = validate_schema_apply_guard(
                apply_flag=True,
                confirmation_flag=False,
                schema_path=schema_path,
                environ=self._valid_env(),
            )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard.confirmation_flag)
        self.assertFalse(diagnostics.guard_results["explicit_confirm_schema_apply_flag"])

    def test_apply_blocked_outside_staging(self):
        env = self._valid_env()
        env["ERP_ENVIRONMENT"] = "production"
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; COMMIT;", encoding="utf-8")
            diagnostics = validate_schema_apply_guard(
                apply_flag=True,
                confirmation_flag=True,
                schema_path=schema_path,
                environ=env,
            )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard.environment_is_staging)
        self.assertFalse(diagnostics.guard_results["ERP_ENVIRONMENT_is_staging"])

    def test_apply_blocked_with_missing_database_url(self):
        env = self._valid_env()
        env.pop("DATABASE_URL")
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; COMMIT;", encoding="utf-8")
            diagnostics = build_schema_apply_guard_diagnostics(
                apply_flag=True,
                confirmation_flag=True,
                schema_path=schema_path,
                environ=env,
            )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertFalse(diagnostics.guard.database_url_present)
        self.assertFalse(diagnostics.guard_results["DATABASE_URL_present"])

    def test_all_guards_pass_but_apply_still_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("BEGIN; COMMIT;", encoding="utf-8")
            diagnostics = validate_schema_apply_guard(
                apply_flag=True,
                confirmation_flag=True,
                schema_path=schema_path,
                environ=self._valid_env(),
                statements_planned=2,
            )
        self.assertEqual(diagnostics.status, SchemaApplyStatus.BLOCKED)
        self.assertTrue(diagnostics.blocked)
        self.assertTrue(diagnostics.all_guards_passed)
        self.assertTrue(all(diagnostics.guard_results.values()))
        self.assertEqual(diagnostics.statements_planned, 2)
        self.assertIn("SQL execution is still disabled", diagnostics.message)

    def test_dry_run_unaffected(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = main(["--dry-run"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        self.assertIn("PostgreSQL staging deployment skeleton dry-run.", stdout.getvalue())
        self.assertIn("No SQL executed. No database connection attempted.", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_apply_reports_guards_and_executes_no_sql(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_staging_deployer.execute_schema_plan", create=True) as execute:
            with patch.dict("os.environ", self._valid_env(), clear=True):
                exit_code = main(
                    ["--apply", "--confirm-schema-apply"],
                    output_stream=stdout,
                    error_stream=stderr,
                )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        output = stderr.getvalue()
        self.assertIn("PostgreSQL guarded schema apply diagnostics.", output)
        self.assertIn("Status: BLOCKED", output)
        self.assertIn("Blocked: True", output)
        self.assertIn("All guards passed: True", output)
        self.assertIn("explicit_confirm_schema_apply_flag: True", output)
        self.assertIn("No SQL executed. No schema created. No migrations run.", output)
        execute.assert_not_called()

    def test_cli_apply_without_confirmation_is_blocked(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict("os.environ", self._valid_env(), clear=True):
            exit_code = main(["--apply"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 1)
        output = stderr.getvalue()
        self.assertIn("Status: BLOCKED", output)
        self.assertIn("explicit_confirm_schema_apply_flag: False", output)
        self.assertIn("No SQL executed.", output)


if __name__ == "__main__":
    unittest.main()
