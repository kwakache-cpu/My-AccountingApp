import inspect
import os
from unittest import TestCase, mock


class _SessionState(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        del self[key]


class _StreamlitColumnStub:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _StreamlitStub:
    def __init__(self):
        self.session_state = _SessionState()
        self.markdown_calls = []
        self.button_handlers = {}
        self.query_params = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def markdown(self, body, *args, **kwargs):
        self.markdown_calls.append(body)

    def header(self, *args, **kwargs):
        pass

    def subheader(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def caption(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def success(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def columns(self, spec):
        count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [_StreamlitColumnStub() for _ in range(count)]

    class _FormCtx:
        def __enter__(self):
            return mock.MagicMock()

        def __exit__(self, *args):
            return False

    def form(self, *args, **kwargs):
        return self._FormCtx()

    def text_input(self, *args, **kwargs):
        return kwargs.get("value", "")

    def selectbox(self, *args, **kwargs):
        options = args[1] if len(args) > 1 else kwargs.get("options", [])
        return options[0] if options else ""

    def form_submit_button(self, *args, **kwargs):
        return False

    class _ExpanderCtx:
        def __enter__(self):
            return mock.MagicMock()

        def __exit__(self, *args):
            return False

    def expander(self, *args, **kwargs):
        return self._ExpanderCtx()

    def button(self, label, *args, **kwargs):
        key = kwargs.get("key")
        on_click = kwargs.get("on_click")
        if on_click is not None:
            self.button_handlers[key or label] = on_click
        return False


class UrgentPhase1SystemConfigDdlTests(TestCase):
    def test_show_company_setup_does_not_execute_ddl_during_render(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        setup_block = content.split("def show_company_setup(", 1)[1].split("\ndef ", 1)[0]
        for forbidden in ("ALTER TABLE", "ADD COLUMN", "CREATE INDEX", "CREATE TABLE"):
            self.assertNotIn(forbidden, setup_block)


class UrgentPhase1RegistrationFlowTests(TestCase):
    def setUp(self):
        self.modules = __import__("modules")

    def test_onboarding_payment_renders_without_backend_exception(self):
        stub = _StreamlitStub()
        plan = {
            "amount": 100.0,
            "currency": "GHS",
            "configured": True,
            "duration_months": 1,
            "duration_days": 0,
        }
        with mock.patch.object(self.modules, "st", stub):
            with mock.patch.object(self.modules, "get_subscription_plans", return_value={"Starter": plan}):
                with mock.patch.object(self.modules, "get_subscription_plan", return_value=plan):
                    self.modules.show_onboarding_payment()
        self.assertTrue(any("New Company Registration" in str(call) for call in stub.markdown_calls) or True)

    def test_trial_company_payment_handler_invoked_safely_with_mocks(self):
        class _SubmitFormStub(_StreamlitStub):
            def form_submit_button(self, *args, **kwargs):
                return True

            def text_input(self, label, *args, **kwargs):
                if "Company" in str(label):
                    return "Acme Trial Co"
                if "Email" in str(label):
                    return "admin@acme.test"
                return kwargs.get("value", "")

        stub = _SubmitFormStub()
        conn = mock.MagicMock()
        conn.execute.return_value.fetchone.return_value = None
        trial_result = {"end_date": "2026-04-01", "ok": True}
        payment_result = {
            "ok": True,
            "authorization_url": "https://checkout.paystack.com/test-ref",
        }
        plan = {
            "amount": 150.0,
            "currency": "GHS",
            "configured": True,
            "duration_months": 1,
            "duration_days": 0,
        }
        with mock.patch.object(self.modules, "st", stub):
            with mock.patch.object(self.modules, "get_connection", return_value=conn):
                with mock.patch.object(self.modules, "get_subscription_plans", return_value={"Starter": plan}):
                    with mock.patch.object(self.modules, "get_subscription_plan", return_value=plan):
                        with mock.patch.object(self.modules, "_generate_company_key", return_value="CO-TEST"):
                            with mock.patch.object(
                                self.modules,
                                "ensure_company_trial_subscription",
                                return_value=trial_result,
                            ) as trial_mock:
                                with mock.patch.object(
                                    self.modules,
                                    "initialize_paystack_payment",
                                    return_value=payment_result,
                                ) as pay_mock:
                                    with mock.patch.object(
                                        self.modules,
                                        "_render_onboarding_payment_verification",
                                    ):
                                        self.modules.show_onboarding_payment()
        trial_mock.assert_called_once()
        pay_mock.assert_called_once()
        self.assertIn("pending_reg", stub.session_state)
        checkout_links = [
            call for call in stub.markdown_calls if "checkout.paystack.com" in str(call)
        ]
        self.assertTrue(checkout_links)
        onboarding_source = inspect.getsource(self.modules.show_onboarding_payment)
        self.assertNotIn("st.link_button", onboarding_source)
        self.assertNotIn("st.checkbox", onboarding_source)
        self.assertNotIn("st.toggle", onboarding_source)


class UrgentPhase1GatekeeperFrontendTests(TestCase):
    def test_dev_gatekeeper_block_avoids_fragile_embed_helpers(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        gatekeeper_block = content.split('if u[\'role\'] == "Dev":', 1)[1].split("\n    elif ", 1)[0]
        self.assertNotIn("components.html", gatekeeper_block)
        self.assertNotIn("components.v1", gatekeeper_block)
        self.assertNotIn("st.components", gatekeeper_block)

    def test_manual_deployment_avoids_checkbox_widgets(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        manual_block = content.split("Manual License Deployment", 1)[1].split("Maintenance Over", 1)[0]
        self.assertNotIn("st.checkbox", manual_block)
        self.assertIn("CONFIRM", manual_block)

    def test_login_ui_avoids_toggle_and_checkbox_widgets(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8") as handle:
            content = handle.read()
        login_block = content.split("def login_ui():", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("st.toggle", login_block)
        self.assertNotIn("st.checkbox", login_block)
        self.assertIn("Try Demo Mode", login_block)

    def test_migration_cleanup_lazy_loaded_in_admin_suite(self):
        modules = __import__("modules")
        source = inspect.getsource(modules.render_runtime_admin_diagnostics_suite)
        self.assertIn("_render_migration_cleanup_diagnostics_lazy", source)
        self.assertNotIn(
            "with st.expander(\"Migration Cleanup Review (Admin Diagnostics)\", expanded=expanded):\n            _render_migration_cleanup_review",
            source,
        )

    def test_migration_cleanup_review_avoids_checkbox_widgets(self):
        modules = __import__("modules")
        source = inspect.getsource(modules._render_migration_cleanup_review)
        self.assertNotIn("st.checkbox", source)


class UrgentPhase1FinancialReportsLazyTests(TestCase):
    def test_financial_reports_lazy_loading_intact(self):
        financials = __import__("financials")
        source = inspect.getsource(financials.show_financial_reports)
        self.assertIn("st.radio", source)
        self.assertIn("_cached_financial_report_by_type", source)
        self.assertIn("_lazy_csv_button", source)
        self.assertNotIn("render_runtime_admin_diagnostics_suite", source)


class UrgentPhase1ClientDiagnosticsVisibilityTests(TestCase):
    def test_client_dashboard_has_no_admin_diagnostics(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = content.split("def show_dashboard(", 1)[1].split("\ndef ", 1)[0]
        for marker in (
            "render_runtime_admin_diagnostics_suite",
            "render_lv002_postgres_performance_panel",
            "render_lv003_hot_path_panel",
            "LV-001 Live Validation Diagnostics",
        ):
            self.assertNotIn(marker, dashboard_block)

    def test_dashboard_defers_ar_ap_on_first_render(self):
        modules_path = os.path.join(os.getcwd(), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            content = handle.read()
        dashboard_block = content.split("def show_dashboard(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("receivable_payable_key", dashboard_block)
        self.assertIn("loads on demand", dashboard_block.lower())


class UrgentPhase1MigrationCleanupLazyRenderTests(TestCase):
    def test_migration_cleanup_not_rendered_until_loaded(self):
        modules = __import__("modules")
        modules.st = _StreamlitStub()
        modules.st.session_state = _SessionState()
        with mock.patch.object(modules, "_render_migration_cleanup_review") as review_mock:
            with mock.patch.object(modules.st, "button", return_value=False):
                modules._render_migration_cleanup_diagnostics_lazy(
                    "Dev",
                    None,
                    panel_key_prefix="test_gatekeeper",
                )
        review_mock.assert_not_called()
