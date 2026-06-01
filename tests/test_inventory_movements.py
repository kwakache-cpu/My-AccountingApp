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

    def test_insert_stock_movement_record_returns_valid_id(self):
        item_id = self._insert_item(qty=10.0)
        movement_id = self.modules._insert_stock_movement_record(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            item_name="Soap",
            movement_type="STOCK_OUT",
            quantity=2.0,
            previous_qty=10.0,
            new_qty=8.0,
            created_by="Manager",
            branch_id=None,
            reason="Adjustment",
            reference="ADJ-001",
            notes="Cycle count",
        )
        self.commit()
        self.assertIsNotNone(movement_id)
        row = self.conn.execute(
            """
            SELECT company_key, branch_id, inventory_item_id, item_name, movement_type,
                   quantity, reason, previous_qty, new_qty, created_by, reference, notes,
                   status, approval_status
            FROM stock_movements WHERE id = ?
            """,
            (movement_id,),
        ).fetchone()
        self.assertEqual(row["company_key"], self.company_key)
        self.assertIsNone(row["branch_id"])
        self.assertEqual(int(row["inventory_item_id"]), item_id)
        self.assertEqual(row["item_name"], "Soap")
        self.assertEqual(row["movement_type"], "STOCK_OUT")
        self.assertEqual(float(row["quantity"]), 2.0)
        self.assertEqual(row["reason"], "Adjustment")
        self.assertEqual(float(row["previous_qty"]), 10.0)
        self.assertEqual(float(row["new_qty"]), 8.0)
        self.assertEqual(row["created_by"], "Manager")
        self.assertEqual(row["reference"], "ADJ-001")
        self.assertEqual(row["notes"], "Cycle count")
        self.assertEqual(row["status"], "Approved")
        self.assertEqual(row["approval_status"], "Approved")

    def test_insert_stock_movement_record_sqlite_matches_lastrowid(self):
        item_id = self._insert_item(qty=4.0)
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO stock_movements (
                    company_key, branch_id, inventory_item_id, item_name, movement_type,
                    quantity, reason, previous_qty, new_qty, created_by, created_at,
                    reference, notes, status, approval_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, 'Approved', 'Approved')
                """
            ),
            (
                self.company_key,
                None,
                item_id,
                "Soap",
                "STOCK_IN",
                1.0,
                "Receive Stock",
                4.0,
                5.0,
                "Manager",
                "RCV-TEST",
                None,
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_stock_movement_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO stock_movements (company_key, inventory_item_id, movement_type, quantity) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

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
