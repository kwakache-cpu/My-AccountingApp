import logging
import os
import sqlite3
from datetime import datetime
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta
from groq import Groq

# Setup Logger
logger = logging.getLogger(__name__)

# Import shared utilities from database
from database import get_connection, log_audit_action


# ==========================================
# PAYSTACK PAYMENT
# ==========================================
def initialize_paystack_payment(email, amount, reference):
    """Initialize a payment with Paystack."""
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {st.secrets['paystack_secret_key']}",
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

    with st.form("onboarding_form"):
        col1, col2 = st.columns(2)
        with col1:
            company_name = st.text_input("Company Name")
            admin_email = st.text_input("Admin Email Address")
        with col2:
            sector = st.selectbox("Business Sector", ["Retail", "Manufacturing", "Services", "Construction", "Other"])
            package = st.selectbox("ERP Package", ["Standard", "Professional", "Enterprise"])

        amount_map = {"Standard": 500, "Professional": 1200, "Enterprise": 2500}
        amount = amount_map[package]

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
                            'reference': reference
                        }
                        st.link_button("Proceed to Paystack", url)
                    else:
                        st.error("Failed to initialize payment.")
                except Exception as e:
                    st.error(f"Onboarding payment error: {e}")
                    logger.error(f"Onboarding payment error: {e}")


# ==========================================
# INVENTORY MANAGEMENT
# ==========================================
def show_inventory(company_key, role):
    st.header("📦 Inventory Management")

    tabs = st.tabs(["Stock Overview", "Stock In/Out", "Items Management"])

    with tabs[0]:
        st.subheader("Current Stock Levels")
        try:
            conn = get_connection()
            if role == "Demo":
                df = pd.DataFrame({
                    "item_code": ["INV-001", "INV-002"],
                    "item_name": ["Product A", "Product B"],
                    "category": ["General", "General"],
                    "quantity": [50, 8],
                    "unit_price": [120.0, 75.0],
                    "total_value": [6000.0, 600.0],
                })
            else:
                query = """
                    SELECT item_code, item_name, category, qty as quantity,
                           price as unit_price, (qty * price) as total_value
                    FROM inventory WHERE company_key = ?
                """
                df = pd.read_sql_query(query, conn, params=(company_key,))
            conn.close()

            if not df.empty:
                st.dataframe(df, use_container_width=True)
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Items", len(df))
                col2.metric("Total Value", f"GH₵ {df['total_value'].sum():,.2f}")
                col3.metric("Low Stock Alerts", len(df[df['quantity'] < 10]))
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
        with st.form("add_inventory_form"):
            item_name = st.text_input("Item Name")
            category = st.text_input("Category")
            qty = st.number_input("Quantity", min_value=0.0, value=0.0)
            price = st.number_input("Selling Price (GH₵)", min_value=0.0, value=0.0)
            cost_price = st.number_input("Cost Price (GH₵)", min_value=0.0, value=0.0)
            submitted = st.form_submit_button("Add Item")
            if submitted and item_name:
                try:
                    conn = get_connection()
                    conn.execute(
                        "INSERT INTO inventory (company_key, item_name, category, qty, price, cost_price) VALUES (?, ?, ?, ?, ?, ?)",
                        (company_key, item_name, category, qty, price, cost_price),
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Item '{item_name}' added successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding item: {e}")


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
                "SELECT date, v_type, narration, credit, reference_no FROM vouchers WHERE company_key = ? ORDER BY date DESC LIMIT 100",
                (company_key,),
            ).fetchall()
            df = pd.DataFrame(data, columns=["Date", "Type", "Narration", "Amount", "Ref"]) if data else pd.DataFrame()
        conn.close()
        if not df.empty:
            st.dataframe(df, use_container_width=True)
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
    try:
        conn = get_connection()
        company = conn.execute("SELECT * FROM companies WHERE key = ?", (company_key,)).fetchone()
        conn.close()
        if company:
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Company Name", value=company["name"], disabled=True)
                st.text_input("License Key", value=company["key"], disabled=True)
                st.text_input("Plan Type", value=company.get("plan_type", "Basic"), disabled=True)
            with col2:
                st.text_input("Subscription Expiry", value=str(company.get("subscription_expiry", "N/A")), disabled=True)
                st.text_input("Status", value=company.get("status", "Active"), disabled=True)
                st.text_input("Contact Email", value=str(company.get("contact_email", "")), disabled=True)
        else:
            st.info("Company profile not found.")
    except Exception as e:
        st.error(f"Error loading company setup: {e}")


