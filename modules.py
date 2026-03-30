import logging
import os
import random
import hashlib
import sqlite3
import base64
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dateutil.relativedelta import relativedelta
from groq import Groq
from PIL import Image

try:
    from pyzbar import pyzbar
except ImportError:
    pyzbar = None

try:
    import cv2
except ImportError:
    cv2 = None

# Setup Logger
logger = logging.getLogger(__name__)

# Import shared utilities from database
from database import get_connection, log_audit_action as database_log_audit_action


def log_audit_action(conn, company_key, user_role, action, module_name, details=None):
    """Proxy audit logging so app.py can import the shared action from this module."""
    return database_log_audit_action(conn, company_key, user_role, action, module_name, details)


# ==========================================
# PAYSTACK PAYMENT
# ==========================================
def initialize_paystack_payment(email, amount, reference):
    """Initialize a payment with Paystack."""
    try:
        paystack_secret_key = st.secrets.get("paystack_secret_key")
    except Exception:
        paystack_secret_key = None
    if not paystack_secret_key:
        st.info(
            "System Configuration Required: the Paystack payment key has not been configured yet. "
            "Please contact the system administrator to complete payment setup."
        )
        return None

    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {paystack_secret_key}",
        "Content-Type": "application/json"
    }
    data = {
        "email": email,
        "amount": int(amount * 100),  # Paystack uses pesewas/kobo
        "reference": reference
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response_data = response.json()
        if response_data.get('status'):
            return response_data['data']['authorization_url']
    except Exception as e:
        logger.error(f"Paystack error: {e}")
    return None


# ==========================================
# DATABASE HELPERS (modules-level)
# ==========================================
DB_NAME = "eka_vault.db"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)


def get_master_price_per_month():
    conn = None
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT master_price_per_month FROM system_settings WHERE id = 1"
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 500.0
    except Exception as exc:
        logger.warning(f"Falling back to default master price: {exc}")
        return 500.0
    finally:
        if conn:
            conn.close()


def _get_active_company_id(expected_company_id=None):
    active_company_id = st.session_state.get("company_id")
    if not active_company_id:
        active_company_id = st.session_state.get("user", {}).get("key")
    if expected_company_id and active_company_id and expected_company_id != active_company_id:
        logger.warning(
            "Blocked cross-tenant access attempt: requested=%s active=%s",
            expected_company_id,
            active_company_id,
        )
    return active_company_id


