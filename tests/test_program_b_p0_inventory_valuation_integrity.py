"""
Program B P0 Sprint 4 — Inventory Valuation and General Ledger Integrity.
"""
import importlib
import inspect
import unittest

from test_support import ERPIsolatedTestCase, build_lines, datetime_suffix


class ProgramBP0InventoryValuationIntegrityTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.engine = importlib.import_module("accounting_engine")
        self.database = importlib.import_module("database")
        self.database.ensure_inventory_schema_integrity(self.conn)
        self.database.ensure_stock_movements_schema_integrity(self.conn)
        self.branch_id = "MAIN"
        self.role = "Accountant"
        self._ensure_branch(self.branch_id, "Main Branch")
        self.commit()

    def _ensure_branch(self, branch_id, branch_name=None):
        existing = self.conn.execute(
            "SELECT branch_id FROM branches WHERE company_key = ? AND branch_id = ?",
            (self.company_key, branch_id),
        ).fetchone()
        if existing:
            return branch_id
        self.conn.execute(
            """
            INSERT INTO branches (branch_id, company_key, branch_name, location, branch_type, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (branch_id, self.company_key, branch_name or branch_id, "Accra", "main"),
        )
        return branch_id

    def _insert_item(self, *, qty=10.0, cost_price=5.0, item_code="VAL-01", name="Valuation Item"):
        self.conn.execute(
            """
            INSERT INTO inventory (
                company_key, item_name, item_code, barcode, qty, price, cost_price, min_stock_level
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.company_key, name, item_code, f"B-{item_code}", qty, 12.0, cost_price, 1.0),
        )
        self.commit()
        return int(
            self.conn.execute(
                "SELECT id FROM inventory WHERE item_code = ? AND company_key = ?",
                (item_code, self.company_key),
            ).fetchone()["id"]
        )

    def _post_inventory_gl(self, amount, reference="INV-GL"):
        inventory_id = self.account_id("Inventory", "Asset")
        equity_id = self.account_id("Opening Balance Equity", "Equity")
        return self.post_entry(
            lines=build_lines(
                {"account_id": inventory_id, "debit": float(amount), "credit": 0.0},
                {"account_id": equity_id, "debit": 0.0, "credit": float(amount)},
            ),
            description="Inventory valuation test funding",
            reference=reference,
        )

    def test_authoritative_cost_field_is_cost_price(self):
        method = self.engine.INVENTORY_COSTING_METHOD
        self.assertEqual(method["authoritative_field"], "cost_price")
        self.assertEqual(method["method_key"], "last_unit_cost_field")
        self.assertIn("FIFO", method["not_implemented"])

    def test_quantity_times_cost_produces_item_and_total_value(self):
        self._insert_item(qty=4.0, cost_price=2.5, item_code="VAL-A", name="A")
        self._insert_item(qty=3.0, cost_price=10.0, item_code="VAL-B", name="B")
        snapshot = self.engine.build_inventory_valuation_snapshot(
            self.company_key,
            branch_id=None,
            conn=self.conn,
            active_backend="sqlite",
        )
        values = {row["item_code"]: row["inventory_value"] for row in snapshot["items"]}
        self.assertEqual(values["VAL-A"], 10.0)
        self.assertEqual(values["VAL-B"], 30.0)
        self.assertEqual(snapshot["totals"]["inventory_value"], 40.0)

    def test_parse_null_blank_and_string_costs_do_not_crash(self):
        cases = [None, "", "  ", "GHS 12.50", "1,200.00", "abc", "null", "-"]
        for raw in cases:
            parsed = self.engine.parse_inventory_cost_value(raw)
            self.assertIn("unit_cost", parsed)
            self.assertIsInstance(parsed["unit_cost"], float)
        resolved = self.engine.resolve_inventory_unit_cost({"cost_price": "GHS 7.25"})
        self.assertEqual(resolved["unit_cost"], 7.25)
        self.assertFalse(resolved["missing"])

    def test_missing_cost_and_negative_stock_are_flagged(self):
        self._insert_item(qty=5.0, cost_price=0.0, item_code="MISS", name="Missing Cost")
        self._insert_item(qty=-2.0, cost_price=4.0, item_code="NEG", name="Negative")
        snapshot = self.engine.build_inventory_valuation_snapshot(
            self.company_key,
            conn=self.conn,
            active_backend="sqlite",
        )
        self.assertEqual(snapshot["totals"]["missing_cost_count"], 1)
        self.assertEqual(snapshot["totals"]["negative_quantity_count"], 1)

    def test_reconciliation_matched_review_critical(self):
        self._insert_item(qty=10.0, cost_price=5.0, item_code="MATCH", name="Match Item")
        self._post_inventory_gl(50.0, reference="GL-MATCH")
        matched = self.engine.reconcile_inventory_subledger_to_gl(
            self.company_key,
            conn=self.conn,
            active_backend="sqlite",
        )
        self.assertEqual(matched["status"], "MATCHED")
        self.assertEqual(matched["difference"], 0.0)
        self.assertFalse(matched["auto_correct_journals_posted"])
        self.assertFalse(matched["costs_auto_modified"])

        review = self.engine.classify_inventory_reconciliation_status(
            25.0,
            subledger_value=50.0,
            gl_balance=25.0,
        )
        self.assertEqual(review, "REVIEW")
        critical = self.engine.classify_inventory_reconciliation_status(
            500.0,
            subledger_value=50.0,
            gl_balance=-450.0,
        )
        self.assertEqual(critical, "CRITICAL")

    def test_reconciliation_reports_difference_without_auto_post(self):
        self._insert_item(qty=10.0, cost_price=5.0, item_code="DRIFT", name="Drift Item")
        # No GL funding → subledger 50, GL 0
        result = self.engine.reconcile_inventory_subledger_to_gl(
            self.company_key,
            conn=self.conn,
            active_backend="sqlite",
        )
        self.assertEqual(result["subledger_value"], 50.0)
        self.assertEqual(result["gl_inventory_balance"], 0.0)
        self.assertEqual(result["difference"], 50.0)
        self.assertIn(result["status"], {"REVIEW", "CRITICAL"})
        journal_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM journal_entries WHERE company_key = ?",
            (self.company_key,),
        ).fetchone()["c"]
        self.assertEqual(int(journal_count), 0)

    def test_company_branch_backend_cache_key_isolation(self):
        snap_a = self.engine.build_inventory_valuation_snapshot(
            "CO-A",
            branch_id="MAIN",
            as_of_date="2026-08-01",
            conn=self.conn,
            active_backend="sqlite",
        )
        snap_b = self.engine.build_inventory_valuation_snapshot(
            "CO-B",
            branch_id="EAST",
            as_of_date="2026-08-02",
            conn=self.conn,
            active_backend="postgres",
        )
        self.assertNotEqual(snap_a["cache_key_parts"], snap_b["cache_key_parts"])
        self.assertEqual(snap_a["cache_key_parts"]["company_key"], "CO-A")
        self.assertEqual(snap_b["cache_key_parts"]["active_backend"], "postgres")
        self.assertEqual(snap_b["cache_key_parts"]["branch_id"], "EAST")

        cache_source = inspect.getsource(self.modules._cached_inventory_valuation_reconciliation)
        self.assertIn("company_key", cache_source)
        self.assertIn("branch_id_key", cache_source)
        self.assertIn("as_of_date_key", cache_source)
        self.assertIn("active_backend", cache_source)

    def test_pos_sale_uses_cost_price_basis(self):
        item_id = self._insert_item(qty=20.0, cost_price=3.5, item_code="POSC", name="POS Cost")
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="POS_SALE",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-2.0,
            reason="POS Sale",
            reference=f"POS-VAL-{datetime_suffix('V')}",
            source_document="pos_sale",
            source_id="T1",
        )
        self.commit()
        resolved = self.engine.resolve_inventory_unit_cost({"cost_price": 3.5})
        self.assertEqual(resolved["unit_cost"], 3.5)
        self.assertEqual(result["after_qty"], 18.0)
        expected_cogs = round(2.0 * 3.5, 2)
        self.assertEqual(expected_cogs, 7.0)

    def test_pos_return_reverses_expected_value(self):
        item_id = self._insert_item(qty=8.0, cost_price=4.0, item_code="POSR", name="POS Return")
        before = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )["totals"]["inventory_value"]
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="POS_RETURN",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=2.0,
            reason="POS Return",
            reference=f"RET-VAL-{datetime_suffix('V')}",
        )
        self.commit()
        after = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )["totals"]["inventory_value"]
        self.assertEqual(round(after - before, 2), 8.0)

    def test_invoice_stock_effects_remain_correct(self):
        item_id = self._insert_item(qty=12.0, cost_price=6.0, item_code="INVX", name="Invoice Item")
        effects = self.modules.apply_invoice_stock_effects(
            self.conn,
            company_key=self.company_key,
            invoice_reference=f"INV-{datetime_suffix('V')}",
            invoice_items=[{"inventory_item_id": item_id, "item_name": "Invoice Item", "quantity": 2.0}],
            role=self.role,
            branch_id=self.branch_id,
        )
        self.commit()
        self.assertEqual(effects["cogs_total"], 12.0)
        self.assertTrue(effects["stock_deduction_applied"])
        qty = float(
            self.conn.execute(
                "SELECT qty FROM inventory WHERE id = ?",
                (item_id,),
            ).fetchone()["qty"]
        )
        self.assertEqual(qty, 10.0)

    def test_stock_receive_updates_cost_and_valuation(self):
        item_id = self._insert_item(qty=1.0, cost_price=2.0, item_code="RCV", name="Receive Item")
        receive = self.modules._receive_inventory_stock(
            self.conn,
            self.company_key,
            self.role,
            inventory_item_id=item_id,
            qty_received=4.0,
            unit_cost=8.0,
            branch_id=self.branch_id,
            reference_number=f"RCV-{datetime_suffix('V')}",
        )
        self.commit()
        cost = float(
            self.conn.execute("SELECT cost_price FROM inventory WHERE id = ?", (item_id,)).fetchone()["cost_price"]
        )
        self.assertEqual(cost, 8.0)
        self.assertEqual(receive["new_qty"], 5.0)
        snapshot = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )
        item_row = next(row for row in snapshot["items"] if row["item_id"] == item_id)
        self.assertEqual(item_row["inventory_value"], 40.0)

    def test_quantity_only_adjustment_with_missing_cost_is_explicit(self):
        item_id = self._insert_item(qty=5.0, cost_price=0.0, item_code="QONLY", name="Qty Only")
        result = self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="ADJUSTMENT",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=2.0,
            reason="Adjustment",
            reference=f"ADJ-{datetime_suffix('V')}",
            notes="unvalued=true | cost_flagged_for_review=true",
        )
        self.commit()
        movement = self.conn.execute(
            "SELECT notes FROM stock_movements WHERE id = ?",
            (result["movement_id"],),
        ).fetchone()
        self.assertIn("unvalued=true", str(movement["notes"] or ""))
        snapshot = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )
        self.assertGreaterEqual(snapshot["totals"]["missing_cost_count"], 1)

    def test_transfer_does_not_create_artificial_company_value(self):
        item_id = self._insert_item(qty=10.0, cost_price=5.0, item_code="XFER", name="Transfer Item")
        before = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )["totals"]["inventory_value"]
        source = inspect.getsource(self.modules.show_inventory)
        self.assertIn("quantity_only_transfer=true", source)
        self.assertIn("Transfer recorded as a quantity movement only", source)
        # Company-wide quantity relocation must not invent GL profit via transfer journals.
        self.modules.apply_inventory_quantity_change(
            self.conn,
            company_key=self.company_key,
            inventory_item_id=item_id,
            movement_type="TRANSFER",
            created_by=self.role,
            branch_id=self.branch_id,
            quantity_delta=-3.0,
            reason="Transfer",
            reference=f"XFER-{datetime_suffix('V')}",
            notes="quantity_only_transfer=true",
        )
        self.commit()
        after = self.engine.build_inventory_valuation_snapshot(
            self.company_key, conn=self.conn, active_backend="sqlite"
        )["totals"]["inventory_value"]
        # Qty reduced but no new GL journal from this helper; valuation falls with qty×cost.
        self.assertEqual(after, before - 15.0)
        journals = self.conn.execute(
            "SELECT COUNT(*) AS c FROM journal_entries WHERE company_key = ? AND reference LIKE 'XFER-%'",
            (self.company_key,),
        ).fetchone()["c"]
        self.assertEqual(int(journals), 0)

    def test_missing_cost_does_not_silently_invent_numeric_cogs(self):
        resolved = self.engine.resolve_inventory_unit_cost({"cost_price": None})
        self.assertTrue(resolved["missing"])
        self.assertEqual(resolved["unit_cost"], 0.0)
        self.assertTrue(resolved["flagged_for_review"])
        effects = self.modules.apply_invoice_stock_effects
        source = inspect.getsource(effects)
        self.assertIn("resolve_inventory_unit_cost", source)
        self.assertIn("cost_flagged_for_review", source)

    def test_ui_role_gate_and_no_client_diagnostics(self):
        self.assertTrue(self.modules.can_view_inventory_valuation("Accountant"))
        self.assertFalse(self.modules.can_view_inventory_valuation("Cashier"))
        self.assertFalse(self.modules.can_view_inventory_valuation("Inventory Officer"))
        valuation_source = inspect.getsource(self.modules.show_inventory_valuation)
        for banned in ("stacktrace", "psycopg2", "ALTER TABLE", "LV-", "migration_cleanup", "raw SQL"):
            self.assertNotIn(banned, valuation_source)
        self.assertIn("No correcting journal was posted", valuation_source)
        app = importlib.import_module("app")
        self.assertIn("Inventory Valuation", app.PAGE_PERMISSION_MAP)
        self.assertEqual(app.PAGE_PERMISSION_MAP["Inventory Valuation"], "view_reports")

    def test_sqlite_and_postgres_paths_remain_portable(self):
        insert_source = inspect.getsource(self.modules._insert_stock_movement_record)
        apply_source = inspect.getsource(self.modules.apply_inventory_quantity_change)
        self.assertIn("ensure_insert_sql_returning", insert_source)
        self.assertIn("execute_portable_write", apply_source)
        recon_source = inspect.getsource(self.engine.reconcile_inventory_subledger_to_gl)
        self.assertIn("get_account_total", recon_source)
        self.assertIn("build_inventory_valuation_snapshot", recon_source)

    def test_finance_integrity_inventory_exposes_status(self):
        self._insert_item(qty=2.0, cost_price=5.0, item_code="FIN", name="Finance Item")
        self._post_inventory_gl(10.0, reference="FIN-GL")
        diagnostics = self.engine.get_finance_integrity_diagnostics(
            self.company_key,
            conn=self.conn,
        )
        self.assertIn("status", diagnostics["inventory"])
        self.assertEqual(diagnostics["inventory"]["status"], "MATCHED")
        self.assertFalse(diagnostics["inventory"]["auto_correct_journals_posted"])

    def test_sprint3_movement_helper_still_present(self):
        self.assertTrue(callable(self.modules.apply_inventory_quantity_change))
        source = inspect.getsource(self.modules.apply_inventory_quantity_change)
        self.assertIn("stock_movements", source)
        self.assertIn("execute_portable_write", source)


if __name__ == "__main__":
    unittest.main()