# ==========================================
# POINT OF SALE (POS)
# ==========================================
def show_pos(company_key, company_name, role):
    st.header("🛒 Point of Sale")
    if role == "Demo":
        _demo_notice()
        st.info("Demo POS: Select items and process a mock sale.")
        demo_items = ["Product A - GH₵ 120.00", "Product B - GH₵ 75.00", "Product C - GH₵ 200.00"]
        selected = st.multiselect("Select Items", demo_items)
        if selected:
            st.success(f"Demo sale: {len(selected)} item(s) selected. Total: GH₵ {len(selected) * 120:.2f}")
        return

    try:
        conn = get_connection()
        items = conn.execute(
            "SELECT id, item_name, price, qty FROM inventory WHERE company_key = ? AND qty > 0",
            (company_key,),
        ).fetchall()
        conn.close()

        if not items:
            st.info("No stock available for sale. Please add inventory items first.")
            return

        items_df = pd.DataFrame(items, columns=["ID", "Item Name", "Price", "Qty"])
        selected_item = st.selectbox("Select Item", items_df["Item Name"].tolist())
        qty_to_sell = st.number_input("Quantity", min_value=1, value=1)
        payment_method = st.selectbox("Payment Method", ["Cash", "Mobile Money", "Bank Transfer", "Cheque"])

        if st.button("Process Sale"):
            item_row = items_df.loc[items_df["Item Name"] == selected_item].iloc[0]
            total = float(item_row["Price"]) * qty_to_sell
            if qty_to_sell > item_row["Qty"]:
                st.error("Insufficient stock.")
            else:
                try:
                    conn = get_connection()
                    conn.execute(
                        "UPDATE inventory SET qty = qty - ? WHERE id = ? AND company_key = ?",
                        (qty_to_sell, int(item_row["ID"]), company_key),
                    )
                    conn.execute(
                        """INSERT INTO vouchers (company_key, date, v_type, ledger, credit, payment_method, narration, created_by)
                           VALUES (?, ?, 'Sales', 'Sales Revenue', ?, ?, ?, ?)""",
                        (company_key, datetime.now().date().isoformat(), total, payment_method,
                         f"POS Sale: {selected_item} x{qty_to_sell}", role),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "POS Sale", "POS", f"Sold {selected_item} x{qty_to_sell} for GH₵{total:.2f}")
                    conn.close()
                    st.success(f"Sale processed! Total: GH₵ {total:,.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error processing sale: {e}")
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
        else:
            st.info(f"No {doc_type} records found.")
    except Exception as e:
        st.error(f"Error loading {doc_type} records: {e}")


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
               WHERE company_key = ? AND payment_method = 'Cash'""",
            (company_key,),
        ).fetchone()[0] or 0.0
        bank_total = conn.execute(
            """SELECT COALESCE(SUM(credit) - SUM(debit), 0) FROM vouchers
               WHERE company_key = ? AND payment_method = 'Bank Transfer'""",
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
            "SELECT date, narration, credit FROM vouchers WHERE company_key = ? AND v_type = ? ORDER BY date ASC",
            (company_key, v_type),
        ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Date", "Description", "Amount (GH₵)"])
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df["Days Outstanding"] = (datetime.now() - df["Date"]).dt.days
            st.dataframe(df, use_container_width=True)
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
            "SELECT COALESCE(SUM(credit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Sales'",
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
    SSNIT_T1_RATE = 0.055
    SSNIT_T2_RATE = 0.05

    def calc_paye(taxable):
        """Calculate Ghana PAYE tax based on GRA bands."""
        bands = [
            (319, 0.0),
            (110, 0.05),
            (130, 0.10),
            (3000, 0.175),
            (16441, 0.25),
            (float('inf'), 0.30),
        ]
        tax = 0.0
        for band, rate in bands:
            if taxable <= 0:
                break
            chunk = min(taxable, band)
            tax += chunk * rate
            taxable -= chunk
        return tax

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
        with st.form("payroll_form"):
            col1, col2 = st.columns(2)
            with col1:
                emp_name = st.text_input("Employee Name")
                basic_salary = st.number_input("Basic Salary (GH₵)", min_value=0.0, step=0.01)
                allowances = st.number_input("Allowances (GH₵)", min_value=0.0, step=0.01)
            with col2:
                month = st.selectbox("Month", ["January","February","March","April","May","June",
                                               "July","August","September","October","November","December"])
                year = st.selectbox("Year", [str(y) for y in range(2023, 2030)],
                                    index=[str(y) for y in range(2023, 2030)].index(str(datetime.now().year)))
                payment_status = st.selectbox("Payment Status", ["Paid", "Unpaid"])

            submitted = st.form_submit_button("Calculate & Save")
            if submitted and emp_name and basic_salary > 0:
                ssnit_t1 = basic_salary * SSNIT_T1_RATE
                ssnit_t2 = basic_salary * SSNIT_T2_RATE
                taxable_income = basic_salary + allowances - ssnit_t1
                paye = calc_paye(taxable_income / 12) * 12 if taxable_income > 0 else 0.0
                net_salary = basic_salary + allowances - ssnit_t1 - paye
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO payroll
                           (company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                            taxable_income, paye, net_salary, month, year, payment_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (company_key, emp_name, basic_salary, allowances, ssnit_t1, ssnit_t2,
                         taxable_income, paye, net_salary, month, year, payment_status),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Payroll Entry Added", "Payroll", f"{emp_name} - {month} {year}")
                    conn.close()
                    st.success(f"Payroll saved. Net Salary: GH₵ {net_salary:,.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving payroll: {e}")

    st.subheader("Payroll Register")
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT emp_name, basic_salary, allowances, ssnit_t1, paye, net_salary, month, year, payment_status
               FROM payroll WHERE company_key = ? ORDER BY year DESC, month DESC""",
            (company_key,),
        ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Employee", "Basic Salary", "Allowances",
                                              "SSNIT T1", "PAYE", "Net Salary", "Month", "Year", "Status"])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No payroll records found.")
    except Exception as e:
        st.error(f"Error loading payroll: {e}")


