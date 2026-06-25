import importlib
from datetime import date
from pathlib import Path

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix, find_trial_balance_row, sum_balance_sheet


class ERPFunctionalCertificationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)
            VALUES (?, ?, ?)
            """,
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _create_inventory_item(self, *, qty=10.0, cost_price=4.0, price=10.0):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode,
                qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Certified Soap", f"SOAP-{datetime_suffix('I')}", "", qty, price, cost_price, 1.0),
        )
        self.commit()
        return int(self.conn.execute("SELECT id FROM inventory ORDER BY id DESC LIMIT 1").fetchone()["id"])

    def test_pos_credit_sale_updates_inventory_journal_customer_balance_and_audit(self):
        customer_id = self.create_customer("POS Credit Customer")
        item_id = self._create_inventory_item(qty=8.0, cost_price=6.0, price=20.0)
        sale_reference = f"POS-CERT-{datetime_suffix('P')}"
        sale_cart = [
            {
                "inventory_item_id": item_id,
                "name": "Certified Soap",
                "item_code": "SOAP",
                "barcode": "",
                "qty": 2,
                "price": 20.0,
                "line_discount": 0.0,
                "tax_rate": 0.0,
                "line_total": 40.0,
                "cost_price": 6.0,
            }
        ]
        receipt_data = {
            "receipt_number": sale_reference,
            "sale_date": self.today.isoformat(),
            "sale_datetime": f"{self.today.isoformat()} 09:00:00",
            "cashier": "Cashier",
            "payment_method": "On Credit",
            "subtotal": 40.0,
            "discount_total": 0.0,
            "tax_total": 0.0,
            "grand_total": 40.0,
        }

        def pos_write(conn, _diagnostics):
            before_qty = float(conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
            self.database.execute_portable_write(
                conn,
                "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
                (2.0, item_id, self.company_key),
            )
            pos_sale_id = self.modules._persist_pos_sale(
                conn,
                self.company_key,
                "MAIN",
                sale_reference,
                receipt_data,
                sale_cart,
                customer_id=customer_id,
            )
            self.engine.post_accounting_impact(
                company_key=self.company_key,
                date=self.today,
                description="Certified POS credit sale",
                reference=sale_reference,
                lines=build_lines(
                    {"account_id": self.engine.get_account_id(conn, "Accounts Receivable", "Asset"), "debit": 40.0, "credit": 0.0},
                    {"account_id": self.engine.get_account_id(conn, "Sales Revenue", "Income"), "debit": 0.0, "credit": 40.0},
                ),
                created_by="Cashier",
                branch_id="MAIN",
                customer_id=customer_id,
                source_module="POS",
                source_table="pos_sales",
                source_type="POS Sale",
                source_id=pos_sale_id,
                user_role="Bookkeeper",
                conn=conn,
            )
            self.modules.log_audit_action(
                conn,
                self.company_key,
                "Cashier",
                "POS Sale",
                "POS",
                details=f"Certified sale {sale_reference}",
                branch_id="MAIN",
                document_ref=sale_reference,
            )
            return {"pos_sale_id": pos_sale_id, "before_qty": before_qty}

        result = self.modules._run_pos_write_transaction(pos_write, operation_name="functional_pos_sale")
        after_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        sale_row = self.conn.execute("SELECT customer_id, grand_total FROM pos_sales WHERE id = ?", (result["pos_sale_id"],)).fetchone()
        audit_count = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE company_key = ? AND action = 'POS Sale' AND module_name = 'POS'",
                (self.company_key,),
            ).fetchone()["c"]
        )

        self.assertEqual(after_qty, result["before_qty"] - 2.0)
        self.assertEqual(int(sale_row["customer_id"]), customer_id)
        self.assertEqual(float(sale_row["grand_total"]), 40.0)
        self.assertEqual(self.journal_count(source_table="pos_sales", source_id=result["pos_sale_id"]), 1)
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 40.0)
        self.assertGreaterEqual(audit_count, 1)

    def test_customer_invoice_and_payment_certify_ar_lifecycle(self):
        customer_id = self.create_customer("Certified AR Customer")
        invoice_id = self.create_invoice(customer_id=customer_id, status="Posted", amount=300.0)
        invoice_entry = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 300.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 300.0},
            ),
            description="Certified customer invoice",
            reference="CERT-INV-300",
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            customer_id=customer_id,
        )
        self.assertGreater(invoice_entry, 0)
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 300.0)

        payment_id = self.create_payment("Customer Receipt", customer_id=customer_id, invoice_id=invoice_id, amount=300.0)
        payment_entry = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 300.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 0.0, "credit": 300.0},
            ),
            description="Certified customer payment",
            reference="CERT-PAY-AR-300",
            source_table="payments",
            source_id=payment_id,
            source_type="Customer Payment",
            customer_id=customer_id,
            payment_id=payment_id,
        )
        self.assertGreater(payment_entry, 0)
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 0.0)

    def test_supplier_bill_and_payment_certify_ap_lifecycle(self):
        supplier_id = self.create_supplier("Certified AP Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=220.0)
        bill_entry = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Purchases", "Expense"), "debit": 220.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 220.0},
            ),
            description="Certified supplier bill",
            reference="CERT-BILL-220",
            source_table="bills",
            source_id=bill_id,
            source_type="Bill",
            supplier_id=supplier_id,
        )
        self.assertGreater(bill_entry, 0)
        self.assertEqual(self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn), 220.0)

        payment_id = self.create_payment("Supplier Payment", supplier_id=supplier_id, bill_id=bill_id, amount=220.0)
        payment_entry = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 220.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 220.0},
            ),
            description="Certified supplier payment",
            reference="CERT-PAY-AP-220",
            source_table="payments",
            source_id=payment_id,
            source_type="Supplier Payment",
            supplier_id=supplier_id,
            payment_id=payment_id,
        )
        self.assertGreater(payment_entry, 0)
        self.assertEqual(self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn), 0.0)

    def test_general_journal_certifies_balancing_and_ledger_updates(self):
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 150.0, "credit": 0.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 150.0},
            ),
            description="Certified capital journal",
            reference="CERT-GJ-150",
            manual_entry=True,
        )
        self.assertGreater(entry_id, 0)
        cash_ledger = self.engine.get_general_ledger(self.company_key, self.account_id("Cash", "Asset"), self.today, self.today)
        self.assertEqual(cash_ledger[-1]["running_balance"], 150.0)
        with self.assertRaisesRegex(ValueError, "Unbalanced journal entry"):
            self.post_entry(
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 10.0, "credit": 0.0},
                    {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 9.0},
                ),
                reference="CERT-GJ-BLOCKED",
                manual_entry=True,
            )

    def test_payroll_posting_creates_journal_and_reconciles_totals(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payroll (
                    company_key, emp_name, basic_salary, allowances, deductions, net_salary,
                    month, year, payment_status, approval_status, created_by, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Unpaid', 'Posted', ?, 'Active')
                """
            ),
            (self.company_key, "Certified Employee", 1000.0, 100.0, 200.0, 900.0, "April", "2026", "Bookkeeper"),
        )
        payroll_id = self.database.get_inserted_id(cursor)
        self.commit()
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Salary Expense", "Expense"), "debit": 1100.0, "credit": 0.0},
                {"account_id": self.account_id("Payroll Payable", "Liability"), "debit": 0.0, "credit": 900.0},
                {"account_id": self.account_id("Payroll Taxes Payable", "Liability"), "debit": 0.0, "credit": 200.0},
            ),
            description="Certified payroll posting",
            reference="CERT-PAYROLL-APR",
            source_table="payroll",
            source_id=payroll_id,
            source_type="Payroll",
        )
        payroll_totals = self.conn.execute(
            "SELECT SUM(basic_salary + allowances) AS gross_total, SUM(net_salary) AS net_total FROM payroll WHERE company_key = ?",
            (self.company_key,),
        ).fetchone()
        salary_row = find_trial_balance_row(self.engine.get_trial_balance(self.company_key), "Salary Expense")
        self.assertGreater(entry_id, 0)
        self.assertEqual(float(payroll_totals["gross_total"]), 1100.0)
        self.assertEqual(float(payroll_totals["net_total"]), 900.0)
        self.assertEqual(float(salary_row["debit_total"]), 1100.0)

    def test_fixed_asset_creation_depreciation_journal_and_book_value(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO fixed_assets (
                    company_key, asset_name, asset_category, purchase_date, cost,
                    opening_book_value, useful_life_years, residual_value, depreciation_method,
                    depreciation_rate, accumulated_depreciation, book_value, status, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Straight-line', ?, 0, ?, 'Active', 'Posted', ?)
                """
            ),
            (self.company_key, "Certified Laptop", "IT Equipment", date(2026, 1, 1).isoformat(), 1200.0, 1200.0, 1.0, 0.0, 100.0, 1200.0, "Bookkeeper"),
        )
        asset_id = self.database.get_inserted_id(cursor)
        self.commit()
        acquisition_entry = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Fixed Assets", "Asset"), "debit": 1200.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 1200.0},
            ),
            description="Certified asset acquisition",
            reference=f"CERT-FA-{asset_id}",
            source_table="fixed_assets",
            source_id=asset_id,
            source_type="Fixed Asset Purchase",
        )
        posted_count = self.modules.run_straight_line_depreciation(
            self.company_key,
            as_of_date=date(2026, 1, 31),
            conn=self.conn,
            created_by="Bookkeeper",
        )
        self.commit()
        asset_row = self.conn.execute(
            "SELECT accumulated_depreciation, book_value FROM fixed_assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        depreciation_journal_count = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM journal_entries WHERE company_key = ? AND reference LIKE ?",
                (self.company_key, f"DEPR-{asset_id}-%"),
            ).fetchone()["c"]
        )
        self.assertGreater(acquisition_entry, 0)
        self.assertGreaterEqual(posted_count, 1)
        self.assertGreaterEqual(depreciation_journal_count, 1)
        self.assertEqual(float(asset_row["accumulated_depreciation"]), 100.0)
        self.assertEqual(float(asset_row["book_value"]), 1100.0)

    def test_financial_reports_certify_trial_balance_income_balance_sheet_and_ledger(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 350.0},
                {"account_id": self.account_id("Owner Capital", "Equity"), "debit": 0.0, "credit": 150.0},
            ),
            description="Certified reporting posting",
            reference="CERT-REPORT-001",
        )
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cost of Goods Sold", "Expense"), "debit": 80.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 80.0},
            ),
            description="Certified expense posting",
            reference="CERT-REPORT-002",
        )
        trial_balance = self.engine.get_trial_balance(self.company_key)
        income_statement = self.engine.generate_income_statement(self.company_key, self.today, self.today)
        balance_sheet = self.engine.generate_balance_sheet(self.company_key, self.today)
        cash_ledger = self.engine.get_general_ledger(self.company_key, self.account_id("Cash", "Asset"), self.today, self.today)
        total_debits = round(sum(float(row["debit_total"] or 0.0) for row in trial_balance), 2)
        total_credits = round(sum(float(row["credit_total"] or 0.0) for row in trial_balance), 2)
        revenue_row = next(row for row in income_statement if row["account_name"] == "Sales Revenue")
        cogs_row = next(row for row in income_statement if row["account_name"] == "Cost of Goods Sold")
        assets = sum_balance_sheet(balance_sheet, "Asset")
        liabilities = sum_balance_sheet(balance_sheet, "Liability")
        equity = sum_balance_sheet(balance_sheet, "Equity")
        self.assertEqual(total_debits, total_credits)
        self.assertEqual(float(revenue_row["amount"]), 350.0)
        self.assertEqual(float(cogs_row["amount"]), 80.0)
        self.assertEqual(round(assets, 2), round(liabilities + equity, 2))
        self.assertGreaterEqual(len(cash_ledger), 2)

    def test_security_role_branch_and_admin_audit_certification(self):
        self.assertTrue(self.modules.user_has_permission("Cashier", "sell_pos"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_reports"))
        self.assertTrue(self.modules.can_access_branch({"role": "Branch_Bookkeeper", "branch_id": "MAIN"}, "MAIN"))
        self.assertFalse(self.modules.can_access_branch({"role": "Branch_Bookkeeper", "branch_id": "MAIN"}, "OTHER"))
        self.modules.log_audit_action(
            self.conn,
            self.company_key,
            "Master Admin",
            "Certified Admin Action",
            "System Configuration",
            details="Functional certification admin audit",
            action_type="admin",
        )
        self.commit()
        audit_count = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM audit_logs
                WHERE company_key = ?
                  AND action = 'Certified Admin Action'
                  AND module_name = 'System Configuration'
                """,
                (self.company_key,),
            ).fetchone()["c"]
        )
        self.assertGreaterEqual(audit_count, 1)

    def test_functional_certification_report_contract(self):
        report_path = Path(__file__).resolve().parents[1] / "reports" / "erp_functional_certification.md"
        self.assertTrue(report_path.exists(), "ERP functional certification report must be generated.")
        report = report_path.read_text(encoding="utf-8")
        for required_text in (
            "Module Readiness",
            "Workflow Certification",
            "Accounting Integrity Issues",
            "Remaining Production Blockers",
            "Recommended Next Action",
            "POS Sale",
            "Customer Invoice / AR",
            "Supplier Bill / AP",
            "General Journal",
            "Payroll",
            "Fixed Assets",
            "Financial Reports",
            "Security",
        ):
            self.assertIn(required_text, report)
