"""
Hotfix 003 — PostgreSQL identity sequence repair for onboarding subscriptions.
"""
import importlib
import inspect
from types import SimpleNamespace
from unittest import mock

from test_support import ERPIsolatedTestCase


class _FakeDiag(SimpleNamespace):
    pass


class _FakeUniqueViolation(Exception):
    pgcode = "23505"

    def __init__(self, message):
        super().__init__(message)
        self.diag = _FakeDiag(constraint_name="company_subscriptions_pkey")


class Hotfix003SequenceRepairTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_repair_postgres_sequence_for_table_aligns_to_max_plus_one(self):
        fake_conn = object()
        max_row = {"max_id": 5}
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "execute_portable_query",
            return_value=mock.MagicMock(fetchone=mock.Mock(return_value=max_row)),
        ) as query_mock, mock.patch.object(
            self.database,
            "execute_portable_write",
        ) as write_mock:
            result = self.database.repair_postgres_sequence_for_table(
                fake_conn,
                "company_subscriptions",
                "id",
            )
        self.assertTrue(result["repaired"])
        self.assertEqual(result["max_id"], 5)
        self.assertEqual(result["next_id"], 6)
        repair_sql = write_mock.call_args.args[1]
        self.assertIn("setval", repair_sql.lower())
        self.assertIn("6", repair_sql)
        query_mock.assert_called_once()

    def test_repair_postgres_sequence_for_table_is_noop_on_sqlite(self):
        result = self.database.repair_postgres_sequence_for_table(self.conn, "company_subscriptions", "id")
        self.assertFalse(result["repaired"])
        self.assertEqual(result["reason"], "not_postgres")

    def test_sequence_health_detects_drift(self):
        health_row = {
            "max_id": 5,
            "sequence_name": "public.company_subscriptions_id_seq",
            "sequence_last_value": 4,
            "sequence_is_called": True,
        }
        fake_conn = object()
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "get_connection",
            return_value=fake_conn,
        ), mock.patch.object(
            self.database,
            "db_table_exists",
            return_value=True,
        ), mock.patch.object(
            self.database,
            "execute_portable_query",
            return_value=mock.MagicMock(fetchone=mock.Mock(return_value=health_row)),
        ):
            health = self.database.get_postgres_identity_sequence_health(conn=fake_conn)
        self.assertTrue(health["checked"])
        self.assertTrue(health["drift_detected"])
        drifted = [item for item in health["tables"] if item.get("drift_detected")]
        self.assertEqual(drifted[0]["table_name"], "company_subscriptions")
        self.assertEqual(drifted[0]["next_sequence_value"], 5)

    def test_upsert_company_subscription_retries_once_after_serial_pk_collision(self):
        fake_conn = mock.MagicMock()
        calls = {"writes": 0}

        def write_side_effect(conn, sql, params=(), backend=None):
            calls["writes"] += 1
            if calls["writes"] == 1:
                raise _FakeUniqueViolation(
                    'duplicate key value violates unique constraint "company_subscriptions_pkey"'
                )

        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "execute_portable_write",
            side_effect=write_side_effect,
        ), mock.patch.object(
            self.database,
            "repair_postgres_sequence_for_table",
            return_value={"repaired": True, "next_id": 6},
        ) as repair_mock:
            self.database.upsert_company_subscription(
                fake_conn,
                company_key="EKA-PAY-RETRY-0001",
                plan_name="Trial",
                status="trial",
                start_date="2026-07-09",
                end_date="2026-07-16",
                correlation_id="HF003TEST01",
            )
        self.assertEqual(calls["writes"], 2)
        repair_mock.assert_called_once_with(fake_conn, "company_subscriptions", "id")
        fake_conn.rollback.assert_called_once()

    def test_upsert_company_subscription_does_not_retry_indefinitely(self):
        fake_conn = mock.MagicMock()
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "execute_portable_write",
            side_effect=_FakeUniqueViolation(
                'duplicate key value violates unique constraint "company_subscriptions_pkey"'
            ),
        ), mock.patch.object(
            self.database,
            "repair_postgres_sequence_for_table",
            return_value={"repaired": True, "next_id": 6},
        ):
            with self.assertRaises(_FakeUniqueViolation):
                self.database.upsert_company_subscription(
                    fake_conn,
                    company_key="EKA-PAY-RETRY-0002",
                    plan_name="Trial",
                    status="trial",
                    start_date="2026-07-09",
                    end_date="2026-07-16",
                    correlation_id="HF003TEST02",
                )
        self.assertEqual(fake_conn.rollback.call_count, 1)

    def test_sqlite_upsert_path_unaffected(self):
        self.database.upsert_company_subscription(
            self.conn,
            company_key=self.company_key,
            plan_name="Trial",
            status="trial",
            start_date="2026-07-09",
            end_date="2026-07-16",
        )
        row = self.conn.execute(
            "SELECT company_key, plan_name, status FROM company_subscriptions WHERE company_key = ?",
            (self.company_key,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["plan_name"], "Trial")

    def test_ensure_company_trial_subscription_succeeds_after_sequence_repair(self):
        fake_conn = mock.MagicMock()
        subscription_writes = {"count": 0}

        def write_side_effect(conn, sql, params=(), backend=None):
            if "INSERT INTO company_subscriptions" in sql:
                subscription_writes["count"] += 1
                if subscription_writes["count"] == 1:
                    raise _FakeUniqueViolation(
                        'duplicate key value violates unique constraint "company_subscriptions_pkey" DETAIL: Key (id)=(5) already exists.'
                    )
            return None

        company_lookup = mock.MagicMock(fetchone=mock.Mock(return_value=None))
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "execute_portable_query",
            return_value=company_lookup,
        ), mock.patch.object(
            self.database,
            "execute_portable_write",
            side_effect=write_side_effect,
        ), mock.patch.object(
            self.database,
            "repair_postgres_sequence_for_table",
            return_value={"repaired": True, "next_id": 6, "table_name": "company_subscriptions"},
        ) as repair_mock:
            result = self.database.ensure_company_trial_subscription(
                fake_conn,
                company_key="EKA-PAY-SEQ-01",
                company_name="Sequence Retry Co",
                contact_email="seq@example.com",
                correlation_id="HF003SEQ01",
            )
        self.assertEqual(result["company_key"], "EKA-PAY-SEQ-01")
        self.assertEqual(subscription_writes["count"], 2)
        repair_mock.assert_called_once_with(fake_conn, "company_subscriptions", "id")

    def test_monitored_sequence_tables_include_subscription_and_license_payment(self):
        table_names = {table for table, _column in self.database.POSTGRES_IDENTITY_SEQUENCE_HEALTH_TABLES}
        self.assertIn("company_subscriptions", table_names)
        self.assertIn("license_payment_transactions", table_names)

    def test_onboarding_workflow_reaches_paystack_after_trial_subscription(self):
        fake_conn = mock.MagicMock()
        fake_conn.execute.return_value.fetchone.return_value = None
        trial_result = {
            "company_key": "EKA-PAY-ONB-01",
            "company_name": "Onboarding Retry Co",
            "status": "trial",
            "start_date": "2026-07-09",
            "end_date": "2026-07-16",
            "days_left": 7,
        }
        with mock.patch.object(self.modules, "get_connection", return_value=fake_conn), mock.patch.object(
            self.modules,
            "get_subscription_plan",
            return_value={
                "plan_name": "Basic",
                "amount": 100.0,
                "currency": "GHS",
                "duration_months": 1,
                "duration_days": 0,
                "configured": True,
            },
        ), mock.patch.object(
            self.modules,
            "ensure_company_trial_subscription",
            return_value=trial_result,
        ) as trial_mock, mock.patch.object(
            self.modules,
            "initialize_paystack_payment",
            return_value={"ok": True, "authorization_url": "https://paystack.test/checkout"},
        ):
            result = self.modules._execute_onboarding_submit_workflow(
                "Onboarding Retry Co",
                "retry@example.com",
                "0240000001",
                "Retail",
                "Basic",
                {
                    "plan_name": "Basic",
                    "amount": 100.0,
                    "currency": "GHS",
                    "duration_months": 1,
                    "duration_days": 0,
                    "configured": True,
                },
                "HF003ONB01",
            )
        self.assertTrue(result["ok"])
        trial_mock.assert_called_once()
        self.assertEqual(trial_mock.call_args.kwargs.get("correlation_id"), "HF003ONB01")
        self.assertTrue((result.get("payment_result") or {}).get("ok"))

    def test_onboarding_stage_d_passes_correlation_id_to_trial_subscription(self):
        source = inspect.getsource(self.modules._execute_onboarding_submit_workflow)
        self.assertIn("correlation_id=correlation_id", source)

    def test_db_sequence_failure_customer_message_is_safe_not_paystack(self):
        fake_conn = mock.MagicMock()
        fake_conn.execute.return_value.fetchone.return_value = None
        sequence_error = _FakeUniqueViolation(
            'duplicate key value violates unique constraint "company_subscriptions_pkey" DETAIL: Key (id)=(5) already exists.'
        )
        with mock.patch.object(self.modules, "get_connection", return_value=fake_conn), mock.patch.object(
            self.modules,
            "get_subscription_plan",
            return_value={
                "plan_name": "Basic",
                "amount": 100.0,
                "currency": "GHS",
                "duration_months": 1,
                "duration_days": 0,
                "configured": True,
            },
        ), mock.patch.object(
            self.modules,
            "ensure_company_trial_subscription",
            side_effect=sequence_error,
        ):
            result = self.modules._execute_onboarding_submit_workflow(
                "Sequence Fail Co",
                "fail@example.com",
                "0240000002",
                "Retail",
                "Basic",
                {
                    "plan_name": "Basic",
                    "amount": 100.0,
                    "currency": "GHS",
                    "duration_months": 1,
                    "duration_days": 0,
                    "configured": True,
                },
                "HF003FAIL1",
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "stage_d_ensure_company_trial_subscription")
        self.assertIn("Support Code: HF003FAIL1", result["customer_message"])
        self.assertNotIn("PAYSTACK", result["customer_message"].upper())
        self.assertNotIn("secret key", result["customer_message"].lower())
        self.assertNotIn("Traceback", result["customer_message"])


if __name__ == "__main__":
    import unittest

    unittest.main()
