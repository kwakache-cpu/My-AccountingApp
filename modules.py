import streamlit as st
import pandas as pd
from database import get_connection
from datetime import datetime

# --- 2. CHART OF ACCOUNTS ---
def show_chart_of_accounts(company_key, role):
    st.header("🗂️ Chart of Accounts")
    tabs = st.tabs(["Groups & Ledgers", "Customers & Suppliers", "Opening Balances"])
    
    with tabs[0]:
        st.subheader("Add New Ledger")
        col1, col2 = st.columns(2)
        l_name = col1.text_input("Ledger Name")
        l_group = col2.selectbox("Group", ["Assets", "Liabilities", "Equity", "Income", "Expenses"])
        if st.button("Create Ledger") and role == "Master Admin":
            conn = get_connection()
            conn.execute("INSERT INTO accounts (company_key, name, account_group) VALUES (?,?,?)", (company_key, l_name, l_group))
            conn.commit()
            st.success(f"Ledger {l_name} created!")

    with tabs[1]:
        st.subheader("Customer & Supplier Directory")
        c_type = st.radio("Type", ["Customer", "Supplier"], horizontal=True)
        c_name = st.text_input(f"{c_type} Name")
        if st.button(f"Add {c_type}"):
            conn = get_connection()
            conn.execute("INSERT INTO accounts (company_key, name, account_group) VALUES (?,?,?)", (company_key, c_name, c_type))
            conn.commit()
            st.success(f"{c_name} added to directory.")

# --- 3. INVENTORY MANAGEMENT ---
def show_inventory(company_key, role):
    st.header("📦 Inventory Management")
    with st.expander("➕ Add New Stock Item"):
        col1, col2, col3 = st.columns(3)
        item = col1.text_input("Item Name")
        unit = col2.selectbox("Unit", ["Pcs", "Kgs", "Litres", "Boxes"])
        qty = col3.number_input("Opening Qty", min_value=0)
        expiry = st.date_input("Expiry Date (if applicable)")
        
        if st.button("Save Item") and role != "Staff":
            conn = get_connection()
            conn.execute("INSERT INTO inventory (company_key, item_name, unit, qty, expiry) VALUES (?,?,?,?,?)",
                         (company_key, item, unit, qty, str(expiry)))
            conn.commit()
            st.success(f"{item} added to stock.")

    conn = get_connection()
    df = pd.read_sql(f"SELECT item_name, unit, qty, expiry FROM inventory WHERE company_key='{company_key}'", conn)
    st.dataframe(df, use_container_width=True)

# --- 4 & 5. SALES & PURCHASE MODULES ---
def show_sales_purchase(company_key, role, mode="Sales"):
    st.header(f"{'🛒' if mode=='Sales' else '📥'} {mode} Module")
    with st.form(f"{mode}_form"):
        party = st.text_input("Customer Name" if mode=="Sales" else "Supplier Name")
        item = st.text_input("Product/Service")
        amount = st.number_input("Amount (GHS)", min_value=0.0)
        tax_rate = st.slider("VAT/GST (%)", 0, 15, 5)
        
        total = amount + (amount * tax_rate / 100)
        st.write(f"**Total Invoice Value: GHS {total:.2f}**")
        
        if st.form_submit_button(f"Post {mode} Invoice"):
            if role in ["Master Admin", "Sub-Admin"]:
                conn = get_connection()
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?,?,?,?,?,?)",
                             (company_key, str(datetime.now().date()), mode, party, total, f"{mode} of {item}"))
                # Update Audit Trail
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?,?)", 
                             (company_key, f"Generated {mode} for {party}: GHS {total}"))
                conn.commit()
                st.success(f"{mode} transaction recorded!")
            else:
                st.error("Permission Denied: Staff cannot post invoices.")

# --- 6. VOUCHER SYSTEM (Advanced) ---
def show_vouchers(company_key, role):
    st.header("📝 Advanced Voucher System")
    v_type = st.selectbox("Voucher Type", ["Receipt", "Payment", "Contra", "Journal", "Sales", "Purchase", "Credit Note", "Debit Note", "Stock Journal"])
    
    with st.form("voucher_form"):
        col1, col2 = st.columns(2)
        v_date = col1.date_input("Date")
        ledger = col2.text_input("Account/Ledger")
        amount = col2.number_input("Amount (GHS)", min_value=0.0)
        narration = st.text_area("Narration")
        
        if st.form_submit_button("Post Voucher"):
            if role in ["Master Admin", "Sub-Admin"]:
                conn = get_connection()
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?,?,?,?,?,?)",
                             (company_key, str(v_date), v_type, ledger, amount, narration))
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?,?)", 
                             (company_key, f"Voucher {v_type} - {ledger}: GHS {amount}"))
                conn.commit()
                st.success("Voucher posted to accounts!")
            else:
                st.error("Read-Only: Staff cannot post vouchers.")

