import importlib

from test_support import ERPIsolatedTestCase, build_lines
from security_utils import build_user_safe_error, sanitize_error_message


class PermissionSecurityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_allowed_role_can_post(self):
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cash", "Asset"), "debit": 75.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 75.0},
            ),
            description="Permission allowed posting",
            reference="PERM-ALLOW-001",
            manual_entry=True,
            user_role="Bookkeeper",
        )
        self.assertGreater(entry_id, 0)
        self.assertEqual(self.journal_count(), 1)

    def test_disallowed_role_cannot_post(self):
        with self.assertRaisesRegex(PermissionError, "not allowed to post accounting impact"):
            self.engine.post_accounting_impact(
                company_key=self.company_key,
                date=self.today,
                description="Blocked posting",
                reference="PERM-DENY-001",
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 50.0, "credit": 0.0},
                    {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 50.0},
                ),
                created_by="Staff",
                source_module="tests",
                source_table="invoices",
                source_type="Invoice",
                source_id=202,
                user_role="Staff",
            )
        self.assertEqual(self.journal_count(source_table="invoices", source_id=202), 0)

    def test_disallowed_role_cannot_close_period(self):
        with self.assertRaisesRegex(PermissionError, "cannot change accounting period controls"):
            self.modules.set_period_status(
                self.company_key,
                self.today,
                "Closed",
                changed_by="Staff",
            )
        row = self.conn.execute(
            "SELECT COUNT(*) AS row_count FROM accounting_periods WHERE company_key = ?",
            (self.company_key,),
        ).fetchone()
        self.assertEqual(int(row["row_count"] or 0), 0)

    def test_disallowed_role_cannot_view_or_export_backup(self):
        self.assertFalse(self.modules.user_has_permission("Staff", "export_backup"))
        self.assertFalse(self.modules.user_has_permission("Staff", "view_system_health"))
        self.assertTrue(self.modules.user_has_permission("Master Admin", "export_backup"))

    def test_permission_denial_is_logged_if_audit_tables_exist(self):
        with self.assertRaises(PermissionError):
            self.engine.post_accounting_impact(
                company_key=self.company_key,
                date=self.today,
                description="Denied posting audit test",
                reference="PERM-AUDIT-001",
                lines=build_lines(
                    {"account_id": self.account_id("Cash", "Asset"), "debit": 40.0, "credit": 0.0},
                    {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 40.0},
                ),
                created_by="Staff",
                source_module="tests",
                source_table="payments",
                source_type="Customer Payment",
                source_id=303,
                user_role="Staff",
            )
        security_log = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM system_logs
            WHERE module_name IN ('Unified Posting Engine', 'Security')
              AND lower(message) LIKE '%permission%'
            """
        ).fetchone()
        audit_log = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM audit_logs
            WHERE company_key = ?
              AND lower(module_name) = 'security'
            """,
            (self.company_key,),
        ).fetchone()
        self.assertGreaterEqual(int(security_log["row_count"] or 0), 1)
        self.assertGreaterEqual(int(audit_log["row_count"] or 0), 1)

    def test_raw_exception_sanitization_removes_secret_like_values(self):
        message = build_user_safe_error(
            "Gemini failed at https://generativelanguage.googleapis.com/v1beta/models/test:generateContent?key=AIzaSECRET1234567890 "
            "Authorization: Bearer SECRET_TOKEN_1234567890",
            role="Dev",
        )
        self.assertIn("An error occurred. Please contact the system administrator.", message)
        self.assertNotIn("AIzaSECRET1234567890", message)
        self.assertNotIn("Bearer SECRET_TOKEN_1234567890", message)
        self.assertNotIn("?key=", message)

    def test_sanitize_error_message_redacts_query_params_headers_and_tokens(self):
        raw_message = (
            "Request failed at https://example.com/callback?token=abc1234567890123456789012345&apikey=XYZ9876543210987654321098765 "
            "Authorization: Bearer SUPER_SECRET_BEARER_TOKEN_1234567890 "
            "api_key=ANOTHER_SECRET_12345678901234567890"
        )
        sanitized = sanitize_error_message(raw_message)
        self.assertNotIn("abc1234567890123456789012345", sanitized)
        self.assertNotIn("XYZ9876543210987654321098765", sanitized)
        self.assertNotIn("SUPER_SECRET_BEARER_TOKEN_1234567890", sanitized)
        self.assertNotIn("ANOTHER_SECRET_12345678901234567890", sanitized)
        self.assertIn("[redacted]", sanitized)

    def test_manual_license_override_requires_permission(self):
        result = self.modules.execute_manual_license_override(
            conn=self.conn,
            actor_role="Master Admin",
            actor_user="Master Admin",
            company_name="Unauthorized Override Co",
            company_key="UNAUTH-OVERRIDE-001",
            duration_months=12,
            number_of_branches=1,
            max_branches=1,
            branch_price_per_month=0.0,
            override_reason="Unauthorized test",
            confirmation_checked=True,
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("permission_denied"))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) AS row_count FROM companies WHERE key = ?",
                ("UNAUTH-OVERRIDE-001",),
            ).fetchone()["row_count"],
            0,
        )

    def test_manual_license_override_requires_reason_and_confirmation(self):
        missing_reason = self.modules.execute_manual_license_override(
            conn=self.conn,
            actor_role="Dev",
            actor_user="Gatekeeper",
            company_name="Override Missing Reason",
            company_key="OVERRIDE-NO-REASON",
            duration_months=12,
            number_of_branches=1,
            max_branches=1,
            branch_price_per_month=0.0,
            override_reason="",
            confirmation_checked=True,
        )
        self.assertFalse(missing_reason["ok"])
        self.assertIn("reason", missing_reason["reason"].lower())

        missing_confirmation = self.modules.execute_manual_license_override(
            conn=self.conn,
            actor_role="Dev",
            actor_user="Gatekeeper",
            company_name="Override Missing Confirmation",
            company_key="OVERRIDE-NO-CONFIRM",
            duration_months=12,
            number_of_branches=1,
            max_branches=1,
            branch_price_per_month=0.0,
            override_reason="Emergency internal deployment",
            confirmation_checked=False,
        )
        self.assertFalse(missing_confirmation["ok"])
        self.assertIn("paystack bypass", missing_confirmation["reason"].lower())

    def test_denied_override_does_not_activate_license(self):
        before_count = int(
            self.conn.execute("SELECT COUNT(*) AS row_count FROM companies").fetchone()["row_count"] or 0
        )
        result = self.modules.execute_manual_license_override(
            conn=self.conn,
            actor_role="Staff",
            actor_user="Staff User",
            company_name="Blocked Company",
            company_key="BLOCKED-LICENSE-001",
            duration_months=6,
            number_of_branches=1,
            max_branches=1,
            branch_price_per_month=0.0,
            override_reason="Should be blocked",
            confirmation_checked=True,
        )
        after_count = int(
            self.conn.execute("SELECT COUNT(*) AS row_count FROM companies").fetchone()["row_count"] or 0
        )
        self.assertFalse(result["ok"])
        self.assertEqual(before_count, after_count)

    def test_dev_manual_license_override_succeeds_with_reason_and_confirmation(self):
        result = self.modules.execute_manual_license_override(
            conn=self.conn,
            actor_role="Dev",
            actor_user="Gatekeeper",
            company_name="Emergency Override Co",
            company_key="OVERRIDE-OK-001",
            duration_months=12,
            number_of_branches=2,
            max_branches=3,
            branch_price_per_month=50.0,
            override_reason="Emergency internal deployment during billing outage",
            confirmation_checked=True,
        )
        self.assertTrue(result["ok"])
        company_row = self.conn.execute(
            "SELECT key, name, status, deployment_status FROM companies WHERE key = ?",
            ("OVERRIDE-OK-001",),
        ).fetchone()
        self.assertIsNotNone(company_row)
        self.assertEqual(company_row["status"], "Active")
        self.assertEqual(company_row["deployment_status"], "Live")
        audit_row = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM audit_logs
            WHERE action_type = 'admin/license_override'
              AND lower(details) LIKE '%emergency internal deployment during billing outage%'
            """
        ).fetchone()
        system_log_row = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count
            FROM system_logs
            WHERE module_name = 'License Override'
              AND lower(message) LIKE '%reason=emergency internal deployment during billing outage%'
            """
        ).fetchone()
        self.assertGreaterEqual(int(audit_row["row_count"] or 0), 1)
        self.assertGreaterEqual(int(system_log_row["row_count"] or 0), 1)

    def test_cashier_role_is_pos_limited(self):
        self.assertTrue(self.modules.user_has_permission("Cashier", "sell_pos"))
        self.assertTrue(self.modules.user_has_permission("Cashier", "close_cash_drawer"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_banking"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "manage_owner_equity_transactions"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "manage_loan_transactions"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "manage_cash_bank_transfers"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_reports"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "view_payroll"))
        self.assertFalse(self.modules.user_has_permission("Cashier", "post_accounting_document"))

    def test_auditor_is_read_only_for_reporting(self):
        self.assertTrue(self.modules.user_has_permission("Auditor / Read Only", "view_reports"))
        self.assertTrue(self.modules.user_has_permission("Auditor", "view_audit_trail"))
        self.assertTrue(self.modules.user_has_permission("Auditor", "view_system_health"))
        self.assertFalse(self.modules.user_has_permission("Auditor", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("Auditor", "void_or_reverse_document"))
        self.assertFalse(self.modules.user_has_permission("Auditor", "manage_company"))
        self.assertFalse(self.modules.user_has_permission("Auditor", "manage_users"))

    def test_accountant_can_post_but_not_manage_users(self):
        self.assertTrue(self.modules.user_has_permission("Accountant", "post_accounting_document"))
        self.assertTrue(self.modules.user_has_permission("Accountant", "view_reports"))
        self.assertTrue(self.modules.user_has_permission("Accountant", "view_banking"))
        self.assertFalse(self.modules.user_has_permission("Accountant", "manage_users"))
        self.assertFalse(self.modules.user_has_permission("Accountant", "manage_payroll"))

    def test_system_admin_can_manage_configuration_without_accounting_bypass(self):
        self.assertTrue(self.modules.user_has_permission("System Admin", "manage_company"))
        self.assertTrue(self.modules.user_has_permission("System Admin", "manage_users"))
        self.assertTrue(self.modules.user_has_permission("System Admin", "view_system_health"))
        self.assertFalse(self.modules.user_has_permission("System Admin", "post_accounting_document"))
        self.assertFalse(self.modules.user_has_permission("System Admin", "void_or_reverse_document"))
        self.assertFalse(self.modules.user_has_permission("System Admin", "manage_owner_equity_transactions"))

    def test_branch_access_helper_restricts_assigned_users(self):
        branch_user = {"role": "Branch_Bookkeeper", "branch_id": "BR-001"}
        self.assertTrue(self.modules.can_access_branch(branch_user, "BR-001"))
        self.assertTrue(self.modules.can_access_branch(branch_user, None))
        self.assertFalse(self.modules.can_access_branch(branch_user, "BR-002"))
        self.assertTrue(self.modules.can_access_branch({"role": "Master Admin"}, "BR-002"))

    def test_filter_by_user_branch_preserves_null_legacy_rows(self):
        rows = [
            {"branch_id": "BR-001", "value": 1},
            {"branch_id": "BR-002", "value": 2},
            {"branch_id": None, "value": 3},
        ]
        filtered = self.modules.filter_by_user_branch(rows, {"role": "Cashier", "branch_id": "BR-001"})
        self.assertEqual([row["value"] for row in filtered], [1, 3])
