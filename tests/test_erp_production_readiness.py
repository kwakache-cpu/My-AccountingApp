import importlib
from pathlib import Path

from test_support import ERPIsolatedTestCase


class ERPProductionReadinessTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.financials = importlib.import_module("financials")

    def test_required_module_entry_points_remain_available(self):
        required_modules = {
            self.modules: [
                "get_company_branches",
                "render_branch_session_diagnostics",
                "user_has_permission",
                "can_access_branch",
                "_run_pos_write_transaction",
                "_persist_pos_sale",
                "_insert_stock_movement_record",
                "show_banking",
                "show_fixed_assets",
                "run_straight_line_depreciation",
                "show_audit_trail",
                "get_deployment_readiness_diagnostics",
                "get_system_health_snapshot",
            ],
            self.financials: [
                "show_invoice_manager",
                "show_customers_page",
                "show_suppliers_page",
                "show_create_invoice_page",
                "show_receive_payment_page",
                "show_supplier_payment_page",
                "show_financial_reports",
                "get_general_journal",
                "get_general_ledger",
                "get_cash_book",
                "get_depreciation_schedule",
            ],
            self.engine: [
                "post_accounting_impact",
                "reverse_journal_entry",
                "get_trial_balance",
                "generate_balance_sheet",
                "generate_income_statement",
                "generate_cash_flow_statement",
                "get_ar_aging_report",
                "get_ap_aging_report",
                "post_vat_transaction",
                "get_finance_integrity_diagnostics",
                "get_reporting_trust_diagnostics",
            ],
            self.database: [
                "execute_db_write_transaction",
                "execute_portable_write",
                "execute_portable_query",
                "get_postgres_readiness_diagnostics",
                "get_schema_manifest_diagnostics",
                "get_recovery_source_diagnostics",
                "force_backup_after_company_creation",
            ],
        }
        for module, function_names in required_modules.items():
            for function_name in function_names:
                self.assertTrue(hasattr(module, function_name), f"{module.__name__}.{function_name} is required")

    def test_security_roles_do_not_gain_unintended_privileges(self):
        self.assertTrue(self.modules.user_has_permission("Dev", "manage_users"))
        self.assertTrue(self.modules.user_has_permission("Master Admin", "post_accounting_document"))
        self.assertTrue(self.modules.user_has_permission("Owner", "manage_cash_bank_transfers"))
        self.assertTrue(self.modules.user_has_permission("Branch Manager", "manage_branch_users"))
        self.assertTrue(self.modules.user_has_permission("Cashier", "sell_pos"))
        self.assertTrue(self.modules.user_has_permission("Inventory Officer", "manage_inventory"))
        self.assertTrue(self.modules.user_has_permission("Payroll Officer", "manage_payroll"))
        self.assertTrue(self.modules.user_has_permission("Auditor", "view_audit_trail"))

        self.assertFalse(self.modules.user_has_permission("System Admin", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_reports"))
        self.assertFalse(self.modules.user_has_permission("Sales Officer", "manage_inventory"))
        self.assertFalse(self.modules.user_has_permission("Inventory Officer", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Payroll Officer", "manage_users"))
        self.assertFalse(self.modules.user_has_permission("Auditor", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Staff", "manage_users"))

    def test_branch_and_company_isolation_helpers_are_enforced(self):
        branch_user = {"role": "Branch_Bookkeeper", "branch_id": "BR-001"}
        self.assertTrue(self.modules.can_access_branch(branch_user, "BR-001"))
        self.assertFalse(self.modules.can_access_branch(branch_user, "BR-002"))
        self.assertFalse(self.modules.can_access_branch(branch_user, None))
        self.assertTrue(self.modules.can_access_branch({"role": "Master Admin"}, "BR-999"))

        records = [
            {"branch_id": "BR-001", "amount": 10},
            {"branch_id": "BR-002", "amount": 20},
            {"branch_id": None, "amount": 30},
        ]
        filtered = self.modules.filter_by_user_branch(records, branch_user)
        self.assertEqual([row["amount"] for row in filtered], [10, 30])

    def test_production_certification_report_contracts_exist(self):
        repo_root = Path(__file__).resolve().parent.parent
        required_reports = {
            "reports/erp_production_readiness_certification.md": [
                "Current production readiness %",
                "Current PostgreSQL readiness %",
                "PASS",
                "WARNING",
                "FAIL",
                "NOT TESTED",
            ],
            "reports/erp_remaining_blockers.md": ["Severity", "Blocker", "Highest-priority next phase"],
            "reports/erp_go_live_checklist.md": ["Go/No-Go", "Rollback", "Backup", "Sign-off"],
            "reports/erp_world_class_gap_analysis.md": ["World-Class Gap Analysis", "Gap", "Recommendation"],
        }
        for relative_path, required_texts in required_reports.items():
            report_text = (repo_root / relative_path).read_text(encoding="utf-8")
            for required_text in required_texts:
                self.assertIn(required_text, report_text)
