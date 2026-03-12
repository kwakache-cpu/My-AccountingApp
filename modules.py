import streamlit as st
import pandas as pd
from database import get_connection

def show_company_setup(comp_key, company_name, user_role):
    # HARD LOCK: Even if the URL is guessed, the code won't run for non-admins
    if user_role != "Master Admin":
        st.error("Access Denied: Master Admin only.")
        return

    st.header(f"🏗️ Company Settings: {company_name}")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔑 Access Management")
        sub_key = st.text_input("Sub-Admin (Data Entry) Key", type="password", help="Full data entry access.")
        if st.button("Save Sub-Admin Key"):
            conn = get_connection()
            conn.execute("UPDATE companies SET sub_admin_key=? WHERE key=?", (sub_key, comp_key))
            conn.commit()
            st.success("Sub-Admin key updated!")
        
        st.info(f"Staff (Read-Only) Key: {comp_key}-staff")
    
    with col2:
        st.subheader("🛡️ Password Recovery")
        ans = st.text_input("Secret Recovery Answer", type="password")
        if st.button("Save Recovery"):
            conn = get_connection()
            conn.execute("UPDATE companies SET recovery_answer=? WHERE key=?", (ans, comp_key))
            conn.commit()
            st.success("Recovery answer saved!")

def show_vouchers(comp_key, user_role):
    st.header("✍️ Voucher Entry")
    # Sub-Admins can enter data, Staff cannot
    if user_role in ["Master Admin", "Sub-Admin"]:
        conn = get_connection()
        ledgers = pd.read_sql("SELECT name FROM ledgers WHERE company_key=?", conn, params=(comp_key,))['name'].tolist()
        with st.form("v_form"):
            v_type = st.selectbox("Type", ["Sales", "Purchase", "Payment", "Receipt"])
            ledger = st.selectbox("Ledger", ledgers if ledgers else ["No Ledgers"])
            amount = st.number_input("Amount (GHS)", min_value=0.0)
            note = st.text_area("Narration")
            if st.form_submit_button("Post Transaction"):
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?, ?, ?, ?, ?, ?)",
                             (comp_key, "2026-03-12", v_type, ledger, amount, note))
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?, ?)", (comp_key, f"{user_role} posted {v_type}"))
                conn.commit()
                st.success("Transaction Recorded!")
    else:
        st.warning("🔒 Staff Access: View-Only.")
    
    conn = get_connection()
    df = pd.read_sql("SELECT date, v_type, ledger, amount FROM vouchers WHERE company_key=?", conn, params=(comp_key,))
    st.table(df)

def show_payroll(comp_key, user_role):
    st.header("🇬🇭 Payroll")
    if user_role in ["Master Admin", "Sub-Admin"]:
        with st.form("pay_form"):
            name = st.text_input("Employee Name")
            basic = st.number_input("Basic Salary", min_value=0.0)
            if st.form_submit_button("Process"):
                ssnit = round(basic * 0.055, 2)
                taxable = basic - ssnit
                paye = round((taxable - 402) * 0.05, 2) if taxable > 402 else 0
                net = round(basic - ssnit - paye, 2)
                conn = get_connection()
                conn.execute("INSERT INTO payroll (company_key, emp_name, basic_salary, ssnit_tier1, paye, net_salary) VALUES (?,?,?,?,?,?)",
                             (comp_key, name, basic, ssnit, paye, net))
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?, ?)", (comp_key, f"{user_role} ran payroll for {name}"))
                conn.commit()
                st.success("Payroll Processed!")
    else:
        st.warning("🔒 Staff Access: View-Only.")
    
    conn = get_connection()
    df = pd.read_sql("SELECT emp_name, net_salary FROM payroll WHERE company_key=?", conn, params=(comp_key,))
    st.dataframe(df)

def show_audit_trail(comp_key):
    st.header("🕵️ Audit Trail")
    conn = get_connection()
    df = pd.read_sql("SELECT timestamp, action FROM audit_logs WHERE company_key=? ORDER BY timestamp DESC", conn, params=(comp_key,))
    st.dataframe(df, use_container_width=True)

def show_reports(comp_key):
    st.header("📊 Reports")
    conn = get_connection()
    df = pd.read_sql('SELECT v.amount, l.category FROM vouchers v JOIN ledgers l ON v.ledger = l.name WHERE v.company_key = ?', conn, params=(comp_key,))
    if not df.empty:
        inc = df[df['category'] == 'Income']['amount'].sum()
        exp = df[df['category'] == 'Expense']['amount'].sum()
        st.metric("Net Profit", f"GHS {inc - exp:,.2f}")