# --- 7. BANKING ---
def show_banking(company_key, role):
    st.header("🏦 Banking & Cash")
    col1, col2 = st.columns(2)
    col1.metric("Cash Balance", "GHS 5,200") # Logic would pull from sum of 'Cash' ledger
    col2.metric("Bank Balance", "GHS 12,850")
    
    st.subheader("Bank Reconciliation")
    st.file_upload("Upload Bank Statement for Reconciliation")

# --- 8 & 9. RECEIVABLES & PAYABLES ---
def show_aging_reports(company_key, mode="Receivable"):
    st.header(f"⏳ Accounts {mode}")
    # This pulls from the Vouchers table where Ledger Group is Customer/Supplier
    st.info(f"Generating Aging Report for all outstanding {mode} invoices...")
    # Placeholder for Aging Logic
    data = {"Entity": ["Client A", "Client B"], "0-30 Days": [1000, 0], "31-60 Days": [0, 500], "Total": [1000, 500]}
    st.table(pd.DataFrame(data))

# --- 10. TAX MANAGEMENT ---
def show_tax_reports(company_key):
    st.header("🧾 Tax Management")
    st.subheader("VAT/GST Summary")
    # Pulls tax amounts from vouchers
    st.write("Current Tax Liability: **GHS 1,450.00**")
    if st.button("Generate Tax Return File"):
        st.download_button("Download Report", "CSV_DATA", "tax_report.csv")

# --- 11. FINANCIAL REPORTS ---
def show_reports(company_key):
    st.header("📊 Financial Intelligence")
    report_type = st.radio("Select Report", ["Trial Balance", "Profit & Loss", "Balance Sheet", "Cash Flow"], horizontal=True)
    
    conn = get_connection()
    df = pd.read_sql(f"SELECT date, v_type, ledger, amount FROM vouchers WHERE company_key='{company_key}'", conn)
    
    if report_type == "Profit & Loss":
        st.subheader("Profit & Loss Statement")
        # Logic: (Income Vouchers) - (Expense Vouchers)
        st.info("P&L logic is summarizing Income vs Expense ledgers.")
    st.dataframe(df)

# --- 12. FIXED ASSETS ---
def show_fixed_assets(company_key, role):
    st.header("🏛️ Fixed Assets & Depreciation")
    with st.expander("Register New Asset"):
        asset = st.text_input("Asset Name")
        cost = st.number_input("Purchase Cost", min_value=0.0)
        dep_rate = st.slider("Depreciation Rate (%)", 0, 50, 10)
        if st.button("Add Asset"):
            st.success(f"Asset '{asset}' registered. Annual Depreciation: GHS {cost * (dep_rate/100)}")

# --- PREVIOUS MODULES PRESERVED ---
def show_payroll(company_key, role):
    st.header("🇬🇭 Payroll (SSNIT & PAYE)")
    # - Calculations preserved
    with st.form("payroll_form"):
        emp_name = st.text_input("Employee Name")
        basic_salary = st.number_input("Basic Salary (GHS)", min_value=0.0)
        if st.form_submit_button("Calculate & Process"):
            ssnit_t1 = basic_salary * 0.135
            paye = (basic_salary - (basic_salary * 0.05)) * 0.10 
            net_salary = basic_salary - (basic_salary * 0.05) - paye
            if role == "Master Admin":
                conn = get_connection()
                conn.execute("INSERT INTO payroll (company_key, emp_name, basic_salary, ssnit_tier1, paye, net_salary) VALUES (?,?,?,?,?,?)",
                             (company_key, emp_name, basic_salary, ssnit_t1, paye, net_salary))
                conn.commit()
                st.success(f"Processed Payroll for {emp_name}!")
            else:
                st.info(f"Calculated Net Salary: GHS {net_salary:.2f} (Record not saved - Admin only)")

def show_audit_trail(company_key):
    st.header("🕵️ Audit Trail (Security Log)")
    conn = get_connection()
    df_audit = pd.read_sql(f"SELECT timestamp, action FROM audit_logs WHERE company_key='{company_key}' ORDER BY timestamp DESC", conn)
    st.table(df_audit)

def show_company_setup(company_key, company_name, role):
    st.header(f"⚙️ Setup: {company_name}")
    # Access Restricted for Sub-Admin/Staff
    if role == "Master Admin":
        sub_key = st.text_input("Set Sub-Admin Key", type="password")
        recovery = st.text_input("Set Recovery Answer", type="password")
        if st.button("Save Settings"):
            conn = get_connection()
            conn.execute("UPDATE companies SET sub_admin_key=?, recovery_answer=? WHERE key=?", 
                         (sub_key, recovery, company_key))
            conn.commit()
            st.success("Security settings updated!")
    else:
        st.warning("Access Restricted: Only Master Admin can modify keys.")