import streamlit as st
import pandas as pd
from database import get_connection

def show_company_setup(key, name, role):
    if role != "Master Admin":
        st.error("Unauthorized.")
        return
    st.header(f"⚙️ Setup: {name}")
    sk = st.text_input("Set Sub-Admin Key", type="password")
    ra = st.text_input("Set Recovery Answer", type="password")
    if st.button("Save Settings"):
        conn = get_connection()
        conn.execute("UPDATE companies SET sub_admin_key=?, recovery_answer=? WHERE key=?", (sk, ra, key))
        conn.commit()
        st.success("Updated!")

def show_vouchers(key, role):
    st.header("📖 Vouchers")
    if role in ["Master Admin", "Sub-Admin"]:
        with st.form("v_form"):
            amt = st.number_input("Amount")
            if st.form_submit_button("Post"):
                conn = get_connection()
                conn.execute("INSERT INTO vouchers (company_key, amount) VALUES (?,?)", (key, amt))
                conn.commit()
                st.success("Posted!")
    else:
        st.warning("Read-Only Mode.")
    # Show data for everyone
    conn = get_connection()
    st.write(pd.read_sql("SELECT amount FROM vouchers WHERE company_key=?", conn, params=(key,)))

# (Define empty functions for show_payroll, show_audit_trail, show_reports to avoid errors)
def show_payroll(k, r): st.info("Payroll Module")
def show_audit_trail(k): st.info("Audit Log")
def show_reports(k): st.info("Reports")