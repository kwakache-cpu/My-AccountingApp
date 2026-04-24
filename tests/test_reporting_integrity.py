from test_support import ERPIsolatedTestCase, build_lines, sum_balance_sheet


class ReportingIntegrityTests(ERPIsolatedTestCase):
    def test_posting_allowed_in_open_period(self):
        self.create_period("2026-04", self.today.replace(day=1), self.today.replace(day=30), status="Open", is_locked=0)
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 100.0},
            ),
            reference="OPEN-PERIOD",
        )
        self.assertGreater(entry_id, 0)

    def test_posting_blocked_in_closed_period(self):
        self.create_period("2026-04", self.today.replace(day=1), self.today.replace(day=30), status="Closed", is_locked=0)
        with self.assertRaisesRegex(ValueError, "locked"):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 100.0},
                ),
                reference="CLOSED-PERIOD",
            )

    def test_posting_blocked_in_locked_period(self):
        self.create_period("2026-04", self.today.replace(day=1), self.today.replace(day=30), status="Locked", is_locked=1)
        with self.assertRaisesRegex(ValueError, "locked"):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 100.0},
                ),
                reference="LOCKED-PERIOD",
            )

    def test_trial_balance_debits_equal_credits(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 300.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 300.0},
            ),
            reference="TB-BALANCE",
        )
        trial_balance = self.engine.get_trial_balance(self.company_key)
        total_debits = round(sum(float(row["debit_total"] or 0.0) for row in trial_balance), 2)
        total_credits = round(sum(float(row["credit_total"] or 0.0) for row in trial_balance), 2)
        self.assertEqual(total_debits, total_credits)

    def test_balance_sheet_equation_validates(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 500.0},
            ),
            reference="BS-EQUATION",
        )
        balance_sheet = self.engine.generate_balance_sheet(self.company_key, self.today)
        assets = sum_balance_sheet(balance_sheet, "Asset")
        liabilities = sum_balance_sheet(balance_sheet, "Liability")
        equity = sum_balance_sheet(balance_sheet, "Equity")
        self.assertEqual(round(assets, 2), round(liabilities + equity, 2))

    def test_ar_reconciliation_detects_mismatch(self):
        customer_id = self.create_customer("Mismatch AR")
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 125.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 125.0},
            ),
            reference="AR-MISMATCH",
        )
        diagnostics = self.engine.get_journal_dominance_diagnostics(self.company_key, conn=self.conn)
        self.assertFalse(diagnostics["integrity"]["accounts_receivable"]["reconciled"])
        self.assertNotEqual(float(diagnostics["integrity"]["accounts_receivable"]["difference"]), 0.0)

    def test_ap_reconciliation_detects_mismatch(self):
        supplier_id = self.create_supplier("Mismatch AP")
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 110.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 110.0},
            ),
            reference="AP-MISMATCH",
        )
        diagnostics = self.engine.get_journal_dominance_diagnostics(self.company_key, conn=self.conn)
        self.assertFalse(diagnostics["integrity"]["accounts_payable"]["reconciled"])
        self.assertNotEqual(float(diagnostics["integrity"]["accounts_payable"]["difference"]), 0.0)
