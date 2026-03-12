import streamlit as st
import pandas as pd
from database import get_connection

# --- 1. COMPANY SETUP ---
def show_company_setup(company_name, can_edit):
    st.header(f"🏗️ Company Setup: {company_name}")
    st.info("Statutory details for Ghana Revenue Authority (GRA) compliance.")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("TIN Number", placeholder="P00XXXXXXXX", disabled=not can_edit)
    with col2:
        st.selectbox("Financial Year", ["2025-2026", "2026-2027"], index=1)

# --- 2. CHART OF ACCOUNTS ---
def show_chart_of_accounts(comp_key, can_edit):
    st.header("📚 Chart of Accounts")
    if can_edit:
        with st.expander("➕ Add New Ledger Account"):
            name = st.text_input("Ledger Name (e.g., Petty Cash)")
            cat = st.selectbox("Category", ["Asset", "Liability", "Equity", "Income", "Expense"])
            if st.button("Save Ledger"):
                conn = get_connection()
                conn.execute("INSERT INTO ledgers (company_key, name, category) VALUES (?, ?, ?)", (comp_key, name, cat))
                conn.commit()
                st.success(f"Ledger '{name}' created!")

    conn = get_connection()
    df = pd.read_sql("SELECT name, category FROM ledgers WHERE company_key=?", conn, params=(comp_key,))
    st.dataframe(df, use_container_width=True)

# --- 6. VOUCHER ENTRY ---
def show_vouchers(comp_key, can_edit):
    st.header("✍️ Voucher Entry")
    if not can_edit:
        st.error("Staff: View-only access.")
        return

    v_type = st.selectbox("Voucher Type", ["Sales", "Purchase", "Payment", "Receipt", "Contra", "Journal", "Credit Note", "Debit Note"])
    
    conn = get_connection()
    ledger_list = pd.read_sql("SELECT name FROM ledgers WHERE company_key=?", conn, params=(comp_key,))['name'].tolist()

    with st.form("voucher_form"):
        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("Date")
            ledger = st.selectbox("Account/Ledger", ledger_list if ledger_list else ["No Ledgers Found - Add some in Module 2"])
        with col2:
            amount = st.number_input("Amount (GHS)", min_value=0.0)
            note = st.text_area("Narration")
        
        if st.form_submit_button("Post Transaction"):
            conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?, ?, ?, ?, ?, ?)",
                         (comp_key, str(date), v_type, ledger, amount, note))
            # Log the action for security
            conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?, ?)", (comp_key, f"Posted {v_type} voucher for GHS {amount}"))
            conn.commit()
            st.success("Voucher Posted Successfully!")