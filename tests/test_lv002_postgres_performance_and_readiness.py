import os
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class Lv002PostgresReadinessScoringTests(TestCase):
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
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "lv002_postgres_readiness")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        return database

    def test_sqlite_backend_uses_code_portability_audit_mode(self):
        database = self._load_database()
        diagnostics = database.get_postgres_readiness_diagnostics(conn=None, include_table_introspection=False)
        self.assertEqual(diagnostics["active_backend"], "sqlite")
        self.assertEqual(diagnostics["readiness_mode"], "code_portability_audit")
        self.assertIsNotNone(diagnostics["code_portability_score"])
        self.assertTrue(diagnostics["switch_blocked"])

    def test_postgres_active_uses_runtime_cutover_evidence_not_static_scan(self):
        database = self._load_database()
        secret_url = "postgresql://user:secret@example.supabase.co:6543/postgres?sslmode=require"
        with mock.patch.dict(
            os.environ,
            {
                "DB_BACKEND": "postgres",
                "DATABASE_URL": secret_url,
                "ERP_ENABLE_POSTGRES_RUNTIME": "1",
                "ERP_ENVIRONMENT": "staging",
            },
            clear=False,
        ):
            with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                with mock.patch.object(
                    database,
                    "validate_postgres_runtime_cutover_guard",
                    return_value={
                        "ok": True,
                        "evidence": {
                            "schema_deployment": {"required_markers_present": True, "report": "reports/a.md"},
                            "row_reconciliation": {"required_markers_present": True, "report": "reports/b.md"},
                            "runtime_readiness": {"required_markers_present": True, "report": "reports/c.md"},
                            "runtime_dryrun": {"required_markers_present": True, "report": "reports/d.md"},
                            "all_required_evidence_present": True,
                        },
                    },
                ):
                    with mock.patch.object(database, "_cached_scan_postgres_readiness_sources") as scan_mock:
                        diagnostics = database.get_postgres_readiness_diagnostics(
                            conn=None,
                            include_table_introspection=False,
                        )
        scan_mock.assert_not_called()
        self.assertEqual(diagnostics["readiness_mode"], "runtime_cutover_evidence")
        self.assertEqual(diagnostics["readiness_score"], 100)
        self.assertFalse(diagnostics["switch_blocked"])
        self.assertIsNone(diagnostics["code_portability_score"])

    def test_postgres_active_reports_missing_cutover_markers(self):
        database = self._load_database()
        with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
            with mock.patch.object(
                database,
                "validate_postgres_runtime_cutover_guard",
                return_value={
                    "ok": False,
                    "evidence": {
                        "schema_deployment": {
                            "required_markers_present": False,
                            "report": "reports/postgres_postdeploy_validation_results.md",
                            "missing_markers": ["Checks passed: 754"],
                        },
                        "row_reconciliation": {"required_markers_present": True, "report": "reports/postcopy_reconciliation_report.md"},
                        "runtime_readiness": {"required_markers_present": True, "report": "reports/postgres_runtime_readiness_report.md"},
                        "runtime_dryrun": {"required_markers_present": True, "report": "reports/postgres_runtime_dryrun_report.md"},
                        "all_required_evidence_present": False,
                    },
                },
            ):
                diagnostics = database.get_postgres_readiness_diagnostics(conn=None, include_table_introspection=False)
        missing = diagnostics.get("runtime_cutover_missing_evidence") or []
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["report"], "reports/postgres_postdeploy_validation_results.md")
        self.assertIn("Checks passed: 754", missing[0]["missing_markers"])
        self.assertEqual(diagnostics["readiness_score"], 75)
        self.assertTrue(diagnostics["switch_blocked"])

    def test_cached_source_scan_avoids_repeat_file_reads(self):
        database = self._load_database()
        database._POSTGRES_READINESS_SOURCE_SCAN_CACHE["signature"] = None
        database._POSTGRES_READINESS_SOURCE_SCAN_CACHE["findings"] = None
        first = database._cached_scan_postgres_readiness_sources()
        second = database._cached_scan_postgres_readiness_sources()
        self.assertIs(first, second)


