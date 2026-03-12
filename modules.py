import streamlit as st
import pandas as pd
from database import get_connection

# --- 1. COMPANY SETUP ---
def show_company_setup(company_name, can_edit):
    st.header(f"🏗️ 1. Company Setup: {company_name}")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("TIN Number", placeholder="P00XXXXXXXX", disabled=not can_edit)
    with col2:
        st.selectbox("Financial Year", ["2026-2027"], index=0)

# --- 2. CHART OF ACCOUNTS ---
def show_chart_of_accounts(comp_key, can_edit):
    st.header("📚 2. Chart of Accounts")
    if can_edit:
        with st.expander("➕ Add New Ledger"):
            name = st.text_input("Ledger Name")
            cat = st.selectbox("Category", ["Income", "Expense", "Asset", "Liability", "Equity"])
            if st.button("Save Ledger"):
                conn = get_connection()
                conn.execute("INSERT INTO ledgers (company_key, name, category) VALUES (?, ?, ?)", (comp_key, name, cat))
                conn.commit()
                st.success(f"Added {name}")

    conn = get_connection()
    df = pd.read_sql("SELECT name, category FROM ledgers WHERE company_key=?", conn, params=(comp_key,))
    st.table(df)

# --- 6. VOUCHER ENTRY ---
def show_vouchers(comp_key, can_edit):
    st.header("✍️ 6. Voucher Entry")
    if not can_edit:
        st.error("Staff: Read-only.")
        return

    conn = get_connection()
    ledger_list = pd.read_sql("SELECT name FROM ledgers WHERE company_key=?", conn, params=(comp_key,))['name'].tolist()

    with st.form("v_form"):
        v_type = st.selectbox("Type", ["Sales", "Purchase", "Payment", "Receipt"])
        ledger = st.selectbox("Ledger", ledger_list if ledger_list else ["Setup Ledgers First"])
        amount = st.number_input("Amount (GHS)", min_value=0.0)
        note = st.text_area("Narration")
        if st.form_submit_button("Post"):
            conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?, ?, ?, ?, ?, ?)",
                         (comp_key, "2026-03-12", v_type, ledger, amount, note))
            conn.commit()
            st.success("Posted!")

# --- 15. FINANCIAL REPORTS ---
def show_reports(comp_key):
    st.header("📊 15. Financial Reports")
    conn = get_connection()
    
    # Simple Profit & Loss Logic
    st.subheader("Profit & Loss Statement")
    
    # Get all vouchers joined with their ledger categories
    query = '''
        SELECT v.amount, l.category 
        FROM vouchers v 
        JOIN ledgers l ON v.ledger = l.name 
        WHERE v.company_key = ?
    '''
    df = pd.read_sql(query, conn, params=(comp_key,))
    
    if not df.empty:
        income = df[df['category'] == 'Income']['amount'].sum()
        expenses = df[df['category'] == 'Expense']['amount'].sum()
        profit = income - expenses
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Income", f"GHS {income:,.2f}")
        c2.metric("Total Expenses", f"GHS {expenses:,.2f}")
        c3.metric("Net Profit", f"GHS {profit:,.2f}")
    else:
        st.warning("No data found. Post some vouchers to see reports.")