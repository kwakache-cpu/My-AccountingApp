import importlib
from datetime import date
from unittest import mock

import pandas as pd

from test_support import ERPIsolatedTestCase, build_lines, find_trial_balance_row


class PaymentFormResetHelperTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.financials = importlib.import_module("financials")
        self.modules = importlib.import_module("modules")

    def test_form_widget_key_changes_after_reset(self):
        counter_key = "receive_payment_form_reset_TESTCO"
        with mock.patch.object(self.financials.st, "session_state", {"receive_payment_form_reset_TESTCO": 0}, create=True):
            first = self.modules._form_widget_key("receive_payment_amount_TESTCO", counter_key)
            self.modules._increment_form_reset(counter_key)
            second = self.modules._form_widget_key("receive_payment_amount_TESTCO", counter_key)
        self.assertNotEqual(first, second)
        self.assertTrue(first.endswith("_0"))
        self.assertTrue(second.endswith("_1"))

    def test_payment_flash_session_helpers(self):
        with mock.patch.object(self.financials.st, "session_state", {}, create=True) as session_state:
            self.financials._set_payment_flash(self.company_key, "customer_receipt", "Customer receipt saved successfully.")
            flash_key = self.financials._payment_flash_session_key(self.company_key, "customer_receipt")
            self.assertEqual(session_state[flash_key], "Customer receipt saved successfully.")
            with mock.patch.object(self.financials.st, "success") as success_mock:
                self.financials._render_payment_flash(self.company_key, "customer_receipt")
                success_mock.assert_called_once_with("Customer receipt saved successfully.")
            self.assertNotIn(flash_key, session_state)


class CashBookNumericCoercionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.financials = importlib.import_module("financials")

    def _sample_journal_df(self, debit, credit):
        return pd.DataFrame(
            [
                {
                    "Date": "2026-07-06",
                    "Entry ID": 1,
                    "Description": "Cash movement",
                    "Reference": "CB-1",
                    "Created By": "Bookkeeper",
                    "Account Code": "1000",
                    "Account": "Cash",
                    "Type": "Asset",
                    "Debit (GHS)": debit,
                    "Credit (GHS)": credit,
                }
            ]
        )

    def test_coerce_ledger_money_columns_handles_currency_strings(self):
        df = self._sample_journal_df("GHS 1,250.50", "250.00")
        coerced = self.financials._coerce_ledger_money_columns(df, ["Debit (GHS)", "Credit (GHS)"])
        self.assertEqual(float(coerced.loc[0, "Debit (GHS)"]), 1250.5)
        self.assertEqual(float(coerced.loc[0, "Credit (GHS)"]), 250.0)

    def test_get_cash_book_cumsum_does_not_crash_on_object_dtype(self):
        journal_df = self._sample_journal_df("1,000.00", "GHS 250.00")
        with mock.patch.object(self.financials, "get_general_journal", return_value=journal_df):
            cash_book = self.financials.get_cash_book(self.company_key)
        self.assertFalse(cash_book.empty)
        self.assertEqual(float(cash_book.loc[0, "Movement (GHS)"]), 750.0)
        self.assertEqual(float(cash_book.loc[0, "Account Running Balance (GHS)"]), 750.0)

    def test_get_cash_book_handles_blanks_and_none(self):
        journal_df = self._sample_journal_df(None, "")
        with mock.patch.object(self.financials, "get_general_journal", return_value=journal_df):
            cash_book = self.financials.get_cash_book(self.company_key)
        self.assertFalse(cash_book.empty)
        self.assertEqual(float(cash_book.loc[0, "Movement (GHS)"]), 0.0)

    def test_get_cash_book_empty_journal_returns_columns_without_crash(self):
        with mock.patch.object(self.financials, "get_general_journal", return_value=pd.DataFrame()):
            cash_book = self.financials.get_cash_book(self.company_key)
        self.assertTrue(cash_book.empty)
        self.assertIn("Movement (GHS)", cash_book.columns)


class PaymentPostingAndTrialBalanceTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.financials = importlib.import_module("financials")
        self.modules = importlib.import_module("modules")

    def _post_customer_receipt(self, customer_id, amount, method="Cash"):
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
                date(2026, 7, 6).isoformat(),
                "Customer Receipt",
                "Posted",
                customer_id,
                None,
                float(amount),
                method,
                "FORM-VERIFY",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        cash_account = self.financials._payment_method_account_name(method)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 6),
            description="Customer receipt - verify form",
            reference="FORM-VERIFY",
            lines=build_lines(
                {"account_id": self.engine.get_account_id(self.conn, cash_account, "Asset"), "debit": float(amount), "credit": 0.0},
                {"account_id": self.engine.get_account_id(self.conn, "Accounts Receivable", "Asset"), "debit": 0.0, "credit": float(amount)},
            ),
            created_by="Bookkeeper",
            customer_id=customer_id,
            payment_id=payment_id,
            source_module="Payments",
            source_table="payments",
            source_type="Customer Receipt",
            source_id=payment_id,
            approval_status="Posted",
            conn=self.conn,
        )
        self.commit()
        return payment_id

    def _post_supplier_payment(self, supplier_id, amount):
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
                date(2026, 7, 6).isoformat(),
                "Supplier Payment",
                "Posted",
                None,
                supplier_id,
                float(amount),
                "Cash",
                "FORM-SUP",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 6),
            description="Supplier payment - verify form",
            reference="FORM-SUP",
            lines=build_lines(
                {"account_id": self.engine.get_account_id(self.conn, "Accounts Payable", "Liability"), "debit": float(amount), "credit": 0.0},
                {"account_id": self.engine.get_account_id(self.conn, "Cash", "Asset"), "debit": 0.0, "credit": float(amount)},
            ),
            created_by="Bookkeeper",
            supplier_id=supplier_id,
            payment_id=payment_id,
            source_module="Payments",
            source_table="payments",
            source_type="Supplier Payment",
            source_id=payment_id,
            approval_status="Posted",
            conn=self.conn,
        )
        self.commit()
        return payment_id

    def _journal_lines(self, payment_id):
        entry = self.conn.execute(
            "SELECT id FROM journal_entries WHERE source_table='payments' AND source_id=?",
            (int(payment_id),),
        ).fetchone()
        return self.conn.execute(
            """
            SELECT COALESCE(c.name, c.account_name) AS account_name, jl.debit, jl.credit
            FROM journal_lines jl
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE jl.entry_id = ?
            """,
            (int(entry["id"]),),
        ).fetchall()

    def test_customer_receipt_posts_debit_cash_credit_ar(self):
        customer_id = self.create_customer("Form Verify Customer")
        payment_id = self._post_customer_receipt(customer_id, 250.0)
        row = self.conn.execute("SELECT customer_id, amount FROM payments WHERE id = ?", (payment_id,)).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        self.assertEqual(float(row["amount"]), 250.0)
        lines = {line["account_name"]: line for line in self._journal_lines(payment_id)}
        self.assertEqual(float(lines["Cash"]["debit"]), 250.0)
        self.assertEqual(float(lines["Accounts Receivable"]["credit"]), 250.0)

    def test_supplier_payment_posts_debit_ap_credit_cash(self):
        supplier_id = self.create_supplier("Form Verify Supplier")
        payment_id = self._post_supplier_payment(supplier_id, 180.0)
        row = self.conn.execute("SELECT supplier_id, amount FROM payments WHERE id = ?", (payment_id,)).fetchone()
        self.assertEqual(int(row["supplier_id"]), supplier_id)
        lines = {line["account_name"]: line for line in self._journal_lines(payment_id)}
        self.assertEqual(float(lines["Accounts Payable"]["debit"]), 180.0)
        self.assertEqual(float(lines["Cash"]["credit"]), 180.0)

    def test_trial_balance_reflects_customer_receipt_in_ar_credit_column(self):
        customer_id = self.create_customer("TB Credit Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, amount=500.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 500.0},
            ),
            source_table="invoices",
            source_id=invoice_id,
            customer_id=customer_id,
        )
        before = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        self._post_customer_receipt(customer_id, 250.0)
        after = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        self.assertAlmostEqual(float(after["credit_total"]), float(before["credit_total"]) + 250.0, places=2)
        self.assertAlmostEqual(float(after["balance"]), 250.0, places=2)

    def test_single_save_creates_one_payment_row(self):
        customer_id = self.create_customer("No Duplicate Customer")
        before = self.conn.execute(
            "SELECT COUNT(*) AS c FROM payments WHERE company_key = ? AND payment_type = 'Customer Receipt'",
            (self.company_key,),
        ).fetchone()["c"]
        self._post_customer_receipt(customer_id, 99.0)
        after = self.conn.execute(
            "SELECT COUNT(*) AS c FROM payments WHERE company_key = ? AND payment_type = 'Customer Receipt'",
            (self.company_key,),
        ).fetchone()["c"]
        self.assertEqual(int(after), int(before) + 1)

    def test_audit_log_failure_does_not_rollback_payment(self):
        customer_id = self.create_customer("Audit Safe Customer")
        payment_id = self._post_customer_receipt(customer_id, 60.0)
        with mock.patch.object(
            self.database,
            "persist_system_log_event",
            side_effect=Exception("duplicate key value violates unique constraint system_logs_pkey"),
        ):
            self.modules.log_system_event("INFO", "Payments", "audit isolation probe")
        row = self.conn.execute(
            "SELECT customer_id, amount FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        lines = {line["account_name"]: line for line in self._journal_lines(payment_id)}
        self.assertEqual(float(lines["Accounts Receivable"]["credit"]), 60.0)


if __name__ == "__main__":
    import unittest

    unittest.main()