class Lv002PostgresPerformanceDiagnosticsTests(ERPIsolatedTestCase):
    def test_lv002_diagnostics_include_timings_and_top_slow(self):
        diagnostics = self.database.get_lv002_postgres_performance_diagnostics(
            conn=self.conn,
            company_key=self.company_key,
        )
        self.assertIn("timings_ms", diagnostics)
        self.assertIn("connection_creation_ms", diagnostics["timings_ms"])
        self.assertIn("postgres_readiness_ms", diagnostics["timings_ms"])
        self.assertIn("backup_diagnostics_ms", diagnostics["timings_ms"])
        top_slow = diagnostics.get("top_slow_operations") or []
        self.assertGreaterEqual(len(top_slow), 1)
        self.assertLessEqual(len(top_slow), 10)
        self.assertIn("operation", top_slow[0])
        self.assertIn("elapsed_ms", top_slow[0])

    def test_persistence_diagnostics_skip_sqlite_file_on_postgres_runtime(self):
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True):
            with mock.patch.object(
                self.database,
                "_get_active_runtime_health_snapshot",
                return_value={
                    "backend_label": "PostgreSQL",
                    "company_count": 3,
                    "structural_valid": True,
                    "production_ready": True,
                    "missing_tables": [],
                    "environment_label": "staging",
                },
            ):
                with mock.patch.object(self.database, "get_database_health_snapshot") as sqlite_health_mock:
                    with mock.patch.object(self.database, "get_local_backup_diagnostics") as local_backup_mock:
                        diagnostics = self.database.get_persistence_diagnostics()
        sqlite_health_mock.assert_not_called()
        local_backup_mock.assert_not_called()
        self.assertTrue(diagnostics.get("postgres_runtime_active"))
        self.assertEqual(diagnostics.get("local_backup_reason"), "skipped_postgres_runtime")
        self.assertEqual(diagnostics.get("company_count"), 3)

    def test_data_migration_plan_can_skip_row_counts(self):
        plan = self.database.get_data_migration_export_plan(conn=self.conn, include_row_counts=False)
        self.assertGreater(plan.get("table_count", 0), 0)
        self.assertTrue(all(row.get("row_count") is None for row in plan.get("tables") or []))
        plan_with_counts = self.database.get_data_migration_export_plan(conn=self.conn, include_row_counts=True)
        self.assertTrue(any(row.get("row_count") is not None for row in plan_with_counts.get("tables") or []))
        self.assertEqual(len(plan.get("tables") or []), len(plan_with_counts.get("tables") or []))

    def test_cutover_evidence_parser_lists_missing_markers_for_real_reports(self):
        evidence = self.database.get_postgres_runtime_cutover_evidence()
        self.assertIn("schema_deployment", evidence)
        for key, payload in evidence.items():
            if key == "all_required_evidence_present":
                continue
            self.assertIn("report", payload)
            self.assertIn("required_markers_present", payload)
            self.assertIn("missing_markers", payload)
            if not payload.get("required_markers_present"):
                self.assertTrue(payload.get("missing_markers"))


class Lv002DiagnosticsCacheTests(TestCase):
    def test_diagnostics_ttl_cache_tracks_hits_and_misses(self):
        data_dir = os.path.join(os.getcwd(), ".test-tmp", "lv002b_cache")
        os.makedirs(data_dir, exist_ok=True)
        database, _engine = load_isolated_modules(data_dir)
        database.clear_diagnostics_ttl_cache()
        calls = {"count": 0}

        def builder():
            calls["count"] += 1
            return {"ok": True}

        first = database.diagnostics_ttl_cache("lv002b_test", 60, builder)
        second = database.diagnostics_ttl_cache("lv002b_test", 60, builder)
        self.assertEqual(first, {"ok": True})
        self.assertEqual(second, {"ok": True})
        self.assertEqual(calls["count"], 1)
        stats = database.get_diagnostics_cache_stats()
        self.assertGreaterEqual(stats["hits"], 1)
        self.assertGreaterEqual(stats["misses"], 1)


