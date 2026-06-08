import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from postgres_connection_probe import (
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    PROBE_ENABLE_ENV_VAR,
    ProbeStatus,
    build_probe_diagnostics,
    is_probe_enabled,
    normalize_connect_timeout,
    run_safe_connection_probe,
)
from postgres_staging_deployer import main


class PostgresConnectionProbeTests(unittest.TestCase):
    def test_probe_disabled_by_default(self):
        connector = Mock()
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(is_probe_enabled())
            result = run_safe_connection_probe("postgresql://user:pw@example.test/app", connector=connector)
        self.assertEqual(result.status, ProbeStatus.PROBE_DISABLED)
        self.assertFalse(result.probe_attempted)
        self.assertFalse(result.probe_succeeded)
        self.assertEqual(result.diagnostics["timeout_seconds"], DEFAULT_PROBE_TIMEOUT_SECONDS)
        self.assertIn(PROBE_ENABLE_ENV_VAR, result.error_message)
        connector.assert_not_called()

    def test_missing_url_handled_when_probe_enabled(self):
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            result = run_safe_connection_probe("")
        self.assertEqual(result.status, ProbeStatus.NOT_CONFIGURED)
        self.assertFalse(result.database_url_present)
        self.assertFalse(result.probe_attempted)

    def test_missing_driver_handled_without_connection_attempt(self):
        connector = Mock()
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=None):
                result = run_safe_connection_probe("postgresql://user:pw@example.test/app", connector=connector)
        self.assertEqual(result.status, ProbeStatus.DRIVER_MISSING)
        self.assertFalse(result.driver_detected)
        self.assertFalse(result.probe_attempted)
        connector.assert_not_called()

    def test_diagnostics_are_safe_and_redacted(self):
        url = "postgresql://user:super-secret@example.test:5432/app?sslmode=require"
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                diagnostics = build_probe_diagnostics(url, ("psycopg",), timeout_seconds=3.5)
        self.assertTrue(diagnostics["ready_for_probe"])
        self.assertTrue(diagnostics["database_url_present"])
        self.assertEqual(diagnostics["timeout_seconds"], 3.5)
        self.assertEqual(diagnostics["connect_timeout_seconds"], 3)
        self.assertNotIn("super-secret", diagnostics["database_url_redacted"])
        self.assertIn("SQL execution", diagnostics["prohibited_actions"])
        self.assertIn("schema deployment", diagnostics["prohibited_actions"])

    def test_timeout_5_float_becomes_integer_connect_timeout(self):
        self.assertEqual(normalize_connect_timeout(5.0), 5)
        url = "postgresql://user:pw@example.test/app"
        connection = Mock()
        driver = Mock()
        driver.connect.return_value = connection
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                with patch("postgres_connection_probe.import_module", return_value=driver):
                    result = run_safe_connection_probe(url, ("psycopg",), timeout_seconds=5.0)
        self.assertEqual(result.status, ProbeStatus.PROBE_SUCCEEDED)
        driver.connect.assert_called_once_with(url, connect_timeout=5)
        connection.close.assert_called_once_with()

    def test_subsecond_timeout_becomes_minimum_one_second_connect_timeout(self):
        self.assertEqual(normalize_connect_timeout(0.2), 1)
        url = "postgresql://user:pw@example.test/app"
        connection = Mock()
        driver = Mock()
        driver.connect.return_value = connection
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                with patch("postgres_connection_probe.import_module", return_value=driver):
                    result = run_safe_connection_probe(url, ("psycopg",), timeout_seconds=0.2)
        self.assertEqual(result.status, ProbeStatus.PROBE_SUCCEEDED)
        driver.connect.assert_called_once_with(url, connect_timeout=1)
        connection.close.assert_called_once_with()

    def test_enabled_probe_connects_and_disconnects_only(self):
        connection = Mock()
        connector = Mock(return_value=connection)

        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                result = run_safe_connection_probe(
                    "postgresql://user:pw@example.test/app",
                    ("psycopg",),
                    connector=connector,
                    timeout_seconds=2.0,
                )
        self.assertEqual(result.status, ProbeStatus.PROBE_SUCCEEDED)
        self.assertTrue(result.probe_attempted)
        self.assertTrue(result.probe_succeeded)
        connector.assert_called_once_with("postgresql://user:pw@example.test/app", "psycopg", 2)
        connection.close.assert_called_once_with()

    def test_enabled_probe_never_calls_sql_methods(self):
        connection = Mock()
        connector = Mock(return_value=connection)
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                result = run_safe_connection_probe(
                    "postgresql://user:pw@example.test/app",
                    ("psycopg",),
                    connector=connector,
                )
        self.assertEqual(result.status, ProbeStatus.PROBE_SUCCEEDED)
        connection.execute.assert_not_called()
        connection.executemany.assert_not_called()
        connection.cursor.assert_not_called()
        connection.close.assert_called_once_with()

    def test_timeout_failure_has_clear_message(self):
        connector = Mock(side_effect=TimeoutError("network timeout"))
        with patch.dict("os.environ", {PROBE_ENABLE_ENV_VAR: "1"}, clear=True):
            with patch("postgres_connection_probe.find_spec", return_value=object()):
                result = run_safe_connection_probe(
                    "postgresql://user:pw@example.test/app",
                    ("psycopg",),
                    connector=connector,
                    timeout_seconds=1.5,
                )
        self.assertEqual(result.status, ProbeStatus.PROBE_FAILED)
        self.assertTrue(result.probe_attempted)
        self.assertFalse(result.probe_succeeded)
        self.assertIn("timed out after 1 seconds", result.error_message)

    def test_probe_never_executes_sql(self):
        source = Path("postgres_connection_probe.py").read_text(encoding="utf-8")
        forbidden_terms = [
            ".execute(",
            ".executemany(",
            ".executescript(",
            ".cursor(",
            "CREATE TABLE",
            "ALTER TABLE",
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, source)

    def test_cli_probe_never_triggers_deployment(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_staging_deployer.run_deployment_dry_run") as dry_run:
            with patch("postgres_staging_deployer.validate_required_artifacts") as artifacts:
                with patch.dict("os.environ", {}, clear=True):
                    exit_code = main(["--probe"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        self.assertIn("PostgreSQL safe connection probe diagnostics.", stdout.getvalue())
        self.assertIn("Status: PROBE_DISABLED", stdout.getvalue())
        self.assertIn("No deployment, migration, schema creation", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        dry_run.assert_not_called()
        artifacts.assert_not_called()

    def test_cli_probe_passes_timeout_to_probe_only(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("postgres_staging_deployer.run_safe_connection_probe") as probe:
            probe.return_value = Mock(
                status=ProbeStatus.PROBE_DISABLED,
                diagnostics={
                    "probe_enabled": False,
                    "database_url_redacted": "",
                    "driver_name": "",
                    "timeout_seconds": 1.25,
                },
                database_url_present=False,
                driver_detected=False,
                probe_attempted=False,
                probe_succeeded=False,
                error_message="disabled",
            )
            exit_code = main(["--probe", "--probe-timeout", "1.25"], output_stream=stdout, error_stream=stderr)
        self.assertEqual(exit_code, 0)
        probe.assert_called_once_with(timeout_seconds=1.25)
        self.assertIn("Timeout seconds: 1.25", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