# ==========================================
# FIXED ASSET REGISTER
# ==========================================
def show_fixed_assets(company_key, role):
    st.header("🏗️ Fixed Asset Register")

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
        with st.form("fixed_asset_form"):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("Asset Name")
                asset_category = st.selectbox("Category", ["Vehicle", "Equipment", "Building", "Furniture", "Land", "Other"])
                purchase_date = st.date_input("Purchase Date", datetime.now().date())
            with col2:
                cost = st.number_input("Cost (GH₵)", min_value=0.0, step=0.01)
                depreciation_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, step=0.1)
                location = st.text_input("Location")

            submitted = st.form_submit_button("Add Asset")
            if submitted and asset_name and cost > 0:
                book_value = cost  # Initial book value equals cost
                try:
                    conn = get_connection()
                    conn.execute(
                        """INSERT INTO fixed_assets
                           (company_key, asset_name, asset_category, purchase_date, cost,
                            depreciation_rate, accumulated_depreciation, book_value, location)
                           VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (company_key, asset_name, asset_category, purchase_date.isoformat(),
                         cost, depreciation_rate, book_value, location),
                    )
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Fixed Asset Added", "Fixed Assets", f"{asset_name} - GH₵{cost:,.2f}")
                    conn.close()
                    st.success(f"Asset '{asset_name}' added. Book Value: GH₵ {book_value:,.2f}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding asset: {e}")

    st.subheader("Asset Register")
    try:
        conn = get_connection()
        data = conn.execute(
            """SELECT asset_name, asset_category, purchase_date, cost,
                      depreciation_rate, accumulated_depreciation, book_value, location, status
               FROM fixed_assets WHERE company_key = ? ORDER BY asset_name""",
            (company_key,),
        ).fetchall()
        conn.close()
        if data:
            df = pd.DataFrame(data, columns=["Asset Name", "Category", "Purchase Date", "Cost (GH₵)",
                                              "Dep. Rate (%)", "Accum. Dep.", "Book Value (GH₵)", "Location", "Status"])
            st.dataframe(df, use_container_width=True)

            total_cost = df["Cost (GH₵)"].sum()
            total_book = df["Book Value (GH₵)"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Assets", len(df))
            col2.metric("Total Cost", f"GH₵ {total_cost:,.2f}")
            col3.metric("Total Book Value", f"GH₵ {total_book:,.2f}")
        else:
            st.info("No fixed assets registered yet.")
    except Exception as e:
        st.error(f"Error loading fixed assets: {e}")


# ==========================================
# FINANCIAL INTELLIGENCE / REPORTS
# ==========================================
def show_reports(company_key):
    st.header("📈 Financial Intelligence")
    try:
        conn = get_connection()

        # Revenue vs Expenses
        total_revenue = conn.execute(
            "SELECT COALESCE(SUM(credit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Sales'",
            (company_key,),
        ).fetchone()[0] or 0.0
        total_expenses = conn.execute(
            "SELECT COALESCE(SUM(debit), 0) FROM vouchers WHERE company_key = ? AND v_type = 'Expense'",
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