class Lv002ModulesAccessControlTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = __import__("modules")

    def test_runtime_admin_diagnostics_roles(self):
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("Dev"))
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("System Admin"))
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("Master Admin"))
        self.assertFalse(self.modules.can_view_runtime_admin_diagnostics("Accountant"))
        self.assertFalse(self.modules.can_view_runtime_admin_diagnostics("Cashier"))

    def test_lv002b_performance_panel_data_shape(self):
        if self.modules.st is None:
            self.skipTest("Streamlit unavailable in test runtime")
        self.modules.st.session_state["lv002b_operation_events"] = [
            {"label": "backup_diagnostics_ms", "elapsed_ms": 250.0, "surface": "system_health"},
            {"label": "dashboard.load", "elapsed_ms": 120.0, "surface": "dashboard"},
        ]
        self.modules.st.session_state["lv002b_surface_timings"] = {
            "login": {"elapsed_ms": 80.0, "label": "auth.login"},
            "dashboard": {"elapsed_ms": 120.0, "label": "dashboard.load"},
        }
        panel = self.modules.get_lv002b_performance_panel_data()
        self.assertEqual(panel["login_ms"], 80.0)
        self.assertEqual(panel["dashboard_load_ms"], 120.0)
        self.assertIn("top_slow_ops", panel)
        self.assertLessEqual(len(panel["top_slow_ops"]), 10)
        self.assertIn("cache_stats", panel)


