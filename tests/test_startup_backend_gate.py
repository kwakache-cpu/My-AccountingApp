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

    def test_postgres_runtime_enabled_blocks_before_sqlite_startup(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "1"},
            clear=False,
        ), mock.patch.object(database, "_ensure_local_db_file") as ensure_local_db_file, mock.patch.object(
            database, "_open_sqlite_connection"
        ) as open_sqlite_connection:
            result = database.startup_database()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "postgres_schema_not_implemented")
        self.assertEqual(result["active_backend"], "postgres")
        self.assertFalse(result["recovery_attempted"])
        ensure_local_db_file.assert_not_called()
        open_sqlite_connection.assert_not_called()

    def test_startup_diagnostics_do_not_expose_database_url_secret(self):
        database = self._load_database()
        secret_url = "postgresql://user:super-secret@example.supabase.co:6543/postgres"
        with mock.patch.dict(
            os.environ,
            {"DB_BACKEND": "postgres", "DATABASE_URL": secret_url, "ERP_ENABLE_POSTGRES_RUNTIME": "1"},
            clear=False,
        ):
            diagnostics = database.get_startup_backend_diagnostics()
        self.assertNotIn("super-secret", str(diagnostics))
        self.assertNotIn(secret_url, str(diagnostics))
        self.assertIn("***", diagnostics["database_url_label"])

    def test_app_sqlite_startup_still_calls_ensure_schema_and_startup_database(self):
        database = self._load_database()
        import app

        stop_error = RuntimeError("stop")
        fake_st = SimpleNamespace(
            cache_data=SimpleNamespace(clear=mock.Mock()),
            cache_resource=SimpleNamespace(clear=mock.Mock()),
            session_state={},
            error=mock.Mock(),
            stop=mock.Mock(side_effect=stop_error),
        )
        with mock.patch.object(app, "st", fake_st), mock.patch.object(app, "should_run_sqlite_startup", return_value=True), mock.patch.object(
            app, "get_startup_backend_diagnostics", return_value=database.get_startup_backend_diagnostics()
        ), mock.patch.object(app, "ensure_schema") as ensure_schema, mock.patch.object(
            app,
            "startup_database",
            return_value={"ok": False, "stage": "test_stop", "reason": "stop after startup gate"},
        ) as startup_database:
            with self.assertRaises(RuntimeError):
                app.main()
        ensure_schema.assert_called_once()
        startup_database.assert_called_once()

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
            "ok": False,
            "stage": "postgres_schema_not_implemented",
            "reason": "PostgreSQL runtime is enabled, but PostgreSQL schema deployment is not implemented yet.",
            "configured_backend": "postgres",
            "active_backend": "postgres",
        }
        with mock.patch.object(app, "st", fake_st), mock.patch.object(app, "should_run_sqlite_startup", return_value=False), mock.patch.object(
            app,
            "get_startup_backend_diagnostics",
            return_value={
                "configured_backend": "postgres",
                "active_backend": "postgres",
                "message": blocked_status["reason"],
            },
        ), mock.patch.object(app, "ensure_schema") as ensure_schema, mock.patch.object(
            app, "startup_database", return_value=blocked_status
        ) as startup_database:
            with self.assertRaises(RuntimeError):
                app.main()
        ensure_schema.assert_not_called()
        startup_database.assert_called_once()
        fake_st.error.assert_called_once()
