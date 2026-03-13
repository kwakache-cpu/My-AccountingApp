import streamlit as st
import pandas as pd
from database import get_connection
from datetime import datetime

# --- POS & PRINTING ---
def show_pos(company_key, company_name, role):
    st.header("🛒 POS - Point of Sale")
    if 'cart' not in st.session_state: st.session_state.cart = []
    col1, col2 = st.columns([2, 1])
    with col1:
        item = st.text_input("Item", key="p_item")
        qty = st.number_input("Qty", min_value=1, key="p_qty")
        prc = st.number_input("Price (GHS)", min_value=0.0, key="p_prc")
        if st.button("Add to Cart", key="p_add"):
            st.session_state.cart.append({"Item": item, "Qty": qty, "Price": prc, "Total": qty*prc})
    with col2:
        if st.session_state.cart:
            df = pd.DataFrame(st.session_state.cart)
            st.table(df)
            total = df['Total'].sum()
            st.write(f"### Total: GHS {total:.2f}")
            if st.button("Print Receipt", key="p_print"):
                st.markdown(f"<div style='border:2px solid black; padding:10px; background:white; color:black;'><h3>{company_name}</h3><hr>{df.to_html(index=False)}<hr><h4>TOTAL: GHS {total:.2f}</h4></div>", unsafe_allow_html=True)
                st.session_state.cart = []

# --- INVENTORY ---
def show_inventory(company_key, role):
    st.header("📦 Inventory")
    with st.expander("Add Stock"):
        it = st.text_input("Item Name", key="i_it")
        q = st.number_input("Qty", key="i_q")
        if st.button("Save", key="i_btn") and role != "Staff":
            conn = get_connection()
            conn.execute("INSERT INTO inventory (company_key, item_name, qty) VALUES (?,?,?)", (company_key, it, q))
            conn.commit()
    conn = get_connection()
    st.dataframe(pd.read_sql(f"SELECT item_name, qty FROM inventory WHERE company_key='{company_key}'", conn))

# --- VOUCHERS ---
def show_vouchers(company_key, role):
    st.header("📝 Voucher Entry")
    with st.form("v_form"):
        vt = st.selectbox("Type", ["Payment", "Receipt", "Journal"])
        ld = st.text_input("Ledger")
        am = st.number_input("Amount")
        if st.form_submit_button("Post"):
            if role != "Staff":
                conn = get_connection()
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount) VALUES (?,?,?,?,?)", (company_key, str(datetime.now().date()), vt, ld, am))
                conn.commit()
                st.success("Posted!")

# --- PAYROLL (Ghana Logic) ---
def show_payroll(company_key, role):
    st.header("🇬🇭 Payroll")
    sal = st.number_input("Basic Salary", key="pay_sal")
    if st.button("Calculate", key="pay_calc"):
        net = sal * 0.85 # Simplified Ghana Tax
        st.success(f"Net: GHS {net:.2f}")

# --- SETUP ---
def show_company_setup(company_key, company_name, role):
    st.header(f"⚙️ Setup: {company_name}")
    with st.form("setup_keys"):
        sk = st.text_input("Sub-Admin Key", type="password")
        stk = st.text_input("Staff Key", type="password")
        ans = st.text_input("Recovery Answer", type="password")
        if st.form_submit_button("Save Settings"):
            conn = get_connection()
            conn.execute("UPDATE companies SET sub_admin_key=?, staff_key=?, recovery_answer=? WHERE key=?", (sk, stk, ans, company_key))
            conn.commit()
            st.success("Updated!")

# Restoring remaining module UIs
def show_chart_of_accounts(k, r): st.header("🗂️ Chart of Accounts"); st.text_input("New Ledger", key="coa_in")
def show_sales_purchase(k, r, m): st.header(f"{m} Module"); st.number_input("Invoice Amount", key=f"{m}_in")
def show_banking(k, r): st.header("🏦 Banking"); st.metric("Balance", "GHS 0.00")
def show_aging_reports(k, m): st.header(f"⏳ {m} Aging"); st.info("Loading balances...")
def show_tax_reports(k): st.header("🧾 Taxation"); st.write("VAT Summary Active")
def show_fixed_assets(k, r): st.header("🏛️ Fixed Assets"); st.text_input("Asset Name", key="fa_in")
def show_reports(k): st.header("📊 Reports"); st.button("Print Statement", key="rep_pr")
def show_audit_trail(k): st.header("🕵️ Audit Trail"); conn = get_connection(); st.table(pd.read_sql(f"SELECT * FROM audit_logs WHERE company_key='{k}'", conn))