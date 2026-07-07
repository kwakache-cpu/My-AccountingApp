"""
Program B P0 Sprint 1 — POS posting permission hardening.
"""
import importlib
import inspect
import os
import unittest

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix


def _extract_function_block(source_text, function_name):
    marker = f"def {function_name}("
    start = source_text.find(marker)
    if start < 0:
        return ""
    next_def = source_text.find("\ndef ", start + len(marker))
    return source_text[start:] if next_def < 0 else source_text[start:next_def]


def _extract_nested_block(source_text, outer_name, inner_marker):
    outer = _extract_function_block(source_text, outer_name)
    inner_start = outer.find(inner_marker)
    if inner_start < 0:
        return ""
    return outer[inner_start:]


class ProgramBP0PosPostingSourceTests(unittest.TestCase):
    def setUp(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            self.modules_source = handle.read()
        self.checkout_block = _extract_nested_block(
            self.modules_source,
            "show_pos",
            "def _pos_checkout_write(conn, pos_backend_diagnostics):",
        )

    def test_pos_checkout_passes_user_role_on_sale_and_cogs_posts(self):
        self.assertIn('source_type="POS Sale"', self.checkout_block)
        self.assertIn('source_type="POS COGS"', self.checkout_block)
        sale_idx = self.checkout_block.index('source_type="POS Sale"')
        cogs_idx = self.checkout_block.index('source_type="POS COGS"')
        self.assertIn("user_role=role", self.checkout_block[sale_idx : sale_idx + 200])
        self.assertIn("user_role=role", self.checkout_block[cogs_idx : cogs_idx + 200])

    def test_process_pos_return_already_passes_user_role(self):
        return_block = _extract_function_block(self.modules_source, "_process_pos_return")
        self.assertIn("user_role=role", return_block)


class ProgramBP0PosPostingPermissionTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_pos_sales_schema(self.conn)
        self.commit()

    def _pos_sale_lines(self, amount=25.0):
        return build_lines(
            {"account_id": self.account_id("Cash", "Asset"), "debit": amount, "credit": 0.0},
            {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": amount},
        )

    def _insert_pos_sale_stub(self):
        sale_reference = f"POS-PERM-{datetime_suffix('P')}"
        cursor = self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number,
                sale_date, cashier, grand_total
            )
            VALUES (?, 'MAIN', ?, ?, ?, 'Cashier', 25.0)
            """,
            (self.company_key, sale_reference, sale_reference, self.today.isoformat()),
        )
        self.commit()
        return int(cursor.lastrowid), sale_reference

    def test_cashier_can_post_pos_scoped_journal_with_sell_pos(self):
        pos_sale_id, sale_reference = self._insert_pos_sale_stub()
        entry_id = self.engine.post_accounting_impact(
            company_key=self.company_key,
            date=self.today,
            description="Cashier POS sale",
            reference=sale_reference,
            lines=self._pos_sale_lines(),
            created_by="Cashier",
            branch_id="MAIN",
            source_module="POS",
            source_table="pos_sales",
            source_type="POS Sale",
            source_id=pos_sale_id,
            user_role="Cashier",
            conn=self.conn,
        )
        self.commit()
        self.assertGreater(entry_id, 0)
        self.assertFalse(self.modules.user_has_permission("Cashier", "post_accounting_document"))

    def test_sales_officer_can_post_pos_scoped_journal(self):
        pos_sale_id, sale_reference = self._insert_pos_sale_stub()
        entry_id = self.engine.post_accounting_impact(
            company_key=self.company_key,
            date=self.today,
            description="Sales officer POS sale",
            reference=sale_reference,
            lines=self._pos_sale_lines(),
            created_by="Sales Officer",
            source_module="POS",
            source_table="pos_sales",
            source_type="POS Sale",
            source_id=pos_sale_id,
            user_role="Sales Officer",
            conn=self.conn,
        )
        self.commit()
        self.assertGreater(entry_id, 0)

    def test_unauthorized_role_cannot_post_through_pos(self):
        pos_sale_id, sale_reference = self._insert_pos_sale_stub()
        for role in ("Auditor / Read Only", "Inventory Officer", "Demo"):
            with self.subTest(role=role):
                with self.assertRaisesRegex(PermissionError, "not allowed to post accounting impact"):
                    self.engine.post_accounting_impact(
                        company_key=self.company_key,
                        date=self.today,
                        description="Blocked POS post",
                        reference=f"{sale_reference}-{role}",
                        lines=self._pos_sale_lines(),
                        created_by=role,
                        source_module="POS",
                        source_table="pos_sales",
                        source_type="POS Sale",
                        source_id=pos_sale_id,
                        user_role=role,
                        conn=self.conn,
                    )
                self.conn.rollback()

    def test_sell_pos_role_cannot_bypass_manual_journal_posting(self):
        with self.assertRaisesRegex(PermissionError, "not allowed to post accounting impact"):
            self.engine.post_accounting_impact(
                company_key=self.company_key,
                date=self.today,
                description="Cashier manual journal attempt",
                reference="POS-BYPASS-MANUAL",
                lines=self._pos_sale_lines(),
                created_by="Cashier",
                source_module="Operational Posting",
                source_table="journal_entries",
                source_type="Manual",
                source_id=901,
                user_role="Cashier",
                conn=self.conn,
            )
        self.assertEqual(self.journal_count(source_table="journal_entries", source_id=901), 0)

    def test_pos_sale_still_posts_balanced_journal(self):
        pos_sale_id, sale_reference = self._insert_pos_sale_stub()
        entry_id = self.engine.post_accounting_impact(
            company_key=self.company_key,
            date=self.today,
            description="Balanced POS sale",
            reference=sale_reference,
            lines=self._pos_sale_lines(40.0),
            created_by="Cashier",
            source_module="POS",
            source_table="pos_sales",
            source_type="POS Sale",
            source_id=pos_sale_id,
            user_role="Cashier",
            conn=self.conn,
        )
        self.commit()
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(debit), 0) AS debits, COALESCE(SUM(credit), 0) AS credits
            FROM journal_lines
            WHERE entry_id = ?
            """,
            (entry_id,),
        ).fetchone()
        self.assertAlmostEqual(float(row["debits"]), 40.0, places=2)
        self.assertAlmostEqual(float(row["credits"]), 40.0, places=2)

    def test_pos_inventory_decrement_unchanged_with_permissioned_post(self):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, 'POS Perm Item', 'PPI-1', '99001', 6.0, 15.0, 5.0, 1.0)
            """,
            (self.company_key,),
        )
        self.commit()
        item_id = int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE item_code = 'PPI-1' AND company_key = ?",
                (self.company_key,),
            ).fetchone()["id"]
        )
        before_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.database.execute_portable_write(
            self.conn,
            "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
            (2.0, item_id, self.company_key),
        )
        pos_sale_id, sale_reference = self._insert_pos_sale_stub()
        self.engine.post_accounting_impact(
            company_key=self.company_key,
            date=self.today,
            description="POS inventory path",
            reference=sale_reference,
            lines=self._pos_sale_lines(),
            created_by="Cashier",
            source_module="POS",
            source_table="pos_sales",
            source_type="POS Sale",
            source_id=pos_sale_id,
            user_role="Cashier",
            conn=self.conn,
        )
        self.commit()
        after_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(after_qty, before_qty - 2.0)


class ProgramBP0PosClientSurfaceTests(unittest.TestCase):
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

    def test_show_pos_has_no_client_diagnostics(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            block = _extract_function_block(handle.read(), "show_pos")
        for marker in self._FORBIDDEN_CLIENT_MARKERS:
            self.assertNotIn(marker, block, msg=f"show_pos must not call {marker}")


class ProgramBP0PosPostingPortabilityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")

    def test_pos_scoped_posting_check_uses_portable_permission_helpers(self):
        module_source = inspect.getsource(self.engine)
        self.assertIn("_POS_SCOPED_POSTING_PERMISSIONS", module_source)
        self.assertIn('"sell_pos"', module_source)
        assert_source = inspect.getsource(self.engine._assert_posting_role_allowed)
        self.assertIn("post_accounting_document", assert_source)
        lowered = assert_source.lower()
        for forbidden in ("julianday(", "ifnull(", "strftime("):
            self.assertNotIn(forbidden, lowered, msg=f"POS posting permission check should avoid {forbidden}")

    def test_post_accounting_impact_forwards_source_module_to_role_assertion(self):
        source = inspect.getsource(self.engine.post_accounting_impact)
        self.assertIn("source_module=source_module", source)
