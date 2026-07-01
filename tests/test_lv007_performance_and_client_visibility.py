import inspect
import os
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class _StreamlitSessionStub:
    def __init__(self):
        self.session_state = {}


class Lv007ProcessWarmupTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")
        self.modules.clear_process_startup_warmup_cache()

    def tearDown(self):
        self.modules.clear_process_startup_warmup_cache()

    def test_warmup_executes_once_and_reuses_cache(self):
        calls = {"count": 0}

        def _pipeline():
            calls["count"] += 1
            return {"startup_ok": True, "ok": True, "startup_route": "postgres_runtime", "elapsed_ms": 1.0}

        with mock.patch("database.get_startup_config_signature", return_value="sig-warmup"):
            with mock.patch("database.run_canonical_startup_pipeline", side_effect=_pipeline):
                with mock.patch("database.get_connection") as conn_mock:
                    conn = mock.MagicMock()
                    conn.execute.return_value.fetchone.return_value = {"company_count": 1, "ping_ok": 1}
                    conn_mock.return_value = conn
                    first = self.modules.run_process_startup_warmup()
                    second = self.modules.run_process_startup_warmup()
        self.assertTrue(first["completed"])
        self.assertTrue(second["completed"])
        self.assertEqual(calls["count"], 1)
        self.assertGreaterEqual(second.get("cache_hits", 0), 1)

    def test_warmup_skips_heavy_paths(self):
        skipped = set(self.modules._WARMUP_SKIP_ITEMS)
        self.assertIn("cloud_backup_download", skipped)
        self.assertIn("firebase_verification", skipped)
        self.assertIn("subscription_billing", skipped)
        self.assertIn("sqlite_recovery", skipped)
        self.assertIn("full_health_audit", skipped)
        self.assertIn("financial_reports", skipped)

    def test_force_refresh_reruns_warmup(self):
        calls = {"count": 0}

        def _pipeline():
            calls["count"] += 1
            return {"startup_ok": True, "ok": True, "startup_route": "postgres_runtime", "elapsed_ms": 1.0}

        with mock.patch("database.get_startup_config_signature", return_value="sig-force"):
            with mock.patch("database.run_canonical_startup_pipeline", side_effect=_pipeline):
                with mock.patch("database.get_connection") as conn_mock:
                    conn_mock.return_value = mock.MagicMock()
                    self.modules.run_process_startup_warmup()
                    after_first = calls["count"]
                    self.modules.run_process_startup_warmup(force=True)
        self.assertGreaterEqual(after_first, 1)
        self.assertGreater(calls["count"], after_first)

    def test_session_startup_reuses_process_warmup(self):
        self.modules.st = _StreamlitSessionStub()
        startup = {"startup_ok": True, "ok": True, "startup_route": "postgres_runtime", "elapsed_ms": 2.0}
        with mock.patch("database.get_startup_config_signature", return_value="sig-session"):
            with mock.patch.object(self.modules, "run_process_startup_warmup", return_value={
                "signature": "sig-session",
                "completed": True,
                "startup_result": startup,
                "cache_hits": 0,
                "cache_misses": 1,
            }):
                with mock.patch("database.run_canonical_startup_pipeline") as pipeline_mock:
                    result = self.modules.get_session_canonical_startup_result()
        pipeline_mock.assert_not_called()
        self.assertTrue(result["startup_ok"])


