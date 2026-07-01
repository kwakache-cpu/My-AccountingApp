import os
from types import SimpleNamespace
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class _StreamlitSessionStub:
    def __init__(self):
        self.session_state = {}


class Lv006CanonicalStartupPipelineTests(TestCase):
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
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "lv006_startup_pipeline")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        database.clear_diagnostics_ttl_cache()
        return database

    def _postgres_env(self, *, environment="staging", production_approved="0"):
        return mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require",
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": environment,
                "ERP_POSTGRES_PRODUCTION_APPROVED": production_approved,
            },
            clear=False,
        )

    def test_canonical_result_includes_required_fields(self):
        database = self._load_database()
        with self._postgres_env():
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "validate_postgres_runtime_enabled", return_value={"ok": True, "reasons": [], "environment_approved": True, "database_url_label": "postgresql://***"}):
                    with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True}):
                        with mock.patch.object(database, "get_connection") as conn_mock:
                            conn = mock.MagicMock()
                            conn.execute.return_value.fetchone.return_value = {"company_count": 2}
                            conn_mock.return_value = conn
                            result = database.run_canonical_startup_pipeline()
        for key in (
            "configured_backend",
            "active_backend",
            "runtime_enabled",
            "environment",
            "startup_route",
            "startup_ok",
            "sqlite_startup_skipped",
            "postgres_connection_ok",
            "production_approved",
            "elapsed_ms",
            "config_resolution_sources",
        ):
            self.assertIn(key, result)
        self.assertTrue(result["startup_ok"])
        self.assertEqual(result["startup_route"], "postgres_runtime")

    def test_postgres_startup_skips_sqlite_path(self):
        database = self._load_database()
        with self._postgres_env():
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "validate_postgres_runtime_enabled", return_value={"ok": True, "reasons": [], "environment_approved": True}):
                    with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True}):
                        with mock.patch.object(database, "get_connection") as conn_mock:
                            with mock.patch.object(database, "_ensure_local_db_file") as ensure_local_mock:
                                with mock.patch.object(database, "get_database_health_snapshot") as sqlite_health_mock:
                                    conn = mock.MagicMock()
                                    conn.execute.return_value.fetchone.return_value = {"company_count": 1}
                                    conn_mock.return_value = conn
                                    result = database.run_canonical_startup_pipeline()
        ensure_local_mock.assert_not_called()
        sqlite_health_mock.assert_not_called()
        self.assertTrue(result["sqlite_startup_skipped"])

    def test_postgres_production_requires_approval(self):
        database = self._load_database()
        with self._postgres_env(environment="production", production_approved="0"):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                result = database.run_canonical_startup_pipeline()
        self.assertFalse(result["startup_ok"])
        self.assertIn("ERP_POSTGRES_PRODUCTION_APPROVED", result.get("blocked_reason", ""))

    def test_postgres_staging_does_not_require_production_approval(self):
        database = self._load_database()
        with self._postgres_env(environment="staging", production_approved="0"):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(database, "test_postgres_connection", return_value={"ok": True}):
                    with mock.patch.object(database, "get_connection") as conn_mock:
                        conn = mock.MagicMock()
                        conn.execute.return_value.fetchone.return_value = {"company_count": 0}
                        conn_mock.return_value = conn
                        result = database.run_canonical_startup_pipeline()
        self.assertTrue(result["startup_ok"])
        self.assertEqual(result["environment"], "staging")

    def test_sqlite_route_uses_sqlite_startup_path(self):
        database = self._load_database()
        with mock.patch.object(database, "get_active_db_backend", return_value="sqlite"):
            result = database.run_canonical_startup_pipeline()
        self.assertTrue(result["startup_ok"])
        self.assertEqual(result["startup_route"], "sqlite_runtime")
        self.assertFalse(result["sqlite_startup_skipped"])
        self.assertIsNotNone(result.get("db_path"))

    def test_startup_database_delegates_to_canonical_pipeline(self):
        database = self._load_database()
        with mock.patch.object(database, "run_canonical_startup_pipeline", return_value={"startup_ok": True}) as pipeline_mock:
            result = database.startup_database()
        pipeline_mock.assert_called_once()
        self.assertTrue(result["startup_ok"])


