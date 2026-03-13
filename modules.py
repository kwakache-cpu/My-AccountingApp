import streamlit as st
import pandas as pd
from database import get_connection
from datetime import datetime

# --- 1. POS (POINT OF SALE) ---
def show_pos(company_key, company_name, role):
    st.header("🛒 Point of Sale")
    if 'cart' not in st.session_state: st.session_state.cart = []
    
    col1, col2 = st.columns([2, 1])
    with col1:
        item = st.text_input("Product Name", key="pos_item")
        qty = st.number_input("Quantity", min_value=1, key="pos_qty")
        price = st.number_input("Unit Price (GHS)", min_value=0.0, key="pos_price")
        if st.button("Add to Cart", key="pos_add"):
            st.session_state.cart.append({"Product": item, "Qty": qty, "Price": price, "Total": qty*price})
            
    with col2:
        if st.session_state.cart:
            df = pd.DataFrame(st.session_state.cart)
            st.table(df)
            total = df['Total'].sum()
            st.write(f"### Grand Total: GHS {total:.2f}")
            
            if st.button("Complete & Print Receipt", key="pos_finish"):
                # Clean HTML Receipt for printing momentum
                receipt_html = f"""
                <div style="border:1px solid black; padding:10px; font-family:monospace;">
                    <h2 style="text-align:center;">{company_name}</h2>
                    <p>Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                    <hr>{df.to_html(index=False)}<hr>
                    <h3 style="text-align:right;">TOTAL: GHS {total:.2f}</h3>
                </div>
                """
                st.markdown(receipt_html, unsafe_allow_html=True)
                st.session_state.cart = [] # Clear cart

# --- 2. CHART OF ACCOUNTS (With Search) ---
def show_chart_of_accounts(company_key, role):
    st.header("🗂️ Chart of Accounts")
    search_l = st.text_input("🔍 Search Ledgers", key="coa_search")
    tabs = st.tabs(["Groups & Ledgers", "Customers & Suppliers", "Opening Balances"])
    
    with tabs[0]:
        st.subheader("Add New Ledger")
        col1, col2 = st.columns(2)
        l_name = col1.text_input("Ledger Name", key="coa_l_name")
        l_group = col2.selectbox("Group", ["Assets", "Liabilities", "Equity", "Income", "Expenses"], key="coa_l_group")
        if st.button("Create Ledger", key="coa_l_btn") and role == "Master Admin":
            conn = get_connection(); conn.execute("INSERT INTO accounts (company_key, name, account_group) VALUES (?,?,?)", (company_key, l_name, l_group)); conn.commit(); st.success("Created!")
        
        conn = get_connection()
        df = pd.read_sql(f"SELECT name, account_group FROM accounts WHERE company_key='{company_key}'", conn)
        if search_l: df = df[df['name'].str.contains(search_l, case=False)]
        st.dataframe(df, use_container_width=True)

    with tabs[1]:
        c_type = st.radio("Type", ["Customer", "Supplier"], horizontal=True, key="coa_dir_type")
        c_name = st.text_input(f"{c_type} Name", key="coa_dir_name")
        if st.button(f"Add {c_type}", key="coa_dir_btn"):
            conn = get_connection(); conn.execute("INSERT INTO accounts (company_key, name, account_group) VALUES (?,?,?)", (company_key, c_name, c_type)); conn.commit(); st.success(f"{c_name} added.")

# --- 3. INVENTORY (With Search) ---
def show_inventory(company_key, role):
    st.header("📦 Inventory Management")
    search_i = st.text_input("🔍 Search Stock Items", key="inv_search")
    with st.expander("➕ Add New Stock Item"):
        col1, col2, col3 = st.columns(3)
        item = col1.text_input("Item Name", key="inv_name")
        unit = col2.selectbox("Unit", ["Pcs", "Kgs", "Litres", "Boxes"], key="inv_unit")
        qty = col3.number_input("Opening Qty", min_value=0, key="inv_qty")
        prc = st.number_input("Cost Price (GHS)", key="inv_prc")
        expiry = st.date_input("Expiry Date", key="inv_exp")
        
        if st.button("Save Item", key="inv_btn") and role != "Staff":
            conn = get_connection(); conn.execute("INSERT INTO inventory (company_key, item_name, unit, qty, price, expiry) VALUES (?,?,?,?,?,?)", (company_key, item, unit, qty, prc, str(expiry))); conn.commit(); st.success("Item Saved!")

    conn = get_connection()
    df = pd.read_sql(f"SELECT item_name, unit, qty, price, expiry FROM inventory WHERE company_key='{company_key}'", conn)
    if search_i: df = df[df['item_name'].str.contains(search_i, case=False)]
    st.dataframe(df, use_container_width=True)

