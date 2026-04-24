import importlib

from test_support import ERPIsolatedTestCase, build_lines


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
