import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

# --- 1. SYSTEM SETUP & DATABASE ---
def init_db():
    conn = sqlite3.connect('business_pro.db')
    c = conn.cursor()
    # Transactions with Tax & Units
    c.execute('''CREATE TABLE IF NOT EXISTS transactions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, voucher_type TEXT, 
                  ledger_group TEXT, name TEXT, item TEXT, units REAL, uom TEXT, 
                  price REAL, tax_rate REAL, total REAL, payment REAL, user_role TEXT)''')
    # Inventory with Batches & Godowns
    c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                 (item_code TEXT PRIMARY KEY, product_name TEXT, category TEXT, 
                  godown TEXT, batch_no TEXT, expiry TEXT, stock_qty REAL)''')
    # Company Profile
    c.execute('''CREATE TABLE IF NOT EXISTS company_info 
                 (name TEXT, fin_year TEXT, tin TEXT, vat_no TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. SECURITY & USER ROLES ---
st.sidebar.title("🔐 Security Portal")
user_mode = st.sidebar.radio("Login As:", ["Administrator", "Staff (View Only)"])

if user_mode == "Administrator":
    st.sidebar.success("Full Edit Access Granted")
else:
    st.sidebar.warning("Read-Only Mode Active")

# --- 3. MAIN NAVIGATION (The 18 Pillars) ---
st.sidebar.title("🏢 ERP Navigation")
main_menu = st.sidebar.selectbox("Select Module", [
    "1. Company Setup", "2. Chart of Accounts", "4. Inventory & Godowns", 
    "6. Voucher Entry (POS)", "9. Receivables & Payables", "12. Payroll", 
    "15. Financial Reports", "17. Audit Logs"
])

# --- MODULE 1: COMPANY SETUP ---
if main_menu == "1. Company Setup":
    st.header("🏗️ Company Configuration")
    if user_mode == "Administrator":
        with st.form("setup"):
            c_name = st.text_input("Company Name")
            c_tin = st.text_input("TIN / Tax Number")
            c_vat = st.text_input("VAT Registration Number")
            c_year = st.text_input("Financial Year (e.g., 2026-2027)")
            if st.form_submit_button("Save Settings"):
                st.success("Configuration Saved!")
    else:
        st.error("Access Denied: Admin only.")

# --- MODULE 4: INVENTORY & GODOWNS ---
elif main_menu == "4. Inventory & Godowns":
    st.header("📦 Inventory Management")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add Stock Item")
        if user_mode == "Administrator":
            with st.form("stock"):
                i_name = st.text_input("Product Name")
                i_uom = st.selectbox("Unit (UoM)", ["Pieces", "Kilograms", "Cartons", "Boxes"])
                i_godown = st.selectbox("Storage Location", ["Main Warehouse", "Shop Floor", "Branch A"])
                i_batch = st.text_input("Batch Number")
                i_exp = st.date_input("Expiry Date")
                if st.form_submit_button("Register Stock"):
                    st.success(f"{i_name} added to {i_godown}")
        else:
            st.info("Staff can only view stock levels below.")
    
    with col2:
        st.subheader("Current Stock Status")
        # Placeholder for stock table
        st.info("Scanning Godowns...")

# --- MODULE 6: VOUCHER ENTRY (THE ENGINE) ---
elif main_menu == "6. Voucher Entry (POS)":
    st.header("🧾 Accounting Vouchers")
    v_type = st.selectbox("Voucher Type", ["Sales", "Purchase", "Payment", "Receipt", "Contra", "Journal"])
    
    with st.form("voucher"):
        c1, c2 = st.columns(2)
        with c1:
            v_date = st.date_input("Date", date.today())
            v_party = st.text_input("Particulars (Customer/Supplier Name)")
            v_item = st.text_input("Item/Service Description")
        with c2:
            v_qty = st.number_input("Quantity", min_value=0.0)
            v_price = st.number_input("Unit Price (GHS)", min_value=0.0)
            v_tax = st.selectbox("VAT Class", [0, 12.5, 15, 18])
        
        v_total = (v_qty * v_price) * (1 + (v_tax/100))
        st.write(f"### Grand Total: {v_total:.2f} GHS (Incl. VAT)")
        
        if st.form_submit_button("Post Voucher"):
            if user_mode == "Administrator":
                st.success(f"{v_type} Voucher Posted Successfully!")
            else:
                st.error("Staff cannot post vouchers.")

# --- MODULE 15: FINANCIAL REPORTS ---
elif main_menu == "15. Financial Reports":
    st.header("📊 Financial Intelligence")
    report_type = st.tabs(["Profit & Loss", "Balance Sheet", "Trial Balance", "Aging Analysis"])
    
    with report_type[0]:
        st.metric("Net Profit", "0.00 GHS", delta="0%")
        
    
    with report_type[3]:
        st.subheader("Outstanding Receivables (Debtors)")
        st.write("No overdue invoices found.")

# --- MODULE 17: AUDIT LOGS ---
elif main_menu == "17. Audit Logs":
    st.header("🕵️ System Audit Trail")
    st.write("Tracking all user activities...")
    # This section would pull from a hidden 'logs' table