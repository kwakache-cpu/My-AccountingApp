import importlib
import json
import os
from datetime import date, datetime, timedelta
from unittest.mock import patch

from test_support import ERPIsolatedTestCase


class _FakePaystackResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class SubscriptionBillingTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self._original_paystack_env = {
            key: os.environ.get(key)
            for key in ("PAYSTACK_SECRET_KEY", "PAYSTACK_PUBLIC_KEY", "PAYSTACK_CALLBACK_URL", "PAYSTACK_CURRENCY")
        }
        os.environ["PAYSTACK_SECRET_KEY"] = "sk_test_subscription_suite"
        os.environ["PAYSTACK_PUBLIC_KEY"] = "pk_test_subscription_suite"
        os.environ["PAYSTACK_CALLBACK_URL"] = "https://example.com/paystack/callback"
        os.environ["PAYSTACK_CURRENCY"] = "GHS"
        self.modules = importlib.import_module("modules")

    def tearDown(self):
        try:
            for key, value in self._original_paystack_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        finally:
            super().tearDown()

    def _seed_initialized_payment(self, *, reference, company_key, company_name, plan_name, amount_major, duration_months=1):
        metadata = {
            "company_key": company_key,
            "company_name": company_name,
            "plan_name": plan_name,
            "subscription_months": duration_months,
            "user_email": f"{company_key.lower()}@example.com",
        }
        self.modules._upsert_license_payment_transaction(
            self.conn,
            reference=reference,
            company_key=company_key,
            company_name=company_name,
            payer_email=f"{company_key.lower()}@example.com",
            payment_context="subscription_renewal",
            plan_name=plan_name,
            expected_amount=int(round(float(amount_major) * 100)),
            currency="GHS",
            status="initialized",
            authorization_url="https://paystack.example.test/checkout",
            callback_url="https://example.com/paystack/callback",
            metadata_json=json.dumps(metadata),
        )
        self.conn.commit()

    def test_new_company_trial_creation(self):
        trial_company_key = "TRIAL-CO-001"
        result = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=trial_company_key,
            company_name="Trial Company",
            contact_email="trial@example.com",
            trial_days=7,
        )
        self.conn.commit()
        self.assertEqual(result["status"], "trial")
        snapshot = self.database.get_company_subscription_snapshot(trial_company_key, conn=self.conn)
        self.assertTrue(snapshot["ok"])
        self.assertTrue(snapshot["is_trial"])
        self.assertTrue(snapshot["access_allowed"])
        self.assertEqual(snapshot["plan_name"], "Trial")
        self.assertGreaterEqual(int(snapshot["days_left"] or 0), 6)

    def test_expired_trial_blocks_access(self):
        trial_company_key = "TRIAL-EXPIRED-001"
        self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=trial_company_key,
            company_name="Expired Trial Company",
            contact_email="expired@example.com",
            trial_days=7,
        )
        expired_on = (date.today() - timedelta(days=1)).isoformat()
        self.conn.execute(
            "UPDATE company_subscriptions SET end_date = ?, updated_at = CURRENT_TIMESTAMP WHERE company_key = ?",
            (expired_on, trial_company_key),
        )
        self.conn.execute(
            "UPDATE companies SET subscription_expiry = ? WHERE key = ?",
            (expired_on, trial_company_key),
        )
        self.conn.commit()
        snapshot = self.database.get_company_subscription_snapshot(trial_company_key, conn=self.conn)
        self.assertEqual(snapshot["status"], "expired")
        self.assertFalse(snapshot["access_allowed"])
        self.assertTrue(snapshot["renewal_required"])

    def test_verified_paystack_payment_activates_subscription(self):
        trial_company_key = "PAYSTACK-ACTIVE-001"
        self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=trial_company_key,
            company_name="Paystack Active Co",
            contact_email="paystack-active@example.com",
            trial_days=7,
        )
        reference = "SUB-VERIFY-001"
        self._seed_initialized_payment(
            reference=reference,
            company_key=trial_company_key,
            company_name="Paystack Active Co",
            plan_name="Basic",
            amount_major=50.0,
            duration_months=1,
        )
        success_payload = {
            "status": True,
            "data": {
                "status": "success",
                "reference": reference,
                "amount": 5000,
                "currency": "GHS",
                "paid_at": datetime.utcnow().isoformat(),
            },
        }
        with patch("modules.requests.get", return_value=_FakePaystackResponse(success_payload)):
            result = self.modules.verify_paystack_payment(reference, activate_license=True)
        self.assertTrue(result["ok"])
        payment_row = self.conn.execute(
            "SELECT status, verified_at, activated_at, plan_name FROM license_payment_transactions WHERE reference = ?",
            (reference,),
        ).fetchone()
        self.assertEqual(payment_row["status"], "success")
        self.assertIsNotNone(payment_row["verified_at"])
        self.assertIsNotNone(payment_row["activated_at"])
        snapshot = self.database.get_company_subscription_snapshot(trial_company_key, conn=self.conn)
        self.assertEqual(snapshot["status"], "active")
        self.assertEqual(snapshot["plan_name"], "Basic")
        self.assertEqual(snapshot["last_payment_reference"], reference)
        self.assertTrue(snapshot["access_allowed"])

    def test_failed_payment_does_not_activate_subscription(self):
        trial_company_key = "PAYSTACK-FAIL-001"
        self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=trial_company_key,
            company_name="Paystack Failed Co",
            contact_email="paystack-failed@example.com",
            trial_days=7,
        )
        reference = "SUB-FAIL-001"
        self._seed_initialized_payment(
            reference=reference,
            company_key=trial_company_key,
            company_name="Paystack Failed Co",
            plan_name="Pro",
            amount_major=120.0,
            duration_months=1,
        )
        failure_payload = {
            "status": True,
            "data": {
                "status": "failed",
                "reference": reference,
                "amount": 12000,
                "currency": "GHS",
            },
        }
        with patch("modules.requests.get", return_value=_FakePaystackResponse(failure_payload)):
            result = self.modules.verify_paystack_payment(reference, activate_license=True)
        self.assertFalse(result["ok"])
        payment_row = self.conn.execute(
            "SELECT status, activated_at FROM license_payment_transactions WHERE reference = ?",
            (reference,),
        ).fetchone()
        self.assertEqual(payment_row["status"], "failed")
        self.assertIsNone(payment_row["activated_at"])
        snapshot = self.database.get_company_subscription_snapshot(trial_company_key, conn=self.conn)
        self.assertIn(snapshot["status"], {"trial", "active"})
        self.assertNotEqual(snapshot["last_payment_reference"], reference)

    def test_renewal_extends_active_subscription_correctly(self):
        active_company_key = "SUB-EXTEND-001"
        original_start = date.today().isoformat()
        original_end = date.today() + timedelta(days=10)
        self.database.create_company_record(
            self.conn,
            company_key=active_company_key,
            company_name="Extend Active Co",
            subscription_expiry=original_end.isoformat(),
            status="Active",
            deployment_status="Live",
            contact_email="extend@example.com",
            subscription_plan_name="Basic",
            subscription_status="active",
            subscription_start_date=original_start,
            subscription_end_date=original_end.isoformat(),
            last_payment_reference="OLD-REF-001",
        )
        self.conn.commit()
        result = self.database.activate_company_subscription(
            self.conn,
            company_key=active_company_key,
            plan_name="Pro",
            payment_reference="NEW-REF-001",
            duration_months=1,
        )
        self.conn.commit()
        new_end = datetime.fromisoformat(result["end_date"]).date()
        self.assertTrue(result["was_extension"])
        self.assertGreater(new_end, original_end + timedelta(days=20))

    def test_expired_renewal_starts_from_today(self):
        expired_company_key = "SUB-RESTART-001"
        expired_end = date.today() - timedelta(days=5)
        self.database.create_company_record(
            self.conn,
            company_key=expired_company_key,
            company_name="Restart Expired Co",
            subscription_expiry=expired_end.isoformat(),
            status="Active",
            deployment_status="Live",
            contact_email="restart@example.com",
            subscription_plan_name="Basic",
            subscription_status="expired",
            subscription_start_date=(expired_end - timedelta(days=30)).isoformat(),
            subscription_end_date=expired_end.isoformat(),
            last_payment_reference="OLD-REF-002",
        )
        self.conn.commit()
        result = self.database.activate_company_subscription(
            self.conn,
            company_key=expired_company_key,
            plan_name="Enterprise",
            payment_reference="NEW-REF-002",
            duration_months=12,
        )
        self.conn.commit()
        self.assertFalse(result["was_extension"])
        self.assertEqual(datetime.fromisoformat(result["start_date"]).date(), date.today())
        self.assertGreater(datetime.fromisoformat(result["end_date"]).date(), date.today())
