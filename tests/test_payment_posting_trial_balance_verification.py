"""
Verify customer receipt and supplier payment journal posting matches financials.py paths
and that Trial Balance aggregates reflect payment credits/debits correctly.
"""
import importlib
from datetime import date
from unittest import mock

from test_support import ERPIsolatedTestCase, build_lines, find_trial_balance_row


class PaymentPostingTrialBalanceVerificationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.financials = importlib.import_module("financials")
        self.modules = importlib.import_module("modules")

    def _journal_lines_for_payment(self, payment_id):
        entry = self.conn.execute(
            """
            SELECT id FROM journal_entries
            WHERE company_key = ? AND source_table = 'payments' AND source_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (self.company_key, int(payment_id)),
        ).fetchone()
        self.assertIsNotNone(entry, msg="Expected journal entry linked to payment")
        return self.conn.execute(
            """
            SELECT
                COALESCE(c.name, c.account_name) AS account_name,
                COALESCE(c.type, c.category, c.account_type) AS account_type,
                jl.debit,
                jl.credit
            FROM journal_lines jl
            JOIN chart_of_accounts c ON c.id = jl.account_id
            WHERE jl.entry_id = ?
            ORDER BY jl.id
            """,
            (int(entry["id"]),),
        ).fetchall()

    def _line_for_account(self, lines, account_name):
        for row in lines:
            if str(row["account_name"]) == account_name:
                return row
        return None

    def _post_customer_receipt_like_financials(self, customer_id, amount, payment_method="Cash"):
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
                date(2026, 7, 5).isoformat(),
                "Customer Receipt",
                "Posted",
                customer_id,
                None,
                float(amount),
                payment_method,
                "VERIFY-RCPT",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        cash_account = self.financials._payment_method_account_name(payment_method)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 5),
            description="Customer receipt - verify",
            reference="VERIFY-RCPT",
            lines=build_lines(
                {
                    "account_id": self.engine.get_account_id(self.conn, cash_account, "Asset"),
                    "debit": float(amount),
                    "credit": 0.0,
                },
                {
                    "account_id": self.engine.get_account_id(self.conn, "Accounts Receivable", "Asset"),
                    "debit": 0.0,
                    "credit": float(amount),
                },
            ),
            created_by="Bookkeeper",
            branch_id=None,
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

    def _post_supplier_payment_like_financials(self, supplier_id, amount, payment_method="Cash"):
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
                date(2026, 7, 5).isoformat(),
                "Supplier Payment",
                "Posted",
                None,
                supplier_id,
                float(amount),
                payment_method,
                "VERIFY-SUP",
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        cash_account = self.financials._payment_method_account_name(payment_method)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 5),
            description="Supplier payment - verify",
            reference="VERIFY-SUP",
            lines=build_lines(
                {
                    "account_id": self.engine.get_account_id(self.conn, "Accounts Payable", "Liability"),
                    "debit": float(amount),
                    "credit": 0.0,
                },
                {
                    "account_id": self.engine.get_account_id(self.conn, cash_account, "Asset"),
                    "debit": 0.0,
                    "credit": float(amount),
                },
            ),
            created_by="Bookkeeper",
            branch_id=None,
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

    def test_customer_receipt_debits_cash_and_credits_accounts_receivable(self):
        customer_id = self.create_customer("Verify AR Customer")
        amount = 175.0
        payment_id = self._post_customer_receipt_like_financials(customer_id, amount, payment_method="Cash")
        payment_row = self.conn.execute(
            "SELECT customer_id, supplier_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(payment_row["customer_id"]), customer_id)
        self.assertIsNone(payment_row["supplier_id"])
        lines = self._journal_lines_for_payment(payment_id)
        cash_line = self._line_for_account(lines, "Cash")
        ar_line = self._line_for_account(lines, "Accounts Receivable")
        self.assertIsNotNone(cash_line)
        self.assertIsNotNone(ar_line)
        self.assertEqual(float(cash_line["debit"]), amount)
        self.assertEqual(float(cash_line["credit"]), 0.0)
        self.assertEqual(str(cash_line["account_type"]).title(), "Asset")
        self.assertEqual(float(ar_line["debit"]), 0.0)
        self.assertEqual(float(ar_line["credit"]), amount)
        self.assertEqual(str(ar_line["account_type"]).title(), "Asset")

    def test_customer_receipt_bank_method_debits_bank_account(self):
        customer_id = self.create_customer("Verify Bank Customer")
        payment_id = self._post_customer_receipt_like_financials(customer_id, 90.0, payment_method="Bank")
        lines = self._journal_lines_for_payment(payment_id)
        bank_line = self._line_for_account(lines, "Bank")
        ar_line = self._line_for_account(lines, "Accounts Receivable")
        self.assertIsNotNone(bank_line)
        self.assertEqual(float(bank_line["debit"]), 90.0)
        self.assertEqual(float(ar_line["credit"]), 90.0)

    def test_supplier_payment_debits_ap_and_credits_cash(self):
        supplier_id = self.create_supplier("Verify AP Supplier")
        amount = 125.0
        payment_id = self._post_supplier_payment_like_financials(supplier_id, amount)
        payment_row = self.conn.execute(
            "SELECT customer_id, supplier_id FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertIsNone(payment_row["customer_id"])
        self.assertEqual(int(payment_row["supplier_id"]), supplier_id)
        lines = self._journal_lines_for_payment(payment_id)
        ap_line = self._line_for_account(lines, "Accounts Payable")
        cash_line = self._line_for_account(lines, "Cash")
        self.assertIsNotNone(ap_line)
        self.assertIsNotNone(cash_line)
        self.assertEqual(float(ap_line["debit"]), amount)
        self.assertEqual(float(ap_line["credit"]), 0.0)
        self.assertEqual(str(ap_line["account_type"]).title(), "Liability")
        self.assertEqual(float(cash_line["debit"]), 0.0)
        self.assertEqual(float(cash_line["credit"]), amount)

    def test_trial_balance_reflects_customer_receipt_credit_to_ar(self):
        customer_id = self.create_customer("TB AR Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, amount=400.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 400.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 400.0},
            ),
            source_table="invoices",
            source_id=invoice_id,
            customer_id=customer_id,
        )
        before = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        before_credit = float(before["credit_total"] if before else 0.0)
        receipt_amount = 150.0
        self._post_customer_receipt_like_financials(customer_id, receipt_amount)
        after = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        self.assertIsNotNone(after)
        self.assertAlmostEqual(float(after["credit_total"]), before_credit + receipt_amount, places=2)
        self.assertAlmostEqual(float(after["debit_total"]), 400.0, places=2)
        self.assertAlmostEqual(float(after["balance"]), 250.0, places=2)

    def test_trial_balance_reflects_supplier_payment_debit_to_ap(self):
        supplier_id = self.create_supplier("TB AP Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, amount=300.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 300.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 300.0},
            ),
            source_table="bills",
            source_id=bill_id,
            supplier_id=supplier_id,
        )
        before = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Payable")
        before_debit = float(before["debit_total"] if before else 0.0)
        payment_amount = 80.0
        self._post_supplier_payment_like_financials(supplier_id, payment_amount)
        after = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Payable")
        self.assertIsNotNone(after)
        self.assertAlmostEqual(float(after["debit_total"]), before_debit + payment_amount, places=2)

    def test_audit_log_failure_does_not_rollback_posted_payment(self):
        customer_id = self.create_customer("Audit Isolation Customer")
        payment_id = self._post_customer_receipt_like_financials(customer_id, 60.0)
        with mock.patch.object(
            self.database,
            "persist_system_log_event",
            side_effect=Exception("duplicate key value violates unique constraint system_logs_pkey"),
        ):
            self.modules.log_system_event("INFO", "Payments", "isolated audit probe")
        row = self.conn.execute(
            "SELECT customer_id, amount FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(row["customer_id"]), customer_id)
        lines = self._journal_lines_for_payment(payment_id)
        ar_line = self._line_for_account(lines, "Accounts Receivable")
        self.assertEqual(float(ar_line["credit"]), 60.0)


if __name__ == "__main__":
    import unittest

    unittest.main()
