"""
Hotfix 002 — staged onboarding payment instrumentation and failure isolation.
"""
import importlib
import inspect
import os
import unittest
from unittest.mock import MagicMock, patch

from test_support import ERPIsolatedTestCase


class Hotfix002OnboardingStageSourceTests(unittest.TestCase):
    def setUp(self):
        self.modules = importlib.import_module("modules")

    def test_legacy_onboarding_error_message_removed(self):
        source = inspect.getsource(self.modules.show_onboarding_payment)
        self.assertNotIn("Onboarding payment could not be started right now", source)

    def test_stage_workflow_helpers_present(self):
        self.assertTrue(callable(self.modules._execute_onboarding_submit_workflow))
        self.assertTrue(callable(self.modules._onboarding_support_message))

    def test_support_code_format(self):
        message = self.modules._onboarding_support_message("ABC123DEF456")
        self.assertIn("Support Code: ABC123DEF456", message)
        self.assertNotIn("Traceback", message)


class Hotfix002OnboardingStageFailureTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self._base_kwargs = {
            "company_name": "Brand New Company",
            "admin_email": "newco@example.com",
            "admin_phone": "0240000000",
            "sector": "Retail",
            "selected_plan_name": "Basic",
            "selected_plan": {
                "plan_name": "Basic",
                "amount": 100.0,
                "currency": "GHS",
                "duration_months": 1,
                "duration_days": 0,
                "configured": True,
            },
            "correlation_id": "HF002TEST01",
        }

    def _run_workflow(self, **overrides):
        kwargs = dict(self._base_kwargs)
        kwargs.update(overrides)
        return self.modules._execute_onboarding_submit_workflow(**kwargs)

    def test_stage_a_load_subscription_plans_failure(self):
        with patch.object(self.modules, "get_subscription_plan", side_effect=RuntimeError("plan load failed")):
            result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_a_load_subscription_plans")
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])

    def test_stage_b_db_connect_failure(self):
        with patch.object(self.modules, "get_connection", side_effect=RuntimeError("db unavailable")):
            result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_b_db_connect")
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])

    def test_stage_c_duplicate_company(self):
        result = self._run_workflow(company_name="Test Company")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_c_duplicate_company_lookup")
        self.assertTrue(result.get("duplicate"))
        self.assertIn("already exists", result["customer_message"])

    def test_stage_d_ensure_company_trial_subscription_failure(self):
        with patch.object(
            self.modules,
            "ensure_company_trial_subscription",
            side_effect=RuntimeError("trial provisioning failed"),
        ):
            result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_d_ensure_company_trial_subscription")
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])

    def test_stage_e_commit_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.commit.side_effect = RuntimeError("commit failed")
        with patch.object(self.modules, "get_connection", return_value=mock_conn):
            with patch.object(
                self.modules,
                "ensure_company_trial_subscription",
                return_value={"end_date": "2026-07-16"},
            ):
                result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_e_commit")
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])
        mock_conn.rollback.assert_called()

    def _configured_plan(self):
        return {
            "plan_name": "Basic",
            "amount": 100.0,
            "currency": "GHS",
            "duration_months": 1,
            "duration_days": 0,
            "configured": True,
        }

    def test_stage_f_initialize_paystack_payment_soft_failure(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        with patch.object(self.modules, "get_subscription_plan", return_value=self._configured_plan()):
            with patch.object(self.modules, "get_connection", return_value=mock_conn):
                with patch.object(
                    self.modules,
                    "ensure_company_trial_subscription",
                    return_value={"end_date": "2026-07-16"},
                ):
                    with patch.object(
                        self.modules,
                        "initialize_paystack_payment",
                        return_value={"ok": False, "reason": "Paystack secret key is not configured."},
                    ):
                        result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_f_initialize_paystack_payment")
        self.assertTrue(result.get("paystack_soft_failure"))
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])
        self.assertIn("Trial access remains active", result["customer_message"])

    def test_stage_f_initialize_paystack_payment_exception(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = None
        with patch.object(self.modules, "get_subscription_plan", return_value=self._configured_plan()):
            with patch.object(self.modules, "get_connection", return_value=mock_conn):
                with patch.object(
                    self.modules,
                    "ensure_company_trial_subscription",
                    return_value={"end_date": "2026-07-16"},
                ):
                    with patch.object(
                        self.modules,
                        "initialize_paystack_payment",
                        side_effect=RuntimeError("gateway transport failed"),
                    ):
                        result = self._run_workflow()
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_f_initialize_paystack_payment")
        self.assertIn("Support Code: HF002TEST01", result["customer_message"])


if __name__ == "__main__":
    unittest.main()
