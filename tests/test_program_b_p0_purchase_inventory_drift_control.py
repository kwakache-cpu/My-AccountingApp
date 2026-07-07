"""
Program B P0 Sprint 2 — purchase / inventory drift control.
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


class ProgramBP0PurchaseInventoryDriftLogicTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.engine = importlib.import_module("accounting_engine")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.commit()

    def _insert_inventory_item(self, *, qty=5.0):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Drift Item", "DRF-01", "88002", qty, 10.0, 4.0, 1.0),
        )
        self.commit()
        return int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE item_code = 'DRF-01' AND company_key = ?",
                (self.company_key,),
            ).fetchone()["id"]
        )

    def _post_inventory_bill(self, supplier_id, bill_number, amount=80.0):
        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=amount)
        self.conn.execute(
            "UPDATE bills SET bill_number = ?, purchase_classification = ? WHERE id = ?",
            (bill_number, "Inventory Purchase", bill_id),
        )
        journal_lines, _ = self.modules.build_purchase_journal_lines(
            self.conn,
            self.company_key,
            classification="Inventory Purchase",
            amount=amount,
            input_vat=0.0,
            status="Pending",
        )
        self.post_entry(
            lines=build_lines(*journal_lines),
            description="Drift control inventory bill",
            reference=bill_number,
            source_table="bills",
            source_id=bill_id,
            source_type="Bill",
            supplier_id=supplier_id,
        )
        self.commit()
        return bill_id, bill_number

    def test_posted_inventory_bill_identified_as_gl_posted_stock_not_received(self):
        supplier_id = self.create_supplier("Drift Supplier")
        item_id = self._insert_inventory_item(qty=6.0)
        before_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        bill_number = f"BILL-DRIFT-{datetime_suffix('B')}"
        bill_id, bill_number = self._post_inventory_bill(supplier_id, bill_number)
        bill_row = self.conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
        status = self.modules.compute_purchase_inventory_status(self.conn, self.company_key, bill_row)
        after_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])

        self.assertTrue(status["bill_posted_to_gl"])
        self.assertTrue(status["inventory_gl_posted"])
        self.assertFalse(status["stock_received"])
        self.assertFalse(status["quantity_updated"])
        self.assertTrue(status["is_drift_risk"])
        self.assertEqual(after_qty, before_qty)
        unmatched = self.modules._fetch_posted_inventory_bills_missing_stock(self.conn, self.company_key)
        self.assertTrue(any(row["bill_number"] == bill_number for row in unmatched))

    def test_linked_receive_clears_drift_risk(self):
        supplier_id = self.create_supplier("Linked Supplier")
        item_id = self._insert_inventory_item(qty=3.0)
        bill_number = f"BILL-LINK-{datetime_suffix('L')}"
        bill_id, bill_number = self._post_inventory_bill(supplier_id, bill_number)
        self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            "Inventory Officer",
            inventory_item_id=item_id,
            qty_received=4.0,
            reference_number=bill_number,
            branch_id="",
        )
        self.commit()
        bill_row = self.conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
        status = self.modules.compute_purchase_inventory_status(self.conn, self.company_key, bill_row)
        after_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])

        self.assertTrue(status["stock_received"])
        self.assertTrue(status["quantity_updated"])
        self.assertFalse(status["is_drift_risk"])
        self.assertEqual(after_qty, 7.0)
        unmatched = self.modules._fetch_posted_inventory_bills_missing_stock(self.conn, self.company_key)
        self.assertFalse(any(row["bill_number"] == bill_number for row in unmatched))

    def test_unlinked_receive_identified_as_quantity_updated_without_bill(self):
        item_id = self._insert_inventory_item(qty=2.0)
        reference = f"RCV-UNLINKED-{datetime_suffix('R')}"
        self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            "Inventory Officer",
            inventory_item_id=item_id,
            qty_received=1.0,
            reference_number=reference,
            branch_id="",
        )
        self.commit()
        link_status = self.modules.compute_stock_receipt_link_status(self.conn, self.company_key, reference)
        unmatched = self.modules._fetch_stock_receipts_missing_bill_link(self.conn, self.company_key)

        self.assertTrue(link_status["quantity_updated"])
        self.assertTrue(link_status["is_unlinked_receipt"])
        self.assertFalse(link_status["bill_posted_to_gl"])
        self.assertTrue(any(row.get("reference") == reference for row in unmatched))

    def test_missing_reference_flagged_on_receive_preview(self):
        preview = self.modules.compute_stock_receipt_link_status(self.conn, self.company_key, "")
        self.assertTrue(preview["missing_bill_reference"])
        self.assertTrue(preview["is_unlinked_receipt"])


class ProgramBP0PurchaseInventoryUiTests(unittest.TestCase):
    def setUp(self):
        self.modules = importlib.import_module("modules")
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            self.modules_source = handle.read()
        self.create_bill_block = _extract_function_block(self.modules_source, "show_create_bill_page")
        self.inventory_block = _extract_function_block(self.modules_source, "show_inventory")

    def test_create_bill_page_shows_drift_monitor_and_warning(self):
        self.assertIn("_render_purchase_inventory_drift_monitor", self.create_bill_block)
        self.assertIn("PURCHASE_INVENTORY_UNRECEIVED_BILL_NOTICE", self.create_bill_block)
        self.assertIn("is_drift_risk", self.create_bill_block)

    def test_inventory_receive_page_shows_bill_link_warning(self):
        self.assertIn("INVENTORY_RECEIVE_BILL_LINK_NOTICE", self.inventory_block)
        self.assertIn("compute_stock_receipt_link_status", self.inventory_block)
        self.assertIn("_render_purchase_inventory_drift_monitor", self.inventory_block)
        self.assertIn("missing_bill_reference", self.inventory_block)


class ProgramBP0PurchaseInventoryClientSurfaceTests(unittest.TestCase):
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

    def test_client_pages_have_no_diagnostics(self):
        modules_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "modules.py")
        with open(modules_path, encoding="utf-8") as handle:
            source = handle.read()
        for function_name in ("show_create_bill_page", "show_inventory"):
            block = _extract_function_block(source, function_name)
            for marker in self._FORBIDDEN_CLIENT_MARKERS:
                self.assertNotIn(marker, block, msg=f"{function_name} must not call {marker}")


class ProgramBP0PurchaseInventoryPortabilityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_drift_queries_use_portable_sql(self):
        for function_name in (
            "_fetch_posted_inventory_bills_missing_stock",
            "_fetch_stock_receipts_missing_bill_link",
            "_bill_has_linked_stock_receipt",
        ):
            source = inspect.getsource(getattr(self.modules, function_name))
            lowered = source.lower()
            for forbidden in ("julianday(", "ifnull(", "strftime("):
                self.assertNotIn(forbidden, lowered, msg=f"{function_name} should avoid {forbidden}")
            self.assertIn("COALESCE", source)
