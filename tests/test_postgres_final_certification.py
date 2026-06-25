import importlib
import inspect
from pathlib import Path

from test_support import ERPIsolatedTestCase, build_lines


class PostgresFinalCertificationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.engine = importlib.import_module("accounting_engine")

    def test_core_write_paths_use_portable_identity_helpers(self):
        critical_sources = {
            "POS sale": inspect.getsource(self.modules._persist_pos_sale),
            "Inventory movement": inspect.getsource(self.modules._insert_stock_movement_record),
            "Journal entry": inspect.getsource(self.engine.post_journal_entry),
            "Payroll page": inspect.getsource(self.modules.show_payroll),
            "Fixed asset page": inspect.getsource(self.modules.show_fixed_assets),
        }
        for workflow, source in critical_sources.items():
            self.assertIn(
                "ensure_insert_sql_returning",
                source,
                msg=f"{workflow} should keep INSERT identity portable for PostgreSQL.",
            )
            self.assertIn(
                "get_inserted_id",
                source,
                msg=f"{workflow} should avoid direct lastrowid use on critical identity paths.",
            )

    def test_journal_writer_has_transaction_and_source_sync_contract(self):
        source = inspect.getsource(self.engine.post_journal_entry)
        self.assertIn("execute_db_write_transaction", source)
        self.assertNotIn("execute_write_transaction", source)
        self.assertIn("ensure_insert_sql_returning", source)
        self.assertIn("get_inserted_id", source)
        self.assertIn("INSERT INTO journal_lines", source)
        self.assertIn("_sync_source_document_posting", source)

    def test_phase_5b16b_transaction_callers_use_backend_aware_wrapper(self):
        branch_write_source = inspect.getsource(self.modules._run_branch_db_write)
        journal_source = inspect.getsource(self.engine.post_journal_entry)
        self.assertIn("execute_db_write_transaction", branch_write_source)
        self.assertIn("execute_db_write_transaction", journal_source)
        self.assertNotIn("execute_write_transaction(", branch_write_source)
        self.assertNotIn("execute_write_transaction(", journal_source)

    def test_phase_5b16b_insert_ignore_paths_use_portable_helper(self):
        financials = importlib.import_module("financials")
        for function_name in ("show_invoice_manager", "show_customers_page", "show_suppliers_page"):
            source = inspect.getsource(getattr(financials, function_name))
            self.assertIn("db_insert_ignore_sql", source)
            self.assertIn("execute_portable_write", source)
            self.assertNotIn("INSERT OR IGNORE", source)

    def test_phase_5b16b_critical_raw_writes_use_portable_helper(self):
        critical_sources = {
            "Invoice line save": inspect.getsource(self.modules.save_invoice_lines),
            "Invoice stock effects": inspect.getsource(self.modules.apply_invoice_stock_effects),
            "POS checkout": inspect.getsource(self.modules.show_pos),
            "Payroll posting": inspect.getsource(self.modules.show_payroll),
            "Depreciation posting": inspect.getsource(self.modules.run_straight_line_depreciation),
        }
        for workflow, source in critical_sources.items():
            self.assertIn(
                "execute_portable_write",
                source,
                msg=f"{workflow} should route critical DML through execute_portable_write().",
            )

    def test_payroll_posting_links_source_document_to_journal(self):
        payroll_cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payroll (
                    company_key, emp_name, basic_salary, net_salary, month, year,
                    approval_status, created_by, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Posted', ?, 'Active')
                """
            ),
            (self.company_key, "Certification Payroll", 1000.0, 900.0, "June", "2026", "tester"),
        )
        payroll_id = self.database.get_inserted_id(payroll_cursor)
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Salary Expense", "Expense"), "debit": 1000.0, "credit": 0.0},
                {"account_id": self.account_id("Payroll Payable", "Liability"), "debit": 0.0, "credit": 1000.0},
            ),
            description="Payroll certification posting",
            reference="PAY-CERT-001",
            source_table="payroll",
            source_type="Payroll",
            source_id=payroll_id,
        )
        payroll_row = self.conn.execute(
            "SELECT posted_entry_id FROM payroll WHERE id = ?",
            (payroll_id,),
        ).fetchone()
        self.assertEqual(int(payroll_row["posted_entry_id"]), int(entry_id))

    def test_fixed_asset_posting_links_source_document_to_journal(self):
        asset_cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO fixed_assets (
                    company_key, asset_name, asset_category, purchase_date, cost,
                    book_value, status, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Active', 'Posted', ?)
                """
            ),
            (
                self.company_key,
                "Certification Asset",
                "Equipment",
                self.today.isoformat(),
                1500.0,
                1500.0,
                "tester",
            ),
        )
        asset_id = self.database.get_inserted_id(asset_cursor)
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Fixed Assets", "Asset"), "debit": 1500.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 1500.0},
            ),
            description="Fixed asset certification posting",
            reference=f"FA-CERT-{asset_id}",
            source_table="fixed_assets",
            source_type="Fixed Asset Purchase",
            source_id=asset_id,
        )
        asset_row = self.conn.execute(
            "SELECT posted_entry_id FROM fixed_assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        self.assertEqual(int(asset_row["posted_entry_id"]), int(entry_id))

    def test_depreciation_run_remains_warning_until_source_link_is_certified(self):
        source = inspect.getsource(self.modules.run_straight_line_depreciation)
        self.assertIn("Depreciation Expense", source)
        self.assertIn("Accumulated Depreciation", source)
        self.assertIn("UPDATE fixed_assets", source)
        self.assertIn("create_journal_entry", source)
        self.assertNotIn("source_table=\"fixed_assets\"", source)

    def test_certification_report_contract(self):
        report_path = Path(__file__).resolve().parents[1] / "reports" / "postgres_final_certification.md"
        self.assertTrue(report_path.exists(), "PostgreSQL final certification report must be generated.")
        report = report_path.read_text(encoding="utf-8")
        for heading in (
            "Write Path Inventory",
            "Critical Workflow Certification",
            "POS Sale",
            "Inventory Adjustment",
            "Customer Invoice",
            "Customer Payment",
            "Supplier Bill",
            "Supplier Payment",
            "Journal Entry",
            "Payroll Posting",
            "Depreciation Posting",
            "User/Role Changes",
        ):
            self.assertIn(heading, report)
        for status in ("PostgreSQL safe", "PostgreSQL warning", "PostgreSQL unsafe"):
            self.assertIn(status, report)
