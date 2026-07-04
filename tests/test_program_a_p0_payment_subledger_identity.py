import importlib
import inspect
import os
import unittest
from datetime import date
from unittest import mock

from test_support import ERPIsolatedTestCase, build_lines


def _extract_function_block(source_text, function_name):
    marker = f"def {function_name}("
    start = source_text.find(marker)
    if start < 0:
        return ""
    next_def = source_text.find("\ndef ", start + len(marker))
    return source_text[start:] if next_def < 0 else source_text[start:next_def]


class ProgramAP0PaymentIdentityWriteTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")

    def _insert_customer_receipt_like_financials(self, customer_id, amount=120.0):
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
                date(2026, 6, 15).isoformat(),
                "Customer Receipt",
                "Posted",
                customer_id,
                None,
                amount,
                "Cash",
                "RCPT-P0-001",
                "Posted",
                "Bookkeeper",
            ),
        )
        self.commit()
        return self.database.get_inserted_id(cursor)

    def _insert_supplier_payment_like_financials(self, supplier_id, amount=80.0):
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
                date(2026, 6, 16).isoformat(),
                "Supplier Payment",
                "Posted",
                None,
                supplier_id,
                amount,
                "Bank",
                "SUP-P0-001",
                "Posted",
                "Bookkeeper",
            ),
        )
        self.commit()
        return self.database.get_inserted_id(cursor)

    def test_customer_payment_stores_customer_id(self):
        customer_id = self.create_customer("P0 Customer")
        payment_id = self._insert_customer_receipt_like_financials(customer_id)
        row = self.conn.execute(
            "SELECT customer_id, supplier_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        self.assertIsNone(row["supplier_id"])

    def test_supplier_payment_stores_supplier_id(self):
        supplier_id = self.create_supplier("P0 Supplier")
        payment_id = self._insert_supplier_payment_like_financials(supplier_id)
        row = self.conn.execute(
            "SELECT customer_id, supplier_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertIsNone(row["customer_id"])
        self.assertEqual(int(row["supplier_id"]), supplier_id)


class ProgramAP0PaymentIdentityReadTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.database = importlib.import_module("database")

    def test_resolve_prefers_payment_row_customer_id(self):
        customer_a = self.create_customer("Resolve A")
        customer_b = self.create_customer("Resolve B")
        payment_id = self.create_payment(
            payment_type="Customer Receipt",
            customer_id=customer_a,
            amount=50.0,
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 50.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 50.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Receipt",
            customer_id=customer_b,
            payment_id=payment_id,
        )
        payment_row = self.conn.execute(
            "SELECT * FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        resolved = self.database.resolve_payment_party_identity(self.conn, payment_row)
        self.assertEqual(resolved["customer_id"], customer_a)
        self.assertEqual(resolved["customer_source"], "payment")

    def test_resolve_falls_back_to_journal_for_legacy_payment(self):
        customer_id = self.create_customer("Legacy Customer")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 5, 1).isoformat(),
                "Customer Receipt",
                "Posted",
                40.0,
                "Cash",
                "LEGACY-RCPT",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.commit()
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 40.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 40.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Receipt",
            customer_id=customer_id,
            payment_id=payment_id,
        )
        payment_row = self.conn.execute(
            "SELECT * FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertIsNone(payment_row["customer_id"])
        resolved = self.database.resolve_payment_party_identity(self.conn, payment_row)
        self.assertEqual(resolved["customer_id"], customer_id)
        self.assertEqual(resolved["customer_source"], "linked")

    def test_legacy_payment_without_payment_id_still_appears_in_ar_aging(self):
        customer_id = self.create_customer("Aging Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, amount=200.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 200.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Revenue"), "debit": 0.0, "credit": 200.0},
            ),
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
        )
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 6, 20).isoformat(),
                "Customer Receipt",
                "Posted",
                50.0,
                "Cash",
                "LEGACY-PARTIAL",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.commit()
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 50.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 50.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Receipt",
            customer_id=customer_id,
            payment_id=payment_id,
        )
        aging_rows = self.engine.get_ar_aging_report(self.company_key, as_of_date=date(2026, 6, 30))
        customer_rows = [row for row in aging_rows if row.get("customer_name") == "Aging Customer"]
        self.assertTrue(customer_rows)
        total_remaining = round(sum(float(row.get("remaining_balance", 0.0) or 0.0) for row in customer_rows), 2)
        self.assertAlmostEqual(total_remaining, 150.0, places=2)


