"""
Hotfix verification: payment journal posting, duplicate guards, trial balance presentation,
and account code integrity.
"""
import importlib
from datetime import date
from unittest import mock

import pandas as pd

from test_support import ERPIsolatedTestCase, build_lines, find_trial_balance_row


class PaymentLedgerTrialBalanceVerificationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.financials = importlib.import_module("financials")

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
                COALESCE(NULLIF(c.code, ''), NULLIF(c.account_code, ''), '') AS account_code,
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

    def _post_customer_receipt(self, customer_id, amount, reference="HOTFIX-RCPT", payment_method="Cash"):
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
                payment_method,
                reference,
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        cash_account = self.financials._payment_method_account_name(payment_method)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 6),
            description="Customer receipt - hotfix verify",
            reference=reference,
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

    def _post_supplier_payment(self, supplier_id, amount, reference="HOTFIX-SUP", payment_method="Cash"):
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
                payment_method,
                reference,
                "Posted",
                "Bookkeeper",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        cash_account = self.financials._payment_method_account_name(payment_method)
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=date(2026, 7, 6),
            description="Supplier payment - hotfix verify",
            reference=reference,
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

    def test_customer_receipt_creates_one_payment_one_entry_two_lines(self):
        customer_id = self.create_customer("Hotfix Receipt Customer")
        payment_id = self._post_customer_receipt(customer_id, 88.0)
        payment_rows = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(payment_rows["row_count"]), 1)
        self.assertEqual(self.journal_count("payments", payment_id), 1)
        lines = self._journal_lines_for_payment(payment_id)
        self.assertEqual(len(lines), 2)
        cash_line = self._line_for_account(lines, "Cash")
        ar_line = self._line_for_account(lines, "Accounts Receivable")
        self.assertEqual(float(cash_line["debit"]), 88.0)
        self.assertEqual(float(ar_line["credit"]), 88.0)

    def test_supplier_payment_creates_one_payment_one_entry_two_lines(self):
        supplier_id = self.create_supplier("Hotfix Supplier")
        payment_id = self._post_supplier_payment(supplier_id, 66.0)
        payment_rows = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(int(payment_rows["row_count"]), 1)
        self.assertEqual(self.journal_count("payments", payment_id), 1)
        lines = self._journal_lines_for_payment(payment_id)
        self.assertEqual(len(lines), 2)
        ap_line = self._line_for_account(lines, "Accounts Payable")
        cash_line = self._line_for_account(lines, "Cash")
        self.assertEqual(float(ap_line["debit"]), 66.0)
        self.assertEqual(float(cash_line["credit"]), 66.0)

    def test_trial_balance_ar_credit_increases_after_customer_receipt(self):
        customer_id = self.create_customer("TB Receipt Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, amount=220.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 220.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 220.0},
            ),
            source_table="invoices",
            source_id=invoice_id,
            customer_id=customer_id,
        )
        before = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        before_credit = float(before["credit_total"] if before else 0.0)
        self._post_customer_receipt(customer_id, 70.0, reference="TB-RCPT")
        after = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Receivable")
        self.assertAlmostEqual(float(after["credit_total"]), before_credit + 70.0, places=2)

    def test_trial_balance_ap_debit_increases_after_supplier_payment(self):
        supplier_id = self.create_supplier("TB Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, amount=180.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 180.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 180.0},
            ),
            source_table="bills",
            source_id=bill_id,
            supplier_id=supplier_id,
        )
        before = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Payable")
        before_debit = float(before["debit_total"] if before else 0.0)
        self._post_supplier_payment(supplier_id, 45.0, reference="TB-SUP")
        after = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Accounts Payable")
        self.assertAlmostEqual(float(after["debit_total"]), before_debit + 45.0, places=2)

    def test_recent_duplicate_payment_detected_by_fingerprint(self):
        customer_id = self.create_customer("Duplicate Guard Customer")
        payment_date = date(2026, 7, 6)
        payment_id = self._post_customer_receipt(customer_id, 55.0, reference="DUP-GUARD")
        duplicate_id = self.financials._find_recent_duplicate_payment(
            self.conn,
            self.company_key,
            "Customer Receipt",
            "customer_id",
            customer_id,
            55.0,
            payment_date,
            "DUP-GUARD",
            "Bookkeeper",
            method="Cash",
        )
        self.assertEqual(int(duplicate_id), int(payment_id))

    def test_session_submit_guard_blocks_repeat_fingerprint(self):
        customer_id = self.create_customer("Session Guard Customer")
        fingerprint = self.financials._payment_fingerprint(
            "Customer Receipt",
            customer_id,
            40.0,
            date(2026, 7, 6),
            "SESSION-GUARD",
            "Bookkeeper",
            "Cash",
        )
        with mock.patch.object(self.financials.st, "session_state", {}, create=True) as session_state:
            blocked_first, _ = self.financials._payment_duplicate_blocked(
                self.company_key,
                "customer_receipt",
                self.conn,
                fingerprint,
                "Customer Receipt",
                "customer_id",
                customer_id,
                40.0,
                date(2026, 7, 6),
                "SESSION-GUARD",
                "Bookkeeper",
                "Cash",
            )
            self.assertFalse(blocked_first)
            blocked_second, message = self.financials._payment_duplicate_blocked(
                self.company_key,
                "customer_receipt",
                self.conn,
                fingerprint,
                "Customer Receipt",
                "customer_id",
                customer_id,
                40.0,
                date(2026, 7, 6),
                "SESSION-GUARD",
                "Bookkeeper",
                "Cash",
            )
            self.assertTrue(blocked_second)
            self.assertIn("session", message.lower())
            self.assertIn(self.financials._payment_submit_guard_key(self.company_key, "customer_receipt"), session_state)

    def test_trial_balance_displays_account_code_when_present(self):
        cash_id = self.account_id("Cash", "Asset")
        self.conn.execute(
            "UPDATE chart_of_accounts SET code = ?, account_code = ? WHERE id = ?",
            ("1000", "1000", cash_id),
        )
        self.commit()
        self._post_customer_receipt(self.create_customer("Code Display Customer"), 10.0, reference="CODE-DISP")
        balances = {
            "Cash": {
                "account_code": "1000",
                "account_type": "Asset",
                "debit": 10.0,
                "credit": 0.0,
                "balance": 10.0,
            }
        }
        tb_df = self.financials._trial_balance_from_balances(balances)
        self.assertEqual(str(tb_df.loc[0, "Account Code"]), "1000")

    def test_trial_balance_shows_em_dash_when_account_code_missing(self):
        balances = {
            "Misc Account": {
                "account_code": "",
                "account_type": "Expense",
                "debit": 5.0,
                "credit": 0.0,
                "balance": 5.0,
            }
        }
        tb_df = self.financials._trial_balance_from_balances(balances)
        self.assertEqual(str(tb_df.loc[0, "Account Code"]), "—")

    def test_backfill_default_account_codes_only_fills_blank_known_accounts(self):
        cash_id = self.account_id("Cash", "Asset")
        self.conn.execute(
            "UPDATE chart_of_accounts SET code = NULL, account_code = NULL WHERE id = ?",
            (cash_id,),
        )
        self.commit()
        stats = self.engine.backfill_default_account_codes(self.conn, dry_run=False)
        self.commit()
        row = self.conn.execute(
            "SELECT code, account_code FROM chart_of_accounts WHERE id = ?",
            (cash_id,),
        ).fetchone()
        self.assertGreaterEqual(int(stats.get("updated") or 0), 1)
        self.assertEqual(str(row["code"]), "1000")
        self.assertEqual(str(row["account_code"]), "1000")

    def test_chart_diagnostics_reports_missing_account_codes(self):
        cursor = self.conn.execute(
            """
            INSERT INTO chart_of_accounts (
                name, account_name, type, account_type, code, account_code,
                posting_allowed, control_account, allow_manual_posting, is_active
            )
            VALUES (?, ?, ?, ?, NULL, NULL, 1, 0, 1, 1)
            """,
            ("Uncoded Expense", "Uncoded Expense", "Expense", "Expense"),
        )
        self.commit()
        diagnostics = self.engine.get_chart_of_accounts_diagnostics(conn=self.conn)
        self.assertIn("Uncoded Expense", diagnostics.get("missing_account_codes") or [])
        self.assertTrue(any("missing codes" in warning for warning in diagnostics.get("warnings") or []))

    def test_cashbook_numeric_coercion_still_works(self):
        journal_df = pd.DataFrame(
            [
                {
                    "Date": "2026-07-06",
                    "Entry ID": 1,
                    "Description": "Cash movement",
                    "Reference": "CB-HOTFIX",
                    "Created By": "Bookkeeper",
                    "Account Code": "1000",
                    "Account": "Cash",
                    "Type": "Asset",
                    "Debit (GHS)": "GHS 500.00",
                    "Credit (GHS)": "100.00",
                }
            ]
        )
        with mock.patch.object(self.financials, "get_general_journal", return_value=journal_df):
            cash_book = self.financials.get_cash_book(self.company_key)
        self.assertFalse(cash_book.empty)
        self.assertEqual(float(cash_book.loc[0, "Movement (GHS)"]), 400.0)

    def test_payment_form_reset_helper_still_changes_widget_keys(self):
        modules = importlib.import_module("modules")
        counter_key = "receive_payment_form_reset_TESTCO"
        with mock.patch.object(self.financials.st, "session_state", {counter_key: 0}, create=True):
            first = modules._form_widget_key("receive_payment_amount_TESTCO", counter_key)
            modules._increment_form_reset(counter_key)
            second = modules._form_widget_key("receive_payment_amount_TESTCO", counter_key)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    import unittest

    unittest.main()