class Lv002cOperationsSnapshotTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database.clear_diagnostics_ttl_cache()
        import enterprise_services

        self.enterprise_services = enterprise_services

    def test_fast_operations_snapshot_skips_deep_cloud_and_column_scans(self):
        with mock.patch.object(self.database, "get_cloud_backup_diagnostics") as cloud_mock:
            with mock.patch.object(self.database, "get_database_health_snapshot") as sqlite_health_mock:
                snapshot = self.enterprise_services.build_operations_console_snapshot(
                    conn=self.conn,
                    audit_mode="fast",
                )
        cloud_mock.assert_not_called()
        sqlite_health_mock.assert_not_called()
        self.assertTrue(snapshot.get("fast_snapshot"))
        self.assertEqual(snapshot.get("audit_mode"), "fast")
        persistence = snapshot.get("persistence") or {}
        self.assertTrue(persistence.get("fast_snapshot"))
        self.assertEqual(persistence.get("cloud_backup_reason"), "fast_snapshot_skipped_network")
        migration = snapshot.get("data_migration_plan") or {}
        self.assertEqual(migration.get("mode"), "fast_summary")
        self.assertIsNone((migration.get("tables") or [{}])[0].get("columns") if migration.get("tables") else None)

    def test_fast_operations_snapshot_excludes_subscription_billing_deep_check(self):
        with mock.patch("modules.get_subscription_billing_health_snapshot") as billing_mock:
            snapshot = self.enterprise_services.build_operations_console_snapshot(
                conn=self.conn,
                audit_mode="fast",
            )
        billing_mock.assert_not_called()
        billing = snapshot.get("subscription_billing") or {}
        self.assertTrue(billing.get("fast_snapshot"))
        self.assertFalse(billing.get("checked", True))
        self.assertEqual(billing.get("reason"), "not_checked_in_fast_mode")
        timings = snapshot.get("timings_ms") or {}
        self.assertNotIn("subscription_billing", timings)

    def test_fast_operations_snapshot_skips_recovery_source_diagnostics(self):
        with mock.patch.object(self.database, "get_recovery_source_diagnostics") as recovery_mock:
            snapshot = self.enterprise_services.build_operations_console_snapshot(
                conn=self.conn,
                audit_mode="fast",
            )
        recovery_mock.assert_not_called()
        recovery = snapshot.get("recovery_source") or {}
        self.assertEqual(recovery.get("reason"), "not_checked_in_fast_mode")
        timings = snapshot.get("timings_ms") or {}
        self.assertNotIn("recovery_source_diagnostics", timings)

    def test_fast_operations_snapshot_uses_runtime_ping_for_persistence(self):
        ping = {
            "company_count": 7,
            "structural_valid": True,
            "production_ready": True,
            "ping_ok": True,
            "backend_label": "SQLite",
            "environment_label": "test",
        }
        with mock.patch.object(self.database, "build_fast_runtime_ping", return_value=ping) as ping_mock:
            with mock.patch.object(
                self.database,
                "get_persistence_diagnostics_fast",
                side_effect=lambda conn=None, runtime_ping=None: {
                    "fast_snapshot": True,
                    "company_count": runtime_ping.get("company_count"),
                    "reason": "fast_runtime_ping_only",
                },
            ) as persistence_mock:
                with mock.patch.object(
                    self.database,
                    "run_persistence_self_test_fast",
                    side_effect=lambda logger_instance=None, conn=None, runtime_ping=None: {
                        "fast_snapshot": True,
                        "ok": runtime_ping.get("ping_ok"),
                        "reason": "fast_runtime_ping_only",
                    },
                ) as self_test_mock:
                    snapshot = self.enterprise_services.build_operations_console_snapshot(
                        conn=self.conn,
                        audit_mode="fast",
                    )
        ping_mock.assert_called_once_with(self.conn)
        persistence_mock.assert_called()
        self_test_mock.assert_called()
        self.assertEqual((snapshot.get("persistence") or {}).get("company_count"), 7)
        self.assertTrue((snapshot.get("persistence_self_test") or {}).get("ok"))

    def test_full_operations_snapshot_includes_subscription_billing_deep_check(self):
        sentinel = {
            "ok": True,
            "billing": {"active_count": 2},
            "paystack": {"secret_key_present": True},
        }
        with mock.patch("modules.get_subscription_billing_health_snapshot", return_value=sentinel) as billing_mock:
            snapshot = self.enterprise_services.build_operations_console_full_audit(conn=self.conn)
        billing_mock.assert_called()
        self.assertEqual(snapshot.get("subscription_billing"), sentinel)
        timings = snapshot.get("timings_ms") or {}
        self.assertIn("subscription_billing", timings)

    def test_fast_persistence_self_test_uses_ping_only_path(self):
        ping = {"company_count": 4, "ping_ok": True, "structural_valid": True}
        result = self.database.run_persistence_self_test_fast(conn=self.conn, runtime_ping=ping)
        self.assertTrue(result.get("fast_snapshot"))
        self.assertEqual(result.get("reason"), "fast_runtime_ping_only")
        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("local_company_count"), 4)
        self.assertIsNone(result.get("cloud_backup_company_count"))

    def test_postgres_fast_persistence_self_test_skips_sqlite_backup_checks(self):
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True):
            with mock.patch.object(self.database, "get_local_backup_diagnostics") as local_backup_mock:
                with mock.patch.object(self.database, "get_cloud_backup_diagnostics") as cloud_mock:
                    result = self.database.run_persistence_self_test_fast(conn=self.conn)
        local_backup_mock.assert_not_called()
        cloud_mock.assert_not_called()
        self.assertTrue(result.get("fast_snapshot"))
        self.assertEqual(result.get("reason"), "fast_runtime_ping_only")

    def test_full_operations_snapshot_uses_deep_persistence_path(self):
        sentinel = {"ok": True, "cloud_backup_reason": "cloud backup diagnostics collected successfully"}
        with mock.patch.object(self.database, "get_persistence_diagnostics", return_value=sentinel) as persistence_mock:
            snapshot = self.enterprise_services.build_operations_console_full_audit(conn=self.conn)
        persistence_mock.assert_called()
        self.assertEqual(snapshot.get("audit_mode"), "full")
        self.assertFalse(snapshot.get("fast_snapshot"))

    def test_fast_operations_snapshot_cache_reuses_result(self):
        calls = {"count": 0}

        def _fast_persistence(conn=None, runtime_ping=None):
            calls["count"] += 1
            return {"fast_snapshot": True, "cloud_backup_reason": "fast_snapshot_skipped_network"}

        with mock.patch.object(self.database, "get_persistence_diagnostics_fast", side_effect=_fast_persistence):
            first = self.enterprise_services.build_operations_console_snapshot(conn=self.conn, audit_mode="fast")
            second = self.enterprise_services.build_operations_console_snapshot(conn=self.conn, audit_mode="fast")
        self.assertEqual(first.get("audit_mode"), "fast")
        self.assertEqual(second.get("audit_mode"), "fast")
        self.assertEqual(calls["count"], 1)

    def test_postgres_fast_persistence_skips_sqlite_file_health_scan(self):
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True):
            with mock.patch.object(self.database, "get_database_health_snapshot") as sqlite_health_mock:
                persistence = self.database.get_persistence_diagnostics_fast()
        sqlite_health_mock.assert_not_called()
        self.assertTrue(persistence.get("fast_snapshot"))
        self.assertTrue(persistence.get("postgres_runtime_active"))
