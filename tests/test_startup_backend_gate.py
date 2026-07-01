import os
from types import SimpleNamespace
from unittest import TestCase, mock

from test_support import load_isolated_modules


class StartupBackendGateTests(TestCase):
    def setUp(self):
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "DB_BACKEND",
                "DATABASE_URL",
                "ERP_ENABLE_POSTGRES_RUNTIME",
                "ERP_ENVIRONMENT",
                "ERP_POSTGRES_PRODUCTION_APPROVED",
                "EKA_DATA_DIR",
                "ERP_PRODUCTION_MODE",
                "ERP_SAFE_STARTUP_MODE",
            )
        }

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load_database(self):
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "startup_backend_gate")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        return database

    def test_production_default_remains_sqlite(self):
        database = self._load_database()
        with mock.patch.dict(os.environ, {"DB_BACKEND": "", "ERP_ENABLE_POSTGRES_RUNTIME": "", "DATABASE_URL": ""}, clear=False):
            diagnostics = database.get_startup_backend_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "sqlite")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["should_run_sqlite_startup"])
        self.assertTrue(database.should_run_sqlite_startup())

    def test_postgres_configured_runtime_disabled_falls_back_safely(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "0"},
            clear=False,
        ):
            diagnostics = database.get_startup_backend_diagnostics()
        self.assertEqual(diagnostics["configured_backend"], "postgres")
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertTrue(diagnostics["postgres_requested"])
        self.assertFalse(diagnostics["postgres_runtime_enabled"])
        self.assertTrue(diagnostics["should_run_sqlite_startup"])
        self.assertFalse(diagnostics["postgres_schema_blocked"])
        self.assertIn("runtime", " ".join(diagnostics["reasons"]).lower())

    def test_postgres_runtime_enabled_allows_startup_without_sqlite_bootstrap_when_evidence_passes(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "1", "ERP_ENVIRONMENT": "staging"},
            clear=False,
        ), mock.patch.object(database, "test_postgres_connection", return_value={"ok": True, "message": "ok"}), mock.patch.object(
            database, "get_connection"
        ) as get_connection, mock.patch.object(database, "_ensure_local_db_file") as ensure_local_db_file, mock.patch.object(
            database, "_open_sqlite_connection"
        ) as open_sqlite_connection:
            conn = mock.MagicMock()
            conn.execute.return_value.fetchone.return_value = {"company_count": 0}
            get_connection.return_value = conn
            result = database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "postgres_runtime_startup")
        self.assertEqual(result["startup_mode"], "postgres_runtime_startup")
        self.assertEqual(result["active_backend"], "postgres")
        self.assertTrue(result["sqlite_startup_skipped"])
        self.assertEqual(result["startup_route"], "postgres_runtime")
        self.assertTrue(result["runtime_cutover_guard_ok"])
        self.assertEqual(result["schema_deployment_status"], "PASSED")
        self.assertEqual(result["row_reconciliation_status"], "PASSED")
        self.assertFalse(result["recovery_attempted"])
        ensure_local_db_file.assert_not_called()
        open_sqlite_connection.assert_not_called()

    def test_postgres_runtime_allows_startup_when_cutover_evidence_missing(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        missing_report = os.path.join(os.getcwd(), ".test-tmp", "startup_backend_gate", "missing_cutover_report.md")
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "1", "ERP_ENVIRONMENT": "staging"},
            clear=False,
        ), mock.patch.dict(
            database.POSTGRES_CUTOVER_REPORTS,
            {"schema_deployment": (missing_report, ("Status: PASSED",))},
            clear=True,
        ), mock.patch.object(database, "test_postgres_connection", return_value={"ok": True, "message": "ok"}), mock.patch.object(
            database, "get_connection"
        ) as get_connection, mock.patch.object(database, "_ensure_local_db_file") as ensure_local_db_file, mock.patch.object(
            database, "_open_sqlite_connection"
        ) as open_sqlite_connection:
            conn = mock.MagicMock()
            conn.execute.return_value.fetchone.return_value = {"company_count": 1}
            get_connection.return_value = conn
            result = database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "postgres_runtime_startup")
        self.assertFalse(result["runtime_cutover_guard_ok"])
        self.assertIn("missing or stale", " ".join(result["runtime_cutover_guard_reasons"]).lower())
        ensure_local_db_file.assert_not_called()
        open_sqlite_connection.assert_not_called()

    def test_startup_diagnostics_do_not_expose_database_url_secret(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "1", "ERP_ENVIRONMENT": "staging"},
            clear=False,
        ):
            diagnostics = database.get_startup_backend_diagnostics()
        self.assertNotIn("super-secret", str(diagnostics))
        self.assertNotIn(secret_url, str(diagnostics))
        self.assertIn("***", diagnostics["database_url_label"])
        self.assertEqual(diagnostics["schema_deployment_status"], "PASSED")
        self.assertEqual(diagnostics["row_reconciliation_status"], "PASSED")
        self.assertEqual(diagnostics["runtime_readiness_status"], "PASSED")
        self.assertEqual(diagnostics["runtime_dryrun_status"], "PASSED")
        self.assertTrue(diagnostics["environment_approved"])

    def test_final_cutover_guard_requires_staging_or_production_approval(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "production",
                "ERP_POSTGRES_PRODUCTION_APPROVED": "0",
            },
            clear=False,
        ):
            guard = database.validate_postgres_runtime_cutover_guard()
        self.assertFalse(guard["ok"])
        self.assertFalse(guard["environment_approved"])
        self.assertIn("ERP_ENVIRONMENT", " ".join(guard["reasons"]))
        self.assertNotIn("super-secret", str(guard))

        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
                "ERP_POSTGRES_PRODUCTION_APPROVED": "0",
            },
            clear=False,
        ):
            guard = database.validate_postgres_runtime_cutover_guard()
        self.assertTrue(guard["ok"])
        self.assertTrue(guard["environment_approved"])
        self.assertEqual(guard["schema_deployment_status"], "PASSED")
        self.assertEqual(guard["row_reconciliation_status"], "PASSED")

    def test_app_sqlite_startup_still_calls_ensure_schema_and_startup_database(self):
        self._load_database()
        import app

        stop_error = RuntimeError("stop")
        fake_st = SimpleNamespace(
            cache_data=SimpleNamespace(clear=mock.Mock()),
            cache_resource=SimpleNamespace(clear=mock.Mock()),
            session_state={},
            error=mock.Mock(),
            stop=mock.Mock(side_effect=stop_error),
        )
        canonical_result = {
            "startup_ok": False,
            "ok": False,
            "startup_route": "sqlite_runtime",
            "stage": "test_stop",
            "reason": "stop after startup gate",
        }
        with mock.patch.object(app, "st", fake_st), mock.patch.object(
            app.eka_modules,
            "get_session_canonical_startup_result",
            return_value=canonical_result,
        ) as canonical_startup, mock.patch.object(app, "ensure_schema") as ensure_schema:
            with self.assertRaises(RuntimeError):
                app.main()
        ensure_schema.assert_called_once()
        canonical_startup.assert_called_once()

    def test_app_postgres_block_skips_sqlite_ensure_schema(self):
        self._load_database()
        import app

        stop_error = RuntimeError("stop")
        fake_st = SimpleNamespace(
            cache_data=SimpleNamespace(clear=mock.Mock()),
            cache_resource=SimpleNamespace(clear=mock.Mock()),
            session_state={},
            error=mock.Mock(),
            stop=mock.Mock(side_effect=stop_error),
        )
        blocked_status = {
            "startup_ok": False,
            "ok": False,
            "stage": "postgres_runtime_validation",
            "reason": "ERP_ENVIRONMENT must be staging, or production with ERP_POSTGRES_PRODUCTION_APPROVED=1.",
            "configured_backend": "postgres",
            "active_backend": "postgres",
            "startup_route": "postgres_runtime",
            "sqlite_startup_skipped": True,
        }
        with mock.patch.object(app, "st", fake_st), mock.patch.object(
            app.eka_modules,
            "get_session_canonical_startup_result",
            return_value=blocked_status,
        ) as canonical_startup, mock.patch.object(app, "ensure_schema") as ensure_schema:
            with self.assertRaises(RuntimeError):
                app.main()
        ensure_schema.assert_not_called()
        canonical_startup.assert_called_once()
        fake_st.error.assert_called_once()
