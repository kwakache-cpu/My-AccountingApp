"""
Program B P0 Sprint 3 — Inventory Movement Integrity.

Guarantees every inventory quantity mutation creates exactly one auditable
stock_movements row with branch context and before/after quantities.
"""
import importlib
import inspect
import unittest
from types import SimpleNamespace
from unittest import mock

from test_support import ERPIsolatedTestCase, datetime_suffix


class ProgramBP0InventoryMovementIntegrityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.branch_id = "MAIN"
        self.role = "Manager"
        self._ensure_branch(self.branch_id, "Main Branch")
        self.commit()

    def _ensure_branch(self, branch_id, branch_name=None):
        existing = self.conn.execute(
            "SELECT branch_id FROM branches WHERE company_key = ? AND branch_id = ?",
            (self.company_key, branch_id),
        ).fetchone()
        if existing:
            return branch_id
        self.conn.execute(
            """
            INSERT INTO branches (branch_id, company_key, branch_name, location, branch_type, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                branch_id,
                self.company_key,
                branch_name or branch_id,
                "Accra",
                "main",
            ),
        )
        return branch_id

    def _insert_item(self, *, qty=10.0, item_code="MOV-01", barcode="77001", name="Integrity Item"):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, name, item_code, barcode, qty, 12.0, 5.0, 1.0),
        )
        self.commit()
        return int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE item_code = ? AND company_key = ?",
                (item_code, self.company_key),
            ).fetchone()["id"]
        )

    def _latest_movement(self, item_id=None):
        query = """
            SELECT *
            FROM stock_movements
            WHERE company_key = ?
        """
        params = [self.company_key]
        if item_id is not None:
            query += " AND inventory_item_id = ?"
            params.append(int(item_id))
        query += " ORDER BY id DESC LIMIT 1"
        return self.conn.execute(query, tuple(params)).fetchone()

    def _movement_count(self, item_id=None):
        query = "SELECT COUNT(*) AS c FROM stock_movements WHERE company_key = ?"
        params = [self.company_key]
        if item_id is not None:
            query += " AND inventory_item_id = ?"
            params.append(int(item_id))
        return int(self.conn.execute(query, tuple(params)).fetchone()["c"])

    def _assert_movement_integrity(
        self,
        movement,
        *,
        movement_type,
        before_qty,
        after_qty,
        quantity,
        branch_id="MAIN",
        item_id=None,
    ):
        self.assertIsNotNone(movement)
        self.assertEqual(movement["company_key"], self.company_key)
        self.assertEqual(str(movement["branch_id"] or ""), str(branch_id))
        self.assertEqual(self.modules._normalize_stock_movement_type(movement["movement_type"]), movement_type)
        self.assertAlmostEqual(float(movement["previous_qty"]), float(before_qty), places=4)
        self.assertAlmostEqual(float(movement["new_qty"]), float(after_qty), places=4)
        self.assertAlmostEqual(float(movement["quantity"]), abs(float(quantity)), places=4)
        self.assertTrue(str(movement["created_by"] or "").strip())
        self.assertTrue(str(movement["created_at"] or "").strip())
        if item_id is not None:
            self.assertEqual(int(movement["inventory_item_id"]), int(item_id))
        notes = str(movement["notes"] or "")
        self.assertIn("source_document=", notes)

    def test_pos_sale_writes_one_movement_with_before_after(self):
        item_id = self._insert_item(qty=10.0)
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="POS_SALE",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-3.0,
            reason="POS Sale",
            reference=f"POS-{datetime_suffix('S')}-{item_id}",
            source_document="pos_sale",
            source_id="token-1",
        )
        self.commit()
        self.assertEqual(result["before_qty"], 10.0)
        self.assertEqual(result["after_qty"], 7.0)
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 7.0)
        self.assertEqual(self._movement_count(item_id), 1)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="POS_SALE",
            before_qty=10.0,
            after_qty=7.0,
            quantity=3.0,
            item_id=item_id,
        )

    def test_pos_return_restocks_with_movement(self):
        self._ensure_branch("BR-EAST", "East Branch")
        self.commit()
        item_id = self._insert_item(qty=4.0)
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="POS_RETURN",
            created_by=self.role,
            branch_id="BR-EAST",
            quantity_delta=2.0,
            reason="Customer return",
            reference=f"RET-{datetime_suffix('R')}-{item_id}",
            source_document="pos_return",
            source_id="ret-1",
        )
        self.commit()
        self.assertEqual(result["after_qty"], 6.0)
        movement = self._latest_movement(item_id)
        self._assert_movement_integrity(
            movement,
            movement_type="POS_RETURN",
            before_qty=4.0,
            after_qty=6.0,
            quantity=2.0,
            branch_id="BR-EAST",
            item_id=item_id,
        )

    def test_inventory_receive_creates_stock_in_movement(self):
        item_id = self._insert_item(qty=2.0)
        receive = self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            self.role,
            inventory_item_id=item_id,
            qty_received=5.0,
            reference_number=f"RCV-{datetime_suffix('R')}",
            branch_id=self.branch_id,
        )
        self.commit()
        self.assertEqual(receive["new_qty"], 7.0)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="STOCK_IN",
            before_qty=2.0,
            after_qty=7.0,
            quantity=5.0,
            item_id=item_id,
        )

    def test_inventory_adjustment_target_qty(self):
        item_id = self._insert_item(qty=8.0)
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="ADJUSTMENT",
            created_by=self.role,
            branch_id=self.branch_id,
            target_qty=5.0,
            reason="Cycle count",
            reference=f"ADJ-{datetime_suffix('A')}",
            source_document="stock_adjustment",
            source_id="adj-1",
        )
        self.commit()
        self.assertEqual(result["after_qty"], 5.0)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="ADJUSTMENT",
            before_qty=8.0,
            after_qty=5.0,
            quantity=3.0,
            item_id=item_id,
        )

    def test_stock_transfer_reason_records_transfer_type(self):
        item_id = self._insert_item(qty=9.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="TRANSFER",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-4.0,
            reason="Transfer",
            reference=f"XFER-{datetime_suffix('T')}",
            source_document="stock_adjustment",
            source_id="xfer-1",
        )
        self.commit()
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="TRANSFER",
            before_qty=9.0,
            after_qty=5.0,
            quantity=4.0,
            item_id=item_id,
        )

    def test_manual_stock_in_and_out(self):
        item_id = self._insert_item(qty=3.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="STOCK_IN",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=2.0,
            reason="Restock",
            reference=f"IN-{datetime_suffix('I')}",
            source_document="stock_adjustment",
            source_id="in-1",
        )
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="STOCK_OUT",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-1.0,
            reason="Manual out",
            reference=f"OUT-{datetime_suffix('O')}",
            source_document="stock_adjustment",
            source_id="out-1",
        )
        self.commit()
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 4.0)
        self.assertEqual(self._movement_count(item_id), 2)

    def test_purchase_receive_path_uses_receive_helper(self):
        self._ensure_branch("WH-1", "Warehouse 1")
        self.commit()
        item_id = self._insert_item(qty=1.0)
        self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            self.role,
            inventory_item_id=item_id,
            qty_received=4.0,
            supplier_name="Vendor Z",
            reference_number=f"PO-RCV-{datetime_suffix('P')}",
            branch_id="WH-1",
        )
        self.commit()
        movement = self._latest_movement(item_id)
        self._assert_movement_integrity(
            movement,
            movement_type="STOCK_IN",
            before_qty=1.0,
            after_qty=5.0,
            quantity=4.0,
            branch_id="WH-1",
            item_id=item_id,
        )
        self.assertIn("Vendor Z", str(movement["notes"] or ""))

    def test_sales_return_alias_normalizes_to_pos_return(self):
        self.assertEqual(self.modules._normalize_stock_movement_type("Sales Return"), "POS_RETURN")
        item_id = self._insert_item(qty=2.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="Sales Return",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=1.0,
            reference=f"SR-{datetime_suffix('S')}",
            source_document="sales_return",
            source_id="sr-1",
        )
        self.commit()
        self.assertEqual(
            self.modules._normalize_stock_movement_type(self._latest_movement(item_id)["movement_type"]),
            "POS_RETURN",
        )

    def test_opening_balance_records_movement_without_double_qty_update(self):
        item_id = self._insert_item(qty=15.0)
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="OPENING_BALANCE",
            created_by=self.role,
            branch_id=self.branch_id,
            update_inventory=False,
            before_qty_override=0.0,
            after_qty_override=15.0,
            reason="Opening",
            reference=f"OPEN-{item_id}",
            source_document="inventory_add_item",
            source_id=item_id,
        )
        self.commit()
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 15.0)
        self.assertFalse(result.get("skipped"))
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="OPENING_BALANCE",
            before_qty=0.0,
            after_qty=15.0,
            quantity=15.0,
            item_id=item_id,
        )

    def test_damage_and_expiry_outbound_movements(self):
        item_id = self._insert_item(qty=10.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="DAMAGE",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-2.0,
            reference=f"DMG-{datetime_suffix('D')}",
            source_document="stock_adjustment",
            source_id="dmg-1",
        )
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="EXPIRY",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-1.0,
            reference=f"EXP-{datetime_suffix('E')}",
            source_document="stock_adjustment",
            source_id="exp-1",
        )
        self.commit()
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 7.0)
        self.assertEqual(self.modules._stock_movement_qty_change("DAMAGE", 2), -2)
        self.assertEqual(self.modules._stock_movement_qty_change("EXPIRY", 1), -1)

    def test_duplicate_prevention_is_idempotent(self):
        item_id = self._insert_item(qty=10.0)
        ref = f"DUP-{datetime_suffix('X')}"
        first = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="STOCK_OUT",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-2.0,
            reference=ref,
            source_document="stock_adjustment",
            source_id="dup-1",
        )
        second = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="STOCK_OUT",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-2.0,
            reference=ref,
            source_document="stock_adjustment",
            source_id="dup-1",
        )
        self.commit()
        self.assertFalse(first.get("duplicate"))
        self.assertTrue(second.get("duplicate"))
        self.assertEqual(first["movement_id"], second["movement_id"])
        self.assertEqual(self._movement_count(item_id), 1)
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 8.0)

    def test_rollback_on_failure_restores_qty_and_skips_orphan_movement(self):
        item_id = self._insert_item(qty=6.0)
        with mock.patch.object(
            self.modules,
            "_insert_stock_movement_record",
            side_effect=RuntimeError("forced movement write failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.modules.apply_inventory_quantity_change(
                    self.conn,
                    company_key=self.company_key,
                    inventory_item_id=item_id,
                    movement_type="STOCK_OUT",
                    created_by=self.role,
                    branch_id=self.branch_id,
                    quantity_delta=-1.0,
                    reference=f"RB-{datetime_suffix('B')}",
                    source_document="stock_adjustment",
                    source_id="rb-1",
                )
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 6.0)
        self.assertEqual(self._movement_count(item_id), 0)

    def test_write_off_outbound_movement(self):
        item_id = self._insert_item(qty=8.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="WRITE_OFF",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-3.0,
            reason="Write Off",
            reference=f"WO-{datetime_suffix('W')}",
            source_document="stock_adjustment",
            source_id="wo-1",
        )
        self.commit()
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 5.0)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="WRITE_OFF",
            before_qty=8.0,
            after_qty=5.0,
            quantity=3.0,
            item_id=item_id,
        )
        self.assertEqual(self.modules._stock_movement_qty_change("WRITE_OFF", 3), -3)

    def test_production_qty_updates_only_via_apply_helper(self):
        source = inspect.getsource(self.modules)
        # The only production inventory qty UPDATE must live inside apply_inventory_quantity_change.
        occurrences = source.count("UPDATE inventory SET qty = ?")
        self.assertGreaterEqual(occurrences, 1)
        apply_source = inspect.getsource(self.modules.apply_inventory_quantity_change)
        self.assertIn("UPDATE inventory SET qty = ?", apply_source)
        # Guardrail: no bare qty decrement patterns remain in modules production paths.
        self.assertNotIn("SET qty = qty -", source)
        self.assertNotIn("SET qty = qty +", source)

    def test_empty_branch_defaults_to_main(self):
        item_id = self._insert_item(qty=5.0)
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="STOCK_IN",
            created_by=self.role,
            branch_id="",
            quantity_delta=1.0,
            reference=f"BR-{datetime_suffix('B')}",
            source_document="stock_adjustment",
            source_id="br-1",
        )
        self.commit()
        movement = self._latest_movement(item_id)
        self.assertEqual(movement["branch_id"], "MAIN")

    def test_invalid_branch_is_blocked(self):
        item_id = self._insert_item(qty=5.0)
        with self.assertRaises(ValueError):
            self.modules.apply_inventory_quantity_change(
                self.conn,
                company_key=self.company_key,
                inventory_item_id=item_id,
                movement_type="STOCK_IN",
                created_by=self.role,
                branch_id="MISSING-BRANCH",
                quantity_delta=1.0,
                reference=f"BAD-{datetime_suffix('B')}",
                source_document="stock_adjustment",
                source_id="bad-1",
            )
        self.conn.rollback()
        self.assertEqual(self._movement_count(item_id), 0)

    def test_invoice_sale_stock_effects_write_movement(self):
        item_id = self._insert_item(qty=10.0)
        invoice_ref = f"INV-{datetime_suffix('I')}"
        result = self.modules.apply_invoice_stock_effects(
            self.conn,
            company_key=self.company_key,
            role=self.role,
            branch_id=self.branch_id,
            invoice_reference=invoice_ref,
            invoice_items=[{"inventory_item_id": item_id, "item_name": "Integrity Item", "quantity": 2.0, "cost_price": 5.0}],
        )
        self.commit()
        self.assertTrue(result["stock_deduction_applied"])
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 8.0)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="POS_SALE",
            before_qty=10.0,
            after_qty=8.0,
            quantity=2.0,
            item_id=item_id,
        )

    def test_import_rows_write_movements_for_create_and_update(self):
        self._ensure_branch("IMP-BRANCH", "Import Branch")
        self.commit()
        existing_id = self._insert_item(qty=2.0, item_code="IMP-EXIST", barcode="99001", name="Existing Import")
        fake_session = {
            "active_branch_id": "IMP-BRANCH",
            "user": {"role": "Manager"},
        }
        validated_rows = [
            {
                "row_number": 1,
                "item_name": "Existing Import",
                "barcode": "99001",
                "item_code": "IMP-EXIST",
                "category": "",
                "brand": "",
                "supplier_name": "",
                "unit": "pcs",
                "qty": 3.0,
                "cost_price": 5.0,
                "price": 12.0,
                "min_stock_level": 1.0,
                "tax_rate": 0.0,
                "warehouse_location": "",
                "expiry_date": None,
                "batch_number": "",
                "vat_category": "",
                "description": "",
                "is_active": 1,
            },
            {
                "row_number": 2,
                "item_name": "Brand New Import",
                "barcode": "99002",
                "item_code": "IMP-NEW",
                "category": "General",
                "brand": "",
                "supplier_name": "",
                "unit": "pcs",
                "qty": 4.0,
                "cost_price": 3.0,
                "price": 8.0,
                "min_stock_level": 1.0,
                "tax_rate": 0.0,
                "warehouse_location": "",
                "expiry_date": None,
                "batch_number": "",
                "vat_category": "",
                "description": "",
                "is_active": 1,
            },
        ]
        with mock.patch.object(self.modules, "st", SimpleNamespace(session_state=fake_session)):
            result = self.modules._import_validated_stock_rows(
                self.conn,
                self.company_key,
                validated_rows,
                "increase_stock",
            )
        self.commit()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["created"], 1)
        existing_qty = float(
            self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (existing_id,)).fetchone()["qty"]
        )
        self.assertEqual(existing_qty, 5.0)
        new_row = self.conn.execute(
            "SELECT id, qty FROM inventory WHERE item_code = ? AND company_key = ?",
            ("IMP-NEW", self.company_key),
        ).fetchone()
        self.assertEqual(float(new_row["qty"]), 4.0)
        existing_move = self._latest_movement(existing_id)
        self.assertEqual(existing_move["branch_id"], "IMP-BRANCH")
        self.assertEqual(self.modules._normalize_stock_movement_type(existing_move["movement_type"]), "IMPORT")
        new_move = self._latest_movement(int(new_row["id"]))
        self.assertEqual(self.modules._normalize_stock_movement_type(new_move["movement_type"]), "OPENING_BALANCE")
        self.assertEqual(new_move["branch_id"], "IMP-BRANCH")

    def test_insufficient_stock_blocks_without_movement(self):
        item_id = self._insert_item(qty=1.0)
        with self.assertRaises(ValueError):
            self.modules.apply_inventory_quantity_change(
                self.conn,
                company_key=self.company_key,
                inventory_item_id=item_id,
                movement_type="POS_SALE",
                created_by=self.role,
                branch_id=self.branch_id,
                quantity_delta=-5.0,
                reference=f"NS-{datetime_suffix('N')}",
                source_document="pos_sale",
                source_id="ns-1",
            )
        self.conn.rollback()
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 1.0)
        self.assertEqual(self._movement_count(item_id), 0)

    def test_sqlite_and_postgres_insert_helpers_for_movements(self):
        base = (
            "INSERT INTO stock_movements (company_key, inventory_item_id, movement_type, quantity) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)
        apply_source = inspect.getsource(self.modules.apply_inventory_quantity_change)
        self.assertIn("execute_portable_write", apply_source)
        insert_source = inspect.getsource(self.modules._insert_stock_movement_record)
        self.assertIn("ensure_insert_sql_returning", insert_source)

    def test_barcode_receive_increments_with_stock_in_movement(self):
        item_id = self._insert_item(qty=2.0, barcode="SCAN-77001")
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="Barcode Receive",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=1.0,
            reason="Barcode Receive",
            reference=f"BARCODE-SCAN-77001-{datetime_suffix('B')}",
            source_document="barcode_receive",
            source_id="SCAN-77001",
        )
        self.commit()
        self.assertEqual(result["after_qty"], 3.0)
        self._assert_movement_integrity(
            self._latest_movement(item_id),
            movement_type="STOCK_IN",
            before_qty=2.0,
            after_qty=3.0,
            quantity=1.0,
            item_id=item_id,
        )

    def test_process_pos_return_restocks_with_branch_and_movement(self):
        self.database.ensure_pos_sales_schema(self.conn)
        self._ensure_branch("RET-BR", "Return Branch")
        self.commit()
        item_id = self._insert_item(qty=5.0)
        sale_ref = f"POS-SRC-{datetime_suffix('S')}"
        return_ref = f"RET-{datetime_suffix('R')}"
        self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number, sale_date, sale_datetime,
                cashier, payment_method, subtotal, discount_total, tax_total, grand_total
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.company_key,
                "RET-BR",
                sale_ref,
                sale_ref,
                "2026-08-04",
                "2026-08-04T10:00:00",
                "Cashier",
                "Cash",
                20.0,
                0.0,
                0.0,
                20.0,
            ),
        )
        sale_id = int(
            self.conn.execute(
                "SELECT id FROM pos_sales WHERE sale_reference = ?",
                (sale_ref,),
            ).fetchone()["id"]
        )
        self.conn.execute(
            """
            INSERT INTO pos_sale_lines (
                pos_sale_id, company_key, inventory_item_id, item_name, qty_sold, unit_price,
                line_discount, tax_rate, line_total, cost_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sale_id, self.company_key, item_id, "Integrity Item", 2.0, 10.0, 0.0, 0.0, 20.0, 5.0),
        )
        line_id = int(
            self.conn.execute(
                "SELECT id FROM pos_sale_lines WHERE pos_sale_id = ? LIMIT 1",
                (sale_id,),
            ).fetchone()["id"]
        )
        self.commit()
        with mock.patch.object(self.modules, "post_journal_entry", return_value=1):
            result = self.modules._process_pos_return(
                self.conn,
                company_key=self.company_key,
                branch_id="RET-BR",
                role=self.role,
                original_sale={"sale_reference": sale_ref, "receipt_number": sale_ref, "customer_id": None},
                return_items=[{"pos_sale_line_id": line_id, "qty_returned": 1.0}],
                refund_method="Cash",
                reason="Customer return",
                return_reference=return_ref,
            )
        self.commit()
        self.assertEqual(result["return_reference"], return_ref)
        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 6.0)
        movement = self._latest_movement(item_id)
        self._assert_movement_integrity(
            movement,
            movement_type="POS_RETURN",
            before_qty=5.0,
            after_qty=6.0,
            quantity=1.0,
            branch_id="RET-BR",
            item_id=item_id,
        )

    def test_zero_delta_skips_movement(self):
        item_id = self._insert_item(qty=4.0)
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="ADJUSTMENT",
            created_by=self.role,
            branch_id=self.branch_id,
            target_qty=4.0,
            reference=f"ZERO-{datetime_suffix('Z')}",
            source_document="inventory_edit",
            source_id=item_id,
        )
        self.commit()
        self.assertTrue(result.get("skipped"))
        self.assertEqual(self._movement_count(item_id), 0)


if __name__ == "__main__":
    unittest.main()
