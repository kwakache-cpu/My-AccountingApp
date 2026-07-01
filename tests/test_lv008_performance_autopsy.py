import os
from unittest import TestCase, mock

from test_support import ERPIsolatedTestCase, load_isolated_modules


class Lv008ConnectionReuseTests(TestCase):
    def setUp(self):
        self.database = __import__("database")
        self.database.clear_lv008_connection_stats()

    def test_postgres_session_proxy_close_is_noop(self):
        raw = mock.MagicMock()
        proxy = self.database._PostgresSessionConnectionProxy(raw)
        proxy.close()
        raw.close.assert_not_called()

    def test_session_connection_reuse_increments_counter(self):
        modules = __import__("modules")

        class _State(dict):
            def get(self, key, default=None):
                return super().get(key, default)

        state = _State(user={"role": "Dev"}, _postgres_session_connection=mock.MagicMock())
        state["_postgres_session_connection"].execute.return_value.fetchone.return_value = {"ping_ok": 1}

        with mock.patch.object(self.database, "is_postgres_backend", return_value=True):
            with mock.patch.object(self.database, "validate_postgres_runtime_enabled", return_value={"ok": True}):
                with mock.patch.object(self.database, "_streamlit_session_state", return_value=state):
                    first = self.database.get_connection()
                    second = self.database.get_connection()
        self.assertEqual(first._conn, second._conn)
        stats = self.database.get_lv008_connection_stats()
        self.assertGreaterEqual(stats.get("reuses", 0), 1)

    def test_logout_closes_session_connection(self):
        class _Conn:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def execute(self, *_args, **_kwargs):
                return self

            def fetchone(self):
                return {"ping_ok": 1}

        raw = _Conn()
        state = {"_postgres_session_connection": raw}
        with mock.patch.object(self.database, "_streamlit_session_state", return_value=state):
            self.database.close_session_postgres_connection()
        self.assertTrue(raw.closed)
        self.assertNotIn("_postgres_session_connection", state)


class Lv008DashboardDeferTests(TestCase):
    def test_dashboard_bundle_excludes_receivable_payable(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        bundle_block = content.split("def _cached_dashboard_analytics_bundle(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("_fetch_dashboard_receivable_payable_health", bundle_block)
        self.assertIn("_cached_dashboard_receivable_payable_health", content)

    def test_dashboard_loads_receivable_on_demand(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = content.split("def show_dashboard(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("Load receivables and payables", dashboard_block)
        self.assertIn("receivable_payable_key", dashboard_block)


class Lv008AutopsyHarnessTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database, _engine = load_isolated_modules(self.data_dir)
        self.financials = __import__("financials")

    def test_autopsy_harness_returns_ranked_timings(self):
        from scripts.lv008_performance_autopsy import run_lv008_autopsy

        report = run_lv008_autopsy(company_key="SYSTEM", iterations=1)
        self.assertIn("top_functions", report)
        self.assertIn("connection_stats", report)
        self.assertIn("backend", report)
        self.assertTrue(report["top_functions"])

    def test_financial_bundle_reports_pipeline_timings(self):
        bundle = self.financials._cached_financial_reports_bundle(
            "SYSTEM",
            "none",
            __import__("datetime").datetime.now().date().isoformat(),
            "none",
            "none",
            self.database.get_active_db_backend(),
        )
        self.financials._cached_financial_reports_bundle.clear()
        timings = bundle.get("pipeline_timings") or {}
        self.assertIn("total_ms", timings)
        self.assertIn("slowest_stage", timings)
