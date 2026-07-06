"""
Program A P0 Sprint 2 — taxation permission hardening and regression safety.
"""
import importlib
import inspect
import os
import unittest

from test_support import ERPIsolatedTestCase, build_lines


def _extract_function_block(source_text, function_name):
    marker = f"def {function_name}("
    start = source_text.find(marker)
    if start < 0:
        return ""
    next_def = source_text.find("\ndef ", start + len(marker))
    return source_text[start:] if next_def < 0 else source_text[start:next_def]


class ProgramAP0TaxationPermissionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.app = importlib.import_module("app")

    def _user(self, role):
        return {"key": self.company_key, "name": "Tax Test User", "role": role}

    def test_permission_keys_are_registered(self):
        self.assertIn("view_taxation", self.modules.ALL_ENTERPRISE_PERMISSIONS)
        self.assertIn("manage_taxation", self.modules.ALL_ENTERPRISE_PERMISSIONS)
        self.assertEqual(
            self.modules.PAGE_PERMISSION_MAP.get("Taxation (VAT/NHIL)"),
            "view_taxation",
        )
        self.assertEqual(
            self.app.PAGE_PERMISSION_MAP.get("Taxation (VAT/NHIL)"),
            "view_taxation",
        )

    def test_authorized_roles_can_access_taxation_page(self):
        for role in ("Accountant", "Bookkeeper", "Auditor / Read Only", "Owner / CEO"):
            with self.subTest(role=role):
                self.assertTrue(
                    self.modules.user_has_permission(role, "view_taxation"),
                    msg=f"{role} should have view_taxation",
                )
                self.assertTrue(
                    self.modules.user_can_access_page(
                        self._user(role),
                        "Taxation (VAT/NHIL)",
                        company_key=self.company_key,
                        conn=self.conn,
                    )
                )

    def test_unauthorized_roles_cannot_access_taxation_page(self):
        for role in ("Cashier", "Staff", "Sales Officer", "Inventory Officer"):
            with self.subTest(role=role):
                self.assertFalse(
                    self.modules.user_has_permission(role, "view_taxation"),
                    msg=f"{role} should not have view_taxation",
                )
                self.assertFalse(
                    self.modules.user_can_access_page(
                        self._user(role),
                        "Taxation (VAT/NHIL)",
                        company_key=self.company_key,
                        conn=self.conn,
                    )
                )

    def test_hr_officer_keeps_reports_but_not_taxation(self):
        role = "HR / Payroll Officer"
        self.assertTrue(self.modules.user_has_permission(role, "view_reports"))
        self.assertFalse(self.modules.user_has_permission(role, "view_taxation"))
        self.assertFalse(
            self.modules.user_can_access_page(
                self._user(role),
                "Taxation (VAT/NHIL)",
                company_key=self.company_key,
                conn=self.conn,
            )
        )

    def test_auditor_can_view_but_not_manage_taxation(self):
        role = "Auditor / Read Only"
        self.assertTrue(self.modules.user_has_permission(role, "view_taxation"))
        self.assertFalse(self.modules.user_has_permission(role, "manage_taxation"))

    def test_sidebar_taxation_hidden_for_unauthorized_roles(self):
        """Sidebar visibility follows user_can_access_page for the taxation route."""
        cashier_user = self._user("Cashier")
        accountant_user = self._user("Accountant")
        taxation_page = "Taxation (VAT/NHIL)"
        self.assertFalse(
            self.modules.user_can_access_page(
                cashier_user,
                taxation_page,
                company_key=self.company_key,
                conn=self.conn,
            )
        )
        self.assertTrue(
            self.modules.user_can_access_page(
                accountant_user,
                taxation_page,
                company_key=self.company_key,
                conn=self.conn,
            )
        )

    def test_show_taxation_requires_view_permission(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            block = _extract_function_block(handle.read(), "show_taxation")
        self.assertIn('"view_taxation"', block)
        self.assertIn("require_permission", block)


class ProgramAP0TaxationReportingTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.engine = importlib.import_module("accounting_engine")

    def test_posted_tax_entries_appear_in_tax_control_balance(self):
        self.modules.ensure_tax_control_accounts(self.company_key, conn=self.conn)
        lines, _ = self.modules.build_sales_tax_journal_lines(
            self.conn,
            self.company_key,
            receipt_account_name="Cash",
            receipt_account_type="Asset",
            amount=1000.0,
            output_vat=125.0,
            nhil=25.0,
            getfund=25.0,
        )
        invoice_id = self.create_invoice(status="Posted", amount=1000.0)
        self.post_entry(
            lines=build_lines(*lines),
            description="Taxable sale",
            reference="TAX-P0-001",
            source_table="invoices",
            source_id=invoice_id,
            source_type="Invoice",
            approval_status="Posted",
        )
        tax_accounts = self.modules.ensure_tax_control_accounts(self.company_key, conn=self.conn)
        vat_row = next(row for row in tax_accounts if row["canonical_name"] == "VAT Payable")
        balance = self.modules._tax_control_balance(self.conn, self.company_key, vat_row)
        self.assertAlmostEqual(float(balance["Journal Balance"]), 125.0, places=2)

    def test_tax_journal_totals_query_is_portable(self):
        source = inspect.getsource(self.modules._tax_account_journal_totals)
        lowered = source.lower()
        for forbidden in ("date(", "datetime(", "strftime(", "julianday(", "ifnull("):
            self.assertNotIn(forbidden, lowered, msg=f"Tax query should avoid sqlite-specific helper: {forbidden}")
        self.assertIn("COALESCE", source)
        self.assertIn("SUM(jl.debit)", source.replace(" ", ""))

    def test_get_account_total_supports_tax_report_sales_basis(self):
        self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 500.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 500.0},
            ),
            description="Revenue for tax basis",
            reference="TAX-P0-REV",
        )
        total_sales = self.engine.get_account_total(
            self.company_key,
            "Sales Revenue",
            balance_side="credit",
            conn=self.conn,
        )
        self.assertAlmostEqual(float(total_sales), 500.0, places=2)


class ProgramAP0TaxationClientSurfaceTests(unittest.TestCase):
    _FORBIDDEN_CLIENT_MARKERS = (
        "render_runtime_admin_diagnostics_suite",
        "render_lv002_postgres_performance_panel",
        "render_lv003_hot_path_panel",
        "render_lv006_startup_pipeline_panel",
        "render_lv007_warmup_panel",
        "get_live_validation_lv001_diagnostics",
        "build_operations_console_full_audit",
        "compare_legacy_and_journal_totals",
    )

    def test_show_taxation_has_no_client_diagnostics(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            block = _extract_function_block(handle.read(), "show_taxation")
        for marker in self._FORBIDDEN_CLIENT_MARKERS:
            self.assertNotIn(marker, block, msg=f"show_taxation must not call {marker}")

    def test_regression_lockdown_manifest_lists_taxation_permission_workflow(self):
        manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "regression_lockdown_manifest.md")
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = handle.read()
        self.assertIn("test_permission_security.py", manifest)
        self.assertIn("Staff/user/role setup", manifest)
        self.assertIn("RegressionLockdownStaffRoleTests", manifest)


if __name__ == "__main__":
    unittest.main()