class Lv007ClientDiagnosticsVisibilityTests(TestCase):
    def test_dashboard_source_has_no_lv_diagnostics(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = content.split("def show_dashboard(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("render_lv002_postgres_performance_panel", dashboard_block)
        self.assertNotIn("render_lv003_hot_path_panel", dashboard_block)
        self.assertNotIn("render_lv006_startup_pipeline_panel", dashboard_block)
        self.assertNotIn("render_backend_activation_diagnostics_panel", dashboard_block)
        self.assertNotIn("LV-001 Live Validation Diagnostics", dashboard_block)

    def test_financial_reports_source_has_no_lv_diagnostics(self):
        financials_path = os.path.join(os.getcwd(), "financials.py")
        with open(financials_path, encoding="utf-8") as handle:
            content = handle.read()
        reports_block = content.split("def show_financial_reports(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("render_backend_activation_diagnostics_panel", reports_block)
        self.assertNotIn("get_live_validation_lv001_diagnostics", reports_block)
        self.assertNotIn("LV-001 Live Validation Diagnostics", reports_block)
        self.assertNotIn("render_runtime_admin_diagnostics_suite", reports_block)

    def test_pos_source_has_no_lv_diagnostics(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        pos_block = content.split("def show_pos(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("render_lv00", pos_block)
        self.assertNotIn("LV-001", pos_block)

    def test_admin_suite_only_on_approved_surfaces(self):
        self.modules = __import__("modules")
        self.assertTrue(self.modules.can_render_admin_diagnostics_surface("dev_gatekeeper"))
        self.assertTrue(self.modules.can_render_admin_diagnostics_surface("system_health"))
        self.assertTrue(self.modules.can_render_admin_diagnostics_surface("system_administration"))
        self.assertFalse(self.modules.can_render_admin_diagnostics_surface("dashboard"))
        self.assertFalse(self.modules.can_render_admin_diagnostics_surface("financial_reports"))


class Lv007AdminDiagnosticsSuiteTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")
        self.modules.st = None

    def test_admin_suite_renders_helpers_for_dev_on_admin_surface(self):
        with mock.patch.object(self.modules, "render_backend_activation_diagnostics_panel") as backend_mock:
            with mock.patch.object(self.modules, "render_lv002_postgres_performance_panel") as lv002_mock:
                with mock.patch.object(self.modules, "render_lv003_hot_path_panel") as lv003_mock:
                    with mock.patch.object(self.modules, "render_lv006_startup_pipeline_panel") as lv006_mock:
                        with mock.patch.object(self.modules, "render_lv007_warmup_panel") as lv007_mock:
                            self.modules.render_runtime_admin_diagnostics_suite(
                                "Dev",
                                surface="system_health",
                                company_key="demo-co",
                            )
        backend_mock.assert_called_once()
        lv002_mock.assert_called_once()
        lv003_mock.assert_called_once()
        lv006_mock.assert_called_once()
        lv007_mock.assert_called_once()

    def test_admin_suite_blocked_on_client_surface(self):
        with mock.patch.object(self.modules, "render_backend_activation_diagnostics_panel") as backend_mock:
            self.modules.render_runtime_admin_diagnostics_suite(
                "Dev",
                surface="dashboard",
                company_key="demo-co",
            )
        backend_mock.assert_not_called()


class Lv007FinancialReportsCacheTests(TestCase):
    def setUp(self):
        self.financials = __import__("financials")

    def test_bundle_cache_signature_includes_scope_keys(self):
        signature = inspect.signature(self.financials._cached_financial_reports_bundle)
        params = list(signature.parameters)
        self.assertIn("company_key", params)
        self.assertIn("start_key", params)
        self.assertIn("end_key", params)
        self.assertIn("branch_key", params)
        self.assertIn("backend_key", params)

    def test_cached_report_wrappers_include_scope_keys(self):
        for fn_name in (
            "_cached_trial_balance_report",
            "_cached_income_statement_report",
            "_cached_balance_sheet_report",
        ):
            fn = getattr(self.financials, fn_name)
            params = list(inspect.signature(fn).parameters)
            self.assertIn("branch_key", params, fn_name)
            self.assertIn("backend_key", params, fn_name)

    def test_show_financial_reports_does_not_call_lv_diagnostics(self):
        reports_block = inspect.getsource(self.financials.show_financial_reports)
        self.assertNotIn("get_live_validation_lv001_diagnostics", reports_block)
        self.assertNotIn("render_backend_activation_diagnostics_panel", reports_block)

    def test_integrity_check_deferred_from_hot_path(self):
        reports_block = inspect.getsource(self.financials.show_financial_reports)
        self.assertIn("Run integrity check", reports_block)
        self.assertNotIn("integrity = get_finance_integrity_diagnostics(", reports_block)


class Lv007FinancialReportsBundleTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.financials = __import__("financials")

    def test_bundle_uses_single_cumulative_and_period_ledger_fetch(self):
        calls = {"count": 0}
        original = self.financials.get_ledger_balances

        def _wrapped(*args, **kwargs):
            calls["count"] += 1
            return {}

        with mock.patch.object(self.financials, "get_ledger_balances", side_effect=_wrapped):
            with mock.patch.object(self.financials, "get_depreciation_schedule", return_value=__import__("pandas").DataFrame()):
                bundle = self.financials._cached_financial_reports_bundle(
                    "demo-co",
                    "2026-01-01",
                    "2026-03-31",
                    "none",
                    "branch-1",
                    "postgres",
                )
                self.financials._cached_financial_reports_bundle.clear()
        self.assertLessEqual(calls["count"], 2)
        self.assertIn("pipeline_timings", bundle)
        self.assertIn("slowest_stage", bundle["pipeline_timings"])


class Lv007AppStartupWiringTests(TestCase):
    def test_main_invokes_process_warmup_before_session_startup(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        main_block = content.split("def main():", 1)[1].split("\ndef ", 1)[0]
        warmup_index = main_block.index("run_process_startup_warmup")
        session_index = main_block.index("get_session_canonical_startup_result")
        self.assertLess(warmup_index, session_index)
