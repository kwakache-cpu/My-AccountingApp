"""
Program C Round A — Paystack config resolution + public surface lockdown.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from test_support import ERPIsolatedTestCase


class _SecretsRoot(dict):
    """Minimal st.secrets stand-in supporting root and nested section lookup."""

    def __contains__(self, key):
        return dict.__contains__(self, key)


def _login_ui_source(app_module):
    return inspect.getsource(app_module.login_ui)


def _function_source(module, name):
    return inspect.getsource(getattr(module, name))


class PaystackConfigResolutionTests(unittest.TestCase):
    def setUp(self):
        self.modules = importlib.import_module("modules")
        self.modules.clear_paystack_runtime_config_cache()
        self._env_backup = {}
        for key in (
            "PAYSTACK_SECRET_KEY",
            "PAYSTACK_PUBLIC_KEY",
            "PAYSTACK_CALLBACK_URL",
            "PAYSTACK_CURRENCY",
            "PAYSTACK_WEBHOOK_SECRET",
            "paystack_secret_key",
            "paystack_public_key",
            "paystack_callback_url",
            "paystack_currency",
            "paystack_webhook_secret",
        ):
            self._env_backup[key] = os.environ.pop(key, None)
        self._original_st = self.modules.st

    def tearDown(self):
        self.modules.st = self._original_st
        self.modules.clear_paystack_runtime_config_cache()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_resolves_root_level_streamlit_secrets(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "PAYSTACK_SECRET_KEY": "sk_test_root",
                    "PAYSTACK_PUBLIC_KEY": "pk_test_root",
                    "PAYSTACK_CALLBACK_URL": "https://example.com/callback",
                    "PAYSTACK_CURRENCY": "ghs",
                    "PAYSTACK_WEBHOOK_SECRET": "whsec_root",
                }
            )
        )
        config = self.modules.get_paystack_runtime_config(force_refresh=True)
        status = self.modules.get_paystack_secret_status()
        self.assertTrue(config["secret_key_present"])
        self.assertTrue(config["public_key_present"])
        self.assertTrue(config["callback_url_configured"])
        self.assertEqual(config["currency"], "GHS")
        self.assertEqual(status["sources"]["PAYSTACK_PUBLIC_KEY"], "st.secrets root")
        self.assertEqual(status["sources"]["PAYSTACK_CALLBACK_URL"], "st.secrets root")

    def test_resolves_nested_paystack_section(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "paystack": {
                        "secret_key": "sk_test_nested",
                        "public_key": "pk_test_nested",
                        "callback_url": "https://example.com/nested-callback",
                        "currency": "GHS",
                        "webhook_secret": "whsec_nested",
                    }
                }
            )
        )
        config = self.modules.get_paystack_runtime_config(force_refresh=True)
        status = self.modules.get_paystack_secret_status()
        self.assertTrue(config["public_key_present"])
        self.assertTrue(config["callback_url_configured"])
        self.assertEqual(status["sources"]["PAYSTACK_PUBLIC_KEY"], "st.secrets nested section")
        self.assertEqual(status["sources"]["PAYSTACK_SECRET_KEY"], "st.secrets nested section")

    def test_environment_variables_still_resolve_and_precede_secrets(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "PAYSTACK_PUBLIC_KEY": "pk_from_secrets",
                    "PAYSTACK_CALLBACK_URL": "https://secrets.example/callback",
                }
            )
        )
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_from_env"
        os.environ["PAYSTACK_PUBLIC_KEY"] = "pk_from_env"
        os.environ["PAYSTACK_CALLBACK_URL"] = "https://env.example/callback"
        config = self.modules.get_paystack_runtime_config(force_refresh=True)
        status = self.modules.get_paystack_secret_status()
        self.assertEqual(config["public_key"], "pk_from_env")
        self.assertEqual(status["sources"]["PAYSTACK_PUBLIC_KEY"], "os.environ")
        self.assertEqual(status["sources"]["PAYSTACK_CALLBACK_URL"], "os.environ")

    def test_empty_values_are_treated_as_missing(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "PAYSTACK_PUBLIC_KEY": "   ",
                    "PAYSTACK_CALLBACK_URL": "",
                    "paystack": {"public_key": "", "callback_url": "   "},
                }
            )
        )
        os.environ["PAYSTACK_PUBLIC_KEY"] = ""
        config = self.modules.get_paystack_runtime_config(force_refresh=True)
        status = self.modules.get_paystack_secret_status()
        self.assertFalse(config["public_key_present"])
        self.assertFalse(config["callback_url_configured"])
        self.assertEqual(status["PAYSTACK_PUBLIC_KEY"], "missing")
        self.assertEqual(status["PAYSTACK_CALLBACK_URL"], "missing")

    def test_callback_url_validity_is_checked(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "PAYSTACK_SECRET_KEY": "sk_test",
                    "PAYSTACK_PUBLIC_KEY": "pk_test",
                    "PAYSTACK_CALLBACK_URL": "not-a-url",
                }
            )
        )
        status = self.modules.get_paystack_secret_status()
        rows = {row["setting"]: row for row in self.modules.get_paystack_config_source_diagnostics()}
        self.assertFalse(status["PAYSTACK_CALLBACK_URL_valid"])
        self.assertEqual(rows["PAYSTACK_CALLBACK_URL"]["presence"], "present")
        self.assertEqual(rows["PAYSTACK_CALLBACK_URL"]["validity"], "invalid")
        init_result = self.modules.initialize_paystack_payment(
            "uat@example.com",
            10,
            "REF-INVALID-CALLBACK",
            company_key="EKA-TEST",
            company_name="Test Co",
            plan_name=None,
        )
        self.assertFalse(init_result.get("ok"))
        self.assertIn("invalid", str(init_result.get("reason") or "").lower())
        self.assertNotIn("sk_test", repr(init_result))
        self.assertNotIn("pk_test", repr(init_result))

    def test_diagnostics_never_include_secret_values(self):
        self.modules.st = SimpleNamespace(
            secrets=_SecretsRoot(
                {
                    "PAYSTACK_SECRET_KEY": "sk_super_secret_value",
                    "PAYSTACK_PUBLIC_KEY": "pk_super_secret_value",
                    "PAYSTACK_CALLBACK_URL": "https://example.com/callback",
                    "PAYSTACK_WEBHOOK_SECRET": "whsec_super_secret",
                }
            )
        )
        status = self.modules.get_paystack_secret_status()
        diagnostics = self.modules.get_paystack_diagnostics()
        rows = self.modules.get_paystack_config_source_diagnostics()
        blob = repr(status) + repr(diagnostics) + repr(rows)
        self.assertNotIn("sk_super_secret_value", blob)
        self.assertNotIn("pk_super_secret_value", blob)
        self.assertNotIn("whsec_super_secret", blob)
        for row in rows:
            self.assertIn(row["presence"], {"present", "missing"})
            self.assertIn(row["validity"], {"valid", "invalid"})
            self.assertIn(
                row["source"],
                {
                    "os.environ",
                    "st.secrets root",
                    "st.secrets nested section",
                    "default",
                    "missing",
                    "malformed",
                    "empty",
                },
            )


class PublicSurfaceLockdownTests(unittest.TestCase):
    def setUp(self):
        self.app = importlib.import_module("app")
        self.modules = importlib.import_module("modules")

    def test_unauthenticated_login_ui_has_no_system_status_tab(self):
        source = _login_ui_source(self.app)
        self.assertNotIn("System Status", source)
        self.assertNotIn("show_system_status()", source)
        self.assertIn('st.tabs(["Secure Login", "System Recovery", "Register New Company"])', source)
        self.assertIn("show_onboarding_payment()", source)
        self.assertIn("Try Demo Mode", source)

    def test_login_ui_has_no_public_admin_recovery_panel(self):
        source = _login_ui_source(self.app)
        self.assertNotIn("_show_admin_recovery_panel()", source)
        self.assertNotIn("Administrative Access Repair Needed", source)
        self.assertNotIn("_has_restored_data_without_admin_users()", source)

    def test_unauthenticated_users_cannot_render_system_status_directly(self):
        calls = {"error": [], "metric": []}
        fake_st = SimpleNamespace(
            session_state={"auth": False, "user": None},
            error=lambda msg: calls["error"].append(msg),
            info=lambda msg: None,
            title=lambda msg: calls.setdefault("title", []).append(msg),
            markdown=lambda *a, **k: None,
            caption=lambda *a, **k: None,
            subheader=lambda *a, **k: None,
            columns=lambda *a, **k: [SimpleNamespace(metric=lambda *x, **y: calls["metric"].append(x))],
            metric=lambda *a, **k: calls["metric"].append(a),
            dataframe=lambda *a, **k: None,
        )
        with mock.patch.object(self.app, "st", fake_st):
            ok = self.app.show_system_status(role="Cashier", require_auth=True)
        self.assertFalse(ok)
        self.assertTrue(calls["error"])
        self.assertFalse(calls["metric"])

    def test_ordinary_client_roles_cannot_render_admin_system_status(self):
        for role in ("Cashier", "Bookkeeper", "Sales Officer", "Demo"):
            fake_st = SimpleNamespace(
                session_state={"auth": True, "user": {"role": role, "key": "U1"}},
                error=mock.Mock(),
                info=mock.Mock(),
                title=mock.Mock(),
                markdown=mock.Mock(),
                caption=mock.Mock(),
                subheader=mock.Mock(),
                columns=mock.Mock(return_value=[SimpleNamespace(metric=mock.Mock())] * 3),
                metric=mock.Mock(),
                dataframe=mock.Mock(),
            )
            with mock.patch.object(self.app, "st", fake_st):
                ok = self.app.show_system_status(role=role, require_auth=True)
            self.assertFalse(ok, role)
            fake_st.error.assert_called()

    def test_admin_roles_can_access_system_status_after_authentication(self):
        class _Col:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def metric(self, *args, **kwargs):
                return None

        for role in ("Dev", "Master Admin", "System Admin"):
            fake_st = SimpleNamespace(
                session_state={"auth": True, "user": {"role": role, "key": "ADMIN"}},
                error=mock.Mock(),
                info=mock.Mock(),
                title=mock.Mock(),
                markdown=mock.Mock(),
                caption=mock.Mock(),
                subheader=mock.Mock(),
                columns=lambda n=3, **kwargs: [_Col() for _ in range(int(n) if not isinstance(n, list) else len(n))],
                metric=mock.Mock(),
                dataframe=mock.Mock(),
            )
            with mock.patch.object(self.app, "st", fake_st):
                ok = self.app.show_system_status(role=role, require_auth=True)
            self.assertTrue(ok, role)
            fake_st.title.assert_called()
            fake_st.error.assert_not_called()

    def test_admin_repair_not_public_by_default(self):
        fake_st = SimpleNamespace(
            session_state={"auth": False, "user": None},
            query_params={},
            error=mock.Mock(),
            info=mock.Mock(),
            warning=mock.Mock(),
            success=mock.Mock(),
            subheader=mock.Mock(),
            markdown=mock.Mock(),
            caption=mock.Mock(),
            text_input=mock.Mock(return_value=""),
            button=mock.Mock(return_value=False),
            selectbox=mock.Mock(),
            form=mock.MagicMock(),
            columns=mock.Mock(return_value=[SimpleNamespace()]),
            form_submit_button=mock.Mock(return_value=False),
        )
        with mock.patch.object(self.app, "st", fake_st):
            self.app._show_admin_recovery_panel()
        fake_st.error.assert_called()
        self.assertFalse(self.app.is_admin_recovery_mode_authorized())

    def test_admin_repair_requires_explicit_secure_recovery_mode_and_token(self):
        fake_st = SimpleNamespace(
            session_state={
                "auth": True,
                "user": {"role": "Dev", "key": "ADMIN"},
                "admin_recovery_unlocked": False,
            },
            query_params={"admin_recovery": "1"},
            error=mock.Mock(),
            info=mock.Mock(),
            warning=mock.Mock(),
            success=mock.Mock(),
            subheader=mock.Mock(),
            markdown=mock.Mock(),
            caption=mock.Mock(),
            text_input=mock.Mock(return_value="wrong-token"),
            button=mock.Mock(return_value=True),
            selectbox=mock.Mock(),
            form=mock.MagicMock(),
            columns=mock.Mock(return_value=[SimpleNamespace()]),
            form_submit_button=mock.Mock(return_value=False),
            rerun=mock.Mock(),
        )
        with mock.patch.object(self.app, "st", fake_st), mock.patch.object(
            self.app, "_admin_recovery_expected_token", return_value="expected-token"
        ), mock.patch.object(self.app, "_has_restored_data_without_admin_users", return_value=True):
            authorized = self.app.is_admin_recovery_mode_authorized()
            self.app._show_admin_recovery_panel()
        self.assertFalse(authorized)
        fake_st.error.assert_called()

        fake_st.session_state["admin_recovery_unlocked"] = True
        with mock.patch.object(self.app, "st", fake_st), mock.patch.object(
            self.app, "_admin_recovery_expected_token", return_value="expected-token"
        ), mock.patch.object(self.app, "_has_restored_data_without_admin_users", return_value=True), mock.patch.object(
            self.app, "_get_restored_companies_needing_admin", return_value=[]
        ):
            self.assertTrue(self.app.is_admin_recovery_mode_authorized())
            self.app._show_admin_recovery_panel()
        fake_st.success.assert_called()

    def test_anonymous_admin_creation_is_blocked(self):
        source = _function_source(self.app, "_show_admin_recovery_panel")
        self.assertIn("is_admin_recovery_mode_authorized", source)
        self.assertIn("Administrative recovery is restricted", source)
        fake_st = SimpleNamespace(
            session_state={"auth": False},
            query_params={"admin_recovery": "1"},
            error=mock.Mock(),
            info=mock.Mock(),
            warning=mock.Mock(),
        )
        with mock.patch.object(self.app, "st", fake_st), mock.patch.object(
            self.app, "_get_restored_companies_needing_admin"
        ) as companies_mock:
            self.app._show_admin_recovery_panel()
        companies_mock.assert_not_called()
        fake_st.error.assert_called()

    def test_secure_login_registration_password_recovery_still_present(self):
        source = _login_ui_source(self.app)
        self.assertIn("Secure Login", source)
        self.assertIn("System Recovery", source)
        self.assertIn("Register New Company", source)
        self.assertIn("v3_final_access_key_field", source)
        self.assertIn("v3_forgot_login_key", source)
        self.assertIn("show_onboarding_payment()", source)

    def test_no_streamlit_duplicate_login_key_regression(self):
        app_path = os.path.join(os.getcwd(), "app.py")
        with open(app_path, encoding="utf-8-sig") as handle:
            content = handle.read()
        self.assertEqual(content.count('key="v3_final_access_key_field"'), 1)
        self.assertIn('if __name__ == "__main__":', content.split("# Main application flow", 1)[1])

    def test_sqlite_postgres_compatibility_helpers_intact(self):
        database = importlib.import_module("database")
        self.assertTrue(hasattr(database, "execute_portable_query"))
        self.assertTrue(hasattr(database, "get_active_db_backend"))
        self.assertTrue(callable(self.modules.get_paystack_runtime_config))


class PublicSurfaceInventoryTests(unittest.TestCase):
    def test_public_login_tabs_are_limited(self):
        app = importlib.import_module("app")
        source = _login_ui_source(app)
        forbidden = (
            "API Gateway",
            "Database Engine",
            "Payment Server",
            "Live Uptime",
            "Past Incidents",
            "Administrative Access Repair Needed",
            "Create New Admin User for Restored Company",
            "render_runtime_admin_diagnostics_suite",
            "migration cleanup",
        )
        for marker in forbidden:
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
