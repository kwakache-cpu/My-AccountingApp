from datetime import datetime, timedelta
from unittest import mock

from test_support import ERPIsolatedTestCase


class CompanySubscriptionDmlPortabilityTests(ERPIsolatedTestCase):
    def test_trial_subscription_creation_still_works(self):
        today = datetime.now().date()
        result = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key="TRIALCO-1",
            company_name="Trial Co 1",
            contact_email="trial1@example.com",
            trial_days=5,
        )
        self.assertTrue(result["days_left"] == 5)
        self.conn.commit()

        company_row = self.conn.execute(
            "SELECT key, contact_email FROM companies WHERE key = ?",
            ("TRIALCO-1",),
        ).fetchone()
        self.assertIsNotNone(company_row)
        self.assertEqual(company_row[0], "TRIALCO-1")
        self.assertEqual(company_row[1], "trial1@example.com")

        sub_row = self.conn.execute(
            "SELECT company_key, plan_name, status, start_date, end_date FROM company_subscriptions WHERE company_key = ?",
            ("TRIALCO-1",),
        ).fetchone()
        self.assertIsNotNone(sub_row)
        self.assertEqual(sub_row["plan_name"], "Trial")
        self.assertEqual(sub_row["status"], "trial")

        # Deterministic within the function call: end_date is today + trial_days.
        expected_end = today + timedelta(days=5)
        self.assertEqual(sub_row["end_date"], expected_end.isoformat())

    def test_existing_trial_subscription_does_not_duplicate(self):
        key = "TRIALCO-2"

        first = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=key,
            company_name="Trial Co 2",
            contact_email="t2a@example.com",
            trial_days=5,
        )
        self.assertEqual(first["days_left"], 5)

        second = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=key,
            company_name="Trial Co 2",
            contact_email="t2a@example.com",
            trial_days=7,
        )
        self.assertEqual(second["days_left"], 7)

        self.conn.commit()

        company_count = self.conn.execute("SELECT COUNT(*) FROM companies WHERE key = ?", (key,)).fetchone()[0]
        self.assertEqual(int(company_count), 1)

        sub_count = self.conn.execute(
            "SELECT COUNT(*) FROM company_subscriptions WHERE company_key = ?",
            (key,),
        ).fetchone()[0]
        self.assertEqual(int(sub_count), 1)

    def test_subscription_metadata_update_still_works(self):
        key = "TRIALCO-3"

        first_today = datetime.now().date()
        first = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=key,
            company_name="Trial Co 3",
            contact_email="old-email@example.com",
            trial_days=4,
        )
        self.assertEqual(first["days_left"], 4)

        expected_end_first = first_today + timedelta(days=4)

        self.conn.commit()

        before_contact = self.conn.execute(
            "SELECT contact_email FROM companies WHERE key = ?",
            (key,),
        ).fetchone()[0]
        self.assertEqual(before_contact, "old-email@example.com")

        before_end = self.conn.execute(
            "SELECT end_date FROM company_subscriptions WHERE company_key = ?",
            (key,),
        ).fetchone()[0]
        self.assertEqual(before_end, expected_end_first.isoformat())

        second_today = datetime.now().date()
        second = self.database.ensure_company_trial_subscription(
            self.conn,
            company_key=key,
            company_name="Trial Co 3",
            contact_email="new-email@example.com",
            trial_days=9,
        )
        self.assertEqual(second["days_left"], 9)
        self.conn.commit()

        after_contact = self.conn.execute(
            "SELECT contact_email FROM companies WHERE key = ?",
            (key,),
        ).fetchone()[0]
        self.assertEqual(after_contact, "new-email@example.com")

        expected_end_second = second_today + timedelta(days=9)
        after_end = self.conn.execute(
            "SELECT end_date FROM company_subscriptions WHERE company_key = ?",
            (key,),
        ).fetchone()[0]
        self.assertEqual(after_end, expected_end_second.isoformat())

    def test_get_company_subscription_snapshot_auto_expires_updates_metadata(self):
        key = "TRIALCO-4"
        expired_end = "2026-01-01"

        self.database.create_company_record(
            self.conn,
            company_key=key,
            company_name="Trial Co 4",
            subscription_expiry=expired_end,
            status="Active",
            deployment_status="Trial",
            contact_email="expired@example.com",
            subscription_plan_name="Trial",
            subscription_status="trial",
            subscription_start_date="2025-12-01",
            subscription_end_date=expired_end,
        )
        self.conn.commit()

        with mock.patch.object(
            self.database, "execute_portable_write", wraps=self.database.execute_portable_write
        ) as portable:
            snapshot = self.database.get_company_subscription_snapshot(
                key, conn=self.conn, as_of=datetime.now().date().isoformat()
            )

        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["status"], "expired")
        self.assertFalse(snapshot["access_allowed"])
        self.assertTrue(snapshot["renewal_required"])

        sub_row = self.conn.execute(
            "SELECT status FROM company_subscriptions WHERE company_key = ?",
            (key,),
        ).fetchone()
        self.assertIsNotNone(sub_row)
        self.assertEqual(sub_row["status"], "expired")

        company_row = self.conn.execute(
            "SELECT subscription_expiry FROM companies WHERE key = ?",
            (key,),
        ).fetchone()
        self.assertIsNotNone(company_row)
        self.assertEqual(company_row["subscription_expiry"], expired_end)

        sqls = [str(call.args[1]) for call in portable.call_args_list]
        self.assertTrue(any("UPDATE company_subscriptions" in sql for sql in sqls))
        self.assertTrue(any("UPDATE companies SET subscription_expiry" in sql for sql in sqls))

    def test_postgres_placeholder_conversion_occurs_via_fake_connection(self):
        captured = {"statements": [], "params": [], "commits": 0}

        class _FakeConn:
            def execute(self, statement, params=()):
                captured["statements"].append(statement)
                captured["params"].append(params)
                return object()

            def commit(self):
                captured["commits"] += 1

        fake = _FakeConn()
        with mock.patch.object(self.database, "get_active_db_backend", return_value="postgres"):
            self.database.create_company_record(
                fake,
                company_key="PGTRIALCO-1",
                company_name="PG Trial Co 1",
                subscription_expiry="2026-12-31",
                status="Active",
                deployment_status="Trial",
                contact_email="pg@example.com",
                subscription_plan_name="Trial",
                subscription_status="trial",
                subscription_start_date="2026-06-01",
                subscription_end_date="2026-06-06",
            )

        self.assertEqual(captured["commits"], 0, "Helper must not commit automatically.")
        joined_sql = "\n".join(str(s) for s in captured["statements"])
        self.assertIn("%s", joined_sql)
        self.assertNotIn("?", joined_sql)

        self.assertTrue(any("INSERT INTO companies" in str(s) for s in captured["statements"]))
        self.assertTrue(any("INSERT INTO company_subscriptions" in str(s) for s in captured["statements"]))