# --- 4 & 5. SALES & PURCHASE ---
def show_sales_purchase(company_key, role, mode="Sales"):
    st.header(f"{'🛒' if mode=='Sales' else '📥'} {mode} Module")
    with st.form(f"{mode}_form"):
        party = st.text_input("Party Name", key=f"{mode}_party")
        item = st.text_input("Product", key=f"{mode}_prod")
        amount = st.number_input("Amount (GHS)", min_value=0.0, key=f"{mode}_amt")
        tax_rate = st.slider("VAT (%)", 0, 15, 5, key=f"{mode}_tax")
        total = amount + (amount * tax_rate / 100)
        st.write(f"**Total Invoice Value: GHS {total:.2f}**")
        if st.form_submit_button("Post Invoice"):
            if role in ["Master Admin", "Sub-Admin"]:
                conn = get_connection(); conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?,?,?,?,?,?)", (company_key, str(datetime.now().date()), mode, party, total, f"{mode} of {item}")); conn.commit(); st.success("Recorded!")
            else: st.error("Admin Only.")

# --- 6. VOUCHER SYSTEM ---
def show_vouchers(company_key, role):
    st.header("📝 Advanced Voucher System")
    v_type = st.selectbox("Voucher Type", ["Receipt", "Payment", "Contra", "Journal"], key="v_type_sel")
    with st.form("voucher_form"):
        v_date = st.date_input("Date")
        ledger = st.text_input("Account")
        amount = st.number_input("Amount (GHS)", min_value=0.0)
        narration = st.text_area("Narration")
        if st.form_submit_button("Post Voucher"):
            if role in ["Master Admin", "Sub-Admin"]:
                conn = get_connection(); conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?,?,?,?,?,?)", (company_key, str(v_date), v_type, ledger, amount, narration)); conn.commit(); st.success("Voucher posted!")

# --- 7. BANKING & OTHER MODULES ---
def show_banking(company_key, role):
    st.header("🏦 Banking & Cash")
    st.metric("Estimated Bank Balance", "GHS 12,850")

def show_aging_reports(company_key, mode="Receivable"):
    st.header(f"⏳ Accounts {mode}")
    st.info("Summarizing aging buckets...")

def show_tax_reports(company_key):
    st.header("🧾 Tax Management")
    st.write("Current Liability: **GHS 1,450.00**")

def show_reports(company_key):
    st.header("📊 Financial Intelligence")
    conn = get_connection()
    st.dataframe(pd.read_sql(f"SELECT * FROM vouchers WHERE company_key='{company_key}'", conn))

def show_fixed_assets(company_key, role):
    st.header("🏛️ Fixed Assets")
    st.text_input("Asset Name", key="asset_name")

def show_payroll(company_key, role):
    st.header("🇬🇭 Payroll (SSNIT & PAYE)")
    sal = st.number_input("Basic Salary", key="pay_basic")
    if st.button("Calculate", key="pay_calc"):
        net = sal * 0.85 # Logic placeholder
        st.success(f"Net: GHS {net:.2f}")

def show_audit_trail(company_key):
    st.header("🕵️ Audit Trail")
    conn = get_connection()
    st.table(pd.read_sql(f"SELECT timestamp, action FROM audit_logs WHERE company_key='{company_key}'", conn))

def show_company_setup(company_key, company_name, role):
    st.header(f"⚙️ Setup: {company_name}")
    if role == "Master Admin":
        sk = st.text_input("Set Sub-Admin Key", type="password", key="setup_sk")
        ra = st.text_input("Set Recovery Answer", type="password", key="setup_ra")
        if st.button("Update Security", key="setup_btn"):
            conn = get_connection(); conn.execute("UPDATE companies SET sub_admin_key=?, recovery_answer=? WHERE key=?", (sk, ra, company_key)); conn.commit(); st.success("Updated!")