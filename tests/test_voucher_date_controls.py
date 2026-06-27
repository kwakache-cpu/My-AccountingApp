from datetime import date, datetime, timedelta

from test_support import ERPIsolatedTestCase, build_lines


class VoucherDateControlsTests(ERPIsolatedTestCase):
    def _balanced_lines(self, amount=25.0):
        return build_lines(
            {"account_id": self.account_id("Cash", "Asset"), "debit": amount, "credit": 0.0},
            {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": amount},
        )

    def test_future_date_selector_returns_warning_without_blocking_authorized_posting(self):
        future_date = datetime.now().date() + timedelta(days=7)
        status = self.engine.get_period_control_diagnostics(self.company_key, as_of_date=future_date, conn=self.conn)
        operational_status = __import__("modules").get_operational_date_control_status(
            self.company_key,
            future_date,
            actor_role="Accountant",
            conn=self.conn,
        )

        self.assertIn("current_period", status)
        self.assertTrue(operational_status["is_future_date"])
        self.assertFalse(operational_status["posting_blocked"])
        self.assertTrue(any("Future-dated" in warning for warning in operational_status["warnings"]))

    def test_locked_period_blocks_voucher_or_journal_posting_date(self):
        self.create_period("2026-02", date(2026, 2, 1), date(2026, 2, 28), status="Locked", is_locked=1)

        with self.assertRaisesRegex(ValueError, "period.*locked"):
            self.post_entry(
                lines=self._balanced_lines(),
                description="Locked period voucher date",
                reference="LOCKED-VOUCHER-DATE",
                user_role="Accountant",
                posting_date=date(2026, 2, 15),
            )

    def test_period_status_changes_are_permissioned_and_audited(self):
        with self.assertRaises(PermissionError):
            __import__("modules").set_period_status(self.company_key, date(2026, 5, 1), "Locked", changed_by="Cashier")

        __import__("modules").set_period_status(self.company_key, date(2026, 5, 1), "Locked", changed_by="Master Admin")
        audit_row = self.conn.execute(
            """
            SELECT action, document_ref
            FROM audit_logs
            WHERE company_key = ? AND module_name = 'Period Control'
            ORDER BY id DESC LIMIT 1
            """,
            (self.company_key,),
        ).fetchone()

        self.assertEqual(audit_row["action"], "Accounting Period Locked")
        self.assertEqual(audit_row["document_ref"], "2026-05")
