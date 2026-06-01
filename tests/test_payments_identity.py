import importlib
from datetime import date

from test_support import ERPIsolatedTestCase, build_lines


class PaymentsIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.engine = importlib.import_module("accounting_engine")
        self.database = importlib.import_module("database")

    def test_payment_insert_returns_valid_id(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 6, 1).isoformat(),
                "Customer Receipt",
                "Posted",
                75.0,
                "Cash",
                "PAY-TEST-001",
                "Posted",
                "test",
            ),
        )
        payment_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            "SELECT payment_type, amount, reference FROM payments WHERE id = ?",
            (payment_id,),
        ).fetchone()
        self.assertEqual(row["payment_type"], "Customer Receipt")
        self.assertEqual(float(row["amount"]), 75.0)
        self.assertEqual(row["reference"], "PAY-TEST-001")

    def test_payment_insert_sqlite_matches_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payments (
                    company_key, payment_date, payment_type, status, amount,
                    currency, method, reference, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, 'GHS', ?, ?, ?, ?)
                """
            ),
            (
                self.company_key,
                date(2026, 6, 1).isoformat(),
                "Supplier Payment",
                "Posted",
                25.0,
                "Bank",
                "PAY-SQLITE",
                "Posted",
                "test",
            ),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)
        self.assertEqual(
            self.database.fetch_inserted_row_id(cursor, backend="sqlite"),
            cursor.lastrowid,
        )

    def test_payment_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO payments (company_key, payment_date, payment_type, amount) "
            "VALUES (?, ?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    def test_allocate_payment_links_allocation_to_payment_id(self):
        supplier_id = self.create_supplier("Alloc Supplier")
        bill_id = self.create_bill(supplier_id=supplier_id, amount=200.0)
        payment_id = self.create_payment(
            payment_type="Supplier Payment",
            supplier_id=supplier_id,
            bill_id=bill_id,
            amount=200.0,
        )
        allocation_id = self.engine.allocate_payment(
            payment_id,
            bill_id=bill_id,
            amount=50.0,
            created_by="test",
            conn=self.conn,
        )
        self.commit()
        row = self.conn.execute(
            """
            SELECT payment_id, bill_id, amount
            FROM payment_allocations
            WHERE id = ?
            """,
            (allocation_id,),
        ).fetchone()
        self.assertEqual(int(row["payment_id"]), payment_id)
        self.assertEqual(int(row["bill_id"]), bill_id)
        self.assertEqual(float(row["amount"]), 50.0)

    def test_payment_journal_linkage_unchanged(self):
        supplier_id = self.create_supplier("Journal Supplier")
        payment_id = self.create_payment(
            payment_type="Supplier Payment",
            supplier_id=supplier_id,
            amount=90.0,
        )
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 90.0, "credit": 0.0},
                {"account_id": self.account_id("Cash", "Asset"), "debit": 0.0, "credit": 90.0},
            ),
            source_table="payments",
            source_id=payment_id,
            source_type="Supplier Payment",
            supplier_id=supplier_id,
            payment_id=payment_id,
            reference="PAY-JOURNAL-90",
        )
        row = self.conn.execute(
            "SELECT payment_id, source_id, source_table FROM journal_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        self.assertEqual(int(row["payment_id"]), payment_id)
        self.assertEqual(int(row["source_id"]), payment_id)
        self.assertEqual(row["source_table"], "payments")
