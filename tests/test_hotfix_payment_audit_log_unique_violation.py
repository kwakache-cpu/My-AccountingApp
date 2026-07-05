import importlib
import sqlite3
from datetime import date
from unittest import mock

from test_support import ERPIsolatedTestCase


class HotfixSystemLogEventTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_log_system_event_survives_duplicate_event_key(self):
        with mock.patch.object(
            self.database,
            "execute_portable_write",
            side_effect=sqlite3.IntegrityError("UNIQUE constraint failed: system_logs.event_id"),
        ):
            self.modules.log_system_event("INFO", "Payments", "duplicate event probe")
        self.modules.log_system_event("INFO", "Payments", "duplicate event probe follow-up")

    def test_log_system_event_generates_unique_event_ids(self):
        first = self.database.generate_collision_safe_event_id("SYS")
        second = self.database.generate_collision_safe_event_id("SYS")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("SYS-"))
        self.assertTrue(second.startswith("SYS-"))

    def test_persist_system_log_event_uses_ephemeral_postgres_connection(self):
        fake_conn = mock.MagicMock()
        fake_conn.commit.return_value = None
        fake_conn.close.return_value = None
        with mock.patch.object(self.database, "is_postgres_backend", return_value=True), mock.patch.object(
            self.database,
            "_open_postgres_connection",
            return_value=fake_conn,
        ) as open_conn, mock.patch.object(
            self.database,
            "get_connection",
            return_value=mock.MagicMock(name="session_conn"),
        ), mock.patch.object(
            self.database,
            "db_table_exists",
            return_value=True,
        ), mock.patch.object(
            self.database,
            "get_cached_table_column_names",
            return_value={"timestamp", "level", "module_name", "message", "event_id"},
        ), mock.patch.object(
            self.database,
            "execute_portable_write",
        ):
            result = self.database.persist_system_log_event("INFO", "Payments", "ephemeral probe")
        self.assertTrue(result)
        open_conn.assert_called_once()
        fake_conn.commit.assert_called_once()
        fake_conn.close.assert_called_once()

    def test_persist_system_log_event_inserts_with_event_id(self):
        self.database.persist_system_log_event("INFO", "Payments", "sqlite insert probe")
        row = self.conn.execute(
            "SELECT level, module_name, message, event_id FROM system_logs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["level"], "INFO")
        self.assertEqual(row["module_name"], "Payments")
        self.assertTrue(str(row["event_id"] or "").startswith("SYS-"))


class HotfixPaymentWriteIsolationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def _insert_customer_receipt(self, customer_id, amount=95.0):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, customer_id, supplier_id,
                    amount, currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 7, 4).isoformat(),
                "Customer Receipt",
                "Posted",
                customer_id,
                None,
                amount,
                "Cash",
                "HOTFIX-RCPT",
                "Posted",
                "Bookkeeper",
            ),
        )
        return self.database.get_inserted_id(cursor)

    def test_failed_system_log_does_not_block_payment_commit(self):
        customer_id = self.create_customer("Hotfix Customer")
        payment_id = self._insert_customer_receipt(customer_id)
        with mock.patch.object(
            self.database,
            "persist_system_log_event",
            return_value=False,
        ):
            self.modules.log_system_event("INFO", "Payments", "should fail safely")
        self.commit()
        row = self.conn.execute(
            "SELECT customer_id, amount FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        self.assertEqual(float(row["amount"]), 95.0)

    def test_supplier_payment_identity_preserved_when_log_system_event_fails(self):
        supplier_id = self.create_supplier("Hotfix Supplier")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, customer_id, supplier_id,
                    amount, currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 7, 4).isoformat(),
                "Supplier Payment",
                "Posted",
                None,
                supplier_id,
                55.0,
                "Bank",
                "HOTFIX-SUP",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        with mock.patch.object(
            self.database,
            "persist_system_log_event",
            side_effect=Exception("duplicate key value violates unique constraint system_logs_pkey"),
        ):
            self.modules.log_system_event("INFO", "Payments", "supplier payment log probe")
        self.commit()
        row = self.conn.execute(
            "SELECT supplier_id, amount FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["supplier_id"]), supplier_id)
        self.assertEqual(float(row["amount"]), 55.0)

    def test_real_payment_write_failure_still_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO payments (
                    payment_date, payment_type, status, amount, currency, method,
                    reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """,
                (
                    date(2026, 7, 4).isoformat(),
                    "Customer Receipt",
                    "Posted",
                    50.0,
                    "Cash",
                    "BAD-WRITE",
                    "Posted",
                    "Bookkeeper",
                ),
            )


class HotfixAuditEventIdTests(ERPIsolatedTestCase):
    def test_audit_event_ids_are_collision_safe(self):
        first = self.database.generate_collision_safe_event_id("AUD")
        second = self.database.generate_collision_safe_event_id("AUD")
        self.assertNotEqual(first, second)

    def test_log_audit_action_survives_duplicate_event_id(self):
        with mock.patch.object(
            self.database,
            "generate_collision_safe_event_id",
            return_value="AUD-fixed-duplicate",
        ), mock.patch.object(
            self.database,
            "execute_portable_write",
            side_effect=[None, sqlite3.IntegrityError("UNIQUE constraint failed: audit_logs.event_id")],
        ):
            self.database.log_audit_action(
                self.conn,
                self.company_key,
                "Bookkeeper",
                "Customer Receipt Posted",
                "Payments",
                details="first",
                action_type="post",
                document_ref="1",
            )
            self.database.log_audit_action(
                self.conn,
                self.company_key,
                "Bookkeeper",
                "Customer Receipt Posted",
                "Payments",
                details="second",
                action_type="post",
                document_ref="2",
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
