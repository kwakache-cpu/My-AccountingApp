import os
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class Lv004PostgresStartupRoutingTests(TestCase):
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
            )
        }

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _load_database(self):
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "lv004_postgres_cutover_startup")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        database.clear_diagnostics_ttl_cache()
        return database

    def _enable_postgres_env(self, database):
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        env = {
            "DB_BACKEND": "postgres",
            "DATABASE_URL": secret_url,
            "ERP_ENABLE_POSTGRES_RUNTIME": "1",
            "ERP_ENVIRONMENT": "staging",
        }
        return mock.patch.dict(os.environ, env, clear=False)

    def _clear_canonical_startup_cache(self):
        """Drop session-cached startup diagnostics so host backend residue cannot leak."""
        try:
            import modules as eka_modules

            if eka_modules.st is not None and hasattr(eka_modules.st, "session_state"):
                eka_modules.st.session_state.pop("canonical_startup_result", None)
                eka_modules.st.session_state.pop("canonical_startup_config_signature", None)
        except Exception:
            pass

    def _assert_startup_diagnostics_for_backend(self, diagnostics, expected_backend):
        """Strong route assertions for the resolved backend (sqlite or postgres)."""
        self.assertEqual(diagnostics.get("configured_backend"), expected_backend)
        self.assertEqual(diagnostics.get("active_backend"), expected_backend)
        if expected_backend == "postgres":
            self.assertTrue(diagnostics.get("runtime_enabled"))
            self.assertEqual(diagnostics.get("startup_route"), "postgres_runtime")
            self.assertTrue(diagnostics.get("sqlite_startup_skipped"))
            self.assertTrue(diagnostics.get("runtime_validation_ok"))
        else:
            self.assertEqual(expected_backend, "sqlite")
            self.assertEqual(diagnostics.get("startup_route"), "sqlite_runtime")
            self.assertFalse(diagnostics.get("sqlite_startup_skipped", False))
            self.assertIsNotNone(diagnostics.get("local_sqlite_db_path") or diagnostics.get("startup_route"))

    def test_postgres_active_runtime_skips_sqlite_startup_path(self):
        database = self._load_database()
        with self._enable_postgres_env(database):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "validate_postgres_runtime_enabled", return_value={"ok": True, "reasons": []}):
                    with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True, "message": "ok"}):
                        with mock.patch.object(database, "get_connection") as conn_mock:
                            with mock.patch.object(database, "get_database_health_snapshot") as sqlite_health_mock:
                                with mock.patch.object(database, "_ensure_local_db_file") as ensure_local_mock:
                                    with mock.patch.object(database, "attempt_production_database_recovery") as recovery_mock:
                                        conn = mock.MagicMock()
                                        conn.execute.return_value.fetchone.return_value = {"company_count": 3}
                                        conn_mock.return_value = conn
                                        result = database.startup_database()
        sqlite_health_mock.assert_not_called()
        ensure_local_mock.assert_not_called()
        recovery_mock.assert_not_called()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("startup_route"), "postgres_runtime")
        self.assertTrue(result.get("sqlite_startup_skipped"))
        self.assertEqual(result.get("stage"), "postgres_runtime_startup")
        self.assertIsNone(result.get("db_path"))

    def test_postgres_active_runtime_does_not_require_local_sqlite_file(self):
        database = self._load_database()
        with self._enable_postgres_env(database):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "validate_postgres_runtime_enabled", return_value={"ok": True, "reasons": []}):
                    with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True, "message": "ok"}):
                        with mock.patch.object(database, "get_connection") as conn_mock:
                            conn = mock.MagicMock()
                            conn.execute.return_value.fetchone.return_value = {"company_count": 0}
                            conn_mock.return_value = conn
                            result = database.startup_database()
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("sqlite_startup_skipped"))
        self.assertIsNone(result.get("db_path"))
        self.assertNotIn("eka_enterprise_v3.db", str(result.get("reason") or ""))

    def test_sqlite_startup_path_still_works_when_db_backend_sqlite(self):
        database = self._load_database()
        with mock.patch.object(database, "get_active_db_backend", return_value="sqlite"):
            result = database.startup_database()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("startup_route", "sqlite_runtime"), "sqlite_runtime")
        self.assertFalse(result.get("sqlite_startup_skipped", False))
        self.assertIsNotNone(result.get("db_path"))

    def test_guard_blocks_unsafe_postgres_configuration(self):
        database = self._load_database()
        with self._enable_postgres_env(database):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(
                    database,
                    "validate_postgres_runtime_enabled",
                    return_value={
                        "ok": False,
                        "reasons": ["ERP_ENVIRONMENT must be staging, or production with ERP_POSTGRES_PRODUCTION_APPROVED=1."],
                    },
                ):
                    result = database.startup_database()
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("stage"), "postgres_runtime_validation")
        self.assertTrue(result.get("sqlite_startup_skipped"))
        self.assertIn("ERP_ENVIRONMENT", result.get("reason", ""))

    def test_startup_diagnostics_report_postgres_runtime_route(self):
        database = self._load_database()
        self._clear_canonical_startup_cache()
        with self._enable_postgres_env(database):
            with mock.patch.object(database, "get_configured_db_backend", return_value="postgres"):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    with mock.patch.object(database, "is_postgres_runtime_enabled", return_value=True):
                        with mock.patch.object(
                            database,
                            "validate_postgres_runtime_enabled",
                            return_value={"ok": True, "reasons": []},
                        ):
                            diagnostics = database.get_database_startup_diagnostics()
        # Resolve from returned diagnostics so host sqlite/postgres residue cannot
        # force a mismatched expected backend; then assert the matching route contract.
        resolved_backend = diagnostics.get("active_backend") or diagnostics.get("configured_backend")
        self.assertIn(resolved_backend, ("sqlite", "postgres"))
        self._assert_startup_diagnostics_for_backend(diagnostics, resolved_backend)
        # With postgres env + patches applied and cache cleared, this path must resolve postgres.
        self.assertEqual(resolved_backend, "postgres")

    def test_postgres_startup_succeeds_without_cutover_evidence_files(self):
        database = self._load_database()
        with self._enable_postgres_env(database):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "validate_postgres_runtime_enabled", return_value={"ok": True, "reasons": []}):
                    with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True, "message": "ok"}):
                        with mock.patch.object(
                            database,
                            "validate_postgres_runtime_cutover_guard",
                            return_value={"ok": False, "reasons": ["Required PostgreSQL cutover evidence reports are missing or stale."]},
                        ):
                            with mock.patch.object(database, "get_connection") as conn_mock:
                                conn = mock.MagicMock()
                                conn.execute.return_value.fetchone.return_value = {"company_count": 2}
                                conn_mock.return_value = conn
                                result = database.startup_database()
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("stage"), "postgres_runtime_startup")
        self.assertFalse(result.get("runtime_cutover_guard_ok"))


class Lv004PostgresStartupIntegrationTests(ERPIsolatedTestCase):
    def test_sqlite_isolated_startup_reports_sqlite_route(self):
        try:
            import modules as eka_modules

            if eka_modules.st is not None and hasattr(eka_modules.st, "session_state"):
                eka_modules.st.session_state.pop("canonical_startup_result", None)
                eka_modules.st.session_state.pop("canonical_startup_config_signature", None)
        except Exception:
            pass
        diagnostics = self.database.get_database_startup_diagnostics()
        resolved_backend = diagnostics.get("active_backend") or diagnostics.get("configured_backend")
        self.assertEqual(resolved_backend, "sqlite")
        self.assertEqual(diagnostics.get("configured_backend"), "sqlite")
        self.assertEqual(diagnostics.get("startup_route"), "sqlite_runtime")
        self.assertFalse(diagnostics.get("sqlite_startup_skipped"))
        result = self.database.startup_database()
        self.assertTrue(result.get("ok"))
        self.assertIsNotNone(result.get("db_path"))
