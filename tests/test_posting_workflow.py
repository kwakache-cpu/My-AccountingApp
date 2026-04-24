from test_support import ERPIsolatedTestCase, build_lines


class PostingWorkflowTests(ERPIsolatedTestCase):
    def test_posted_invoice_creates_ar_and_revenue_journal(self):
        customer_id = self.create_customer("Invoice Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=250.0)
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 250.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 250.0},
            ),
            description="Posted invoice",
            reference="INV-POST-001",
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
        )
        self.assertGreater(entry_id, 0)
        posted_entry_id = self.conn.execute(
            "SELECT posted_entry_id FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()["posted_entry_id"]
        self.assertEqual(int(posted_entry_id), entry_id)
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 250.0)

    def test_posted_bill_creates_expense_and_ap_journal(self):
        supplier_id = self.create_supplier("Bill Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=180.0)
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 180.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 180.0},
            ),
            description="Posted bill",
            reference="BILL-POST-001",
            source_table="bills",
            source_id=bill_id,
            source_type="Bill",
            supplier_id=supplier_id,
        )
        self.assertGreater(entry_id, 0)
        posted_entry_id = self.conn.execute(
            "SELECT posted_entry_id FROM bills WHERE id = ?",
            (bill_id,),
        ).fetchone()["posted_entry_id"]
        self.assertEqual(int(posted_entry_id), entry_id)
        self.assertEqual(self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn), 180.0)

    def test_customer_payment_reduces_accounts_receivable(self):
        customer_id = self.create_customer("Paying Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=200.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 200.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 200.0},
            ),
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
            reference="INV-AR-200",
        )
        payment_id = self.create_payment(
            payment_type="Customer Receipt",
            customer_id=customer_id,
            invoice_id=invoice_id,
            status="Posted",
            amount=200.0,
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 200.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 200.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Payment",
            customer_id=customer_id,
            payment_id=payment_id,
            reference="PAY-AR-200",
        )
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 0.0)

    def test_supplier_payment_reduces_accounts_payable(self):
        supplier_id = self.create_supplier("Paid Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=140.0)
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 140.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 140.0},
            ),
            source_table="bills",
            source_id=bill_id,
            source_type="Bill",
            supplier_id=supplier_id,
            reference="BILL-AP-140",
        )
        payment_id = self.create_payment(
            payment_type="Supplier Payment",
            supplier_id=supplier_id,
            bill_id=bill_id,
            status="Posted",
            amount=140.0,
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 140.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 140.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Supplier Payment",
            supplier_id=supplier_id,
            payment_id=payment_id,
            reference="PAY-AP-140",
        )
        self.assertEqual(self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn), 0.0)

    def test_duplicate_posting_of_same_source_document_is_blocked(self):
        customer_id = self.create_customer("Duplicate Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=90.0)
        lines = build_lines(
            {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 90.0, "credit": 0.0},
            {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 90.0},
        )
        self.post_entry(
            lines=lines,
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
            reference="INV-DUP-001",
        )
        with self.assertRaisesRegex(ValueError, "already posted"):
            self.post_entry(
                lines=lines,
                source_table="invoices",
                source_id=invoice_id,
                source_type="Invoice",
                customer_id=customer_id,
                reference="INV-DUP-002",
            )
