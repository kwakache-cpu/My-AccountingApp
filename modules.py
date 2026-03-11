import streamlit as st
import pandas as pd

def show_company_setup(company_name, can_edit):
    st.header("🏗️ 1. Company Setup")
    st.text_input("Company Name", value=company_name, disabled=not can_edit)
    st.text_input("Financial Year", value="2026-2027", disabled=not can_edit)
    st.text_input("Base Currency", value="Ghana Cedi (GHS)", disabled=True)
    if can_edit: st.button("Save Settings")

def show_inventory(can_edit):
    st.header("📦 4. Inventory Management")
    t1, t2, t3 = st.tabs(["Stock Items", "Warehouses", "Pricing"])
    with t1:
        st.text_input("Item Name (e.g. Cement Bag)")
        st.selectbox("Unit", ["Pieces", "Bags", "Kg", "Liters"])
        if can_edit: st.button("Add to Stock")

def show_vouchers(can_edit):
    st.header("✍️ 6. Voucher Entry")
    if not can_edit:
        st.error("Staff Account: View-only access. You cannot post transactions.")
        return
    v_type = st.selectbox("Type", ["Sales", "Purchase", "Payment", "Receipt", "Contra"])
    amt = st.number_input("Amount (GHS)", min_value=0.0)
    st.text_area("Narration / Description")
    if st.button("Post to Ledger"):
        st.success(f"{v_type} recorded successfully.")

def show_reports():
    st.header("📊 15. Financial Reports")
    st.button("📄 Generate Profit & Loss")
    st.button("📄 View Balance Sheet")