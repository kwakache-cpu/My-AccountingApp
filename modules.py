import streamlit as st
import pandas as pd
from database import get_connection

def show_company_setup(company_key, company_name, role):
    st.header(f"⚙️ Setup: {company_name}")
    
    # Only Master Admins can modify keys and recovery settings
    if role == "Master Admin":
        with st.container():
            sub_key = st.text_input("Set Sub-Admin Key (e.g., for Bookkeepers)", type="password")
            recovery = st.text_input("Set Recovery Answer (Secret Word)", type="password")
            
            if st.button("Save Settings"):
                conn = get_connection()
                conn.execute("UPDATE companies SET sub_admin_key=?, recovery_answer=? WHERE key=?", 
                             (sub_key, recovery, company_key))
                conn.commit()
                st.success("Security settings updated successfully!")
    else:
        st.warning("Access Restricted: Only the Master Admin can modify company security settings.")

def show_vouchers(company_key, role):
    st.header("📝 Voucher Entry")
    
    # Form for entering new vouchers
    with st.form("voucher_form"):
        col1, col2 = st.columns(2)
        v_date = col1.date_input("Date")
        v_type = col1.selectbox("Type", ["Receipt", "Payment", "Journal"])
        ledger = col2.text_input("Ledger Name")
        amount = col2.number_input("Amount (GHS)", min_value=0.0)
        narration = st.text_area("Narration")
        
        submit = st.form_submit_button("Post Voucher")
        
        if submit:
            if role in ["Master Admin", "Sub-Admin"]:
                conn = get_connection()
                conn.execute("INSERT INTO vouchers (company_key, date, v_type, ledger, amount, narration) VALUES (?,?,?,?,?,?)",
                             (company_key, str(v_date), v_type, ledger, amount, narration))
                # Log the action for the Audit Trail
                conn.execute("INSERT INTO audit_logs (company_key, action) VALUES (?,?)", 
                             (company_key, f"Posted {v_type} for {ledger}: GHS {amount}"))
                conn.commit()
                st.success("Voucher posted and logged!")
            else:
                st.error("Permission Denied: Staff accounts are read-only.")

    # Show recent entries
    st.subheader("Recent Vouchers")
    conn = get_connection()
    df = pd.read_sql(f"SELECT date, v_type, ledger, amount, narration FROM vouchers WHERE company_key='{company_key}' ORDER BY id DESC", conn)
    st.table(df)

def show_payroll(company_key, role):
    st.header("🇬🇭 Payroll (SSNIT & PAYE)")
    
    with st.form("payroll_form"):
        emp_name = st.text_input("Employee Name")
        basic_salary = st.number_input("Basic Salary (GHS)", min_value=0.0)
        
        if st.form_submit_button("Calculate & Process"):
            # Calculations based on Ghana tax laws
            ssnit_t1 = basic_salary * 0.135
            # Simplified PAYE for this example
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

    # Display Payroll History
    conn = get_connection()
    df_pay = pd.read_sql(f"SELECT emp_name, basic_salary, ssnit_tier1, paye, net_salary FROM payroll WHERE company_key='{company_key}'", conn)
    st.dataframe(df_pay)

def show_audit_trail(company_key):
    st.header("🕵️ Audit Trail (Security Log)")
    conn = get_connection()
    df_audit = pd.read_sql(f"SELECT timestamp, action FROM audit_logs WHERE company_key='{company_key}' ORDER BY timestamp DESC", conn)
    st.table(df_audit)

def show_reports(company_key):
    st.header("📊 Financial Reports")
    conn = get_connection()
    
    # Financial Summary logic
    df = pd.read_sql(f"SELECT v_type, SUM(amount) as total FROM vouchers WHERE company_key='{company_key}' GROUP BY v_type", conn)
    if not df.empty:
        st.bar_chart(df.set_index('v_type'))
    else:
        st.info("No data available for reports yet.")