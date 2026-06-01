import importlib

from test_support import ERPIsolatedTestCase, datetime_suffix


class PosSaleIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)
            VALUES (?, ?, ?)
            """,
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _receipt_data(self, *, sale_reference, receipt_number=None):
        return {
            "receipt_number": receipt_number or sale_reference,
            "sale_date": self.today.isoformat(),
            "sale_datetime": f"{self.today.isoformat()} 12:00:00",
            "cashier": "Cashier",
            "payment_method": "Cash",
            "subtotal": 100.0,
            "discount_total": 0.0,
            "tax_total": 15.0,
            "grand_total": 115.0,
            "amount_tendered": 120.0,
            "change_due": 5.0,
        }

    def _sample_cart(self):
        return [
            {
                "inventory_item_id": None,
                "name": "Service Item",
                "item_code": "SVC1",
                "barcode": "",
                "qty": 2,
                "price": 50.0,
                "line_discount": 0.0,
                "tax_rate": 0.0,
                "line_total": 100.0,
                "cost_price": 0.0,
            }
        ]

    def test_persist_pos_sale_returns_valid_id_and_preserves_references(self):
        sale_reference = f"POS-REF-{datetime_suffix('S')}"
        receipt_number = f"RCP-{datetime_suffix('R')}"
        receipt_data = self._receipt_data(
            sale_reference=sale_reference,
            receipt_number=receipt_number,
        )

        pos_sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            receipt_data,
            self._sample_cart(),
        )
        self.commit()

        row = self.conn.execute(
            """
            SELECT sale_reference, receipt_number, branch_id, grand_total, payment_method
            FROM pos_sales WHERE id = ?
            """,
            (pos_sale_id,),
        ).fetchone()
        self.assertEqual(row["sale_reference"], sale_reference)
        self.assertEqual(row["receipt_number"], receipt_number)
        self.assertEqual(row["branch_id"], "MAIN")
        self.assertEqual(float(row["grand_total"]), 115.0)
        self.assertEqual(row["payment_method"], "Cash")

    def test_persist_pos_sale_lines_link_to_pos_sale_id(self):
        sale_reference = f"POS-LINES-{datetime_suffix('L')}"
        pos_sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            self._receipt_data(sale_reference=sale_reference),
            self._sample_cart(),
        )
        self.commit()
        lines = self.conn.execute(
            "SELECT pos_sale_id, item_name, qty_sold, line_total FROM pos_sale_lines WHERE pos_sale_id = ?",
            (pos_sale_id,),
        ).fetchall()
        self.assertEqual(len(lines), 1)
        self.assertEqual(int(lines[0]["pos_sale_id"]), pos_sale_id)
        self.assertEqual(lines[0]["item_name"], "Service Item")
        self.assertEqual(float(lines[0]["qty_sold"]), 2.0)
        self.assertEqual(float(lines[0]["line_total"]), 100.0)

    def test_persist_pos_sale_idempotent_by_sale_reference(self):
        sale_reference = f"POS-IDEM-{datetime_suffix('I')}"
        receipt_data = self._receipt_data(sale_reference=sale_reference)
        cart = self._sample_cart()

        first_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            receipt_data,
            cart,
        )
        second_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            receipt_data,
            cart,
        )
        self.commit()
        self.assertEqual(first_id, second_id)
        count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM pos_sales WHERE company_key = ? AND sale_reference = ?",
            (self.company_key, sale_reference),
        ).fetchone()["c"]
        self.assertEqual(int(count), 1)

    def test_pos_sale_insert_sqlite_matches_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO pos_sales (
                    company_key, branch_id, sale_reference, receipt_number, sale_date,
                    cashier, grand_total
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                "MAIN",
                "SQLITE-REF",
                "SQLITE-RCP",
                self.today.isoformat(),
                "test",
                10.0,
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_pos_sale_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO pos_sales (company_key, sale_reference, receipt_number, grand_total) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    def test_persist_pos_sale_leaves_posted_entry_columns_null(self):
        sale_reference = f"POS-POSTED-{datetime_suffix('P')}"
        pos_sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            self._receipt_data(sale_reference=sale_reference),
            self._sample_cart(),
        )
        self.commit()
        row = self.conn.execute(
            "SELECT posted_entry_id, cogs_posted_entry_id FROM pos_sales WHERE id = ?",
            (pos_sale_id,),
        ).fetchone()
        self.assertIsNone(row["posted_entry_id"])
        self.assertIsNone(row["cogs_posted_entry_id"])
