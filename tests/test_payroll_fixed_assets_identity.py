import importlib
from datetime import date

from test_support import ERPIsolatedTestCase


class PayrollFixedAssetsIdentityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.database = importlib.import_module("database")

    def test_payroll_insert_returns_valid_id(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payroll (
                    company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                    taxable_income, paye, net_salary, deductions, month, year,
                    payment_status, payment_method, approval_status, created_by, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Posted', ?, 'Active')
                """
            ),
            (
                self.company_key,
                "Jane Doe",
                1000.0,
                100.0,
                55.0,
                130.0,
                1045.0,
                120.0,
                895.0,
                0.0,
                "June",
                "2026",
                "Unpaid",
                None,
                "test",
            ),
        )
        payroll_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            "SELECT emp_name, net_salary, month, year FROM payroll WHERE id = ?",
            (payroll_id,),
        ).fetchone()
        self.assertEqual(row["emp_name"], "Jane Doe")
        self.assertEqual(float(row["net_salary"]), 895.0)
        self.assertEqual(row["month"], "June")
        self.assertEqual(row["year"], "2026")

    def test_fixed_asset_insert_returns_valid_id(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO fixed_assets (
                    company_key, asset_name, asset_category, purchase_date, cost,
                    opening_book_value, useful_life_years, residual_value, depreciation_method,
                    depreciation_rate, accumulated_depreciation, book_value, status, approval_status, created_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Straight-line', ?, 0, ?, 'Active', 'Posted', ?)
                """
            ),
            (
                self.company_key,
                "Laptop",
                "IT Equipment",
                date(2026, 6, 1).isoformat(),
                5000.0,
                5000.0,
                5,
                500.0,
                20.0,
                5000.0,
                "test",
            ),
        )
        asset_id = self.database.get_inserted_id(cursor)
        self.commit()
        row = self.conn.execute(
            "SELECT asset_name, cost, book_value FROM fixed_assets WHERE id = ?",
            (asset_id,),
        ).fetchone()
        self.assertEqual(row["asset_name"], "Laptop")
        self.assertEqual(float(row["cost"]), 5000.0)
        self.assertEqual(float(row["book_value"]), 5000.0)
        self.assertEqual(f"FA-{asset_id}", f"FA-{int(asset_id)}")

    def test_payroll_insert_sqlite_matches_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payroll (company_key, emp_name, basic_salary, net_salary, month, year, approval_status, created_by, status)
                VALUES (?, ?, ?, ?, ?, ?, 'Posted', ?, 'Active')
                """
            ),
            (self.company_key, "SQLite Emp", 500.0, 450.0, "May", "2026", "test"),
        )
        self.assertEqual(self.database.get_inserted_id(cursor), cursor.lastrowid)

    def test_fixed_asset_insert_sql_postgres_returning(self):
        base = (
            "INSERT INTO fixed_assets (company_key, asset_name, cost) "
            "VALUES (?, ?, ?)"
        )
        sqlite_sql = self.database.ensure_insert_sql_returning(base, backend="sqlite")
        postgres_sql = self.database.ensure_insert_sql_returning(base, backend="postgres")
        self.assertEqual(sqlite_sql, base)
        self.assertIn("RETURNING id", postgres_sql)

    def test_payroll_records_insert_does_not_require_lastrowid(self):
        cursor = self.conn.execute(
            self.database.ensure_insert_sql_returning(
                """
                INSERT INTO payroll (
                    company_key, emp_name, basic_salary, net_salary, month, year,
                    approval_status, created_by, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Posted', ?, 'Active')
                """
            ),
            (self.company_key, "Record Link", 800.0, 700.0, "April", "2026", "test"),
        )
        payroll_id = self.database.get_inserted_id(cursor)
        self.conn.execute(
            """
            INSERT INTO payroll_records (
                company_key, period_start, period_end, employee_name, gross_pay, deductions, net_pay, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.company_key,
                "2026-04-01",
                "2026-04-30",
                "Record Link",
                800.0,
                100.0,
                700.0,
                "Unpaid",
            ),
        )
        self.commit()
        payroll_row = self.conn.execute(
            "SELECT emp_name FROM payroll WHERE id = ?",
            (payroll_id,),
        ).fetchone()
        record_row = self.conn.execute(
            "SELECT employee_name, net_pay FROM payroll_records WHERE employee_name = ? ORDER BY id DESC LIMIT 1",
            ("Record Link",),
        ).fetchone()
        self.assertEqual(payroll_row["emp_name"], "Record Link")
        self.assertEqual(record_row["employee_name"], "Record Link")
        self.assertEqual(float(record_row["net_pay"]), 700.0)
