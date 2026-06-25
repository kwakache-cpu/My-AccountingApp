import importlib
import os
from unittest import mock

from test_support import ERPIsolatedTestCase


class PostgresE2EWriteExecutionGuardTests(ERPIsolatedTestCase):
    def test_e2e_runner_aborts_before_writes_when_backend_is_not_postgres(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        diagnostics = runner._backend_diagnostics(self.database)
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertFalse(diagnostics["database_url_present"])

        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "sqlite",
                "ERP_ENABLE_POSTGRES_RUNTIME": "",
                "ERP_ENVIRONMENT": "",
            },
            clear=False,
        ):
            payload = runner._abort_if_not_postgres(self.database)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["overall_status"], "ABORTED")
        self.assertEqual(payload["cleanup_status"], "NOT_STARTED")
        self.assertIn("active backend is not postgres", payload["abort_reason"])
        self.assertFalse(payload["workflows"])

    def test_e2e_report_contract_exists_after_guarded_abort(self):
        runner = importlib.import_module("scripts.run_postgres_e2e_write_execution")
        payload = runner._abort_if_not_postgres(self.database)
        self.assertIsNotNone(payload)
        report = runner.REPORT_PATH.read_text(encoding="utf-8")
        for required_text in (
            "PostgreSQL E2E Write Execution",
            "Backend Diagnostics",
            "Workflow Results",
            "Cleanup Strategy",
            "Production Readiness Recommendation",
            "ABORTED",
        ):
            self.assertIn(required_text, report)
