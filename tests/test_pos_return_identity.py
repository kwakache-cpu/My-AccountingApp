import importlib
from datetime import date
from unittest.mock import patch

from test_support import ERPIsolatedTestCase, datetime_suffix


class PosReturnIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_pos_sales_schema(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)
            VALUES (?, ?, ?)
            """,
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _create_inventory_item(self, *, qty=10.0, cost_price=5.0):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, "Return Widget", "RW1", "RW-001", qty, 20.0, cost_price, 1.0),
        )
        self.commit()
        return int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE item_code = 'RW1' AND company_key = ?",
                (self.company_key,),
            ).fetchone()["id"]
        )

    def _create_pos_sale_with_line(self, inventory_item_id, *, qty_sold=2.0, unit_price=15.0):
        sale_reference = f"REF-{datetime_suffix('S')}"
        return_reference = f"RET-{datetime_suffix('R')}"
        receipt_number = f"POS-{datetime_suffix('P')}"
        sale_cursor = self.conn.execute(
            """
            INSERT INTO pos_sales (
                company_key, branch_id, sale_reference, receipt_number,
                sale_date, cashier, grand_total
            )
            VALUES (?, ?, ?, ?, ?, 'Cashier', ?)
            """,
            (
                self.company_key,
                "MAIN",
                sale_reference,
                receipt_number,
                self.today.isoformat(),
                qty_sold * unit_price,
            ),
        )
        pos_sale_id = int(sale_cursor.lastrowid)
        line_cursor = self.conn.execute(
            """
            INSERT INTO pos_sale_lines (
                pos_sale_id, company_key, inventory_item_id, item_name, qty_sold,
                unit_price, line_total, cost_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos_sale_id,
                self.company_key,
                inventory_item_id,
                "Return Widget",
                qty_sold,
                unit_price,
                qty_sold * unit_price,
                5.0,
            ),
        )
        pos_sale_line_id = int(line_cursor.lastrowid)
        self.commit()
        return {
            "sale_reference": sale_reference,
            "receipt_number": receipt_number,
            "return_reference": return_reference,
            "pos_sale_line_id": pos_sale_line_id,
            "original_sale": {
                "sale_reference": sale_reference,
                "receipt_number": receipt_number,
                "customer_id": None,
            },
        }

    def test_pos_return_insert_returns_valid_id(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO pos_returns (
                    company_key, branch_id, original_sale_reference, return_reference,
                    pos_sale_line_id, item_name, qty_returned, unit_price, refund_amount,
                    reason, refund_method, returned_by, status
                )
                VALUES (?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted')
                """
            ),
            (
                self.company_key,
                "SALE-REF-1",
                "RET-REF-1",
                1,
                "Widget",
                1.0,
                10.0,
                10.0,
                "Damaged",
                "Cash",
                "test",
            ),
        )
        pos_return_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            """
            SELECT return_reference, refund_amount, refund_method, status
            FROM pos_returns WHERE id = ?
            """,
            (pos_return_id,),
        ).fetchone()
        self.assertEqual(row["return_reference"], "RET-REF-1")
        self.assertEqual(float(row["refund_amount"]), 10.0)
        self.assertEqual(row["refund_method"], "Cash")
        self.assertEqual(row["status"], "Posted")

    def test_pos_return_insert_sqlite_matches_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO pos_returns (
                    company_key, original_sale_reference, return_reference, item_name,
                    qty_returned, unit_price, refund_amount, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Posted')
                """
            ),
            (self.company_key, "SALE-2", "RET-2", "Item", 1.0, 5.0, 5.0),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_pos_return_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO pos_returns (company_key, return_reference, item_name, refund_amount) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    @patch("modules.post_journal_entry", return_value=4242)
    def test_process_pos_return_links_source_id_and_restock(self, mock_post_journal):
        item_id = self._create_inventory_item(qty=8.0)
        sale_ctx = self._create_pos_sale_with_line(item_id, qty_sold=2.0, unit_price=15.0)
        return_ref = f"RET-TEST-{datetime_suffix('T')}"

        result = self.modules._process_pos_return(
            self.conn,
            company_key=self.company_key,
            branch_id="MAIN",
            role="Manager",
            original_sale=sale_ctx["original_sale"],
            return_items=[{"pos_sale_line_id": sale_ctx["pos_sale_line_id"], "qty_returned": 1.0}],
            refund_method="Cash",
            reason="Customer return",
            return_reference=return_ref,
        )
        self.commit()

        self.assertEqual(result["return_reference"], return_ref)
        mock_post_journal.assert_called_once()
        journal_kwargs = mock_post_journal.call_args.kwargs
        self.assertEqual(journal_kwargs["source_table"], "pos_returns")
        self.assertEqual(journal_kwargs["reference"], return_ref)
        self.assertEqual(journal_kwargs["branch_id"], "MAIN")

        pos_return_id = journal_kwargs["source_id"]
        row = self.conn.execute(
            "SELECT return_reference, posted_entry_id, refund_amount FROM pos_returns WHERE id = ?",
            (pos_return_id,),
        ).fetchone()
        self.assertEqual(row["return_reference"], return_ref)
        self.assertEqual(int(row["posted_entry_id"]), 4242)
        self.assertEqual(float(row["refund_amount"]), 15.0)

        qty_row = self.conn.execute(
            "SELECT qty FROM inventory WHERE id = ?",
            (item_id,),
        ).fetchone()
        self.assertEqual(float(qty_row["qty"]), 9.0)
