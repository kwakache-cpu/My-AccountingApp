import os
from types import SimpleNamespace
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class _StreamlitSessionStub:
    def __init__(self):
        self.session_state = {}


class Lv003HotPathRecorderTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")
        self._original_st = self.modules.st
        self.stub = _StreamlitSessionStub()
        self.modules.st = self.stub

    def tearDown(self):
        self.modules.st = self._original_st

    def test_hot_path_recorder_captures_call_counts_and_elapsed_ms(self):
        self.modules.begin_lv003_hot_path_rerun(active_page="Dashboard")
        self.modules.record_lv003_hot_path_call("app.main", 12.5, surface="main")
        self.modules.record_lv003_hot_path_call("app.sidebar_build", 4.2, surface="sidebar")
        self.modules.record_lv003_hot_path_call("app.sidebar_build", 1.8, surface="sidebar")
        tree = self.modules.get_lv003_hot_path_call_tree()
        labels = {row["label"]: row for row in tree}
        self.assertEqual(labels["app.main"]["count"], 1)
        self.assertEqual(labels["app.main"]["elapsed_ms"], 12.5)
        self.assertEqual(labels["app.sidebar_build"]["count"], 2)
        self.assertEqual(labels["app.sidebar_build"]["elapsed_ms"], 6.0)

    def test_finalize_persists_rerun_history(self):
        self.modules.begin_lv003_hot_path_rerun(active_page="Financial Reports")
        self.modules.record_lv003_hot_path_call("financials.show_financial_reports", 25.0, surface="financial_reports")
        self.modules.finalize_lv003_hot_path_rerun(active_page="Financial Reports")
        history = self.stub.session_state.get("lv003_rerun_history") or []
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["active_page"], "Financial Reports")
        self.assertGreaterEqual(history[0]["total_elapsed_ms"], 25.0)

    def test_next_rerun_finalizes_previous_rerun(self):
        self.modules.begin_lv003_hot_path_rerun(active_page="Dashboard")
        self.modules.record_lv003_hot_path_call("modules.show_dashboard", 30.0, surface="dashboard")
        self.modules.begin_lv003_hot_path_rerun(active_page="Dashboard")
        history = self.stub.session_state.get("lv003_rerun_history") or []
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["top_label"], "modules.show_dashboard")


class Lv003AdminAccessTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")

    def test_runtime_admin_diagnostics_roles(self):
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("Dev"))
        self.assertTrue(self.modules.can_view_runtime_admin_diagnostics("System Admin"))
        self.assertFalse(self.modules.can_view_runtime_admin_diagnostics("Accountant"))

    def test_hot_path_panel_is_admin_only(self):
        self.modules.st = None
        # Should return without error when Streamlit is unavailable.
        self.modules.render_lv003_hot_path_panel("Accountant")


class Lv003SessionCacheTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = __import__("modules")
        self.modules.st = _StreamlitSessionStub()
        self.modules.st.session_state = {
            "database_startup_status": {"ok": True, "stage": "local_production_ready"},
        }
        self.modules.st.session_state.pop("session_startup_backend_diagnostics", None)

    def test_startup_guard_is_session_cached_after_success(self):
        sentinel = {
            "startup_ok": True,
            "configured_backend": "sqlite",
            "active_backend": "sqlite",
            "startup_route": "sqlite_runtime",
            "sqlite_startup_skipped": False,
            "runtime_enabled": False,
            "production_approved": False,
            "environment": "unknown",
        }
        self.modules.st.session_state["canonical_startup_result"] = sentinel
        with mock.patch.object(self.modules, "get_startup_backend_diagnostics") as guard_mock:
            first = self.modules.get_session_startup_backend_diagnostics()
            second = self.modules.get_session_startup_backend_diagnostics()
        guard_mock.assert_not_called()
        self.assertEqual(first["active_backend"], "sqlite")
        self.assertEqual(second["active_backend"], "sqlite")

    def test_subscription_snapshot_is_session_cached(self):
        sentinel = {"ok": True, "renewal_required": False, "days_left": 30}
        with mock.patch.object(self.modules, "get_company_subscription_snapshot", return_value=sentinel) as snapshot_mock:
            first = self.modules.get_session_company_subscription_status(self.company_key)
            second = self.modules.get_session_company_subscription_status(self.company_key)
        self.assertEqual(first, second)
        snapshot_mock.assert_called_once()


class Lv003OrdinaryRenderHotPathTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = __import__("modules")
        self.modules.st = _StreamlitSessionStub()
        self.modules.st.session_state = {
            "user": {"key": self.company_key, "role": "Owner / CEO", "name": "Test"},
            "_dashboard_loaded_once": False,
        }
        import enterprise_services

        self.enterprise_services = enterprise_services
        self.database.clear_diagnostics_ttl_cache()

    def test_fast_snapshot_excludes_subscription_and_recovery_from_hot_path(self):
        with mock.patch("modules.get_subscription_billing_health_snapshot") as billing_mock:
            with mock.patch.object(self.database, "get_recovery_source_diagnostics") as recovery_mock:
                with mock.patch.object(self.database, "get_cloud_backup_diagnostics") as cloud_mock:
                    snapshot = self.enterprise_services.build_operations_console_snapshot(
                        conn=self.conn,
                        audit_mode="fast",
                    )
        billing_mock.assert_not_called()
        recovery_mock.assert_not_called()
        cloud_mock.assert_not_called()
        billing = snapshot.get("subscription_billing") or {}
        self.assertEqual(billing.get("reason"), "not_checked_in_fast_mode")
        recovery = snapshot.get("recovery_source") or {}
        self.assertEqual(recovery.get("reason"), "not_checked_in_fast_mode")

    def test_dashboard_analytics_bundle_does_not_call_cloud_backup(self):
        with mock.patch.object(self.database, "get_cloud_backup_diagnostics") as cloud_mock:
            bundle = self.modules._cached_dashboard_analytics_bundle(
                self.company_key,
                "",
                "2026-06-30",
            )
        cloud_mock.assert_not_called()
        self.assertIn("kpis", bundle)

    def test_full_health_audit_remains_available_on_demand(self):
        with mock.patch("modules.get_subscription_billing_health_snapshot", return_value={"ok": True, "billing": {}}):
            snapshot = self.enterprise_services.build_operations_console_full_audit(conn=self.conn)
        self.assertEqual(snapshot.get("audit_mode"), "full")
        self.assertFalse(snapshot.get("fast_snapshot"))
        self.assertIsNotNone(snapshot.get("subscription_billing"))

    def test_fast_operations_snapshot_not_required_on_ordinary_rerun_when_session_cached(self):
        import enterprise_services

        first = enterprise_services.build_operations_console_snapshot(conn=self.conn, audit_mode="fast")
        calls = {"count": 0}

        def _counting_build(*args, **kwargs):
            calls["count"] += 1
            return first

        with mock.patch.object(enterprise_services, "_build_operations_console_snapshot", side_effect=_counting_build):
            second = enterprise_services.build_operations_console_snapshot(conn=self.conn, audit_mode="fast")
        self.assertEqual(first.get("audit_mode"), "fast")
        self.assertEqual(second.get("audit_mode"), "fast")
        self.assertEqual(calls["count"], 0)
