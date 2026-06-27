import importlib

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix


class ERPCrossModuleWorkflowTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.database.ensure_pos_sales_schema(self.conn)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO branches (branch_id, company_key, branch_name)
            VALUES (?, ?, ?)
            """,
            ("MAIN", self.company_key, "Main Branch"),
        )
        self.commit()

    def _create_inventory_item(self, *, qty=10.0, cost_price=5.0, price=15.0):
        cursor = self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode,
                qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, '', ?, ?, ?, 1)
            """,
            (self.company_key, "Cross Module Item", f"XMOD-{datetime_suffix('I')}", qty, price, cost_price),
        )
        self.commit()
        return int(cursor.lastrowid)

    def test_pos_sale_reduces_inventory_posts_revenue_cogs_and_customer_balance(self):
        customer_id = self.create_customer("Cross POS Customer")
        item_id = self._create_inventory_item(qty=6.0, cost_price=7.0, price=20.0)
        sale_reference = f"PROD-POS-{datetime_suffix('POS')}"
        cart = [
            {
                "inventory_item_id": item_id,
                "name": "Cross Module Item",
                "item_code": "XMOD",
                "barcode": "",
                "qty": 2.0,
                "price": 20.0,
                "line_discount": 0.0,
                "tax_rate": 0.0,
                "line_total": 40.0,
                "cost_price": 7.0,
            }
        ]
        self.database.execute_portable_write(
            self.conn,
            "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
            (2.0, item_id, self.company_key),
        )
        pos_sale_id = self.modules._persist_pos_sale(
            self.conn,
            self.company_key,
            "MAIN",
            sale_reference,
            {
                "receipt_number": sale_reference,
                "sale_date": self.today.isoformat(),
                "sale_datetime": f"{self.today.isoformat()} 12:00:00",
                "cashier": "Cashier",
                "payment_method": "On Credit",
                "subtotal": 40.0,
                "discount_total": 0.0,
                "tax_total": 0.0,
                "grand_total": 40.0,
            },
            cart,
            customer_id=customer_id,
        )
        revenue_entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Accounts Receivable", "Asset"), "debit": 40.0, "credit": 0.0},
                {"account_id": self.account_id("Sales Revenue", "Income"), "debit": 0.0, "credit": 40.0},
            ),
            description="Cross-module POS revenue",
            reference=f"{sale_reference}-REV",
            source_table="pos_sales",
            source_id=pos_sale_id,
            source_type="POS Sale",
            customer_id=customer_id,
        )
        cogs_entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Cost of Goods Sold", "Expense"), "debit": 14.0, "credit": 0.0},
                {"account_id": self.account_id("Inventory", "Asset"), "debit": 0.0, "credit": 14.0},
            ),
            description="Cross-module POS COGS",
            reference=f"{sale_reference}-COGS",
            source_table="pos_sales",
            source_id=pos_sale_id,
            source_type="POS COGS",
            inventory_item_id=item_id,
        )
        self.commit()

        qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.assertEqual(qty, 4.0)
        self.assertGreater(revenue_entry_id, 0)
        self.assertGreater(cogs_entry_id, 0)
        self.assertEqual(self.engine.get_customer_balance(self.company_key, customer_id, conn=self.conn), 40.0)
        cogs_total = self.engine.get_account_total(self.company_key, "Cost of Goods Sold", conn=self.conn)
        self.assertEqual(cogs_total["debit_total"], 14.0)

    def test_purchase_inventory_increase_supplier_ap_and_journal_sync(self):
        supplier_id = self.create_supplier("Cross Purchase Supplier")
        item_id = self._create_inventory_item(qty=1.0, cost_price=10.0, price=15.0)
        bill_id = self.create_bill(supplier_id=supplier_id, status="Posted", amount=120.0)
        before_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        self.modules._insert_stock_movement_record(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            item_name="Cross Module Item",
            movement_type="STOCK_IN",
            quantity=3.0,
            previous_qty=before_qty,
            new_qty=before_qty + 3.0,
            created_by="Inventory Officer",
            branch_id="MAIN",
            reason="Production certification purchase",
            reference="PROD-PURCHASE-001",
        )
        self.database.execute_portable_write(
            self.conn,
            "UPDATE inventory SET qty = ? WHERE id = ? AND company_key = ?",
            (before_qty + 3.0, item_id, self.company_key),
        )
        entry_id = self.post_entry(
            lines=build_lines(
                {"account_id": self.account_id("Inventory", "Asset"), "debit": 120.0, "credit": 0.0},
                {"account_id": self.account_id("Accounts Payable", "Liability"), "debit": 0.0, "credit": 120.0},
            ),
            description="Cross-module purchase inventory/AP",
            reference="PROD-PURCHASE-001",
            source_table="bills",
            source_id=bill_id,
            source_type="Inventory Purchase",
            supplier_id=supplier_id,
        )
        self.commit()

        after_qty = float(self.conn.execute("SELECT qty FROM inventory WHERE id = ?", (item_id,)).fetchone()["qty"])
        movement_count = int(
            self.conn.execute(
                "SELECT COUNT(*) AS c FROM stock_movements WHERE inventory_item_id = ? AND company_key = ?",
                (item_id, self.company_key),
            ).fetchone()["c"]
        )
        self.assertEqual(after_qty, before_qty + 3.0)
        self.assertEqual(movement_count, 1)
        self.assertGreater(entry_id, 0)
        self.assertEqual(self.engine.get_supplier_balance(self.company_key, supplier_id, conn=self.conn), 120.0)

    def test_failed_cross_module_write_rolls_back_all_rows(self):
        before_customers = int(
            self.conn.execute("SELECT COUNT(*) AS c FROM customers WHERE company_key = ?", (self.company_key,)).fetchone()["c"]
        )

        def failing_write(tx_conn):
            tx_conn.execute(
                "INSERT INTO customers (company_key, customer_id, name, currency) VALUES (?, ?, ?, 'GHS')",
                (self.company_key, "ROLLBACK-CUST", "Rollback Customer"),
            )
            raise RuntimeError("force rollback")

        with self.assertRaisesRegex(RuntimeError, "force rollback"):
            self.database.execute_db_write_transaction(
                failing_write,
                operation_name="production_certification_rollback",
                conn=self.conn,
                backend=self.database.get_active_db_backend(),
            )
        after_customers = int(
            self.conn.execute("SELECT COUNT(*) AS c FROM customers WHERE company_key = ?", (self.company_key,)).fetchone()["c"]
        )
        self.assertEqual(after_customers, before_customers)