class ProgramAP0PaymentBackfillTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")

    def test_backfill_populates_customer_id_from_journal(self):
        customer_id = self.create_customer("Backfill Customer")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 4, 10).isoformat(),
                "Customer Receipt",
                "Posted",
                65.0,
                "Cash",
                "BF-RCPT",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.commit()
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 65.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 65.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Receipt",
            customer_id=customer_id,
            payment_id=payment_id,
        )
        stats = self.database.backfill_payments_party_identity(self.conn, company_key=self.company_key)
        self.commit()
        row = self.conn.execute(
            "SELECT customer_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        self.assertEqual(stats["customer_updated"], 1)
        repeat = self.database.backfill_payments_party_identity(self.conn, company_key=self.company_key)
        self.assertEqual(repeat["customer_updated"], 0)

    def test_backfill_skips_ambiguous_customer_matches(self):
        customer_a = self.create_customer("Ambiguous A")
        customer_b = self.create_customer("Ambiguous B")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 4, 11).isoformat(),
                "Customer Receipt",
                "Posted",
                30.0,
                "Cash",
                "BF-AMB",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.commit()
        for customer_id in (customer_a, customer_b):
            self.conn.execute(
                """
                INSERT INTO journal_entries (
                    company_key, date, description, reference, created_by,
                    customer_id, payment_id, source_table, source_id, source_type, approval_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'payments', ?, 'Customer Receipt', 'Posted')
                """,
                (
                    self.company_key,
                    date(2026, 4, 11).isoformat(),
                    f"Ambiguous journal {customer_id}",
                    f"AMB-{customer_id}",
                    "Bookkeeper",
                    customer_id,
                    payment_id,
                    payment_id,
                ),
            )
        self.commit()
        stats = self.database.backfill_payments_party_identity(self.conn, company_key=self.company_key)
        row = self.conn.execute(
            "SELECT customer_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertIsNone(row["customer_id"])
        self.assertEqual(stats["customer_skipped_ambiguous"], 1)


class ProgramAP0PaymentSchemaSafetyTests(unittest.TestCase):
    def test_payments_party_identity_schema_integrity_is_idempotent(self):
        database = importlib.import_module("database")
        conn = mock.MagicMock()
        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", return_value={"customer_id", "supplier_id", "amount"}):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    first = database.ensure_payments_party_identity_schema_integrity(conn)
                    second = database.ensure_payments_party_identity_schema_integrity(conn)
        self.assertTrue(first["customer_id_column_present"])
        self.assertTrue(first["supplier_id_column_present"])
        self.assertFalse(first["customer_id_column_added"])
        self.assertFalse(first["supplier_id_column_added"])
        self.assertTrue(second["customer_id_column_present"])
        conn.execute.assert_not_called()

    def test_postgres_schema_ensure_uses_if_not_exists(self):
        database = importlib.import_module("database")
        conn = mock.MagicMock()
        with mock.patch.object(database, "db_table_exists", return_value=True):
            with mock.patch.object(database, "_get_existing_columns", return_value={"amount"}):
                with mock.patch.object(database, "get_active_db_backend", return_value="postgres"):
                    with mock.patch.object(database, "execute_portable_write") as write_mock:
                        database.ensure_payments_party_identity_schema_integrity(conn)
        sql_calls = [call.args[1] for call in write_mock.call_args_list]
        self.assertTrue(any("ADD COLUMN IF NOT EXISTS customer_id" in sql for sql in sql_calls))
        self.assertTrue(any("ADD COLUMN IF NOT EXISTS supplier_id" in sql for sql in sql_calls))

    def test_financials_payment_pages_have_no_ddl(self):
        financials_path = os.path.join(os.getcwd(), "financials.py")
        with open(financials_path, encoding="utf-8") as handle:
            content = handle.read()
        for function_name in ("show_receive_payment_page", "show_supplier_payment_page"):
            block = _extract_function_block(content, function_name)
            for forbidden in ("ALTER TABLE", "ADD COLUMN", "CREATE INDEX", "CREATE TABLE"):
                self.assertNotIn(forbidden, block, msg=f"{function_name} must not run DDL")


class ProgramAP0PaymentRegressionCompatibilityTests(ERPIsolatedTestCase):
    def test_startup_integrity_includes_payments_party_columns(self):
        columns = self.database._get_existing_columns(self.conn, "payments")
        self.assertIn("customer_id", columns)
        self.assertIn("supplier_id", columns)
        result = self.database.ensure_payments_party_identity_schema_integrity(self.conn)
        self.assertTrue(result["customer_id_column_present"])
        self.assertTrue(result["supplier_id_column_present"])


if __name__ == "__main__":
    unittest.main()
