import importlib
from datetime import date

from test_support import ERPIsolatedTestCase, datetime_suffix


class SalesInvoiceIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")

    def _create_customer(self, name="Invoice Customer"):
        customer_id = self.modules._register_customer(self.conn, self.company_key, name)
        self.commit()
        return customer_id

    def test_invoice_insert_returns_valid_id_and_invoice_number(self):
        customer_id = self._create_customer()
        invoice_number = f"SAL-{datetime_suffix('INV')}"
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO invoices (
                    company_key, customer_id, invoice_number, invoice_date, due_date,
                    status, approval_status, amount, output_vat, currency, description, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                """
            ),
            (
                self.company_key,
                customer_id,
                invoice_number,
                date(2026, 6, 1).isoformat(),
                date(2026, 6, 1).isoformat(),
                "Paid",
                "Posted",
                200.0,
                0.0,
                "Sales invoice test",
                "test",
            ),
        )
        invoice_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            "SELECT invoice_number, customer_id, amount FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        self.assertEqual(row["invoice_number"], invoice_number)
        self.assertEqual(int(row["customer_id"]), customer_id)
        self.assertEqual(float(row["amount"]), 200.0)

    def test_invoice_lines_link_to_inserted_invoice_id(self):
        customer_id = self._create_customer("Line Customer")
        invoice_number = f"SAL-LINES-{datetime_suffix('L')}"
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO invoices (
                    company_key, customer_id, invoice_number, invoice_date, due_date,
                    status, approval_status, amount, currency, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?)
                """
            ),
            (
                self.company_key,
                customer_id,
                invoice_number,
                date(2026, 6, 1).isoformat(),
                date(2026, 6, 1).isoformat(),
                "Draft",
                "Draft",
                60.0,
                "test",
            ),
        )
        invoice_id = self.database.get_inserted_id(cursor)
        self.conn.execute(
            """
            INSERT INTO invoice_lines (invoice_id, item_name, quantity, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (invoice_id, "Widget", 2.0, 30.0, 60.0),
        )
        self.commit()
        line = self.conn.execute(
            "SELECT invoice_id, item_name, line_total FROM invoice_lines WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()
        self.assertEqual(int(line["invoice_id"]), invoice_id)
        self.assertEqual(line["item_name"], "Widget")
        self.assertEqual(float(line["line_total"]), 60.0)

    def test_invoice_insert_sqlite_matches_lastrowid(self):
        customer_id = self._create_customer("SQLite Customer")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO invoices (
                    company_key, customer_id, invoice_number, invoice_date, due_date,
                    status, approval_status, amount, currency, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?)
                """
            ),
            (
                self.company_key,
                customer_id,
                "SAL-SQLITE",
                date(2026, 6, 1).isoformat(),
                date(2026, 6, 1).isoformat(),
                "Pending",
                "Draft",
                10.0,
                "test",
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_invoice_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO invoices (company_key, customer_id, invoice_number, amount) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)
