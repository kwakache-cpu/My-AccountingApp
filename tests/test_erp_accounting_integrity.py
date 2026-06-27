from datetime import date

from test_support import ERPIsolatedTestCase, build_lines, find_trial_balance_row, sum_balance_sheet


class ERPAccountingIntegrityTests(ERPIsolatedTestCase):
    def test_source_document_posting_blocks_duplicate_journal_impact(self):
        customer_id = self.create_customer("Integrity Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=125.0)
        lines = build_lines(
            {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 125.0, "credit": 0.0},
            {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 125.0},
        )
        entry_id = self.post_entry(
            lines=lines,
            description="Integrity invoice posting",
            reference="PROD-CERT-INV-001",
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
        )

        linked_invoice = self.conn.execute("SELECT posted_entry_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        self.assertEqual(int(linked_invoice["posted_entry_id"]), entry_id)
        self.assertEqual(self.journal_count(source_table="invoices", source_id=invoice_id), 1)
        with self.assertRaisesRegex(ValueError, "already posted"):
            self.post_entry(
                lines=lines,
                description="Duplicate invoice posting",
                reference="PROD-CERT-INV-001-DUP",
                source_table="invoices",
                source_id=invoice_id,
                source_type="Invoice",
                customer_id=customer_id,
            )

    def test_vat_and_bank_transfer_journals_remain_balanced(self):
        vat_entry_id = self.engine.post_vat_transaction(
            self.company_key,
            self.today,
            "Output VAT certification sale",
            net_amount=100.0,
            vat_amount=15.0,
            vat_type="OutputVAT",
            created_by="Bookkeeper",
            source_module="Production Certification",
            source_table=None,
            source_id=None,
            conn=self.conn,
        )
        self.commit()
        bank_transfer_entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Bank", "Asset"), "debit": 80.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 80.0},
            ),
            description="Cash to bank transfer certification",
            reference="PROD-CERT-BANK-001",
            source_table=None,
            source_id=None,
            source_type="Bank Transfer",
            manual_entry=True,
        )

        for entry_id in (vat_entry_id, bank_transfer_entry_id):
            row = self.conn.execute(
                """
                SELECT ROUND(COALESCE(SUM(debit), 0), 2) AS debit_total,
                       ROUND(COALESCE(SUM(credit), 0), 2) AS credit_total
                FROM journal_lines
                WHERE entry_id = ?
                """,
                (entry_id,),
            ).fetchone()
            self.assertEqual(float(row["debit_total"]), float(row["credit_total"]))
        vat_payable = self.engine.get_account_total(self.company_key, "VAT Payable", conn=self.conn)
        self.assertEqual(vat_payable["credit_total"], 15.0)

    def test_financial_reports_reconcile_to_posted_journals(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 500.0},
            ),
            description="Owner funding",
            reference="PROD-CERT-FUNDING",
            manual_entry=True,
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 200.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 200.0},
            ),
            description="Certification revenue",
            reference="PROD-CERT-REV",
            manual_entry=True,
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 75.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 75.0},
            ),
            description="Certification expense",
            reference="PROD-CERT-EXP",
            manual_entry=True,
        )

        trial_balance = self.engine.get_trial_balance(self.company_key, start_date=self.today, end_date=self.today)
        debit_total = round(sum(float(row["debit_total"] or 0.0) for row in trial_balance), 2)
        credit_total = round(sum(float(row["credit_total"] or 0.0) for row in trial_balance), 2)
        self.assertEqual(debit_total, credit_total)
        self.assertIsNotNone(find_trial_balance_row(trial_balance, "Cash"))

        income_statement = self.engine.generate_income_statement(self.company_key, self.today, self.today)
        net_profit = next(row["amount"] for row in income_statement if row["account_name"] == "Net Profit")
        self.assertEqual(net_profit, 125.0)

        balance_sheet = self.engine.generate_balance_sheet(self.company_key, self.today)
        assets = sum_balance_sheet(balance_sheet, "Asset")
        liabilities = sum_balance_sheet(balance_sheet, "Liability")
        equity = sum_balance_sheet(balance_sheet, "Equity")
        self.assertEqual(round(assets - (liabilities + equity), 2), 0.0)

        diagnostics = self.engine.get_reporting_trust_diagnostics(
            self.company_key,
            start_date=self.today,
            end_date=self.today,
            conn=self.conn,
        )
        self.assertEqual(diagnostics["trial_balance"]["difference"], 0.0)
