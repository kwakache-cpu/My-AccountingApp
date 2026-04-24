import importlib
import os
import shutil
import sys
import unittest
import uuid
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _purge_erp_modules():
    for module_name in [
        "app",
        "enterprise_services",
        "financials",
        "modules",
        "accounting_engine",
        "database",
    ]:
        sys.modules.pop(module_name, None)


def load_isolated_modules(data_dir):
    os.environ["EKA_DATA_DIR"] = str(data_dir)
    os.environ["ERP_PRODUCTION_MODE"] = "0"
    os.environ["ERP_SAFE_STARTUP_MODE"] = "0"
    _purge_erp_modules()
    database = importlib.import_module("database")
    database.LEGACY_DB_PATH = str(Path(data_dir) / "_legacy_disabled_for_tests.db")
    accounting_engine = importlib.import_module("accounting_engine")
    return database, accounting_engine


class ERPIsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self._original_env = {
            key: os.environ.get(key)
            for key in ("EKA_DATA_DIR", "ERP_PRODUCTION_MODE", "ERP_SAFE_STARTUP_MODE")
        }
        self._workspace_temp_root = REPO_ROOT / ".test-tmp"
        self._workspace_temp_root.mkdir(parents=True, exist_ok=True)
        self._tempdir_path = self._workspace_temp_root / f"eka_test_{uuid.uuid4().hex}"
        self._tempdir_path.mkdir(parents=True, exist_ok=True)
        self.data_dir = self._tempdir_path / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database, self.engine = load_isolated_modules(self.data_dir)
        self._initialize_schema()
        self.conn = self.database._open_sqlite_connection(path=self.database.DB_PATH)
        self.today = date(2026, 4, 24)
        self.company_key = "TESTCO"
        self.database.create_company_record(
            self.conn,
            company_key=self.company_key,
            company_name="Test Company",
            subscription_expiry="Permanent",
            status="Active",
            deployment_status="Live",
            number_of_branches=1,
            max_branches=1,
            branch_price_per_month=0.0,
            contact_email="test@example.com",
        )
        self.conn.commit()

    def tearDown(self):
        try:
            if getattr(self, "conn", None):
                self.conn.close()
                self.conn = None
        finally:
            _purge_erp_modules()
            self.database = None
            self.engine = None
            for key, value in self._original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            shutil.rmtree(self._tempdir_path, ignore_errors=True)

    def _initialize_schema(self):
        startup_result = self.database.startup_database()
        if not startup_result.get("ok"):
            raise RuntimeError(
                f"Isolated test database startup failed: stage={startup_result.get('stage')} "
                f"reason={startup_result.get('reason')}"
            )

    def commit(self):
        self.conn.commit()

    def account_id(self, account_name, account_type=None):
        return int(self.engine.get_account_id(self.conn, account_name, account_type))

    def create_customer(self, name="Customer A"):
        cursor = self.conn.execute(
            """
            INSERT INTO customers (company_key, customer_id, name, email, phone, address, current_balance, currency)
            VALUES (?, ?, ?, ?, ?, ?, 0, 'GHS')
            """,
            (self.company_key, f"CUST-{name.replace(' ', '').upper()}", name, f"{name}@example.com", "000", "Accra"),
        )
        self.commit()
        return int(cursor.lastrowid)

    def create_supplier(self, name="Supplier A"):
        cursor = self.conn.execute(
            """
            INSERT INTO suppliers (company_key, name, email, phone, address, category, currency)
            VALUES (?, ?, ?, ?, ?, 'General', 'GHS')
            """,
            (self.company_key, name, f"{name}@example.com", "000", "Accra"),
        )
        self.commit()
        return int(cursor.lastrowid)

    def create_invoice(self, customer_id=None, status="Posted", amount=100.0, invoice_date=None):
        cursor = self.conn.execute(
            """
            INSERT INTO invoices (
                company_key, customer_id, invoice_number, invoice_date, due_date,
                status, approval_status, amount, currency, description, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
            """,
            (
                self.company_key,
                customer_id,
                f"INV-{datetime_suffix('INV')}",
                (invoice_date or self.today).isoformat(),
                (invoice_date or self.today).isoformat(),
                status,
                status,
                float(amount),
                "Test invoice",
                "Bookkeeper",
            ),
        )
        self.commit()
        return int(cursor.lastrowid)

    def create_bill(self, supplier_id=None, status="Posted", amount=100.0, bill_date=None):
        cursor = self.conn.execute(
            """
            INSERT INTO bills (
                company_key, supplier_id, bill_number, bill_date, due_date,
                status, approval_status, amount, currency, description, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'GHS', ?, ?)
            """,
            (
                self.company_key,
                supplier_id,
                f"BILL-{datetime_suffix('BILL')}",
                (bill_date or self.today).isoformat(),
                (bill_date or self.today).isoformat(),
                status,
                status,
                float(amount),
                "Test bill",
                "Bookkeeper",
            ),
        )
        self.commit()
        return int(cursor.lastrowid)

    def create_payment(
        self,
        payment_type,
        customer_id=None,
        supplier_id=None,
        invoice_id=None,
        bill_id=None,
        status="Posted",
        amount=100.0,
        payment_date=None,
    ):
        cursor = self.conn.execute(
            """
            INSERT INTO payments (
                company_key, payment_date, payment_type, status, customer_id, supplier_id,
                invoice_id, bill_id, amount, currency, method, reference, approval_status, created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'GHS', 'Cash', ?, ?, ?)
            """,
            (
                self.company_key,
                (payment_date or self.today).isoformat(),
                payment_type,
                status,
                customer_id,
                supplier_id,
                invoice_id,
                bill_id,
                float(amount),
                f"PAY-{datetime_suffix('PAY')}",
                status,
                "Bookkeeper",
            ),
        )
        self.commit()
        return int(cursor.lastrowid)

    def create_period(self, label, start_date, end_date, status="Open", is_locked=0):
        self.conn.execute(
            """
            INSERT INTO accounting_periods (
                company_key, period_label, start_date, end_date, status, is_locked
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, label, start_date.isoformat(), end_date.isoformat(), status, int(is_locked)),
        )
        self.commit()

    def post_entry(
        self,
        lines,
        description="Test posting",
        reference="TEST-REF",
        source_table=None,
        source_id=None,
        source_type=None,
        customer_id=None,
        supplier_id=None,
        payment_id=None,
        inventory_item_id=None,
        approval_status="Posted",
        manual_entry=False,
        created_by="Bookkeeper",
        user_role="Bookkeeper",
        posting_date=None,
    ):
        entry_id = self.engine.post_accounting_impact(
            company_key=self.company_key,
            date=posting_date or self.today,
            description=description,
            reference=reference,
            lines=lines,
            created_by=created_by,
            branch_id=None,
            customer_id=customer_id,
            supplier_id=supplier_id,
            inventory_item_id=inventory_item_id,
            payment_id=payment_id,
            source_module="tests",
            source_table=source_table,
            source_type=source_type,
            source_id=source_id,
            approval_status=approval_status,
            manual_entry=manual_entry,
            user_role=user_role,
            conn=self.conn,
        )
        self.commit()
        return int(entry_id)

    def journal_count(self, source_table=None, source_id=None):
        query = "SELECT COUNT(*) AS row_count FROM journal_entries WHERE company_key = ?"
        params = [self.company_key]
        if source_table is not None:
            query += " AND lower(COALESCE(source_table, '')) = lower(?)"
            params.append(source_table)
        if source_id is not None:
            query += " AND source_id = ?"
            params.append(int(source_id))
        row = self.conn.execute(query, tuple(params)).fetchone()
        return int(row["row_count"] or 0)


def datetime_suffix(prefix):
    return f"{prefix}-{os.getpid()}-{next(_suffix_counter)}"


def build_lines(*entries):
    return list(entries)


def find_trial_balance_row(rows, account_name):
    for row in rows:
        if str(row.get("account_name")) == account_name:
            return row
    return None


def sum_balance_sheet(rows, category):
    return round(
        sum(float(row.get("amount") or 0.0) for row in rows if str(row.get("category")) == category),
        2,
    )


def _counter():
    value = 0
    while True:
        value += 1
        yield value


_suffix_counter = _counter()
