import importlib
from datetime import datetime

from test_support import ERPIsolatedTestCase


class ApBillsIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database = importlib.import_module("database")

    def _create_supplier(self, name="AP Supplier"):
        supplier_id = self.modules._get_or_create_party(self.conn, "suppliers", self.company_key, name)
        self.commit()
        return supplier_id

    def test_bill_insert_returns_valid_id_and_fields(self):
        supplier_id = self._create_supplier()
        bill_number = "BILL-TEST-001"
        bill_date = datetime.now().date().isoformat()
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO bills (
                    company_key, supplier_id, bill_number, bill_date, due_date, status, approval_status,
                    amount, input_vat, purchase_classification, currency, description, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                """
            ),
            (
                self.company_key,
                supplier_id,
                bill_number,
                bill_date,
                bill_date,
                "Pending",
                "Draft",
                250.0,
                0.0,
                "Expense Purchase",
                "Portable bill insert",
                "test",
            ),
        )
        bill_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            """
            SELECT bill_number, supplier_id, amount, approval_status, description
            FROM bills WHERE id = ?
            """,
            (bill_id,),
        ).fetchone()
        self.assertEqual(row["bill_number"], bill_number)
        self.assertEqual(int(row["supplier_id"]), supplier_id)
        self.assertEqual(float(row["amount"]), 250.0)
        self.assertEqual(row["approval_status"], "Draft")
        self.assertEqual(row["description"], "Portable bill insert")

    def test_bill_insert_sqlite_matches_lastrowid(self):
        supplier_id = self._create_supplier("SQLite Supplier")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO bills (
                    company_key, supplier_id, bill_number, bill_date, due_date,
                    status, approval_status, amount, currency, description, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                """
            ),
            (
                self.company_key,
                supplier_id,
                "BILL-SQLITE-001",
                "2026-06-01",
                "2026-06-01",
                "Pending",
                "Draft",
                10.0,
                "sqlite parity",
                "test",
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_bill_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO bills (company_key, supplier_id, bill_number, amount) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    def test_create_bill_lines_link_to_inserted_bill_id(self):
        supplier_id = self._create_supplier("Line Supplier")
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO bills (
                    company_key, supplier_id, bill_number, bill_date, due_date,
                    status, approval_status, amount, currency, description, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
                """
            ),
            (
                self.company_key,
                supplier_id,
                "BILL-LINES-001",
                "2026-06-01",
                "2026-06-01",
                "Pending",
                "Draft",
                60.0,
                "bill with lines",
                "test",
            ),
        )
        bill_id = self.database.get_inserted_id(cursor)
        self.conn.execute(
            """
            INSERT INTO bill_lines (bill_id, item_name, quantity, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bill_id, "Widget", 2.0, 30.0, 60.0),
        )
        self.commit()
        line = self.conn.execute(
            "SELECT item_name, line_total FROM bill_lines WHERE bill_id = ?",
            (bill_id,),
        ).fetchone()
        self.assertEqual(line["item_name"], "Widget")
        self.assertEqual(float(line["line_total"]), 60.0)
