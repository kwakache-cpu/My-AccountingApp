import importlib
from datetime import datetime, timedelta

from test_support import ERPIsolatedTestCase


class InventoryMovementTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.commit()

    def _insert_item(self, *, qty=5.0, expiry_date=None):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Soap", "S1", "9003", qty, 10.0, 4.0, 2.0),
        )
        self.commit()
        if expiry_date is not None:
            item_id = int(self.conn.execute("SELECT id FROM inventory WHERE item_code = 'S1'").fetchone()["id"])
            self.conn.execute(
                "UPDATE inventory SET expiry_date = ? WHERE id = ?",
                (expiry_date, item_id),
            )
            self.commit()
        return int(self.conn.execute("SELECT id FROM inventory WHERE item_code = 'S1'").fetchone()["id"])

    def test_receive_stock_creates_movement_and_updates_qty(self):
        item_id = self._insert_item(qty=2.0)
        result = self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            "Manager",
            inventory_item_id=item_id,
            qty_received=3.0,
            unit_cost=4.5,
            supplier_name="Vendor A",
            reference_number="PO-100",
            notes="Delivery 1",
            branch_id="",
        )
        self.commit()
        self.assertEqual(result["new_qty"], 5.0)
        movement = self.conn.execute(
            "SELECT movement_type, quantity, reference FROM stock_movements WHERE company_key = ? ORDER BY id DESC LIMIT 1",
            (self.company_key,),
        ).fetchone()
        self.assertEqual(movement["movement_type"], "STOCK_IN")
        self.assertEqual(float(movement["quantity"]), 3.0)
        self.assertEqual(movement["reference"], "PO-100")

    def test_receive_stock_rejects_invalid_expiry(self):
        item_id = self._insert_item()
        with self.assertRaises(ValueError):
            self.modules._receive_inventory_stock(
                self.conn,
                self.company_key,
                "Manager",
                inventory_item_id=item_id,
                qty_received=1.0,
                expiry_date="not-a-date",
            )

    def test_movement_qty_change_signs(self):
        self.assertEqual(self.modules._stock_movement_qty_change("STOCK_OUT", 4), -4)
        self.assertEqual(self.modules._stock_movement_qty_change("POS_SALE", 2), -2)
        self.assertEqual(self.modules._stock_movement_qty_change("STOCK_IN", 2), 2)

    def test_health_filter_low_stock(self):
        overview = self.modules._prepare_inventory_overview_dataframe(
            __import__("pandas").DataFrame(
                [
                    {"item_name": "A", "quantity": 1, "min_stock_level": 5, "expiry_date": None},
                    {"item_name": "B", "quantity": 20, "min_stock_level": 5, "expiry_date": None},
                ]
            )
        )
        filtered = self.modules._filter_inventory_overview_dataframe(overview, "LOW STOCK")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["item_name"], "A")
