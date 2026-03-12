import streamlit as st
import pandas as pd
from database import get_connection

def show_company_setup(comp_key, company_name, user_role):
    st.header(f"🏗️ Company Settings: {company_name}")
    is_master = (user_role == "Master Admin")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🔑 Access Management")
        new_sub = st.text_input("Set Bookkeeper/Sub-Admin Key", type="password")
        if st.button("Update Keys") and is_master:
            conn = get_connection()
            conn.execute("UPDATE companies SET sub_admin_key=? WHERE key=?", (new_sub, comp_key))
            conn.commit()
            st.success("Sub-Admin Key updated!")
    
    with col2:
        st.subheader("🛡️ Password Recovery")
        ans = st.text_input("Set Recovery Answer (Your first car/pet?)", type="password")
        if st.button("Save Recovery") and is_master:
            conn = get_connection()
            conn.execute("UPDATE companies SET recovery_answer=? WHERE key=?", (ans, comp_key))
            conn.commit()
            st.success("Recovery answer saved!")

def show_vouchers(comp_key, user_role):
    st.header("✍️ 6. Voucher Entry")
    # SECURITY: Only Master Admin and Sub-Admin (Bookkeeper) can see the input form
    if user_role in ["Master Admin", "Sub-Admin"]:
        conn = get_connection()
        ledger_list = pd.read_sql("SELECT name FROM ledgers WHERE company_key=?", conn, params=(comp_key,))['name'].tolist()
        with st.form("v_form"):
            v_type = st.selectbox("Type", ["Sales", "Purchase", "Payment", "Receipt"])
            ledger = st.selectbox("Ledger", ledger_list if ledger_list else ["No Ledgers"])
            amount = st.number_input("Amount (GHS)", min_value=0.0)
            note = st.text_area("Narration")
            if st.form_submit_button("Post Transaction"):
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?, ?, ?, ?, ?, ?)",
                             (comp_key, "2026-03-12", v_type, ledger, amount, note))
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?, ?)", (comp_key, f"{user_role} posted {v_type}: {amount}"))
                conn.commit()
                st.success("Transaction Saved!")
    else:
        st.warning("🔒 Staff Access: Read-Only Mode. You cannot enter vouchers.")
    
    conn = get_connection()
    df = pd.read_sql("SELECT date, v_type, ledger, amount FROM vouchers WHERE company_key=?", conn, params=(comp_key,))
    st.table(df)

def show_payroll(comp_key, user_role):
    st.header("🇬🇭 12. Payroll (SSNIT & PAYE)")
    if user_role in ["Master Admin", "Sub-Admin"]:
        with st.form("payroll_calc"):
            name = st.text_input("Employee Name")
            basic = st.number_input("Basic Salary (GHS)", min_value=0.0)
            if st.form_submit_button("Process"):
                ssnit = round(basic * 0.055, 2)
                taxable = basic - ssnit
                paye = round((taxable - 402) * 0.05, 2) if taxable > 402 else 0
                net = round(basic - ssnit - paye, 2)
                conn = get_connection()
                conn.execute("INSERT INTO payroll (company_key, emp_name, basic_salary, ssnit_tier1, paye, net_salary) VALUES (?,?,?,?,?,?)",
                             (comp_key, name, basic, ssnit, paye, net))
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?, ?)", (comp_key, f"{user_role} processed payroll: {name}"))
                conn.commit()
                st.success(f"Processed!")
    else:
        st.warning("🔒 Staff Access: Read-Only Mode.")
    
    conn = get_connection()
    df = pd.read_sql("SELECT emp_name, net_salary FROM payroll WHERE company_key=?", conn, params=(comp_key,))
    st.dataframe(df)

def show_audit_trail(comp_key):
    st.header("🕵️ Audit Trail (Security Log)")
    conn = get_connection()
    df = pd.read_sql("SELECT timestamp, action FROM audit_logs WHERE company_key=? ORDER BY timestamp DESC", conn, params=(comp_key,))
    st.dataframe(df, use_container_width=True)

def show_reports(comp_key):
    st.header("📊 15. Financial Reports")
    conn = get_connection()
    df = pd.read_sql('SELECT v.amount, l.category FROM vouchers v JOIN ledgers l ON v.ledger = l.name WHERE v.company_key = ?', conn, params=(comp_key,))
    if not df.empty:
        inc = df[df['category'] == 'Income']['amount'].sum()
        exp = df[df['category'] == 'Expense']['amount'].sum()
        st.metric("Net Profit", f"GHS {inc - exp:,.2f}")