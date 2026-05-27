import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock

from test_support import ERPIsolatedTestCase


class _SessionState(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key, value):
        self[key] = value


class PosSuspendedSalesTests(ERPIsolatedTestCase):
    def setUp(self):
        super().setUp()
        self.modules = importlib.import_module("modules")
        self.database.ensure_pos_sales_schema(self.conn)
        self.commit()

    def _patch_streamlit_session(self, initial=None):
        state = _SessionState(initial or {})
        mock_st = MagicMock()
        mock_st.session_state = state
        self.modules.st = mock_st
        return state

    def _insert_suspended_sale(self, cashier, cart_payload, branch_id="", note="", suspend_reference=None):
        cart_json = json.dumps(cart_payload)
        reference = suspend_reference or self.modules._generate_suspended_sale_reference()
        self.conn.execute(
            """
            INSERT INTO pos_suspended_sales (
                company_key, branch_id, suspend_reference, cashier, cart_json, note, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'suspended', CURRENT_TIMESTAMP)
            """,
            (self.company_key, branch_id, reference, cashier, cart_json, note),
        )
        self.commit()

    def _fetch_suspended_rows(self, cashier, branch_id=None):
        suspend_query = """
            SELECT id, suspend_reference, cashier, note, created_at
            FROM pos_suspended_sales
            WHERE company_key = ?
              AND status = 'suspended'
        """
        suspend_params = [self.company_key]
        if branch_id:
            suspend_query += " AND COALESCE(branch_id, '') = ?"
            suspend_params.append(str(branch_id))
        suspend_query += " AND cashier = ? ORDER BY created_at DESC"
        suspend_params.append(cashier)
        return self.conn.execute(suspend_query, tuple(suspend_params)).fetchall()

    def test_suspend_query_filters_branch_and_cashier(self):
        self._insert_suspended_sale("CashierA", {"cart": [], "discount_state": {}}, branch_id="BR1")
        self._insert_suspended_sale("CashierB", {"cart": [], "discount_state": {}}, branch_id="BR1")

        rows_a = self._fetch_suspended_rows("CashierA", branch_id="BR1")
        self.assertEqual(len(rows_a), 1)
        self.assertEqual(rows_a[0]["cashier"], "CashierA")

        rows_b = self._fetch_suspended_rows("CashierB", branch_id="BR1")
        self.assertEqual(len(rows_b), 1)

    def test_restore_cart_payload_roundtrip(self):
        company_key = self.company_key
        cart_key = f"pos_cart_{company_key}"
        discount_key = f"pos_cart_discount_{company_key}"
        sample_cart = [
            {
                "inventory_item_id": 1,
                "item_id": 1,
                "name": "Widget",
                "item_name": "Widget",
                "item_code": "W1",
                "barcode": "111",
                "price": 10.0,
                "cost_price": 5.0,
                "tax_rate": 0.0,
                "qty": 2,
                "is_manual": False,
                "line_discount_type": "amount",
                "line_discount_value": 0.0,
                "line_discount": 0.0,
                "line_total": 20.0,
            }
        ]
        state = self._patch_streamlit_session(
            {
                cart_key: [],
                discount_key: {
                    "type": "amount",
                    "value": 0.0,
                    "computed": 0.0,
                    "threshold_requires_approval": False,
                },
            }
        )
        state[cart_key] = sample_cart
        payload_json = self.modules._serialize_pos_cart_payload(company_key, "CashierA", "hold")
        self.modules._restore_pos_cart_payload(company_key, payload_json)

        restored = state[cart_key]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["item_name"], "Widget")
        self.assertEqual(int(restored[0]["qty"]), 2)
        self.assertEqual(float(restored[0]["line_total"]), 20.0)

    def test_resume_marks_row_resumed(self):
        payload = {
            "cart": [
                {
                    "inventory_item_id": None,
                    "name": "Manual",
                    "item_name": "Manual",
                    "qty": 1,
                    "price": 5.0,
                    "line_discount_type": "amount",
                    "line_discount_value": 0.0,
                }
            ],
            "discount_state": {"type": "amount", "value": 0.0, "computed": 0.0},
        }
        self._insert_suspended_sale("CashierA", payload)
        row = self._fetch_suspended_rows("CashierA")[0]
        self.conn.execute(
            "UPDATE pos_suspended_sales SET status = 'resumed', resumed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (int(row["id"]),),
        )
        self.commit()
        still_suspended = self._fetch_suspended_rows("CashierA")
        self.assertEqual(len(still_suspended), 0)

    def test_show_pos_resume_ui_outside_cart_branch(self):
        source = Path(self.modules.__file__).read_text(encoding="utf-8")
        show_pos_start = source.index("def show_pos(")
        show_pos_end = source.index("\ndef show_sales_purchase", show_pos_start)
        show_pos_source = source[show_pos_start:show_pos_end]

        resume_marker = 'key=f"pos_resume_sale_{company_key}"'
        self.assertIn(resume_marker, show_pos_source)

        payment_panel = 'section_header("Payment & Discounts")'
        payment_idx = show_pos_source.index(payment_panel)
        resume_idx = show_pos_source.index(resume_marker, payment_idx)

        cart_branch = 'if not cart:\n            st.markdown("#### Payment")'
        cart_idx = show_pos_source.index(cart_branch, payment_idx)
        cart_else_idx = show_pos_source.index("\n        else:\n", cart_idx)

        self.assertGreater(resume_idx, cart_else_idx)
        resume_line = show_pos_source[:resume_idx].splitlines()[-1].strip()
        self.assertTrue(resume_line.startswith("if resume_col.button("), resume_line)

        suspend_in_actions = 'if suspend_action_col.button("Suspend Sale"'
        suspend_idx = show_pos_source.index(suspend_in_actions, payment_idx)
        resume_after_suspend = show_pos_source.index(resume_marker, suspend_idx)
        between = show_pos_source[suspend_idx:resume_after_suspend]
        self.assertIn('st.markdown("</div>", unsafe_allow_html=True)', between)