class Lv006SessionCacheTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")
        self._original_st = self.modules.st
        self.stub = _StreamlitSessionStub()
        self.modules.st = self.stub
        self.modules.clear_process_startup_warmup_cache()

    def tearDown(self):
        self.modules.st = self._original_st
        self.modules.clear_process_startup_warmup_cache()

    def test_startup_result_session_cached_after_success(self):
        calls = {"count": 0}

        def _pipeline():
            calls["count"] += 1
            return {
                "startup_ok": True,
                "ok": True,
                "configured_backend": "postgres",
                "active_backend": "postgres",
                "startup_route": "postgres_runtime",
                "sqlite_startup_skipped": True,
                "elapsed_ms": 1.0,
            }

        def _warmup(*, force=False):
            cache = self.modules._PROCESS_WARMUP_CACHE
            if not force and cache.get("completed") and cache.get("signature") == "sig-v1":
                cache["cache_hits"] = int(cache.get("cache_hits", 0)) + 1
                return cache
            cache.update(
                {
                    "signature": "sig-v1",
                    "completed": True,
                    "startup_result": _pipeline(),
                    "cache_misses": int(cache.get("cache_misses", 0)) + 1,
                }
            )
            return cache

        with mock.patch("database.get_startup_config_signature", return_value="sig-v1"):
            with mock.patch("database.run_canonical_startup_pipeline", side_effect=_pipeline):
                with mock.patch.object(self.modules, "run_process_startup_warmup", side_effect=_warmup):
                    first = self.modules.get_session_canonical_startup_result()
                    second = self.modules.get_session_canonical_startup_result()
        self.assertTrue(first["startup_ok"])
        self.assertEqual(first, second)
        self.assertEqual(calls["count"], 1)

    def test_failed_startup_not_session_cached(self):
        calls = {"count": 0}

        def _pipeline():
            calls["count"] += 1
            return {
                "startup_ok": False,
                "ok": False,
                "blocked_reason": "ERP_ENVIRONMENT must be staging",
                "startup_route": "postgres_runtime",
                "elapsed_ms": 1.0,
            }

        def _warmup(*, force=False):
            cache = self.modules._PROCESS_WARMUP_CACHE
            if not force and cache.get("completed") and cache.get("signature") == "sig-v1":
                cache["cache_hits"] = int(cache.get("cache_hits", 0)) + 1
                return cache
            cache.update(
                {
                    "signature": "sig-v1",
                    "completed": True,
                    "startup_result": _pipeline(),
                    "cache_misses": int(cache.get("cache_misses", 0)) + 1,
                }
            )
            return cache

        with mock.patch("database.get_startup_config_signature", return_value="sig-v1"):
            with mock.patch("database.run_canonical_startup_pipeline", side_effect=_pipeline):
                with mock.patch.object(self.modules, "run_process_startup_warmup", side_effect=_warmup):
                    first = self.modules.get_session_canonical_startup_result()
                    second = self.modules.get_session_canonical_startup_result()
        self.assertFalse(first["startup_ok"])
        self.assertFalse(second["startup_ok"])
        self.assertEqual(calls["count"], 1)

    def test_init_db_uses_canonical_startup(self):
        with mock.patch.object(self.modules, "get_session_canonical_startup_result", return_value={"startup_ok": True}) as startup_mock:
            result = self.modules.init_db()
        startup_mock.assert_called_once()
        self.assertTrue(result["startup_ok"])

    def test_clear_session_includes_canonical_startup_keys(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn('"canonical_startup_result"', content)
        self.assertIn('"canonical_startup_config_signature"', content)
        self.assertIn('"_clear_streamlit_caches"', content)
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn('"canonical_startup_result"', content)
        self.assertIn('"canonical_startup_config_signature"', content)
        self.assertIn('"_clear_streamlit_caches"', content)


class Lv006DiagnosticsAccessTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")

    def test_normal_user_cannot_see_diagnostics_panels(self):
        self.modules.st = None
        self.modules.render_lv006_startup_pipeline_panel("Accountant")
        self.modules.render_lv003_hot_path_panel("Cashier")
        self.modules.render_lv002_postgres_performance_panel("Bookkeeper")

    def test_admin_roles_can_access_diagnostics_helpers(self):
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("Dev"))
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("Master Admin"))
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("System Admin"))
        self.assertFalse(self.modules.can_view_runtime_admin_diagnostics("Owner / CEO"))


class Lv006FastSystemHealthTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        import enterprise_services

        self.enterprise_services = enterprise_services
        self.database.clear_diagnostics_ttl_cache()

    def test_fast_health_excludes_heavy_checks(self):
        with mock.patch("modules.get_subscription_billing_health_snapshot") as billing_mock:
            with mock.patch.object(self.database, "get_recovery_source_diagnostics") as recovery_mock:
                with mock.patch.object(self.database, "get_cloud_backup_diagnostics") as cloud_mock:
                    with mock.patch.object(self.database, "get_database_health_snapshot") as sqlite_health_mock:
                        with mock.patch.object(self.database, "get_data_migration_export_plan_summary") as migration_mock:
                            with mock.patch.object(self.database, "get_postgres_readiness_diagnostics") as readiness_mock:
                                snapshot = self.enterprise_services.build_operations_console_snapshot(
                                    conn=self.conn,
                                    audit_mode="fast",
                                )
        billing_mock.assert_not_called()
        recovery_mock.assert_not_called()
        cloud_mock.assert_not_called()
        sqlite_health_mock.assert_not_called()
        migration_mock.assert_not_called()
        readiness_mock.assert_not_called()
        self.assertEqual((snapshot.get("subscription_billing") or {}).get("reason"), "not_checked_in_fast_mode")
        self.assertEqual((snapshot.get("data_migration_plan") or {}).get("reason"), "not_checked_in_fast_mode")

    def test_full_audit_still_available_on_demand(self):
        with mock.patch("modules.get_subscription_billing_health_snapshot", return_value={"ok": True, "billing": {}}):
            snapshot = self.enterprise_services.build_operations_console_full_audit(conn=self.conn)
        self.assertEqual(snapshot.get("audit_mode"), "full")
        self.assertIsNotNone(snapshot.get("subscription_billing"))
