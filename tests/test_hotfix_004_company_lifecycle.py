"""
Hotfix 004 — onboarding Paystack diagnostics and trial company lifecycle wipe hardening.
"""
import importlib
import inspect
import unittest
from unittest import mock

from test_support import ERPIsolatedTestCase


class Hotfix004PaystackStageFDiagnosticsTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_initialize_paystack_reports_failure_step_for_missing_public_key(self):
        config = self.modules.get_paystack_runtime_config()
        config = dict(config)
        config["secret_key_present"] = True
        config["public_key_present"] = False
        config["callback_url_configured"] = True
        with mock.patch.object(self.modules, "get_paystack_runtime_config", return_value=config):
            result = self.modules.initialize_paystack_payment(
                "trial@example.com",
                100.0,
                "ONB-HF004-001",
                metadata_extra={"correlation_id": "1C22837EDB1F"},
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["failure_step"], "validate_public_key")
        self.assertEqual(result["paystack_status"]["PAYSTACK_SECRET_KEY"], "present")
        self.assertEqual(result["paystack_status"]["PAYSTACK_PUBLIC_KEY"], "missing")

    def test_stage_f_logs_failure_step_field(self):
        source = inspect.getsource(self.modules._execute_onboarding_submit_workflow)
        self.assertIn("failure_step", source)
        self.assertIn("callback_url_valid", source)


class Hotfix004CompanyWipeTests(ERPIsolatedTestCase):
    def _create_trial_company(self, company_key, company_name):
        end_date = "2026-07-16"
        self.database.create_company_record(
            self.conn,
            company_key=company_key,
            company_name=company_name,
            subscription_expiry=end_date,
            status="Active",
            deployment_status="Trial",
            contact_email="trial@example.com",
            subscription_plan_name="Trial",
            subscription_status="trial",
            subscription_start_date="2026-07-09",
            subscription_end_date=end_date,
        )
        self.database.execute_portable_write(
            self.conn,
            """
            INSERT INTO license_payment_transactions (
                reference, company_key, company_name, payer_email, payment_context,
                plan_name, expected_amount, currency, status
            )
            VALUES (?, ?, ?, ?, 'onboarding', 'Basic', 10000, 'GHS', 'initialized')
            """,
            (f"PAY-{company_key}", company_key, company_name, "trial@example.com"),
        )
        self.conn.commit()

    def test_delete_trial_company_removes_subscription_and_payment_records(self):
        company_key = "EKA-TRIAL-WIPE-01"
        self._create_trial_company(company_key, "Trial Wipe Co")
        result = self.database.wipe_company_records(
            self.conn,
            company_key,
            correlation_id="HF004WIPE01",
            manage_transaction=True,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["deployment_status"], "Trial")
        self.assertIn("company_subscriptions", result["deleted_tables"])
        self.assertIn("license_payment_transactions", result["deleted_tables"])
        self.assertIsNone(
            self.conn.execute("SELECT key FROM companies WHERE key = ?", (company_key,)).fetchone()
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT company_key FROM company_subscriptions WHERE company_key = ?",
                (company_key,),
            ).fetchone()
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT company_key FROM license_payment_transactions WHERE company_key = ?",
                (company_key,),
            ).fetchone()
        )

    def test_delete_archived_company(self):
        company_key = "EKA-ARCH-WIPE-01"
        self._create_trial_company(company_key, "Archived Wipe Co")
        self.conn.execute(
            "UPDATE companies SET status = 'Inactive', deployment_status = 'Archived' WHERE key = ?",
            (company_key,),
        )
        self.conn.commit()
        result = self.database.wipe_company_records(self.conn, company_key, manage_transaction=True)
        self.assertTrue(result["ok"])
        self.assertIsNone(self.conn.execute("SELECT key FROM companies WHERE key = ?", (company_key,)).fetchone())

    def test_delete_paid_company_subscription(self):
        company_key = "EKA-PAID-WIPE-01"
        self._create_trial_company(company_key, "Paid Wipe Co")
        self.database.upsert_company_subscription(
            self.conn,
            company_key=company_key,
            plan_name="Basic",
            status="active",
            start_date="2026-07-01",
            end_date="2027-07-01",
            last_payment_reference="PAY-PAID-001",
        )
        self.conn.commit()
        result = self.database.wipe_company_records(self.conn, company_key, manage_transaction=True)
        self.assertTrue(result["ok"])
        self.assertIsNone(
            self.conn.execute(
                "SELECT company_key FROM company_subscriptions WHERE company_key = ?",
                (company_key,),
            ).fetchone()
        )

    def test_wipe_plan_deletes_company_subscriptions_before_companies(self):
        plan = self.database.build_company_wipe_delete_plan(self.conn, self.company_key)
        table_names = [table_name for table_name, _sql, _params in plan]
        self.assertIn("company_subscriptions", table_names)
        self.assertLess(
            table_names.index("company_subscriptions"),
            len(table_names),
        )
        self.assertNotIn("companies", table_names)

    def test_sqlite_wipe_rollback_on_failure_preserves_company(self):
        company_key = "EKA-ROLLBACK-01"
        self._create_trial_company(company_key, "Rollback Co")

        original_write = self.database.execute_portable_write

        def failing_write(conn, sql, params=(), backend=None):
            if "DELETE FROM companies" in sql:
                raise RuntimeError("simulated companies delete failure")
            return original_write(conn, sql, params, backend=backend)

        with mock.patch.object(self.database, "execute_portable_write", side_effect=failing_write):
            with self.assertRaises(RuntimeError):
                self.database.wipe_company_records(
                    self.conn,
                    company_key,
                    correlation_id="HF004ROLL01",
                    manage_transaction=True,
                )
        self.assertIsNotNone(self.conn.execute("SELECT key FROM companies WHERE key = ?", (company_key,)).fetchone())
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT company_key FROM company_subscriptions WHERE company_key = ?",
                (company_key,),
            ).fetchone()
        )

    def test_company_subscriptions_references_companies_key(self):
        refs = self.database.get_company_wipe_referencing_tables(self.conn)
        self.assertIn("company_subscriptions", refs["foreign_key_references_to_companies"])

    def test_postgres_fk_ordering_places_child_before_parent(self):
        edges = [
            ("company_subscriptions", "companies"),
            ("payments", "companies"),
            ("payment_allocations", "payments"),
        ]
        ordered = self.database.sort_company_wipe_tables(
            ["company_subscriptions", "payments", "payment_allocations"],
            edges,
        )
        self.assertLess(ordered.index("payment_allocations"), ordered.index("payments"))
        self.assertLess(ordered.index("company_subscriptions"), ordered.index("payments"))


class Hotfix004AppWipeUxTests(unittest.TestCase):
    def test_app_uses_database_wipe_and_support_code_message(self):
        import app

        app_source = inspect.getsource(app)
        self.assertNotIn("def wipe_company_records", app_source)
        self.assertIn("wipe_company_records", app_source)
        self.assertIn("Trial company deleted successfully.", app_source)
        self.assertIn("Company could not be deleted. Support Code:", app_source)


if __name__ == "__main__":
    import unittest

    unittest.main()