def _get_groq_client():
    """Create a Groq client only when the API key is available."""
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        api_key = None
    if not api_key:
        return None
    try:
        return Groq(api_key=api_key)
    except Exception as exc:
        logger.warning(f"Failed to initialize Groq client: {exc}")
        return None


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _fetch_ai_assistant_records(conn, client_id):
    """Collect the last 30 days of invoice, expense, and payroll activity for a client."""
    since_date = (datetime.now() - timedelta(days=30)).date().isoformat()
    records = {"invoices": [], "expenses": [], "payroll": []}

    if _table_exists(conn, "vouchers"):
        invoice_rows = conn.execute(
            """
            SELECT date, narration, reference_no, credit
            FROM vouchers
            WHERE company_key = ? AND v_type = 'Sales' AND date >= ? AND COALESCE(status, 'Active') != 'Void'
            ORDER BY date DESC
            LIMIT 50
            """,
            (client_id, since_date),
        ).fetchall()
        expense_rows = conn.execute(
            """
            SELECT date, narration, reference_no, debit, credit
            FROM vouchers
            WHERE company_key = ? AND v_type = 'Expense' AND date >= ? AND COALESCE(status, 'Active') != 'Void'
            ORDER BY date DESC
            LIMIT 50
            """,
            (client_id, since_date),
        ).fetchall()
        records["invoices"] = [dict(row) for row in invoice_rows]
        records["expenses"] = [dict(row) for row in expense_rows]

    if _table_exists(conn, "payroll"):
        payroll_rows = conn.execute(
            """
            SELECT created_at, emp_name, basic_salary, allowances, paye, net_salary, month, year, payment_status
            FROM payroll
            WHERE company_key = ? AND date(COALESCE(created_at, CURRENT_TIMESTAMP)) >= date(?) AND COALESCE(status, 'Active') != 'Void'
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (client_id, since_date),
        ).fetchall()
        records["payroll"] = [dict(row) for row in payroll_rows]

    return records


def _summarize_ai_assistant_data(records):
    invoice_total = sum(float(row.get("credit") or 0) for row in records["invoices"])
    expense_total = sum(
        float(row.get("debit") or row.get("credit") or 0) for row in records["expenses"]
    )
    payroll_total = sum(float(row.get("net_salary") or 0) for row in records["payroll"])

    lines = [
        f"Invoices in last 30 days: {len(records['invoices'])}, total value GHs {invoice_total:,.2f}.",
        f"Expenses in last 30 days: {len(records['expenses'])}, total value GHs {expense_total:,.2f}.",
        f"Payroll entries in last 30 days: {len(records['payroll'])}, net payroll GHs {payroll_total:,.2f}.",
    ]

    for label, rows in (
        ("Recent invoices", records["invoices"][:5]),
        ("Recent expenses", records["expenses"][:5]),
        ("Recent payroll", records["payroll"][:5]),
    ):
        if rows:
            lines.append(f"{label}: {rows}")

    return "\n".join(lines)


def _row_to_dict(row):
    return dict(row) if row is not None else {}


def _generate_staff_login_key(company_key, role_name):
    suffix = "BK" if role_name == "Bookkeeper" else "STF"
    return f"{company_key}-{suffix}-{random.randint(1000, 9999)}"


def _hash_staff_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _clear_streamlit_state(*keys):
    for key in keys:
        st.session_state.pop(key, None)


def _ensure_counterparty(conn, company_key, party_name, party_type, city_region, tx_date, balance_delta):
    existing = conn.execute(
        """
        SELECT id, balance
        FROM counterparties
        WHERE company_key = ? AND party_name = ? AND party_type = ?
        """,
        (company_key, party_name, party_type),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE counterparties
            SET city_region = COALESCE(NULLIF(?, ''), city_region),
                last_transaction = ?,
                balance = COALESCE(balance, 0) + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (city_region, tx_date, balance_delta, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO counterparties
                (company_key, party_name, party_type, city_region, last_transaction, balance)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (company_key, party_name, party_type, city_region, tx_date, balance_delta),
        )


def show_debtors_by_city_report(company_key):
    st.subheader("Debtors by City")
    conn = None
    try:
        conn = get_connection()
        city_rows = conn.execute(
            """
            SELECT DISTINCT COALESCE(NULLIF(city_region, ''), 'Unassigned') AS city_region
            FROM counterparties
            WHERE company_key = ? AND party_type = 'Customer'
            ORDER BY city_region
            """,
            (company_key,),
        ).fetchall()
        city_options = ["All Cities"] + [row[0] for row in city_rows]
        selected_city = st.selectbox("Filter by City / Region", city_options, key=f"debtor_city_{company_key}")

        query = """
            SELECT party_name, last_transaction, balance, COALESCE(NULLIF(city_region, ''), 'Unassigned') AS city_region
            FROM counterparties
            WHERE company_key = ? AND party_type = 'Customer' AND balance > 0
        """
        params = [company_key]
        if selected_city != "All Cities":
            query += " AND COALESCE(NULLIF(city_region, ''), 'Unassigned') = ?"
            params.append(selected_city)
        query += " ORDER BY city_region, party_name"

        debtors = conn.execute(query, tuple(params)).fetchall()
        if not debtors:
            st.info("No debtor balances are available for the selected city.")
            return

        report_df = pd.DataFrame(
            debtors,
            columns=["Customer Name", "Last Transaction", "Balance", "City / Region"],
        )
        road_df = report_df[["Customer Name", "Last Transaction", "Balance"]].copy()
        road_df["Balance"] = road_df["Balance"].map(lambda value: f"GHs {float(value):,.2f}")

        st.dataframe(report_df, use_container_width=True)
        st.markdown("Road Summary")
        st.dataframe(road_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Debtor city report error: {exc}")
    finally:
        if conn:
            conn.close()


def init_db():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                admin_name TEXT,
                contact_email TEXT,
                status TEXT DEFAULT 'Active',
                subscription_expiry TEXT,
                created_at TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                amount REAL,
                status TEXT,
                date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts_payable (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT,
                amount REAL,
                status TEXT,
                date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chart_of_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT,
                account_type TEXT,
                balance REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS vouchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                narration TEXT,
                amount REAL,
                ref_no TEXT,
                date TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                module_name TEXT,
                message TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def log_system_event(level, module_name, message):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO system_logs (timestamp, level, module_name, message) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), level, module_name, message),
        )
        conn.commit()
    finally:
        conn.close()


def get_excel_bin(df):
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Export")
        return output.getvalue()
    except Exception:
        return b""


def _build_receipt(company_name, items, total_amount, sale_date):
    lines = [
        company_name,
        "STANDARD POS RECEIPT",
        f"Date: {sale_date}",
        "-" * 36,
        "Item                     Qty    Price",
        "-" * 36,
    ]
    for item in items:
        lines.append(
            f"{item['name'][:20]:<20} {int(item['qty']):>3} {float(item['price']):>8.2f}"
        )
    lines.extend(
        [
            "-" * 36,
            f"TOTAL: GHs {float(total_amount):,.2f}",
        ]
    )
    return "\n".join(lines)


def _calculate_payroll_values(basic_salary, allowances, deductions=0.0):
    ssnit_t1_rate = 0.055
    ssnit_t2_rate = 0.05
    bands = [
        (319, 0.0),
        (110, 0.05),
        (130, 0.10),
        (3000, 0.175),
        (16441, 0.25),
        (float("inf"), 0.30),
    ]

    taxable = max(float(basic_salary) + float(allowances) - float(deductions), 0.0)
    ssnit_t1 = float(basic_salary) * ssnit_t1_rate
    ssnit_t2 = float(basic_salary) * ssnit_t2_rate
    chargeable = max(taxable - ssnit_t1, 0.0)

    monthly_taxable = chargeable / 12 if chargeable > 0 else 0.0
    paye = 0.0
    remaining = monthly_taxable
    for band, rate in bands:
        if remaining <= 0:
            break
        chunk = min(remaining, band)
        paye += chunk * rate
        remaining -= chunk
    paye *= 12
    net_salary = float(basic_salary) + float(allowances) - float(deductions) - ssnit_t1 - paye

    return {
        "ssnit_t1": ssnit_t1,
        "ssnit_t2": ssnit_t2,
        "taxable_income": taxable,
        "paye": paye,
        "net_salary": net_salary,
    }


def _import_inventory_from_excel(conn, company_key, file_obj):
    imported_df = pd.read_excel(file_obj)
    if imported_df.empty:
        return 0

    column_map = {column.lower().strip(): column for column in imported_df.columns}
    required = ["item_name", "category", "quantity"]
    missing = [column for column in required if column not in column_map]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    changed_rows = 0
    for _, row in imported_df.iterrows():
        row_id = row[column_map["id"]] if "id" in column_map and not pd.isna(row[column_map["id"]]) else None
        item_name = str(row[column_map["item_name"]]).strip()
        if not item_name:
            continue
        category = str(row[column_map["category"]]).strip()
        opening_column = column_map.get("opening_stock") or column_map.get("opening_balance")
        barcode_column = column_map.get("barcode")
        qty = float(row[column_map["quantity"]] or 0)
        opening_balance = float(row[opening_column] or qty) if opening_column else qty
        price_column = column_map.get("selling_price") or column_map.get("unit_price") or column_map.get("price")
        cost_column = column_map.get("cost_price")
        barcode = str(row[barcode_column]).strip() if barcode_column and not pd.isna(row[barcode_column]) else ""
        price = float(row[price_column] or 0) if price_column else 0.0
        cost_price = float(row[cost_column] or 0) if cost_column else 0.0
        if row_id is not None:
            existing = conn.execute(
                "SELECT id FROM inventory WHERE company_key = ? AND id = ?",
                (company_key, int(row_id)),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE inventory
                    SET item_name = ?, barcode = ?, category = ?, opening_balance = ?, qty = ?, price = ?, cost_price = ?
                    WHERE company_key = ? AND id = ?
                    """,
                    (item_name, barcode, category, opening_balance, qty, price, cost_price, company_key, int(row_id)),
                )
                changed_rows += 1
                continue
        existing = conn.execute(
            """
            SELECT id FROM inventory
            WHERE company_key = ? AND item_name = ? AND COALESCE(category, '') = ?
            """,
            (company_key, item_name, category),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE inventory
                SET barcode = COALESCE(NULLIF(?, ''), barcode), opening_balance = ?, qty = ?, price = ?, cost_price = ?
                WHERE company_key = ? AND id = ?
                """,
                (barcode, opening_balance, qty, price, cost_price, company_key, existing["id"]),
            )
            changed_rows += 1
            continue
        conn.execute(
            """
            INSERT INTO inventory (company_key, item_name, barcode, category, opening_balance, qty, price, cost_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (company_key, item_name, barcode, category, opening_balance, qty, price, cost_price),
        )
        changed_rows += 1
    return changed_rows


SCANNER_BEEP_BASE64 = (
    "UklGRlQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YTAAAAAAAP//AAD//wAA//8AAP//"
    "AAD//wAA//8AAP//AAD//wAA"
)


def _set_input_pending(source_key, pending_key):
    pending_value = str(st.session_state.get(source_key, "") or "").strip()
    if pending_value:
        st.session_state[pending_key] = pending_value


def _trigger_scan_feedback(message_key, message, level="success", beep_key=None):
    st.session_state[message_key] = {"level": level, "text": message}
    if beep_key:
        st.session_state[beep_key] = True


def _render_flash_message(message_key, beep_key=None):
    payload = st.session_state.pop(message_key, None)
    if not payload:
        return
    level = payload.get("level", "info")
    text = payload.get("text", "")
    getattr(st, level, st.info)(text)
    if beep_key and st.session_state.pop(beep_key, False):
        components.html(
            f"""
            <audio autoplay>
                <source src="data:audio/wav;base64,{SCANNER_BEEP_BASE64}" type="audio/wav">
            </audio>
            """,
            height=0,
        )


def _focus_text_input(input_label):
    components.html(
        f"""
        <script>
        const focusTarget = () => {{
            const parentDoc = window.parent.document;
            const input = parentDoc.querySelector('input[aria-label="{input_label}"]');
            if (input) {{
                input.focus();
                input.select();
            }}
        }};
        focusTarget();
        setTimeout(focusTarget, 150);
        </script>
        """,
        height=0,
    )


def _decode_camera_code(camera_file):
    if camera_file is None:
        return None, "Capture an image to scan."

    image_bytes = camera_file.getvalue()
    image = Image.open(BytesIO(image_bytes)).convert("RGB")

    try:
        if pyzbar is not None:
            decoded = pyzbar.decode(image)
            if decoded:
                return decoded[0].data.decode("utf-8").strip(), None
    except Exception:
        pass

    try:
        import numpy as np

        if cv2 is not None:
            image_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            qr_detector = cv2.QRCodeDetector()
            decoded_text, _, _ = qr_detector.detectAndDecode(image_array)
            if decoded_text:
                return decoded_text.strip(), None
    except Exception:
        pass

    if pyzbar is None or cv2 is None:
        return None, "Scanner module loading... Please ensure dependencies are installed."
    return None, "Install `pyzbar` or `opencv-python-headless` on the host to decode camera scans."


def _render_camera_scanner(module_key, pending_key):
    toggle_key = f"{module_key}_camera_open"
    nonce_key = f"{module_key}_camera_nonce"
    image_sig_key = f"{module_key}_camera_image_sig"
    button_label = "Close Camera" if st.session_state.get(toggle_key) else "Tap to Scan"

    if st.button(button_label, key=f"{module_key}_camera_toggle_btn"):
        if pyzbar is None or cv2 is None:
            st.info("Scanner module loading... Please ensure dependencies are installed.")
            return
        st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
        if not st.session_state[toggle_key]:
            st.session_state.pop(image_sig_key, None)
        st.rerun()

    if not st.session_state.get(toggle_key):
        return

    nonce = st.session_state.get(nonce_key, 0)
    camera_file = st.camera_input("Scan with Camera", key=f"{module_key}_camera_input_{nonce}")
    if camera_file is None:
        return

    image_signature = f"{camera_file.name}:{len(camera_file.getvalue())}"
    if image_signature == st.session_state.get(image_sig_key):
        return

    decoded_value, error_message = _decode_camera_code(camera_file)
    st.session_state[image_sig_key] = image_signature
    if decoded_value:
        st.session_state[pending_key] = decoded_value
        st.session_state[toggle_key] = False
        st.session_state[nonce_key] = nonce + 1
        st.rerun()
    if error_message:
        st.info(error_message)


def _lookup_inventory_by_barcode(conn, company_key, barcode_value):
    return conn.execute(
        """
        SELECT id, item_name, category, qty, price, cost_price, barcode
        FROM inventory
        WHERE company_key = ? AND barcode = ?
        """,
        (company_key, barcode_value),
    ).fetchone()


def _add_item_to_pos_cart(company_key, item_row):
    cart_key = f"pos_cart_{company_key}"
    cart = st.session_state.setdefault(cart_key, [])
    item_id = int(item_row["id"])
    for existing_line in cart:
        if int(existing_line["inventory_item_id"]) == item_id:
            existing_line["qty"] += 1
            existing_line["line_total"] = existing_line["qty"] * existing_line["price"]
            return

    cart.append(
        {
            "inventory_item_id": item_id,
            "name": item_row["item_name"],
            "barcode": item_row["barcode"] or "",
            "price": float(item_row["price"] or 0.0),
            "available_qty": float(item_row["qty"] or 0.0),
            "qty": 1,
            "line_total": float(item_row["price"] or 0.0),
        }
    )


def _import_sales_from_excel(conn, company_key, doc_type, file_obj, created_by):
    imported_df = pd.read_excel(file_obj)
    if imported_df.empty:
        return 0

    column_map = {column.lower().strip(): column for column in imported_df.columns}
    required = ["date", "description", "amount"]
    missing = [column for column in required if column not in column_map]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    changed_rows = 0
    ledger = "Sales Revenue" if doc_type == "Sales" else "Accounts Payable"
    for _, row in imported_df.iterrows():
        row_id = row[column_map["id"]] if "id" in column_map and not pd.isna(row[column_map["id"]]) else None
        tx_date = pd.to_datetime(row[column_map["date"]], errors="coerce")
        narration = str(row[column_map["description"]]).strip()
        amount = float(row[column_map["amount"]] or 0)
        if pd.isna(tx_date) or not narration or amount <= 0:
            continue
        tx_date_str = tx_date.date().isoformat()
        if row_id is not None:
            existing = conn.execute(
                "SELECT id FROM vouchers WHERE company_key = ? AND id = ?",
                (company_key, int(row_id)),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE vouchers
                    SET date = ?, v_type = ?, ledger = ?, credit = ?, narration = ?, created_by = ?
                    WHERE company_key = ? AND id = ?
                    """,
                    (tx_date_str, doc_type, ledger, amount, narration, created_by, company_key, int(row_id)),
                )
                changed_rows += 1
                continue
        existing = conn.execute(
            """
            SELECT id FROM vouchers
            WHERE company_key = ? AND v_type = ? AND date = ? AND narration = ?
            """,
            (company_key, doc_type, tx_date_str, narration),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE vouchers
                SET credit = ?, created_by = ?
                WHERE company_key = ? AND id = ?
                """,
                (amount, created_by, company_key, existing["id"]),
            )
            changed_rows += 1
            continue
        conn.execute(
            """
            INSERT INTO vouchers (company_key, date, v_type, ledger, credit, narration, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_key, tx_date_str, doc_type, ledger, amount, narration, created_by),
        )
        changed_rows += 1
    return changed_rows


def get_financial_metrics():
    conn = get_connection()
    try:
        revenue = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM sales_invoices WHERE status = 'Paid'"
        ).fetchone()[0] or 0.0
        payables = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM accounts_payable WHERE status = 'Unpaid'"
        ).fetchone()[0] or 0.0
        has_data = (
            (conn.execute("SELECT COUNT(*) FROM sales_invoices").fetchone()[0] or 0)
            + (conn.execute("SELECT COUNT(*) FROM accounts_payable").fetchone()[0] or 0)
        ) > 0
    finally:
        conn.close()

    metrics = {
        "revenue": float(revenue),
        "payables": float(payables),
        "net_health": float(revenue) - float(payables),
        "has_data": has_data,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_demo_financial_metrics():
    metrics = {
        "revenue": 12500.0,
        "payables": 4200.0,
        "net_health": 8300.0,
        "has_data": True,
    }
    chart_df = pd.DataFrame(
        {"Amount": [metrics["revenue"], metrics["payables"]]},
        index=["Income", "Expenses"],
    )
    return metrics, chart_df


def get_system_health_snapshot():
    conn = get_connection()
    try:
        company_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] or 0
        active_licenses = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE status = 'Active'"
        ).fetchone()[0] or 0
        db_status = "Online"
    except Exception:
        company_count = 0
        active_licenses = 0
        db_status = "Offline"
    finally:
        conn.close()

    return {
        "api_status": "Operational",
        "db_status": db_status,
        "company_count": company_count,
        "active_licenses": active_licenses,
    }


def _demo_notice():
    st.info("Enterprise Demo Mode is active. These values are virtual and are not written to the vault database.")


def format_money(value):
    return f"GH₵ {value:,.2f}"


def show_vault_dashboard_module(demo_on):
    st.subheader("EKA Vault / Dashboard")
    metrics, chart_df = get_demo_financial_metrics() if demo_on else get_financial_metrics()

    with st.container():
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Revenue", format_money(metrics["revenue"]), "Healthy")
        col2.metric("Outstanding Payables", format_money(metrics["payables"]), "Controlled", delta_color="inverse")
        col3.metric("Net Health", format_money(metrics["net_health"]), "Good")
        if not metrics["has_data"] and not demo_on:
            st.caption("Add your first invoice to activate vault metrics.")

    st.bar_chart(chart_df)

    if demo_on:
        _demo_notice()


def show_company_registration_module():
    st.subheader("New Company Registration")
    with st.form("company_registration_form"):
        company_name = st.text_input("Company Name")
        admin_name = st.text_input("Admin Contact")
        contact_email = st.text_input("Contact Email")
        duration_months = st.number_input("Subscription Length (Months)", min_value=1, value=12)
        submitted = st.form_submit_button("Register Company")

        if submitted and company_name and admin_name:
            expiry_date = datetime.now() + relativedelta(months=+int(duration_months))
            conn = get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO companies (company_name, admin_name, contact_email, status, subscription_expiry, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        company_name,
                        admin_name,
                        contact_email,
                        "Active",
                        expiry_date.date().isoformat(),
                        datetime.now().date().isoformat(),
                    ),
                )
                conn.commit()
                st.success(f"{company_name} registered successfully.")
                log_system_event("INFO", "New Company Registration", f"Registered company: {company_name}")
                st.rerun()
            finally:
                conn.close()

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT company_name, admin_name, contact_email, status, subscription_expiry FROM companies ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()

    if rows:
        st.dataframe(
            pd.DataFrame(rows, columns=["Company Name", "Admin Contact", "Contact Email", "Status", "Subscription Expiry"]),
            use_container_width=True,
        )
    else:
        st.caption("No companies registered yet.")


def show_system_health_module():
    st.subheader("System Health & Logs")
    snapshot = get_system_health_snapshot()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("API Status", snapshot["api_status"])
    col2.metric("Database Status", snapshot["db_status"])
    col3.metric("Companies", str(snapshot["company_count"]))
    col4.metric("Active Licenses", str(snapshot["active_licenses"]))

    conn = get_connection()
    try:
        logs = conn.execute(
            "SELECT timestamp, level, module_name, message FROM system_logs ORDER BY id DESC LIMIT 50"
        ).fetchall()
    finally:
        conn.close()

    if logs:
        logs_df = pd.DataFrame(logs, columns=["Timestamp", "Level", "Module", "Message"])
        st.dataframe(logs_df, use_container_width=True)
        excel_bin = get_excel_bin(logs_df)
        if excel_bin:
            st.download_button("Export Logs", data=excel_bin, file_name="eka_gatekeeper_logs.xlsx")
    else:
        st.caption("System logs will appear here after activity begins.")


def show_license_renewal_module():
    st.subheader("Renew License")
    conn = get_connection()
    try:
        companies = conn.execute(
            "SELECT id, company_name, status, subscription_expiry FROM companies ORDER BY company_name"
        ).fetchall()
    finally:
        conn.close()

    if not companies:
        st.info("No companies are available for renewal yet.")
        return

    companies_df = pd.DataFrame(companies, columns=["ID", "Company Name", "Status", "Subscription Expiry"])
    st.dataframe(companies_df, use_container_width=True)

    selected_name = st.selectbox("Select Company", companies_df["Company Name"].tolist())
    duration_months = st.number_input("Extend By (Months)", min_value=1, value=12, key="renew_duration_months")

    if st.button("Renew License", key="renew_license_action"):
        selected_row = companies_df.loc[companies_df["Company Name"] == selected_name].iloc[0]
        existing_expiry = selected_row["Subscription Expiry"]
        base_date = datetime.now()
        if existing_expiry:
            try:
                base_date = datetime.fromisoformat(str(existing_expiry))
            except ValueError:
                base_date = datetime.now()
        new_expiry = base_date + relativedelta(months=+int(duration_months))

        conn = get_connection()
        try:
            conn.execute(
                "UPDATE companies SET subscription_expiry = ?, status = 'Active' WHERE id = ?",
                (new_expiry.date().isoformat(), int(selected_row["ID"])),
            )
            conn.commit()
            st.success(f"License renewed for {selected_name} until {new_expiry.date().isoformat()}.")
            log_system_event("INFO", "Renew License", f"Renewed license for {selected_name}")
            st.rerun()
        finally:
            conn.close()


def show_sales_invoices_page(conn, demo_on):
    st.subheader("Sales Invoices")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Customer Name": "Accra Retail Ltd", "Amount": 12500.0, "Status": "Paid", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.form("sales_invoice_form"):
        customer_name = st.text_input("Customer Name")
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
        status = st.selectbox("Status", ["Paid", "Pending", "Draft"])
        invoice_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Save Invoice")
        if submitted and customer_name and amount > 0:
            conn.execute(
                "INSERT INTO sales_invoices (customer_name, amount, status, date) VALUES (?, ?, ?, ?)",
                (customer_name, amount, status, invoice_date.isoformat()),
            )
            conn.commit()
            log_system_event("INFO", "Sales Invoices", f"Saved invoice for {customer_name}")
            st.success("Invoice saved.")
            st.rerun()

    rows = conn.execute("SELECT customer_name, amount, status, date FROM sales_invoices ORDER BY date DESC, id DESC").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Customer Name", "Amount", "Status", "Date"])
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No invoices yet.")


def show_accounts_payable_page(conn, demo_on):
    st.subheader("Accounts Payable")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Supplier Name": "Tema Supplier Co.", "Amount": 4200.0, "Status": "Unpaid", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.form("accounts_payable_form"):
        supplier_name = st.text_input("Supplier Name")
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
        status = st.selectbox("Status", ["Unpaid", "Paid"])
        payable_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Save Payable")
        if submitted and supplier_name and amount > 0:
            conn.execute(
                "INSERT INTO accounts_payable (supplier_name, amount, status, date) VALUES (?, ?, ?, ?)",
                (supplier_name, amount, status, payable_date.isoformat()),
            )
            conn.commit()
            log_system_event("INFO", "Accounts Payable", f"Saved payable for {supplier_name}")
            st.success("Payable saved.")
            st.rerun()

    rows = conn.execute("SELECT supplier_name, amount, status, date FROM accounts_payable ORDER BY date DESC, id DESC").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Supplier Name", "Amount", "Status", "Date"])
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No payables yet.")


def show_chart_of_accounts_page(conn, demo_on):
    st.subheader("Chart of Accounts")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [
                {"Account Name": "Sales Revenue", "Account Type": "Income", "Balance": 12500.0},
                {"Account Name": "Accounts Payable", "Account Type": "Liability", "Balance": 4200.0},
            ]
        )
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.form("chart_of_accounts_form"):
        account_name = st.text_input("Account Name")
        account_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
        balance = st.number_input("Opening Balance (GH₵)", value=0.0)
        submitted = st.form_submit_button("Add Account")
        if submitted and account_name:
            conn.execute(
                "INSERT INTO chart_of_accounts (account_name, account_type, balance) VALUES (?, ?, ?)",
                (account_name, account_type, balance),
            )
            conn.commit()
            log_system_event("INFO", "Chart of Accounts", f"Added account: {account_name}")
            st.success("Account saved.")
            st.rerun()

    rows = conn.execute("SELECT account_name, account_type, balance FROM chart_of_accounts ORDER BY account_name").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Account Name", "Account Type", "Balance"])
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No chart of accounts records yet.")


def show_vouchers_page(conn, demo_on):
    st.subheader("Vouchers")
    if demo_on:
        _demo_notice()
        demo_df = pd.DataFrame(
            [{"Narration": "Demo voucher", "Amount": 12500.0, "Reference": "DEMO-001", "Date": datetime.now().date().isoformat()}]
        )
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.form("voucher_form"):
        narration = st.text_area("Narration")
        amount = st.number_input("Amount (GH₵)", min_value=0.0, value=0.0)
        ref_no = st.text_input("Reference Number")
        voucher_date = st.date_input("Date", value=datetime.now().date())
        submitted = st.form_submit_button("Post Voucher")
        if submitted and narration and amount > 0:
            conn.execute(
                "INSERT INTO vouchers (narration, amount, ref_no, date) VALUES (?, ?, ?, ?)",
                (narration, amount, ref_no, voucher_date.isoformat()),
            )
            conn.commit()
            log_system_event("INFO", "Vouchers", f"Posted voucher: {ref_no or narration}")
            st.success("Voucher saved.")
            st.rerun()

    rows = conn.execute("SELECT narration, amount, ref_no, date FROM vouchers ORDER BY date DESC, id DESC").fetchall()
    if rows:
        df = pd.DataFrame(rows, columns=["Narration", "Amount", "Reference", "Date"])
        st.dataframe(df, use_container_width=True)
    else:
        st.caption("No vouchers yet.")


# ==========================================
# ONBOARDING & NEW COMPANY REGISTRATION
# ==========================================
def show_onboarding_payment():
    """Handle the onboarding payment process for new companies."""
    st.header("🏢 New Company Registration")
    st.info("Complete the registration and onboarding payment to activate your EKA ERP instance.")
    master_price_per_month = get_master_price_per_month()

    with st.form("onboarding_form"):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company Name")
            admin_email = st.text_input("Admin Email Address")
        with col2:
            sector = st.selectbox("Business Sector", ["Retail", "Manufacturing", "Services", "Construction", "Other"])
            subscription_months = st.selectbox("Subscription Duration (Months)", [1, 3, 6, 12, 24], index=3)

        amount = float(master_price_per_month) * int(subscription_months)

        st.caption(f"Master Price Per Month: GH₵ {master_price_per_month:,.2f}")
        st.write(f"### Total Due: GH₵ {amount:,.2f}")
        submit = st.form_submit_button("Proceed to Payment")

        if submit:
            if not company_name or not admin_email:
                st.error("Please fill in all required fields.")
            else:
                try:
                    reference = f"ONB-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    url = initialize_paystack_payment(admin_email, amount, reference)
                    if url:
                        st.success("Payment initialized!")
                        st.session_state.pending_reg = {
                            'company_name': company_name,
                            'email': admin_email,
                            'amount': amount,
                            'months': int(subscription_months),
                            'reference': reference
                        }
                        st.link_button("Proceed to Paystack", url)
                    else:
                        st.warning("Payment could not be initialized yet. Please review the system configuration and try again.")
                except Exception as e:
                    st.error(f"Onboarding payment error: {e}")
                    logger.error(f"Onboarding payment error: {e}")


# ==========================================
# INVENTORY MANAGEMENT
# ==========================================
def show_inventory(company_key, role):
    st.header("📦 Inventory Management")
    success_key = f"inventory_add_success_{company_key}"
    delete_success_key = f"inventory_delete_success_{company_key}"
    inventory_message_key = f"inventory_message_{company_key}"
    inventory_scan_beep_key = f"inventory_scan_beep_{company_key}"
    inventory_scan_input_key = f"inventory_scan_input_{company_key}"
    inventory_pending_scan_key = f"inventory_pending_scan_{company_key}"
    inventory_new_barcode_key = f"inventory_new_barcode_{company_key}"
    if st.session_state.get(success_key):
        _trigger_scan_feedback(inventory_message_key, "Item added successfully!")
        st.session_state.pop(success_key, None)
    if st.session_state.get(delete_success_key):
        _trigger_scan_feedback(inventory_message_key, "Item deleted")
        st.session_state.pop(delete_success_key, None)

    _render_flash_message(inventory_message_key, inventory_scan_beep_key)
    st.text_input(
        "Scan Barcode",
        key=inventory_scan_input_key,
        placeholder="Scan or type a barcode and press Enter",
        on_change=_set_input_pending,
        args=(inventory_scan_input_key, inventory_pending_scan_key),
    )
    _render_camera_scanner(f"inventory_{company_key}", inventory_pending_scan_key)

    pending_inventory_barcode = str(st.session_state.get(inventory_pending_scan_key, "") or "").strip()
    if pending_inventory_barcode and role != "Demo":
        conn = None
        try:
            conn = get_connection()
            matched_item = _lookup_inventory_by_barcode(conn, company_key, pending_inventory_barcode)
            if matched_item:
                updated_qty = float(matched_item["qty"] or 0) + 1
                conn.execute(
                    """
                    UPDATE inventory
                    SET qty = COALESCE(qty, 0) + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND company_key = ?
                    """,
                    (int(matched_item["id"]), company_key),
                )
                conn.commit()
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "Inventory Barcode Scan",
                    "Inventory",
                    f"Incremented {matched_item['item_name']} via barcode {pending_inventory_barcode}",
                )
                _trigger_scan_feedback(
                    inventory_message_key,
                    f"{matched_item['item_name']} quantity increased to {updated_qty:,.2f}.",
                    "success",
                    inventory_scan_beep_key,
                )
            else:
                st.session_state[inventory_new_barcode_key] = pending_inventory_barcode
                _trigger_scan_feedback(
                    inventory_message_key,
                    f"Barcode {pending_inventory_barcode} is new. Enter the item name and prices below to save it.",
                    "info",
                )
        except Exception as exc:
            st.error(f"Inventory barcode scan failed: {exc}")
        finally:
            if conn:
                conn.close()
            st.session_state.pop(inventory_pending_scan_key, None)
            st.session_state[inventory_scan_input_key] = ""
            st.rerun()

    tabs = st.tabs(["Stock Overview", "Stock In/Out", "Items Management"])

    with tabs[0]:
        st.subheader("Current Stock Levels")
        try:
            conn = get_connection()
            if role == "Demo":
                df = pd.DataFrame({
                    "item_code": ["INV-001", "INV-002"],
                    "barcode": ["1234567890123", "0987654321098"],
                    "item_name": ["Product A", "Product B"],
                    "category": ["General", "General"],
                    "quantity": [50, 8],
                    "unit_price": [120.0, 75.0],
                    "total_value": [6000.0, 600.0],
                })
            else:
                query = """
                    SELECT id, item_code, barcode, item_name, category, opening_balance, qty as quantity,
                           price as unit_price, cost_price, (qty * cost_price) as total_value
                    FROM inventory WHERE company_key = ?
                """
                df = pd.read_sql_query(query, conn, params=(company_key,))
            conn.close()

            if not df.empty:
                st.dataframe(df, use_container_width=True)
                excel_bin = get_excel_bin(df)
                if excel_bin:
                    st.download_button(
                        "Export to Excel",
                        data=excel_bin,
                        file_name=f"inventory_{company_key}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"inventory_export_{company_key}",
                    )
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Items", len(df))
                col2.metric("Total Value", f"GH₵ {df['total_value'].sum():,.2f}")
                col3.metric("Low Stock Alerts", len(df[df['quantity'] < 10]))
                if role in ("Master Admin", "Bookkeeper", "Sub-Admin") and "id" in df.columns:
                    st.markdown("Edit Stock Item")
                    selected_edit_key = f"inventory_edit_selected_{company_key}"
                    delete_confirm_key = f"inventory_delete_confirm_{company_key}"
                    for _, stock_row in df.iterrows():
                        name_col, edit_col, delete_col = st.columns([4, 1, 1])
                        name_col.caption(
                            f"{stock_row['item_name']} | Barcode {stock_row.get('barcode') or 'N/A'} | Qty {float(stock_row['quantity']):,.2f} | "
                            f"Sell GH₵ {float(stock_row['unit_price']):,.2f}"
                        )
                        if edit_col.button("Edit", key=f"inventory_edit_btn_{company_key}_{int(stock_row['id'])}"):
                            st.session_state[selected_edit_key] = int(stock_row["id"])
                        if delete_col.button("Delete", key=f"inventory_delete_btn_{company_key}_{int(stock_row['id'])}"):
                            st.session_state[delete_confirm_key] = int(stock_row["id"])
                    delete_item_id = st.session_state.get(delete_confirm_key)
                    if delete_item_id is not None:
                        st.warning("Are you sure you want to permanently delete this item?")
                        confirm_col, cancel_col = st.columns(2)
                        if confirm_col.button("Confirm Delete", key=f"inventory_delete_confirm_btn_{company_key}_{delete_item_id}"):
                            conn = get_connection()
                            conn.execute(
                                "DELETE FROM inventory WHERE id = ? AND company_key = ?",
                                (int(delete_item_id), company_key),
                            )
                            conn.commit()
                            log_audit_action(conn, company_key, role, "Inventory Item Deleted", "Inventory", f"Deleted item ID {int(delete_item_id)}")
                            conn.close()
                            _clear_streamlit_state(delete_confirm_key, selected_edit_key)
                            st.session_state[delete_success_key] = True
                            st.rerun()
                        if cancel_col.button("Cancel", key=f"inventory_delete_cancel_btn_{company_key}_{delete_item_id}"):
                            _clear_streamlit_state(delete_confirm_key)
                            st.rerun()
                    edit_item_id = st.session_state.get(selected_edit_key, int(df["id"].iloc[0]))
                    edit_row = df.loc[df["id"] == edit_item_id].iloc[0]
                    with st.form(f"inventory_edit_form_{company_key}_{edit_item_id}", clear_on_submit=True):
                        edit_barcode = st.text_input("Barcode", value=str(edit_row.get("barcode") or ""))
                        edit_category = st.text_input("Category", value=str(edit_row["category"] or ""))
                        edit_qty = st.number_input("Quantity", min_value=0.0, value=float(edit_row["quantity"] or 0.0))
                        edit_price = st.number_input("Selling Price (GH₵)", min_value=0.0, value=float(edit_row["unit_price"] or 0.0))
                        edit_cost_price = st.number_input("Cost Price (GH₵)", min_value=0.0, value=float(edit_row["cost_price"] or 0.0))
                        if st.form_submit_button("Edit Item"):
                            try:
                                conn = get_connection()
                                conn.execute(
                                    """
                                    UPDATE inventory
                                    SET barcode = ?, category = ?, qty = ?, price = ?, cost_price = ?, updated_at = CURRENT_TIMESTAMP
                                    WHERE id = ? AND company_key = ?
                                    """,
                                    (edit_barcode.strip(), edit_category, edit_qty, edit_price, edit_cost_price, int(edit_item_id), company_key),
                                )
                                conn.commit()
                                log_audit_action(conn, company_key, role, "Inventory Item Updated", "Inventory", f"Updated item ID {int(edit_item_id)}")
                                conn.close()
                                _clear_streamlit_state(selected_edit_key, delete_confirm_key)
                                st.success("Entry Updated")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Inventory update failed: {exc}")
            else:
                st.info("No items in inventory.")
        except Exception as e:
            st.error(f"Error loading inventory: {e}")

    with tabs[1]:
        st.subheader("Stock In / Out")
        st.info("Stock movement recording coming soon.")

    with tabs[2]:
        st.subheader("Items Management")
        if role == "Demo":
            st.info("Items management is disabled in Demo mode.")
            return
        with st.form("add_inventory_form", clear_on_submit=True):
            barcode = st.text_input("New Barcode", value=str(st.session_state.get(inventory_new_barcode_key, "") or ""))
            item_name = st.text_input("Item Name")
            category = st.text_input("Category")
            opening_stock = st.number_input("Opening Stock Quantity", min_value=0.0, value=0.0)
            price = st.number_input("Selling Price (GH₵)", min_value=0.0, value=0.0)
            cost_price = st.number_input("Cost Price (GH₵)", min_value=0.0, value=0.0)
            submitted = st.form_submit_button("Add Item")
            if submitted and item_name:
                try:
                    conn = get_connection()
                    normalized_barcode = barcode.strip()
                    if normalized_barcode:
                        existing_barcode = _lookup_inventory_by_barcode(conn, company_key, normalized_barcode)
                        if existing_barcode:
                            st.error(f"Barcode {normalized_barcode} is already assigned to {existing_barcode['item_name']}.")
                            conn.close()
                            return
                    conn.execute(
                        """
                        INSERT INTO inventory (company_key, item_name, barcode, category, opening_balance, qty, price, cost_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (company_key, item_name, normalized_barcode, category, opening_stock, opening_stock, price, cost_price),
                    )
                    conn.commit()
                    conn.close()
                    st.session_state.pop(inventory_new_barcode_key, None)
                    st.session_state[success_key] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding item: {e}")

        import_file = st.file_uploader(
            "Import from Excel",
            type=["xlsx"],
            key=f"inventory_import_{company_key}",
        )
        if import_file and st.button("Import Inventory File", key=f"inventory_import_btn_{company_key}"):
            try:
                conn = get_connection()
                added_rows = _import_inventory_from_excel(conn, company_key, import_file)
                conn.commit()
                conn.close()
                st.success(f"Imported {added_rows} new inventory row(s).")
                st.rerun()
            except Exception as exc:
                st.error(f"Inventory import failed: {exc}")


# ==========================================
# VOUCHERS & JOURNALS
# ==========================================
def show_vouchers(company_key, role):
    st.header("📑 Vouchers & Journals")

    with st.expander("➕ Create New Voucher", expanded=True):
        with st.form("voucher_entry_form"):
            col1, col2 = st.columns(2)
            with col1:
                v_type = st.selectbox("Voucher Type", ["Payment", "Receipt", "Journal", "Sales", "Purchase", "Expense"])
                narration = st.text_area("Narration")
            with col2:
                amount = st.number_input("Amount (GH₵)", min_value=0.0, step=0.01)
                ref_no = st.text_input("Reference Number")
                v_date = st.date_input("Date", datetime.now())

            if st.form_submit_button("Post Voucher"):
                if role == "Demo":
                    st.info("Voucher posting is disabled in Demo mode.")
                elif amount <= 0 or not narration:
                    st.warning("Please provide a valid amount and narration.")
                else:
                    try:
                        conn = get_connection()
                        conn.execute(
                            """INSERT INTO vouchers (company_key, date, v_type, ledger, credit, reference_no, narration, created_by)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (company_key, v_date.isoformat(), v_type, v_type, amount, ref_no, narration, role),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Voucher Created", "Vouchers & Journals", f"Posted {v_type} voucher: {ref_no}")
                        conn.close()
                        st.success("Voucher posted successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error posting voucher: {e}")

    st.subheader("Voucher Ledger")
    try:
        conn = get_connection()
        if role == "Demo":
            rows = [
                {"Date": "2026-03-15", "Type": "Sales", "Narration": "Product Sale", "Amount": 5000.0, "Ref": "DEMO-001"},
            ]
            df = pd.DataFrame(rows)
        else:
            data = conn.execute(
                "SELECT id, date, v_type, narration, credit, reference_no FROM vouchers WHERE company_key = ? ORDER BY date DESC LIMIT 100",
                (company_key,),
            ).fetchall()
            df = pd.DataFrame(data, columns=["ID", "Date", "Type", "Narration", "Amount", "Ref"]) if data else pd.DataFrame()
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            if role in ("Master Admin", "Bookkeeper", "Sub-Admin") and "ID" in df.columns:
                expense_rows = df[df["Type"] == "Expense"]
                if not expense_rows.empty:
                    selected_expense_key = f"expense_edit_selected_{company_key}"
                    for _, expense_list_row in expense_rows.iterrows():
                        name_col, button_col = st.columns([4, 1])
                        name_col.caption(
                            f"{expense_list_row['Narration']} | GH₵ {float(expense_list_row['Amount']):,.2f}"
                        )
                        if button_col.button("Edit", key=f"expense_edit_btn_{company_key}_{int(expense_list_row['ID'])}"):
                            st.session_state[selected_expense_key] = int(expense_list_row["ID"])
                    expense_edit_id = st.session_state.get(selected_expense_key, int(expense_rows["ID"].iloc[0]))
                    expense_row = expense_rows.loc[expense_rows["ID"] == expense_edit_id].iloc[0]
                    with st.form(f"expense_edit_form_{company_key}_{expense_edit_id}", clear_on_submit=True):
                        edit_narration = st.text_area("Narration", value=str(expense_row["Narration"] or ""))
                        edit_amount = st.number_input("Amount (GH₵)", min_value=0.0, value=float(expense_row["Amount"] or 0.0))
                        if st.form_submit_button("Update Expense"):
                            conn = get_connection()
                            conn.execute(
                                """
                                UPDATE vouchers
                                SET narration = ?, credit = ?
                                WHERE id = ? AND company_key = ?
                                """,
                                (edit_narration, edit_amount, int(expense_edit_id), company_key),
                            )
                            conn.commit()
                            log_audit_action(conn, company_key, role, "Expense Updated", "Expenses", f"Voucher {int(expense_edit_id)} updated")
                            conn.close()
                            st.session_state.pop(selected_expense_key, None)
                            st.success("Entry Updated")
                            st.rerun()
        else:
            st.info("No vouchers found.")
    except Exception as e:
        st.error(f"Error loading vouchers: {e}")


# ==========================================
# CHART OF ACCOUNTS
# ==========================================
def show_chart_of_accounts(company_key, role):
    st.header("📊 Chart of Accounts")
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT account_code, account_name, account_type FROM chart_of_accounts ORDER BY account_code"
        ).fetchall()
        conn.close()
        if rows:
            df = pd.DataFrame(rows, columns=["Account Code", "Account Name", "Account Type"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No chart of accounts entries found.")
    except Exception as e:
        st.error(f"Error loading chart of accounts: {e}")

    if role not in ("Staff", "Demo"):
        with st.form("add_coa_form"):
            acc_code = st.text_input("Account Code")
            acc_name = st.text_input("Account Name")
            acc_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Income", "Expense"])
            if st.form_submit_button("Add Account"):
                if acc_name:
                    try:
                        conn = get_connection()
                        conn.execute(
                            "INSERT INTO chart_of_accounts (account_code, account_name, account_type) VALUES (?, ?, ?)",
                            (acc_code, acc_name, acc_type),
                        )
                        conn.commit()
                        conn.close()
                        st.success("Account added.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error adding account: {e}")


# ==========================================
# COMPANY SETUP
# ==========================================
def show_company_setup(company_key, company_name, role):
    st.header("🏢 Company Setup")
    st.subheader("Company Profile")
    conn = None
    try:
        conn = get_connection()
        company = conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()
        company_data = dict(company) if company is not None else {}
        if company:
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Company Name", value=company_data["name"], disabled=True)
                st.text_input("License Key", value=company_data["key"], disabled=True)
                st.text_input("Plan Type", value=company_data.get("plan_type", "Basic"), disabled=True)
            with col2:
                expiry_value = company_data.get("subscription_expiry") or company_data.get("subscription_end_date") or "N/A"
                st.text_input("Subscription Expiry", value=str(expiry_value), disabled=True)
                st.text_input("Status", value=company_data.get("status", "Active"), disabled=True)
                st.text_input("Contact Email", value=str(company_data.get("contact_email") or company_data.get("admin_email") or ""), disabled=True)

            if role in ("Master Admin", "Sub-Admin"):
                edit_settings_key = f"company_settings_edit_{company_key}"
                settings_col, button_col = st.columns([4, 1])
                settings_col.caption(
                    f"{company_data.get('name')} | {company_data.get('contact_email') or company_data.get('admin_email') or 'No email'}"
                )
                if button_col.button("Edit", key=f"company_settings_edit_btn_{company_key}"):
                    st.session_state[edit_settings_key] = True
                if st.session_state.get(edit_settings_key):
                    with st.form(f"company_settings_form_{company_key}", clear_on_submit=True):
                        updated_contact_email = st.text_input(
                            "Edit Contact Email",
                            value=str(company_data.get("contact_email") or company_data.get("admin_email") or ""),
                        )
                        updated_plan_type = st.text_input(
                            "Edit Plan Type",
                            value=str(company_data.get("plan_type") or "Basic"),
                        )
                        if st.form_submit_button("Update Client Settings"):
                            conn.execute(
                                """
                                UPDATE companies
                                SET contact_email = ?, plan_type = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE key = ?
                                """,
                                (updated_contact_email, updated_plan_type, company_key),
                            )
                            conn.commit()
                            log_audit_action(
                                conn,
                                company_key,
                                role,
                                "Client Settings Updated",
                                "Company Setup",
                                f"contact_email={updated_contact_email}, plan_type={updated_plan_type}",
                            )
                            st.session_state.pop(edit_settings_key, None)
                            st.success("Entry Updated")
                            st.rerun()

            if role == "Master Admin":
                st.markdown("---")
                st.subheader("Staff Management")
                with st.form("company_setup_staff_form"):
                    staff_name = st.text_input("Full Name")
                    staff_role = st.selectbox("Role", ["Bookkeeper", "Staff"])
                    staff_password = st.text_input("Assign Password", type="password")
                    submitted = st.form_submit_button("Create Staff Login")

                    if submitted:
                        if not staff_name.strip():
                            st.warning("Enter a staff name before creating a login.")
                        elif not staff_password:
                            st.warning("Assign a password before creating the staff login.")
                        else:
                            login_key = _generate_staff_login_key(company_key, staff_role)
                            try:
                                conn.execute(
                                    """
                                    INSERT INTO users (company_key, full_name, login_key, password_hash, role, status)
                                    VALUES (?, ?, ?, ?, ?, 'Active')
                                    """,
                                    (
                                        company_key,
                                        staff_name.strip(),
                                        login_key,
                                        _hash_staff_password(staff_password),
                                        staff_role,
                                    ),
                                )
                                conn.commit()
                                log_audit_action(
                                    conn,
                                    company_key,
                                    role,
                                    "Staff Login Created",
                                    "Company Setup",
                                    f"{staff_name.strip()} created as {staff_role} with key {login_key}",
                                )
                                st.success(f"Staff login created. Login key: {login_key}")
                            except Exception as exc:
                                st.error(f"Could not create staff login: {exc}")

                users = conn.execute(
                    """
                    SELECT full_name, role, login_key, status, created_at
                    FROM users
                    WHERE company_key = ?
                    ORDER BY created_at DESC
                    """,
                    (company_key,),
                ).fetchall()
                if users:
                    users_df = pd.DataFrame(
                        users,
                        columns=["Full Name", "Role", "Login Key", "Status", "Created At"],
                    )
                    st.dataframe(users_df, use_container_width=True)
                else:
                    st.caption("No staff logins created yet.")
        else:
            st.info("Company profile not found.")
    except Exception as e:
        st.error(f"Error loading company setup: {e}")
    finally:
        if conn:
            conn.close()


# ==========================================
# POINT OF SALE (POS)
# ==========================================
def show_pos(company_key, company_name, role):
    st.header("???? Point of Sale")
    receipt_key = f"pos_receipt_{company_key}"
    pos_success_key = f"pos_sale_success_{company_key}"
    void_success_key = f"pos_void_success_{company_key}"
    pos_message_key = f"pos_message_{company_key}"
    pos_scan_beep_key = f"pos_scan_beep_{company_key}"
    pos_scan_input_key = f"pos_scan_input_{company_key}"
    pos_pending_scan_key = f"pos_pending_scan_{company_key}"
    cart_key = f"pos_cart_{company_key}"
    if role == "Demo":
        _demo_notice()
        st.info("Demo POS: Select items and process a mock sale.")
        demo_items = ["Product A - GH??? 120.00", "Product B - GH??? 75.00", "Product C - GH??? 200.00"]
        selected = st.multiselect("Select Items", demo_items)
        if selected:
            st.success(f"Demo sale: {len(selected)} item(s) selected. Total: GH??? {len(selected) * 120:.2f}")
        return

    if st.session_state.get(pos_success_key):
        _trigger_scan_feedback(pos_message_key, "Sale processed successfully.")
        st.session_state.pop(pos_success_key, None)
    if st.session_state.get(void_success_key):
        _trigger_scan_feedback(pos_message_key, "Transaction voided")
        st.session_state.pop(void_success_key, None)

    _render_flash_message(pos_message_key, pos_scan_beep_key)

    try:
        conn = get_connection()
        company_row = conn.execute("SELECT name FROM companies WHERE key = ?", (company_key,)).fetchone()
        items = conn.execute(
            "SELECT id, item_name, barcode, price, qty FROM inventory WHERE company_key = ? AND qty > 0",
            (company_key,),
        ).fetchall()
        conn.close()

        company_label = company_row[0] if company_row else company_name
        items_df = pd.DataFrame(items, columns=["ID", "Item Name", "Barcode", "Price", "Qty"]) if items else pd.DataFrame()

        st.caption("Scanner-ready checkout")
        st.text_input(
            "Barcode Search",
            key=pos_scan_input_key,
            placeholder="Scan barcode and the item will be added to the cart",
            label_visibility="collapsed",
            on_change=_set_input_pending,
            args=(pos_scan_input_key, pos_pending_scan_key),
        )
        _focus_text_input("Barcode Search")
        _render_camera_scanner(f"pos_{company_key}", pos_pending_scan_key)

        pending_pos_barcode = str(st.session_state.get(pos_pending_scan_key, "") or "").strip()
        if pending_pos_barcode:
            conn = None
            try:
                conn = get_connection()
                matched_item = _lookup_inventory_by_barcode(conn, company_key, pending_pos_barcode)
                if matched_item and float(matched_item["qty"] or 0) > 0:
                    _add_item_to_pos_cart(company_key, matched_item)
                    _trigger_scan_feedback(
                        pos_message_key,
                        f"Added {matched_item['item_name']} to the active sale.",
                        "success",
                        pos_scan_beep_key,
                    )
                else:
                    _trigger_scan_feedback(
                        pos_message_key,
                        f"No in-stock item found for barcode {pending_pos_barcode}.",
                        "warning",
                    )
            except Exception as exc:
                st.error(f"POS barcode scan failed: {exc}")
            finally:
                if conn:
                    conn.close()
                st.session_state.pop(pos_pending_scan_key, None)
                st.session_state[pos_scan_input_key] = ""
                st.rerun()

        item_mode = st.radio(
            "Item Entry Mode",
            ["From Stock", "Manual Entry"],
            horizontal=True,
            key=f"pos_item_mode_{company_key}",
        )
        if item_mode == "From Stock":
            if items_df.empty:
                st.info("No stock available for sale. Switch to Manual Entry to continue.")
            else:
                selected_item = st.selectbox("Select Item", items_df["Item Name"].tolist(), key=f"pos_item_{company_key}")
                qty_to_sell = st.number_input("Quantity", min_value=1, value=1, key=f"pos_qty_{company_key}")
                if st.button("Add Selected Item", key=f"pos_add_selected_{company_key}"):
                    item_row = items_df.loc[items_df["Item Name"] == selected_item].iloc[0]
                    for _ in range(int(qty_to_sell)):
                        _add_item_to_pos_cart(
                            company_key,
                            {
                                "id": int(item_row["ID"]),
                                "item_name": item_row["Item Name"],
                                "barcode": item_row["Barcode"],
                                "price": float(item_row["Price"] or 0.0),
                                "qty": float(item_row["Qty"] or 0.0),
                            },
                        )
                    _trigger_scan_feedback(pos_message_key, f"Added {selected_item} x{int(qty_to_sell)} to the cart.")
                    st.rerun()
        else:
            selected_item = st.text_input("New Item Name", key=f"manual_pos_item_{company_key}")
            manual_price = st.number_input("Manual Price (GH???)", min_value=0.0, value=0.0, key=f"manual_pos_price_{company_key}")
            qty_to_sell = st.number_input("Quantity", min_value=1, value=1, key=f"manual_pos_qty_{company_key}")
            if st.button("Add Manual Item", key=f"pos_add_manual_{company_key}"):
                if selected_item and float(manual_price) > 0:
                    cart = st.session_state.setdefault(cart_key, [])
                    cart.append(
                        {
                            "inventory_item_id": None,
                            "name": selected_item.strip(),
                            "barcode": "",
                            "price": float(manual_price),
                            "available_qty": None,
                            "qty": int(qty_to_sell),
                            "line_total": int(qty_to_sell) * float(manual_price),
                        }
                    )
                    _trigger_scan_feedback(pos_message_key, f"Added manual item {selected_item.strip()} to the cart.")
                    st.rerun()
                st.warning("Enter a valid manual item and price before adding it.")

        payment_method = st.selectbox("Payment Method", ["Cash", "Mobile Money", "Bank Transfer", "Cheque"])
        cart = st.session_state.setdefault(cart_key, [])
        if cart:
            cart_df = pd.DataFrame(
                [
                    {
                        "Item": row["name"],
                        "Barcode": row.get("barcode") or "",
                        "Qty": row["qty"],
                        "Unit Price": row["price"],
                        "Line Total": row["qty"] * row["price"],
                    }
                    for row in cart
                ]
            )
            st.subheader("Active Sale Cart")
            st.dataframe(cart_df, use_container_width=True)
            st.metric("Cart Total", f"GH??? {cart_df['Line Total'].sum():,.2f}")
            remove_choice = st.selectbox(
                "Remove Cart Line",
                ["Keep all items"] + [f"{index + 1}. {line['name']} x{line['qty']}" for index, line in enumerate(cart)],
                key=f"pos_remove_line_{company_key}",
            )
            remove_col, clear_col = st.columns(2)
            if remove_col.button("Remove Selected Line", key=f"pos_remove_selected_{company_key}") and remove_choice != "Keep all items":
                remove_index = int(remove_choice.split(".", 1)[0]) - 1
                cart.pop(remove_index)
                st.rerun()
            if clear_col.button("Clear Cart", key=f"pos_clear_cart_{company_key}"):
                st.session_state[cart_key] = []
                st.rerun()
        else:
            st.info("Scan a barcode or add an item manually to start the sale.")

        def process_pos_sale(print_receipt=False):
            sale_cart = st.session_state.get(cart_key, [])
            if not sale_cart:
                st.warning("Add at least one item to the cart before processing the sale.")
                return

            try:
                conn = get_connection()
                line_items = []
                total = 0.0
                for sale_line in sale_cart:
                    line_items.append(
                        {
                            "name": sale_line["name"],
                            "qty": sale_line["qty"],
                            "price": sale_line["price"],
                        }
                    )
                    total += float(sale_line["qty"]) * float(sale_line["price"])
                    if sale_line["inventory_item_id"] is not None:
                        current_item = conn.execute(
                            "SELECT qty FROM inventory WHERE id = ? AND company_key = ?",
                            (int(sale_line["inventory_item_id"]), company_key),
                        ).fetchone()
                        current_qty = float(current_item["qty"] or 0) if current_item else 0.0
                        if float(sale_line["qty"]) > current_qty:
                            st.error(f"Insufficient stock for {sale_line['name']}.")
                            conn.close()
                            return
                        conn.execute(
                            "UPDATE inventory SET qty = qty - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND company_key = ?",
                            (sale_line["qty"], int(sale_line["inventory_item_id"]), company_key),
                        )
                narration = ", ".join(f"{item['name']} x{item['qty']}" for item in line_items)
                conn.execute(
                    """INSERT INTO vouchers (company_key, date, v_type, ledger, credit, payment_method, narration, status, created_by)
                       VALUES (?, ?, 'Sales', 'Sales Revenue', ?, ?, ?, 'Active', ?)""",
                    (
                        company_key,
                        datetime.now().date().isoformat(),
                        total,
                        payment_method,
                        f"POS Sale: {narration}",
                        role,
                    ),
                )
                conn.commit()
                log_audit_action(
                    conn,
                    company_key,
                    role,
                    "POS Sale",
                    "POS",
                    f"Sold {narration} for GH???{float(total):.2f}",
                )
                conn.close()
                if print_receipt:
                    st.session_state[receipt_key] = _build_receipt(
                        company_label,
                        line_items,
                        total,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                    )
                st.session_state[cart_key] = []
                st.session_state[pos_success_key] = True
                _clear_streamlit_state(
                    f"pos_item_{company_key}",
                    f"pos_qty_{company_key}",
                    f"manual_pos_item_{company_key}",
                    f"manual_pos_price_{company_key}",
                    f"manual_pos_qty_{company_key}",
                    pos_scan_input_key,
                )
                st.rerun()
            except Exception as e:
                st.error(f"Error processing sale: {e}")

        action_col1, action_col2 = st.columns(2)
        if action_col1.button("Process Sale", key=f"process_sale_{company_key}"):
            process_pos_sale(print_receipt=False)
        if action_col2.button("Save and Print", key=f"save_print_sale_{company_key}"):
            process_pos_sale(print_receipt=True)

        st.subheader("Recent POS Transactions")
        conn = get_connection()
        sales_rows = conn.execute(
            """
            SELECT id, date, narration, credit, COALESCE(status, 'Active') AS status
            FROM vouchers
            WHERE company_key = ? AND v_type = 'Sales'
            ORDER BY date DESC, id DESC
            LIMIT 20
            """,
            (company_key,),
        ).fetchall()
        conn.close()
        if sales_rows:
            sales_df = pd.DataFrame(sales_rows, columns=["ID", "Date", "Narration", "Amount", "Status"])
            st.dataframe(sales_df, use_container_width=True)
            if role in ("Master Admin", "Bookkeeper", "Sub-Admin"):
                pos_void_confirm_key = f"pos_void_confirm_{company_key}"
                for _, sale_row in sales_df.iterrows():
                    info_col, action_col = st.columns([4, 1])
                    info_col.caption(
                        f"{sale_row['Date']} | {sale_row['Narration']} | GH??????? {float(sale_row['Amount']):,.2f} | {sale_row['Status']}"
                    )
                    if sale_row["Status"] != "Void" and action_col.button("Void", key=f"pos_void_btn_{company_key}_{int(sale_row['ID'])}"):
                        st.session_state[pos_void_confirm_key] = int(sale_row["ID"])
                void_sale_id = st.session_state.get(pos_void_confirm_key)
                if void_sale_id is not None:
                    st.warning("Are you sure you want to void this transaction?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("Confirm Void", key=f"pos_void_confirm_btn_{company_key}_{void_sale_id}"):
                        conn = get_connection()
                        conn.execute(
                            "UPDATE vouchers SET status = 'Void' WHERE id = ? AND company_key = ?",
                            (int(void_sale_id), company_key),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "POS Transaction Voided", "POS", f"Voided voucher ID {int(void_sale_id)}")
                        conn.close()
                        _clear_streamlit_state(pos_void_confirm_key)
                        st.session_state[void_success_key] = True
                        st.rerun()
                    if cancel_col.button("Cancel", key=f"pos_void_cancel_btn_{company_key}_{void_sale_id}"):
                        _clear_streamlit_state(pos_void_confirm_key)
                        st.rerun()

        if st.session_state.get(receipt_key):
            st.subheader("Receipt Preview")
            st.code(st.session_state[receipt_key], language="text")
            st.download_button(
                "Download Receipt",
                data=st.session_state[receipt_key],
                file_name=f"receipt_{company_key}.txt",
                mime="text/plain",
                key=f"receipt_download_{company_key}",
            )
    except Exception as e:
        st.error(f"POS Error: {e}")
# ==========================================
# SALES & PURCHASE
# ==========================================
def show_sales_purchase(company_key, role, doc_type="Sales"):
    st.header(f"{'🧾 Sales Invoicing' if doc_type == 'Sales' else '📦 Purchase Orders'}")
    if role == "Demo":
        _demo_notice()
        demo_data = pd.DataFrame({
            "Customer/Supplier": ["Demo Client Ltd", "Demo Supplier Co."],
            "Amount (GH₵)": [5000.0, 2000.0],
            "Status": ["Paid", "Pending"],
            "Date": [datetime.now().date().isoformat()] * 2,
        })
        st.dataframe(demo_data, use_container_width=True)
        return

    with st.form(f"{doc_type.lower()}_form"):
        col1, col2 = st.columns(2)
        with col1:
            party_name = st.text_input("Customer Name" if doc_type == "Sales" else "Supplier Name")
            amount = st.number_input("Amount (GH₵)", min_value=0.0, step=0.01)
        with col2:
            status = st.selectbox("Status", ["Paid", "Pending", "Draft"] if doc_type == "Sales" else ["Received", "Pending", "Cancelled"])
            doc_date = st.date_input("Date", datetime.now().date())
        city_region = st.text_input("City / Region")
        narration = st.text_input("Description / Reference")
        submitted = st.form_submit_button(f"Save {doc_type}")

        if submitted and party_name and amount > 0:
            try:
                conn = get_connection()
                ledger = "Sales Revenue" if doc_type == "Sales" else "Accounts Payable"
                conn.execute(
                    """INSERT INTO vouchers (company_key, date, v_type, ledger, credit, narration, created_by)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (company_key, doc_date.isoformat(), doc_type, ledger, amount,
                     f"{party_name}: {narration}", role),
                )
                balance_delta = amount if status == "Pending" else 0.0
                _ensure_counterparty(
                    conn,
                    company_key,
                    party_name,
                    "Customer" if doc_type == "Sales" else "Vendor",
                    city_region,
                    doc_date.isoformat(),
                    balance_delta,
                )
                conn.commit()
                log_audit_action(conn, company_key, role, f"{doc_type} Recorded", doc_type, f"{party_name} - GH₵{amount:.2f}")
                conn.close()
                st.success(f"{doc_type} saved successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving {doc_type}: {e}")

    try:
        conn = get_connection()
        data = conn.execute(
            "SELECT date, narration, credit FROM vouchers WHERE company_key = ? AND v_type = ? ORDER BY date DESC LIMIT 50",
            (company_key, doc_type),
        ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Date", "Description", "Amount (GH₵)"])
            st.dataframe(df, use_container_width=True)
            excel_bin = get_excel_bin(df)
            if excel_bin:
                st.download_button(
                    "Export to Excel",
                    data=excel_bin,
                    file_name=f"{doc_type.lower()}_{company_key}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"{doc_type.lower()}_export_{company_key}",
                )
        else:
            st.info(f"No {doc_type} records found.")
    except Exception as e:
        st.error(f"Error loading {doc_type} records: {e}")

    import_file = st.file_uploader(
        f"Import {doc_type} from Excel",
        type=["xlsx"],
        key=f"{doc_type.lower()}_import_{company_key}",
    )
    if import_file and st.button(f"Import {doc_type} File", key=f"{doc_type.lower()}_import_btn_{company_key}"):
        try:
            conn = get_connection()
            added_rows = _import_sales_from_excel(conn, company_key, doc_type, import_file, role)
            conn.commit()
            conn.close()
            st.success(f"Imported {added_rows} new {doc_type.lower()} row(s).")
            st.rerun()
        except Exception as exc:
            st.error(f"{doc_type} import failed: {exc}")


# ==========================================
# BANKING & CASH
# ==========================================
def show_banking(company_key, role):
    st.header("🏦 Banking & Cash")
    if role == "Demo":
        _demo_notice()
        st.metric("Cash Balance", "GH₵ 8,300.00")
        st.metric("Bank Balance", "GH₵ 15,000.00")
        return

    try:
        conn = get_connection()
        cash_total = conn.execute(
            """SELECT COALESCE(SUM(credit) - SUM(debit), 0) FROM vouchers
               WHERE company_key = ? AND payment_method = 'Cash' AND COALESCE(status, 'Active') != 'Void'""",
            (company_key,),
        ).fetchone()[0] or 0.0
        bank_total = conn.execute(
            """SELECT COALESCE(SUM(credit) - SUM(debit), 0) FROM vouchers
               WHERE company_key = ? AND payment_method = 'Bank Transfer' AND COALESCE(status, 'Active') != 'Void'""",
            (company_key,),
        ).fetchone()[0] or 0.0
        conn.close()

        col1, col2 = st.columns(2)
        col1.metric("Cash Balance", f"GH₵ {cash_total:,.2f}")
        col2.metric("Bank Balance", f"GH₵ {bank_total:,.2f}")
    except Exception as e:
        st.error(f"Banking module error: {e}")


# ==========================================
# ACCOUNTS AGING (RECEIVABLE / PAYABLE)
# ==========================================
def show_aging(company_key, aging_type="Receivable"):
    st.header(f"📋 Accounts {aging_type}")
    if aging_type == "Receivable":
        v_type = "Sales"
        status_filter = "Pending"
    else:
        v_type = "Purchase"
        status_filter = "Pending"

    try:
        conn = get_connection()
        data = conn.execute(
            "SELECT date, narration, credit FROM vouchers WHERE company_key = ? AND v_type = ? AND COALESCE(status, 'Active') != 'Void' ORDER BY date ASC",
            (company_key, v_type),
        ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Date", "Description", "Amount (GH₵)"])
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Days Outstanding"] = (datetime.now() - df["Date"]).dt.days
            st.dataframe(df, use_container_width=True)
            if aging_type == "Receivable":
                show_debtors_by_city_report(company_key)
        else:
            st.info(f"No {aging_type} records found.")
    except Exception as e:
        st.error(f"Aging module error: {e}")


# ==========================================
# TAXATION (VAT / NHIL)
# ==========================================
def show_taxation(company_key):
    st.header("🧮 Taxation (VAT / NHIL)")
    VAT_RATE = 0.125
    NHIL_RATE = 0.025
    GETFUND_RATE = 0.025

    try:
        conn = get_connection()
        total_sales = conn.execute(
            "SELECT COALESCE(SUM(credit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Sales' AND COALESCE(status, 'Active') != 'Void'",
            (company_key,),
        ).fetchone()[0] or 0.0
        conn.close()

        vat = total_sales * VAT_RATE
        nhil = total_sales * NHIL_RATE
        getfund = total_sales * GETFUND_RATE
        total_tax = vat + nhil + getfund

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Sales", f"GH₵ {total_sales:,.2f}")
        col2.metric(f"VAT ({VAT_RATE*100:.1f}%)", f"GH₵ {vat:,.2f}")
        col3.metric(f"NHIL ({NHIL_RATE*100:.1f}%)", f"GH₵ {nhil:,.2f}")
        col4.metric("Total Tax Due", f"GH₵ {total_tax:,.2f}")
    except Exception as e:
        st.error(f"Taxation module error: {e}")


# ==========================================
# GHANA PAYROLL (SSNIT)
# ==========================================
def show_payroll(company_key, role):
    st.header("👷 Ghana Payroll (SSNIT)")

    if role == "Demo":
        _demo_notice()
        demo_df = pd.DataFrame({
            "Employee": ["John Mensah", "Ama Asante"],
            "Basic Salary": [2500.0, 3000.0],
            "SSNIT T1": [137.5, 165.0],
            "PAYE": [210.0, 280.0],
            "Net Salary": [2152.5, 2555.0],
            "Month": ["March 2026"] * 2,
        })
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.expander("➕ Add Payroll Entry", expanded=True):
        with st.form("payroll_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                emp_name = st.text_input("Employee Name")
                basic_salary = st.number_input("Basic Salary (GH₵)", min_value=0.0, step=0.01)
                allowances = st.number_input("Allowances (GH₵)", min_value=0.0, step=0.01)
                deductions = st.number_input("Deductions (GH₵)", min_value=0.0, step=0.01)
            with col2:
                month = st.selectbox("Month", ["January","February","March","April","May","June",
                                               "July","August","September","October","November","December"])
                year = st.selectbox("Year", [str(y) for y in range(2023, 2030)],
                                    index=[str(y) for y in range(2023, 2030)].index(str(datetime.now().year)))
                payment_status = st.selectbox("Payment Status", ["Paid", "Unpaid"])

            submitted = st.form_submit_button("Calculate & Save")
            if submitted and emp_name and basic_salary > 0:
                payroll_values = _calculate_payroll_values(basic_salary, allowances, deductions)
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO payroll
                           (company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                            taxable_income, paye, net_salary, deductions, month, year, payment_status, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active')""",
                        (
                            company_key,
                            emp_name,
                            basic_salary,
                            allowances,
                            payroll_values["ssnit_t1"],
                            payroll_values["ssnit_t2"],
                            payroll_values["taxable_income"],
                            payroll_values["paye"],
                            payroll_values["net_salary"],
                            deductions,
                            month,
                            year,
                            payment_status,
                        ),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Payroll Entry Added", "Payroll", f"{emp_name} - {month} {year}")
                    conn.close()
                    st.success("Entry Updated")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving payroll: {e}")

    st.subheader("Payroll Register")
    conn = None
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT id, emp_name, basic_salary, allowances, deductions, ssnit_t1, paye, net_salary, month, year,
                      payment_status, COALESCE(status, 'Active')
               FROM payroll WHERE company_key = ? ORDER BY year DESC, month DESC""",
            (company_key,),
        ).fetchall()
        if data:
            df = pd.DataFrame(data, columns=["ID", "Employee", "Basic Salary", "Allowances", "Deductions",
                                              "SSNIT T1", "PAYE", "Net Salary", "Month", "Year", "Payment Status", "Status"])
            st.dataframe(df, use_container_width=True)
            if role == "Master Admin":
                selected_payroll_key = f"payroll_edit_selected_{company_key}"
                void_payroll_key = f"payroll_void_selected_{company_key}"
                for _, payroll_list_row in df.iterrows():
                    name_col, edit_col, void_col = st.columns([4, 1, 1])
                    name_col.caption(
                        f"{payroll_list_row['Employee']} | Salary GH₵ {float(payroll_list_row['Basic Salary']):,.2f} | "
                        f"Net GH₵ {float(payroll_list_row['Net Salary']):,.2f} | {payroll_list_row['Status']}"
                    )
                    if edit_col.button("Edit", key=f"payroll_edit_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[selected_payroll_key] = int(payroll_list_row["ID"])
                    if payroll_list_row["Status"] != "Void" and void_col.button("Void", key=f"payroll_void_btn_{company_key}_{int(payroll_list_row['ID'])}"):
                        st.session_state[void_payroll_key] = int(payroll_list_row["ID"])
                void_payroll_id = st.session_state.get(void_payroll_key)
                if void_payroll_id is not None:
                    st.warning("Are you sure you want to void this payroll entry?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("Confirm Void", key=f"payroll_void_confirm_btn_{company_key}_{void_payroll_id}"):
                        conn.execute(
                            "UPDATE payroll SET status = 'Void' WHERE id = ? AND company_key = ?",
                            (int(void_payroll_id), company_key),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Payroll Voided", "Payroll", f"Voided payroll ID {int(void_payroll_id)}")
                        _clear_streamlit_state(void_payroll_key, selected_payroll_key)
                        st.success("Entry Updated")
                        st.rerun()
                    if cancel_col.button("Cancel", key=f"payroll_void_cancel_btn_{company_key}_{void_payroll_id}"):
                        _clear_streamlit_state(void_payroll_key)
                        st.rerun()
                payroll_record_id = st.session_state.get(selected_payroll_key, int(df["ID"].iloc[0]))
                edit_row = df.loc[df["ID"] == payroll_record_id].iloc[0]
                with st.form(f"payroll_edit_form_{company_key}_{payroll_record_id}", clear_on_submit=True):
                    edit_salary = st.number_input("Salary", min_value=0.0, value=float(edit_row["Basic Salary"] or 0.0))
                    edit_bonus = st.number_input("Bonus", min_value=0.0, value=float(edit_row["Allowances"] or 0.0))
                    edit_deductions = st.number_input("Deductions", min_value=0.0, value=float(edit_row["Deductions"] or 0.0))
                    edit_status = st.selectbox("Payment Status", ["Paid", "Unpaid"], index=0 if edit_row["Payment Status"] == "Paid" else 1)
                    if st.form_submit_button("Update Payroll"):
                        updated_values = _calculate_payroll_values(edit_salary, edit_bonus, edit_deductions)
                        details = (
                            f"{edit_row['Employee']} salary {float(edit_row['Basic Salary']):,.2f}->{edit_salary:,.2f}; "
                            f"bonus {float(edit_row['Allowances']):,.2f}->{edit_bonus:,.2f}; "
                            f"deductions {float(edit_row['Deductions']):,.2f}->{edit_deductions:,.2f}"
                        )
                        conn.execute(
                            """
                            UPDATE payroll
                            SET basic_salary = ?, allowances = ?, ssnit_t1 = ?, ssnit_t2 = ?,
                                taxable_income = ?, paye = ?, net_salary = ?, deductions = ?, payment_status = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_salary,
                                edit_bonus,
                                updated_values["ssnit_t1"],
                                updated_values["ssnit_t2"],
                                updated_values["taxable_income"],
                                updated_values["paye"],
                                updated_values["net_salary"],
                                edit_deductions,
                                edit_status,
                                int(payroll_record_id),
                                company_key,
                            ),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Payroll Updated", "Payroll", details)
                        _clear_streamlit_state(selected_payroll_key, void_payroll_key)
                        st.success("Entry Updated")
                        st.rerun()
        else:
            st.info("No payroll records found.")
    except Exception as e:
        st.error(f"Error loading payroll: {e}")
    finally:
        if conn:
            conn.close()


# ==========================================
# FIXED ASSET REGISTER
# ==========================================
def show_fixed_assets(company_key, role):
    st.header("🏗️ Fixed Asset Register")
    delete_success_key = f"asset_delete_success_{company_key}"
    if st.session_state.get(delete_success_key):
        st.success("Item deleted")
        st.session_state.pop(delete_success_key, None)

    if role == "Demo":
        _demo_notice()
        demo_df = pd.DataFrame({
            "Asset Name": ["Company Vehicle", "Office Computer"],
            "Category": ["Vehicle", "Equipment"],
            "Cost (GH₵)": [85000.0, 5500.0],
            "Depreciation Rate (%)": [20.0, 33.3],
            "Book Value (GH₵)": [68000.0, 3685.0],
            "Status": ["Active", "Active"],
        })
        st.dataframe(demo_df, use_container_width=True)
        return

    with st.expander("➕ Add Fixed Asset", expanded=True):
        with st.form("fixed_asset_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Category", ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"])
                purchase_date = st.date_input("Purchase Date", datetime.now().date())
            with col2:
                cost = st.number_input("Cost (GH₵)", min_value=0.0, step=0.01)
                opening_book_value = st.number_input("Opening Book Value", min_value=0.0, step=0.01)
                depreciation_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, step=0.1)
                location = st.text_input("Location")

            submitted = st.form_submit_button("Add Asset")
            if submitted and asset_name and cost > 0:
                book_value = opening_book_value if opening_book_value > 0 else cost
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO fixed_assets
                           (company_key, asset_name, asset_category, purchase_date, cost,
                            opening_book_value, depreciation_rate, accumulated_depreciation, book_value, location)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (company_key, asset_name, asset_category, purchase_date.isoformat(),
                         cost, book_value, depreciation_rate, book_value, location),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Added", "Fixed Assets", f"{asset_name} - GH₵{cost:,.2f}")
                    conn.close()
                    st.success("Entry Updated")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding asset: {e}")

    st.subheader("Asset Register")
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT id, asset_name, asset_category, purchase_date, cost, opening_book_value,
                      depreciation_rate, accumulated_depreciation, book_value, location, status
               FROM fixed_assets WHERE company_key = ? ORDER BY asset_name""",
            (company_key,),
        ).fetchall()
        if data:
            df = pd.DataFrame(data, columns=["ID", "Asset Name", "Category", "Purchase Date", "Cost (GH₵)",
                                              "Opening Book Value", "Dep. Rate (%)", "Accum. Dep.", "Current Value", "Location", "Status"])
            st.dataframe(df, use_container_width=True)

            total_cost = df["Cost (GH₵)"].sum()
            total_book = df["Current Value"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Assets", len(df))
            col2.metric("Total Cost", f"GH₵ {total_cost:,.2f}")
            col3.metric("Total Book Value", f"GH₵ {total_book:,.2f}")
            if role in ("Master Admin", "Bookkeeper", "Sub-Admin"):
                selected_asset_key = f"asset_edit_selected_{company_key}"
                delete_asset_key = f"asset_delete_selected_{company_key}"
                for _, asset_row in df.iterrows():
                    name_col, edit_col, delete_col = st.columns([4, 1, 1])
                    name_col.caption(
                        f"{asset_row['Asset Name']} | Current GH₵ {float(asset_row['Current Value']):,.2f} | "
                        f"Purchase Date {asset_row['Purchase Date']}"
                    )
                    if edit_col.button("Edit", key=f"asset_edit_btn_{company_key}_{int(asset_row['ID'])}"):
                        st.session_state[selected_asset_key] = int(asset_row["ID"])
                    if delete_col.button("Delete", key=f"asset_delete_btn_{company_key}_{int(asset_row['ID'])}"):
                        st.session_state[delete_asset_key] = int(asset_row["ID"])
                delete_asset_id = st.session_state.get(delete_asset_key)
                if delete_asset_id is not None:
                    st.warning("Are you sure you want to permanently delete this item?")
                    confirm_col, cancel_col = st.columns(2)
                    if confirm_col.button("Confirm Delete", key=f"asset_delete_confirm_btn_{company_key}_{delete_asset_id}"):
                        conn.execute(
                            "DELETE FROM fixed_assets WHERE id = ? AND company_key = ?",
                            (int(delete_asset_id), company_key),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Fixed Asset Deleted", "Fixed Assets", f"Deleted asset ID {int(delete_asset_id)}")
                        _clear_streamlit_state(delete_asset_key, selected_asset_key)
                        st.session_state[delete_success_key] = True
                        st.rerun()
                    if cancel_col.button("Cancel", key=f"asset_delete_cancel_btn_{company_key}_{delete_asset_id}"):
                        _clear_streamlit_state(delete_asset_key)
                        st.rerun()
                edit_asset_id = st.session_state.get(selected_asset_key, int(df["ID"].iloc[0]))
                edit_asset_row = df.loc[df["ID"] == edit_asset_id].iloc[0]
                with st.form(f"asset_edit_form_{company_key}_{edit_asset_id}", clear_on_submit=True):
                    edit_asset_name = st.text_input("Asset Name", value=str(edit_asset_row["Asset Name"] or ""))
                    edit_purchase_date = st.date_input("Purchase Date", value=pd.to_datetime(edit_asset_row["Purchase Date"]).date())
                    edit_cost = st.number_input("Cost (GH₵)", min_value=0.0, value=float(edit_asset_row["Cost (GH₵)"] or 0.0))
                    edit_opening_book = st.number_input("Opening Book Value", min_value=0.0, value=float(edit_asset_row["Opening Book Value"] or 0.0))
                    edit_depr_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, value=float(edit_asset_row["Dep. Rate (%)"] or 0.0))
                    edit_location = st.text_input("Location", value=str(edit_asset_row["Location"] or ""))
                    if st.form_submit_button("Update Asset"):
                        conn.execute(
                            """
                            UPDATE fixed_assets
                            SET asset_name = ?, purchase_date = ?, cost = ?, opening_book_value = ?,
                                depreciation_rate = ?, book_value = ?, location = ?
                            WHERE id = ? AND company_key = ?
                            """,
                            (
                                edit_asset_name,
                                edit_purchase_date.isoformat(),
                                edit_cost,
                                edit_opening_book,
                                edit_depr_rate,
                                edit_opening_book if edit_opening_book > 0 else edit_cost,
                                edit_location,
                                int(edit_asset_id),
                                company_key,
                            ),
                        )
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Fixed Asset Updated", "Fixed Assets", f"Updated asset ID {int(edit_asset_id)}")
                        _clear_streamlit_state(selected_asset_key, delete_asset_key)
                        st.success("Entry Updated")
                        st.rerun()
        else:
            st.info("No fixed assets registered yet.")
    except Exception as e:
        st.error(f"Error loading fixed assets: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


# ==========================================
# FINANCIAL INTELLIGENCE / REPORTS
# ==========================================
def show_reports(company_key):
    st.header("📈 Financial Intelligence")
    try:
        conn = get_connection()

        # Revenue vs Expenses
        total_revenue = conn.execute(
            "SELECT COALESCE(SUM(credit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Sales' AND COALESCE(status, 'Active') != 'Void'",
            (company_key,),
        ).fetchone()[0] or 0.0
        total_expenses = conn.execute(
            "SELECT COALESCE(SUM(debit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Expense' AND COALESCE(status, 'Active') != 'Void'",
            (company_key,),
        ).fetchone()[0] or 0.0
        net_profit = total_revenue - total_expenses

        conn.close()

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Revenue", f"GH₵ {total_revenue:,.2f}")
        col2.metric("Total Expenses", f"GH₵ {total_expenses:,.2f}")
        col3.metric("Net Profit / (Loss)", f"GH₵ {net_profit:,.2f}",
                    delta="Profit" if net_profit >= 0 else "Loss",
                    delta_color="normal" if net_profit >= 0 else "inverse")

        # P&L Chart
        chart_df = pd.DataFrame(
            {"Amount (GH₵)": [total_revenue, total_expenses]},
            index=["Revenue", "Expenses"],
        )
        st.bar_chart(chart_df)

    except Exception as e:
        st.error(f"Reports module error: {e}")


# ==========================================
# AI DATA ASSESSMENT
# ==========================================
def show_ai_assistant(client_id):
    active_company_id = _get_active_company_id(client_id)
    if not active_company_id:
        st.warning("No active company context is available for the AI assistant.")
        return

    st.header("AI Data Assessment")
    st.caption("Ask questions about your last 30 days of invoices, expenses, and payroll activity.")

    conn = None
    try:
        conn = get_connection()
        records = _fetch_ai_assistant_records(conn, active_company_id)
    except Exception as exc:
        logger.error(f"AI assistant data fetch failed: {exc}")
        st.error("The AI assistant could not load your accounting records.")
        return
    finally:
        if conn:
            conn.close()

    data_summary = _summarize_ai_assistant_data(records)
    col1, col2, col3 = st.columns(3)
    col1.metric("Invoices", str(len(records["invoices"])))
    col2.metric("Expenses", str(len(records["expenses"])))
    col3.metric("Payroll Entries", str(len(records["payroll"])))

    with st.expander("30-Day Data Snapshot", expanded=False):
        st.text(data_summary)

    history_key = f"ai_assistant_messages_{active_company_id}"
    if history_key not in st.session_state:
        st.session_state[history_key] = [
            {
                "role": "assistant",
                "content": (
                    "I can review your recent invoices, expenses, and payroll activity. "
                    "Ask about trends, missing records, unusual balances, or possible corrections."
                ),
            }
        ]

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_question = st.chat_input(
        "Ask about invoices, expenses, or payroll...",
        key=f"ai_assistant_input_{active_company_id}",
    )
    if not user_question:
        return

    st.session_state[history_key].append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.markdown(user_question)

    groq_client = _get_groq_client()
    if not groq_client:
        fallback_response = (
            "AI insights are unavailable because the `GROQ_API_KEY` secret is not configured. "
            "Your 30-day data snapshot is still available above for manual review."
        )
        st.session_state[history_key].append({"role": "assistant", "content": fallback_response})
        with st.chat_message("assistant"):
            st.markdown(fallback_response)
        return

    prompt = (
        "You are an accounting data assessment assistant for a Ghana-focused ERP. "
        "Use the supplied 30-day accounting summary to answer clearly, highlight anomalies, "
        "and suggest edits or follow-up checks when appropriate. "
        "Do not invent records that are not present.\n\n"
        f"Client ID: {active_company_id}\n"
        f"30-day data summary:\n{data_summary}\n\n"
        f"User question: {user_question}"
    )

    try:
        with st.chat_message("assistant"):
            with st.spinner("Reviewing your accounting records..."):
                completion = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a careful accounting assistant. Base your answer only on the "
                                "provided summary, note uncertainty, and keep suggestions practical."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
                assistant_reply = completion.choices[0].message.content.strip()
                st.markdown(assistant_reply)
        st.session_state[history_key].append({"role": "assistant", "content": assistant_reply})
    except Exception as exc:
        logger.error(f"AI assistant request failed: {exc}")
        failure_message = (
            "The AI assessment request failed just now. Please try again, or review the 30-day snapshot above."
        )
        st.session_state[history_key].append({"role": "assistant", "content": failure_message})
        with st.chat_message("assistant"):
            st.markdown(failure_message)


# ==========================================
# SYSTEM AUDIT TRAIL
# ==========================================
def show_audit_trail(company_key):
    st.header("🔍 System Audit Trail")
    try:
        conn = get_connection()
        if company_key == "ADMIN" or company_key == "DEMO":
            data = conn.execute(
                "SELECT timestamp, company_key, user_role, action, module_name, details FROM audit_logs ORDER BY timestamp DESC LIMIT 100"
            ).fetchall()
        else:
            data = conn.execute(
                "SELECT timestamp, company_key, user_role, action, module_name, details FROM audit_logs WHERE company_key = ? ORDER BY timestamp DESC LIMIT 100",
                (company_key,),
            ).fetchall()
        conn.close()

        if data:
            df = pd.DataFrame(data, columns=["Timestamp", "Company", "Role", "Action", "Module", "Details"])
            st.dataframe(df, use_container_width=True)
            excel_bin = get_excel_bin(df)
            if excel_bin:
                st.download_button("📥 Export Audit Trail", data=excel_bin, file_name="audit_trail.xlsx")
        else:
            st.info("No audit records found.")
    except Exception as e:
        st.error(f"Audit trail error: {e}")
