"""
Program A P0 Sprint 3 — bill vs inventory receive clarity and regression safety.
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


class ProgramAP0CreateBillUiClarityTests(unittest.TestCase):
    def setUp(self):
        self.modules = importlib.import_module("modules")
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            self.modules_source = handle.read()
        self.create_bill_block = _extract_function_block(self.modules_source, "show_create_bill_page")

    def test_create_bill_notice_constants_are_defined(self):
        self.assertIn("supplier liability/accounting", self.modules.CREATE_BILL_ACCOUNTING_NOTICE)
        self.assertIn("does not receive stock", self.modules.CREATE_BILL_ACCOUNTING_NOTICE)
        self.assertIn("will not increase", self.modules.CREATE_BILL_INVENTORY_QTY_NOTICE)
        self.assertIn("Receive Stock", self.modules.CREATE_BILL_INVENTORY_NEXT_STEP)
        self.assertIn("payment is settled", self.modules.CREATE_BILL_PAYMENT_STATUS_NOTICE)
        self.assertIn("not that stock was received", self.modules.CREATE_BILL_PAYMENT_STATUS_NOTICE.lower())

    def test_create_bill_page_renders_workflow_guidance(self):
        self.assertIn("_render_create_bill_workflow_guidance", self.create_bill_block)
        self.assertIn("CREATE_BILL_INVENTORY_QTY_NOTICE", self.create_bill_block)
        self.assertIn("CREATE_BILL_INVENTORY_NEXT_STEP", self.create_bill_block)
        self.assertIn("CREATE_BILL_PAYMENT_STATUS_NOTICE", self.create_bill_block)
        self.assertIn("Inventory Purchase", self.create_bill_block)
        self.assertIn("Payment Status", self.create_bill_block)


class ProgramAP0BillInventorySeparationTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.engine = importlib.import_module("accounting_engine")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.commit()

    def _insert_inventory_item(self, *, qty=4.0):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Bill Clarity Item", "BCI-01", "88001", qty, 12.0, 6.0, 2.0),
        )
        self.commit()
        return int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE company_key = ? AND item_code = 'BCI-01'",
                (self.company_key,),
            ).fetchone()["id"]
        )

    def test_posted_inventory_bill_does_not_create_stock_movement_or_qty_change(self):
        supplier_id = self.create_supplier("Bill Clarity Supplier")
        item_id = self._insert_inventory_item(qty=4.0)
        before_qty = float(
            self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"]
        )
        before_movements = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM stock_movements WHERE company_key = ?",
                (self.company_key,),
            ).fetchone()["c"]
        )

        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=60.0)
        journal_lines, _ = self.modules.build_purchase_journal_lines(
            self.conn,
            self.company_key,
            classification="Inventory Purchase",
            amount=60.0,
            input_vat=0.0,
            status="Pending",
        )
        self.post_entry(
            lines=build_lines(*journal_lines),
            description="Inventory-classified supplier bill",
            reference="BILL-CLARITY-001",
            source_table="bills",
            source_id=bill_id,
            source_type="Bill",
            supplier_id=supplier_id,
        )
        self.commit()

        after_qty = float(
            self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"]
        )
        after_movements = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM stock_movements WHERE company_key = ?",
                (self.company_key,),
            ).fetchone()["c"]
        )
        self.assertEqual(after_qty, before_qty)
        self.assertEqual(after_movements, before_movements)
        self.assertEqual(
            self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn),
            60.0,
        )

    def test_inventory_receive_path_remains_separate_from_bill_posting(self):
        item_id = self._insert_inventory_item(qty=2.0)
        before_qty = float(
            self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"]
        )
        receive_result = self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            "Inventory Officer",
            inventory_item_id=item_id,
            qty_received=5.0,
            unit_cost=6.0,
            supplier_name="Separate Receive Supplier",
            reference_number="RCV-CLARITY-001",
            branch_id="",
        )
        self.commit()

        movement = self.conn.execute(
            """
            SELECT movement_type, reference
            FROM stock_movements
            WHERE company_key = ? AND inventory_item_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (self.company_key, item_id),
        ).fetchone()
        self.assertEqual(receive_result["new_qty"], before_qty + 5.0)
        self.assertEqual(movement["movement_type"], "STOCK_IN")
        self.assertEqual(movement["reference"], "RCV-CLARITY-001")

    def test_build_purchase_journal_lines_inventory_classification_unchanged(self):
        journal_lines, meta = self.modules.build_purchase_journal_lines(
            self.conn,
            self.company_key,
            classification="Inventory Purchase",
            amount=100.0,
            input_vat=12.5,
            status="Pending",
        )
        self.assertEqual(meta["classification"], "Inventory Purchase")
        self.assertEqual(meta["debit_account_name"], "Inventory")
        self.assertEqual(meta["credit_account_name"], "Accounts Payable")
        debits = sum(float(line["debit"]) for line in journal_lines)
        credits = sum(float(line["credit"]) for line in journal_lines)
        self.assertAlmostEqual(debits, credits, places=2)
        self.assertAlmostEqual(debits, 112.5, places=2)

    def test_show_create_bill_page_does_not_call_stock_receive_helpers(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            block = _extract_function_block(handle.read(), "show_create_bill_page")
        for forbidden in (
            "_receive_inventory_stock",
            "_insert_stock_movement_record",
            "UPDATE inventory",
        ):
            self.assertNotIn(forbidden, block, msg=f"show_create_bill_page must not call {forbidden}")


class ProgramAP0CreateBillClientSurfaceTests(unittest.TestCase):
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

    def test_show_create_bill_has_no_client_diagnostics(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            block = _extract_function_block(handle.read(), "show_create_bill_page")
        for marker in self._FORBIDDEN_CLIENT_MARKERS:
            self.assertNotIn(marker, block, msg=f"show_create_bill_page must not call {marker}")


class ProgramAP0BillInventoryPortabilityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_build_purchase_journal_lines_uses_portable_account_helpers(self):
        source = inspect.getsource(self.modules.build_purchase_journal_lines)
        self.assertIn("get_or_create_account", source)
        lowered = source.lower()
        for forbidden in ("date(", "datetime(", "strftime(", "julianday(", "ifnull("):
            self.assertNotIn(forbidden, lowered, msg=f"Bill journal builder should avoid sqlite helper: {forbidden}")

    def test_receive_inventory_stock_source_avoids_sqlite_specific_helpers(self):
        source = inspect.getsource(self.modules._receive_inventory_stock)
        lowered = source.lower()
        for forbidden in ("julianday(", "ifnull("):
            self.assertNotIn(forbidden, lowered, msg=f"Receive stock should avoid sqlite helper: {forbidden}")
