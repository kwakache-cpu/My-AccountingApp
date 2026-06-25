import importlib
import inspect
from pathlib import Path

from test_support import ERPIsolatedTestCase, datetime_suffix


class MigrationCleanupUITests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.cleanup = importlib.import_module("migration_cleanup")

    def _create_branch(self, branch_id, branch_name):
        self.conn.execute(
            """
            INSERT INTO branches (
                branch_id, company_key, branch_name, branch_code, branch_type,
                branch_access_key, is_active
            )
            VALUES (?, ?, ?, ?, 'retail', ?, 1)
            """,
            (
                branch_id,
                self.company_key,
                branch_name,
                branch_name,
                f"KEY-{branch_id}",
            ),
        )
        self.commit()

    def _create_pos_sale(self, *, receipt_number=None, branch_id=""):
        receipt_number = receipt_number or f"POS-{datetime_suffix('R')}"
        sale_reference = f"REF-{datetime_suffix('S')}"
        cursor = self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number,
                sale_date, cashier, grand_total
            )
            VALUES (?, ?, ?, ?, ?, 'Cashier', 100.0)
            """,
            (
                self.company_key,
                branch_id,
                sale_reference,
                receipt_number,
                self.today.isoformat(),
            ),
        )
        self.commit()
        return int(cursor.lastrowid), receipt_number

    def test_parse_readiness_reads_top_warning_counts(self):
        summary = (
            "# Migration Integrity Summary\n\n"
            "**Overall readiness score:** **YELLOW**\n"
            "**Recommendation:** **GO WITH WARNINGS**\n\n"
            "## Top Warnings\n\n"
            "- **sales_without_branch_id:** 8 (MEDIUM)\n"
            "- **missing_manager_user_id:** 2 (LOW)\n"
        )
        path = self.data_dir / "migration_integrity_summary.md"
        path.write_text(summary, encoding="utf-8")
        snapshot = self.cleanup.parse_readiness_from_summary(path)
        self.assertEqual(sum(snapshot.warning_counts.values()), 10)
        self.assertEqual(snapshot.warning_counts.get("sales_without_branch_id"), 8)

    def test_build_readiness_uses_plan_json_counts(self):
        plan = {
            "pos_missing_branch_id": [{"id": 1}],
            "missing_manager_user_id": [{"id": 1}, {"id": 2}],
            "payments_without_reference": [],
            "invalid_expiry_dates": [],
        }
        plan_path = self.data_dir / "migration_cleanup_plan.json"
        plan_path.write_text(__import__("json").dumps(plan), encoding="utf-8")
        summary_path = self.data_dir / "migration_integrity_summary.md"
        summary_path.write_text(
            "**Overall readiness score:** **YELLOW**\n**Recommendation:** **GO WITH WARNINGS**\n"
            "## Top Warnings\n\n- **sales_without_branch_id:** 8 (MEDIUM)\n",
            encoding="utf-8",
        )
        snapshot = self.cleanup.build_readiness_snapshot(summary_path, plan_path)
        self.assertEqual(snapshot.plan_warning_total, 3)
        self.assertEqual(snapshot.display_warning_total, 3)

    def test_branch_list_with_grants_requires_role_argument(self):
        params = list(inspect.signature(self.modules._render_branch_list_with_grants).parameters)
        self.assertEqual(params, ["conn", "company_key", "role"])

    def test_only_dev_and_master_admin_can_access_cleanup_ui(self):
        self.assertTrue(self.cleanup.can_access_migration_cleanup("Dev"))
        self.assertTrue(self.cleanup.can_access_migration_cleanup("Master Admin"))
        self.assertFalse(self.cleanup.can_access_migration_cleanup("Staff"))
        self.assertFalse(self.cleanup.can_access_migration_cleanup("Bookkeeper"))
        self.assertTrue(self.modules.can_access_migration_cleanup("Dev"))
        self.assertFalse(self.modules.can_access_migration_cleanup("Staff"))

    def test_pos_branch_assignment_updates_only_branch_id(self):
        branch_id = f"{self.company_key}-main"
        self._create_branch(branch_id, "Main")
        sale_id, receipt_number = self._create_pos_sale(branch_id="")
        result = self.cleanup.assign_pos_sale_branch_id(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            branch_id=branch_id,
            actor_role="Master Admin",
            confirmed=True,
        )
        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT branch_id, receipt_number FROM pos_sales WHERE id = ?",
            (sale_id,),
        ).fetchone()
        self.assertEqual(row["branch_id"], branch_id)
        self.assertEqual(row["receipt_number"], receipt_number)

    def test_pos_branch_assignment_requires_confirmation(self):
        branch_id = f"{self.company_key}-main2"
        self._create_branch(branch_id, "Main2")
        sale_id, _ = self._create_pos_sale()
        result = self.cleanup.assign_pos_sale_branch_id(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            branch_id=branch_id,
            actor_role="Master Admin",
            confirmed=False,
        )
        self.assertFalse(result["ok"])
        row = self.conn.execute(
            "SELECT branch_id FROM pos_sales WHERE id = ?",
            (sale_id,),
        ).fetchone()
        self.assertEqual(str(row["branch_id"] or "").strip(), "")

    def test_manager_link_uses_same_company_user(self):
        branch_id = f"{self.company_key}-mgr"
        self._create_branch(branch_id, "Mgr Branch")
        user_id = "user-mgr-test-001"
        self.conn.execute(
            """
            INSERT INTO users (company_key, user_id, full_name, role, login_key, status, branch_id)
            VALUES (?, ?, 'Manager Person', 'Staff', 'mgr.login', 'Active', ?)
            """,
            (self.company_key, user_id, branch_id),
        )
        self.commit()
        result = self.database.assign_branch_manager(
            self.conn,
            self.company_key,
            branch_id,
            user_id,
            promote_to_branch_manager=True,
        )
        self.assertTrue(result["ok"])
        branch = self.conn.execute(
            "SELECT manager_user_id FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        self.assertEqual(branch["manager_user_id"], user_id)
        user = self.conn.execute(
            "SELECT company_key, branch_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        self.assertEqual(user["company_key"], self.company_key)
        self.assertEqual(user["branch_id"], branch_id)

    def test_cleanup_manager_link_preserves_existing_user_state(self):
        branch_id = f"{self.company_key}-cleanup-mgr"
        self._create_branch(branch_id, "Cleanup Mgr Branch")
        user_id = "user-cleanup-mgr-001"
        self.conn.execute(
            """
            INSERT INTO users (company_key, user_id, full_name, role, login_key, status, branch_id)
            VALUES (?, ?, 'Cleanup Manager', 'Staff', 'cleanup.mgr.login', 'Active', NULL)
            """,
            (self.company_key, user_id),
        )
        self.commit()
        result = self.cleanup.assign_branch_manager_user_id(
            self.conn,
            company_key=self.company_key,
            branch_id=branch_id,
            manager_user_id=user_id,
            actor_role="Master Admin",
            confirmed=True,
        )
        self.assertTrue(result["ok"])
        branch = self.conn.execute(
            "SELECT branch_manager, manager_user_id FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        self.assertEqual(branch["manager_user_id"], user_id)
        self.assertEqual(branch["branch_manager"], "Cleanup Manager")
        user = self.conn.execute(
            "SELECT role, branch_id FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        self.assertEqual(user["role"], "Staff")
        self.assertIsNone(user["branch_id"])
        self.assertEqual(result["before"]["user_role"], "Staff")
        self.assertEqual(result["after"]["user_role"], "Staff")

    def test_cleanup_manager_link_requires_active_user(self):
        branch_id = f"{self.company_key}-inactive-mgr"
        self._create_branch(branch_id, "Inactive Mgr Branch")
        user_id = "user-inactive-mgr-001"
        self.conn.execute(
            """
            INSERT INTO users (company_key, user_id, full_name, role, login_key, status, branch_id)
            VALUES (?, ?, 'Inactive Manager', 'Staff', 'inactive.mgr.login', 'Inactive', NULL)
            """,
            (self.company_key, user_id),
        )
        self.commit()
        result = self.cleanup.assign_branch_manager_user_id(
            self.conn,
            company_key=self.company_key,
            branch_id=branch_id,
            manager_user_id=user_id,
            actor_role="Master Admin",
            confirmed=True,
        )
        self.assertFalse(result["ok"])
        branch = self.conn.execute(
            "SELECT manager_user_id FROM branches WHERE branch_id = ?",
            (branch_id,),
        ).fetchone()
        self.assertIsNone(branch["manager_user_id"])

    def test_payment_fix_refuses_without_confirmation(self):
        customer_id = self.create_customer("Pay Customer")
        payment_id = self.conn.execute(
            """
            INSERT INTO payments (
                company_key, payment_date, payment_type, status,
                customer_id, invoice_id, bill_id, amount, currency, method, reference, created_by
            )
            VALUES (?, ?, 'Customer Receipt', 'Posted', NULL, NULL, NULL, 50.0, 'GHS', 'Cash', '', 'test')
            """,
            (self.company_key, self.today.isoformat()),
        ).lastrowid
        self.commit()
        result = self.cleanup.apply_payment_reference_fix(
            self.conn,
            company_key=self.company_key,
            payment_id=int(payment_id),
            customer_id=customer_id,
            reference="Receipt ref",
            actor_role="Master Admin",
            confirmed=False,
            confirmation_text=self.cleanup.CONFIRM_PAYMENT_APPLY_TEXT,
            create_backup=False,
        )
        self.assertFalse(result["ok"])
        row = self.conn.execute(
            "SELECT customer_id, reference FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertIsNone(row["customer_id"])
        self.assertEqual(str(row["reference"] or "").strip(), "")

    def test_payment_fix_updates_only_customer_id_and_reference(self):
        customer_id = self.create_customer("Pay Customer Two")
        payment_id = self.conn.execute(
            """
            INSERT INTO payments (
                company_key, payment_date, payment_type, status,
                customer_id, invoice_id, bill_id, amount, currency, method, reference, created_by
            )
            VALUES (?, ?, 'Customer Receipt', 'Posted', NULL, NULL, NULL, 75.0, 'GHS', 'Bank', '', 'test')
            """,
            (self.company_key, self.today.isoformat()),
        ).lastrowid
        self.commit()
        before = self.conn.execute(
            "SELECT amount, method, payment_type FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        result = self.cleanup.apply_payment_reference_fix(
            self.conn,
            company_key=self.company_key,
            payment_id=int(payment_id),
            customer_id=customer_id,
            reference="Linked receipt",
            actor_role="Master Admin",
            confirmed=True,
            confirmation_text=self.cleanup.CONFIRM_PAYMENT_APPLY_TEXT,
            create_backup=False,
        )
        self.assertTrue(result["ok"])
        after = self.conn.execute(
            "SELECT customer_id, reference, amount, method, payment_type FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(after["customer_id"], customer_id)
        self.assertEqual(after["reference"], "Linked receipt")
        self.assertEqual(after["amount"], before["amount"])
        self.assertEqual(after["method"], before["method"])
        self.assertEqual(after["payment_type"], before["payment_type"])
        self.assertEqual(result["before"]["reference"], "")
        self.assertEqual(result["after"]["reference"], "Linked receipt")
        self.assertEqual(result["after"]["customer_id"], customer_id)

    def test_audit_log_entry_created_for_pos_assignment(self):
        branch_id = f"{self.company_key}-audit"
        self._create_branch(branch_id, "Audit Branch")
        sale_id, _ = self._create_pos_sale()
        before_count = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count FROM audit_logs
            WHERE company_key = ? AND module_name = 'Migration Cleanup'
            """,
            (self.company_key,),
        ).fetchone()["row_count"]
        result = self.cleanup.assign_pos_sale_branch_id(
            self.conn,
            company_key=self.company_key,
            sale_id=sale_id,
            branch_id=branch_id,
            actor_role="Dev",
            confirmed=True,
        )
        self.assertTrue(result["ok"])
        after_count = self.conn.execute(
            """
            SELECT COUNT(*) AS row_count FROM audit_logs
            WHERE company_key = ? AND module_name = 'Migration Cleanup'
            """,
            (self.company_key,),
        ).fetchone()["row_count"]
        self.assertGreater(after_count, before_count)
