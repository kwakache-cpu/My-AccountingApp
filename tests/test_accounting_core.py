from test_support import ERPIsolatedTestCase, build_lines, find_trial_balance_row


class AccountingCoreTests(ERPIsolatedTestCase):
    def test_balanced_journal_posting_succeeds(self):
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 100.0},
            ),
            description="Owner funding",
            reference="CAPITAL-001",
        )
        self.assertGreater(entry_id, 0)
        self.assertEqual(self.journal_count(), 1)

    def test_unbalanced_journal_posting_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unbalanced journal entry"):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 90.0},
                ),
                description="Broken funding",
                reference="CAPITAL-BROKEN",
            )

    def test_posted_only_reports_exclude_draft_journals(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 100.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 100.0},
            ),
            reference="POSTED-ONLY",
        )
        self.engine.post_journal_entry(
            company_key=self.company_key,
            date=self.today,
            description="Draft journal",
            reference="DRAFT-ONLY",
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 500.0},
            ),
            created_by="Bookkeeper",
            approval_status="Draft",
            conn=self.conn,
        )
        self.commit()
        trial_balance = self.engine.get_trial_balance(self.company_key)
        cash_row = find_trial_balance_row(trial_balance, "Cash")
        self.assertIsNotNone(cash_row)
        self.assertEqual(float(cash_row["debit_total"]), 100.0)

    def test_draft_and_submitted_documents_do_not_affect_balances(self):
        customer_id = self.create_customer("Draft Customer")
        self.create_invoice(customer_id=customer_id, status="Draft", amount=175.0)
        self.create_invoice(customer_id=customer_id, status="Submitted", amount=200.0)
        customer_balance = self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn)
        self.assertEqual(customer_balance, 0.0)
        trial_balance = self.engine.get_trial_balance(self.company_key)
        self.assertEqual(trial_balance, [])

    def test_voided_journals_are_excluded_from_reports(self):
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 120.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 120.0},
            ),
            reference="VOID-ME",
        )
        self.conn.execute(
            "UPDATE journal_entries SET is_voided = 1, approval_status = 'Voided' WHERE id = ?",
            (entry_id,),
        )
        self.commit()
        trial_balance = self.engine.get_trial_balance(self.company_key)
        cash_row = find_trial_balance_row(trial_balance, "Cash")
        self.assertTrue(cash_row is None or float(cash_row["debit_total"]) == 0.0)
