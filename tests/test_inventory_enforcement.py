import importlib
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from test_support import ERPIsolatedTestCase


class InventoryEnforcementTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")

    def test_expiry_validation_missing_date_is_ok(self):
        result = self.modules._get_inventory_expiry_validation(None)
        self.assertEqual(result["status"], "OK")
        self.assertIsNone(result["parsed_date"])

    def test_expiry_validation_invalid_string_is_blocked(self):
        result = self.modules._get_inventory_expiry_validation("not-a-date")
        self.assertEqual(result["status"], "INVALID")

    def test_expiry_validation_expired_date(self):
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
        result = self.modules._get_inventory_expiry_validation(yesterday)
        self.assertEqual(result["status"], "EXPIRED")

    def test_expiry_validation_expiring_soon(self):
        soon = (datetime.now().date() + timedelta(days=10)).isoformat()
        result = self.modules._get_inventory_expiry_validation(soon)
        self.assertEqual(result["status"], "EXPIRING_SOON")

    def test_add_block_reason_invalid_expiry(self):
        reason = self.modules._get_pos_add_block_reason(
            {
                "id": 1,
                "item_name": "Widget",
                "qty": 5.0,
                "min_stock_level": 0.0,
                "expiry_date": "bad-date",
            }
        )
        self.assertIn("Invalid expiry", reason)

    def test_checkout_blocks_expired_inventory_line(self):
        expiry = (datetime.now().date() - timedelta(days=2)).isoformat()
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price,
                min_stock_level, tax_rate, expiry_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Milk", "M1", "9001", 4.0, 10.0, 5.0, 0.0, 0.0, expiry),
        )
        self.commit()
        item_id = int(self.conn.execute("SELECT id FROM inventory WHERE item_code = ?", ("M1",)).fetchone()["id"])
        sale_line = {
            "inventory_item_id": item_id,
            "item_name": "Milk",
            "name": "Milk",
            "qty": 1,
            "is_manual": False,
        }
        error = self.modules._validate_pos_checkout_inventory_line(self.conn, self.company_key, sale_line)
        self.assertIsNotNone(error)
        self.assertIn("Expired", error)

    def test_checkout_blocks_insufficient_stock(self):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price,
                min_stock_level, tax_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Bread", "B1", "9002", 2.0, 5.0, 2.0, 0.0, 0.0),
        )
        self.commit()
        item_id = int(self.conn.execute("SELECT id FROM inventory WHERE item_code = ?", ("B1",)).fetchone()["id"])
        sale_line = {
            "inventory_item_id": item_id,
            "item_name": "Bread",
            "name": "Bread",
            "qty": 5,
            "is_manual": False,
        }
        error = self.modules._validate_pos_checkout_inventory_line(self.conn, self.company_key, sale_line)
        self.assertIsNotNone(error)
        self.assertIn("Insufficient stock", error)

    def test_revalidate_restored_cart_removes_missing_inventory(self):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price,
                min_stock_level, tax_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Soap", "S1", "9003", 3.0, 8.0, 4.0, 0.0, 0.0),
        )
        self.commit()
        item_id = int(self.conn.execute("SELECT id FROM inventory WHERE item_code = ?", ("S1",)).fetchone()["id"])
        cart = [
            {
                "inventory_item_id": item_id,
                "item_name": "Soap",
                "name": "Soap",
                "qty": 2,
                "is_manual": False,
                "price": 8.0,
                "line_discount_type": "amount",
                "line_discount_value": 0.0,
            },
            {
                "inventory_item_id": 999999,
                "item_name": "Ghost",
                "name": "Ghost",
                "qty": 1,
                "is_manual": False,
            },
        ]
        validated, messages = self.modules._revalidate_pos_cart_inventory(self.conn, self.company_key, cart)
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0]["item_name"], "Soap")
        self.assertTrue(any("Removed Ghost" in message for message in messages))

    def test_cart_qty_limit_clamps_to_available(self):
        line = {
            "inventory_item_id": 1,
            "item_name": "Clamp Me",
            "name": "Clamp Me",
            "available_qty": 3.0,
            "is_manual": False,
        }
        applied_qty, clamped, message = self.modules._apply_pos_cart_line_qty_limit(line, 5)
        self.assertEqual(applied_qty, 3)
        self.assertTrue(clamped)
        self.assertIn("limited", message)
