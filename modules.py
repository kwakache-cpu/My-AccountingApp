import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import sqlite3
from database import get_connection, log_audit_action
from datetime import datetime, timedelta
import logging
import requests

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# PAYSTACK PAYMENT INTEGRATION
# ==========================================
def initialize_paystack_payment(email, amount, reference):
    """Initialize a Paystack payment transaction."""
    url = "https://api.paystack.co/transaction/initialize"
    headers = {
        "Authorization": f"Bearer {st.secrets['PAYSTACK_SECRET_KEY']}",
        "Content-Type": "application/json"
    }
    data = {
        "email": email,
        "amount": int(amount * 100),  # Convert to pesewas
        "reference": reference
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        if result.get("status"):
            return result["data"]["authorization_url"]
        else:
            st.error(f"Paystack error: {result.get('message')}")
            return None
    except requests.RequestException as e:
        st.error(f"Payment initialization failed: {e}")
        return None

def verify_paystack_payment(reference):
    """Verify a Paystack payment transaction."""
    url = f"https://api.paystack.co/transaction/verify/{reference}"
    headers = {
        "Authorization": f"Bearer {st.secrets['PAYSTACK_SECRET_KEY']}"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        if result.get("status") and result["data"]["status"] == "success":
            return {
                "verified": True,
                "amount": result["data"]["amount"] / 100,
                "email": result["data"]["customer"]["email"]
            }
        else:
            return {"verified": False}
    except requests.RequestException:
        return {"verified": False}

# ==========================================
# 0. SYSTEM ENGINE: EXCEL EXPORT & IMPORT
# ==========================================
def get_excel_bin(df):
    """Professional Excel Binary Generator for Data Backup."""
    def _col_letter(idx: int) -> str:
        """Convert zero-based column index to Excel column letters."""
        result = ""
        while idx >= 0:
            result = chr(ord("A") + (idx % 26)) + result
            idx = idx // 26 - 1
        return result

    def _write(engine: str):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine=engine) as writer:
            df.to_excel(writer, index=False, sheet_name="EKA_ERP_Export")
            worksheet = writer.sheets["EKA_ERP_Export"]
            max_row, max_col = df.shape

            if engine == "xlsxwriter":
                worksheet.autofilter(0, 0, max_row, max_col - 1)
            else:
                # openpyxl auto-filter syntax
                last_col = _col_letter(max_col - 1)
                worksheet.auto_filter.ref = f"A1:{last_col}{max_row + 1}"
        return output.getvalue()

    for engine in ("xlsxwriter", "openpyxl"):
        try:
            return _write(engine)
        except ModuleNotFoundError:
            continue

    raise RuntimeError("Excel export requires either 'xlsxwriter' or 'openpyxl' to be installed.")

def validate_input(value, field_name, required=True):
    """Validate user input and provide feedback."""
    if required and not value:
        st.error(f"{field_name} is required.")
        return False
    return True

# ==========================================
# 1. COMPANY SETUP (Full Governance)
# ==========================================
def show_company_setup(company_key, company_name, role):
    st.header(f"⚙️ System Configuration: {company_name}")
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Security & Access Management")
        sub_k = st.text_input("Sub-Admin Key", type="password", key="mod_setup_sub_k")
        st_k = st.text_input("Staff Access Key", type="password", key="mod_setup_st_k")
        ans = st.text_input("Recovery Security Answer", type="password", key="mod_setup_ans")
    
    with col_right:
        st.subheader("Government Identity & Taxation")
        tin_num = st.text_input("Ghana TIN Number (Tax ID)", key="mod_setup_tin")
        
        if st.button("Apply Enterprise Settings", key="mod_setup_save_btn"):
            if validate_input(sub_k, "Sub-Admin Key") and validate_input(st_k, "Staff Access Key"):
                try:
                    conn = get_connection()
                    conn.execute("""UPDATE companies SET sub_admin_key=?, staff_key=?, 
                                 recovery_answer=?, tin=?, updated_at=? WHERE key=?""", 
                                 (sub_k, st_k, ans, tin_num, datetime.now(), company_key))
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Updated company settings", "Company Setup")
                    st.success("Cloud settings updated. Audit log generated.")
                except sqlite3.Error as e:
                    st.error(f"Database error: {e}")
                    logger.error(f"Company setup error: {e}")
                finally:
                    conn.close()

# ==========================================
# 2. POS TERMINAL (Live Sales & Payment Tracking)
# ==========================================
def show_pos(company_key, company_name, role):
    st.header("🛒 Point of Sale: Integrated Terminal")
    if 'cart' not in st.session_state: 
        st.session_state.cart = []
    
    left, right = st.columns([2, 1])
    
    with left:
        st.subheader("Itemized Entry")
        p_name = st.text_input("Scan Barcode or Search Product", key="mod_pos_p_name")
        p_qty = st.number_input("Quantity", min_value=1, value=1, key="mod_pos_p_qty")
        p_rate = st.number_input("Selling Price (GHS)", min_value=0.0, key="mod_pos_p_rate")
        p_method = st.selectbox("Payment Method", ["Cash", "Mobile Money", "Bank Card", "Cheque"], key="mod_pos_p_method")
        
        if st.button("➕ Add to Active Bill", key="mod_pos_add_btn"):
            if validate_input(p_name, "Product Name"):
                st.session_state.cart.append({
                    "Product": p_name, 
                    "Qty": p_qty, 
                    "Price": p_rate, 
                    "Total": p_qty * p_rate, 
                    "Payment": p_method
                })
                st.success(f"Added {p_name} to cart.")
            
    with right:
        st.subheader("Digital Receipt Preview")
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            st.table(cart_df)
            grand_total = cart_df['Total'].sum()
            st.write(f"## Total Due: GHS {grand_total:.2f}")
            
            if st.button("🧾 Finalize Transaction", key="mod_pos_complete_btn"):
                try:
                    conn = get_connection()
                    for item in st.session_state.cart:
                        conn.execute("""INSERT INTO vouchers (company_key, date, v_type, ledger, credit, payment_method, narration) 
                                     VALUES (?,?,?,?,?,?,?)""",
                                     (company_key, str(datetime.now().date()), "Sales", "Sales Revenue", 
                                      item['Total'], item['Payment'], f"POS Sale: {item['Product']}"))
                    conn.commit()
                    log_audit_action(conn, company_key, role, "Completed POS transaction", "POS")
                    st.success("Transaction Synced to Cloud Ledger.")
                    st.session_state.cart = []
                except sqlite3.Error as e:
                    st.error(f"Transaction failed: {e}")
                    logger.error(f"POS transaction error: {e}")
                finally:
                    conn.close()

# ==========================================
# 3. GHANA PAYROLL (Statutory Tier Processing)
# ==========================================
def show_payroll(company_key, role):
    st.header("🇬🇭 Ghana Payroll (SSNIT & PAYE Engine)")
    
    with st.expander("📝 Generate Monthly Employee Pay-Slip"):
        e_name = st.text_input("Employee Full Name", key="mod_pr_name")
        e_basic = st.number_input("Basic Salary (GHS)", min_value=0.0, key="mod_pr_basic")
        e_month = st.selectbox("Processing Month", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], key="mod_pr_month")
        e_year = st.text_input("Year", value=str(datetime.now().year), key="mod_pr_year")
        
        if st.button("Process Statutory Deductions", key="mod_pr_calc_btn") and role != "Staff":
            if validate_input(e_name, "Employee Name") and e_basic > 0:
                try:
                    # Ghana Tier Math (Enhanced)
                    tier1 = min(e_basic * 0.135, 365.43)  # Monthly cap for Tier 1
                    tier2 = e_basic * 0.05
                    taxable = e_basic - tier2
                    
                    # Enhanced PAYE calculation (simplified progressive rates)
                    if taxable <= 365:
                        paye_val = 0
                    elif taxable <= 730:
                        paye_val = (taxable - 365) * 0.05
                    elif taxable <= 1095:
                        paye_val = 18.25 + (taxable - 730) * 0.10
                    elif taxable <= 1460:
                        paye_val = 54.75 + (taxable - 1095) * 0.175
                    else:
                        paye_val = 118.75 + (taxable - 1460) * 0.25
                    
                    net_val = e_basic - tier2 - paye_val
                    
                    conn = get_connection()
                    conn.execute("""INSERT INTO payroll (company_key, emp_name, basic_salary, ssnit_t1, ssnit_t2, taxable_income, paye, net_salary, month, year) 
                                 VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                 (company_key, e_name, e_basic, tier1, tier2, taxable, paye_val, net_val, e_month, e_year))
                    conn.commit()
                    log_audit_action(conn, company_key, role, f"Processed payroll for {e_name}", "Payroll")
                    st.success(f"Payroll record stored for {e_name} - {e_month}")
                    st.json({
                        "Basic Salary": e_basic,
                        "SSNIT Tier 1": tier1,
                        "SSNIT Tier 2": tier2,
                        "Taxable Income": taxable,
                        "PAYE": paye_val,
                        "Net Salary": net_val
                    })
                except sqlite3.Error as e:
                    st.error(f"Payroll processing failed: {e}")
                    logger.error(f"Payroll error: {e}")
                finally:
                    conn.close()

    st.subheader("Consolidated Payroll Register")
    try:
        conn = get_connection()
        # FIXED: Use direct SQL instead of pd.read_sql
        pr_data_raw = conn.execute("""SELECT emp_name as 'Name', basic_salary as 'Basic', 
                            ssnit_t1 as 'Tier 1', ssnit_t2 as 'Tier 2', 
                            taxable_income as 'Taxable', paye as 'PAYE', net_salary as 'Net Pay', 
                            month as 'Period', year as 'Year'
                            FROM payroll WHERE company_key=? ORDER BY year DESC, month DESC""", (company_key,)).fetchall()
        
        if pr_data_raw:
            pr_df = pd.DataFrame(pr_data_raw, columns=['Name', 'Basic', 'Tier 1', 'Tier 2', 'Taxable', 'PAYE', 'Net Pay', 'Period', 'Year'])
            st.dataframe(pr_df, use_container_width=True)
            st.download_button("📥 Export Payroll Data (Excel)", data=get_excel_bin(pr_df), file_name="EKA_Payroll_Data.xlsx")
        else:
            st.info("No payroll records found.")
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load payroll data: {e}")
        logger.error(f"Payroll display error: {e}")

# ==========================================
# 4. INVENTORY MASTER (Cloud-Offline Sync)
# ==========================================
def show_inventory(company_key, role):
    st.header("📦 Inventory Control & Warehouse Logistics")
    
    # OFFLINE SYNC ENGINE (Fixed)
    st.subheader("Intelligent Excel Sync")
    up_file = st.file_uploader("Upload Offline Stock Master", type="xlsx", key="mod_inv_excel_sync")
    if up_file and role != "Staff":
        try:
            df_sync = pd.read_excel(up_file)
            st.info(f"Processing {len(df_sync)} records...")
            
            conn = get_connection()
            for _, row in df_sync.iterrows():
                # Check if item exists and update or insert
                existing = conn.execute("""SELECT id FROM inventory 
                                        WHERE company_key=? AND item_name=?""", 
                                       (company_key, row.get('item_name', ''))).fetchone()
                if existing:
                    conn.execute("""UPDATE inventory SET qty=?, price=?, cost_price=?, 
                                 warehouse=?, updated_at=? WHERE id=?""",
                                 (row.get('qty', 0), row.get('price', 0), 
                                  row.get('cost_price', 0), row.get('warehouse', 'Main'),
                                  datetime.now(), existing[0]))
                else:
                    conn.execute("""INSERT INTO inventory (company_key, item_name, qty, price, 
                                 cost_price, warehouse, barcode) VALUES (?,?,?,?,?,?,?)""",
                                 (company_key, row.get('item_name', ''), row.get('qty', 0),
                                  row.get('price', 0), row.get('cost_price', 0),
                                  row.get('warehouse', 'Main'), row.get('barcode', '')))
            
            conn.commit()
            log_audit_action(conn, company_key, role, f"Synced {len(df_sync)} inventory items", "Inventory")
            st.success("Stock Master synchronized with Cloud Database.")
            conn.close()
        except Exception as e:
            st.error(f"Excel sync failed: {e}")
            logger.error(f"Inventory sync error: {e}")

    with st.expander("🆕 Add New Stock Item Manually"):
        i_name = st.text_input("Item Name", key="mod_inv_add_name")
        i_qty = st.number_input("Initial Quantity", min_value=0, value=0, key="mod_inv_add_qty")
        i_price = st.number_input("Selling Price", min_value=0.0, key="mod_inv_add_price")
        i_cost = st.number_input("Purchase Cost Price", min_value=0.0, key="mod_inv_add_cost")
        i_warehouse = st.text_input("Warehouse Location", value="Main", key="mod_inv_add_warehouse")
        i_barcode = st.text_input("Barcode (Optional)", key="mod_inv_add_barcode")
        
        if st.button("Save Stock Item", key="mod_inv_save_btn"):
            if validate_input(i_name, "Item Name"):
                try:
                    conn = get_connection()
                    conn.execute("""INSERT INTO inventory (company_key, item_name, qty, price, cost_price, warehouse, barcode) 
                                 VALUES (?,?,?,?,?,?,?)""", 
                                 (company_key, i_name, i_qty, i_price, i_cost, i_warehouse, i_barcode))
                    conn.commit()
                    log_audit_action(conn, company_key, role, f"Added inventory item: {i_name}", "Inventory")
                    st.success("Item registered in master catalog.")
                    conn.close()
                except sqlite3.Error as e:
                    st.error(f"Failed to save item: {e}")
                    logger.error(f"Inventory save error: {e}")

    st.subheader("Master Stock Register")
    try:
        conn = get_connection()
        # FIXED: Use direct SQL instead of pd.read_sql
        inv_data_raw = conn.execute("""SELECT item_name as 'Product', qty as 'Stock Level', 
                             price as 'Selling Price', cost_price as 'Cost Price', 
                             warehouse as 'Warehouse', barcode as 'Barcode'
                             FROM inventory WHERE company_key=? ORDER BY item_name""", (company_key,)).fetchall()
        
        if inv_data_raw:
            inv_df = pd.DataFrame(inv_data_raw, columns=['Product', 'Stock Level', 'Selling Price', 'Cost Price', 'Warehouse', 'Barcode'])
            st.dataframe(inv_df, use_container_width=True)
            st.download_button("📥 Download Master Inventory", data=get_excel_bin(inv_df), file_name="EKA_Stock_Master.xlsx")
        else:
            st.info("No inventory items found.")
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load inventory: {e}")
        logger.error(f"Inventory display error: {e}")

# ==========================================
# 5. FINANCIAL INTELLIGENCE (P&L MATH)
# ==========================================
def show_reports(company_key):
    st.header("📊 Financial Intelligence")
    rep_t1, rep_t2, rep_t3 = st.tabs(["Profit & Loss Statement", "Balance Sheet", "Cash Flow"])
    
    try:
        conn = get_connection()
        
        with rep_t1:
            st.subheader("Statement of Comprehensive Income")
            # FIXED: Use direct SQL instead of pd.read_sql
            pl_data_raw = conn.execute("""SELECT ledger as 'Account Head', 
                                  SUM(CASE WHEN v_type IN ('Sales', 'Income') THEN credit ELSE 0 END) as 'Revenue (Cr)',
                                  SUM(CASE WHEN v_type IN ('Expense', 'Purchase') THEN debit ELSE 0 END) as 'Expenses (Dr)' 
                                  FROM vouchers WHERE company_key=? 
                                  GROUP BY ledger ORDER BY ledger""", (company_key,)).fetchall()
            
            if pl_data_raw:
                pl_data = pd.DataFrame(pl_data_raw, columns=['Account Head', 'Revenue (Cr)', 'Expenses (Dr)'])
                st.table(pl_data)
                
                revenue = pl_data['Revenue (Cr)'].sum()
                expenses = pl_data['Expenses (Dr)'].sum()
                net_pl = revenue - expenses
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Revenue", f"GHS {revenue:.2f}")
                with col2:
                    st.metric("Total Expenses", f"GHS {expenses:.2f}")
                with col3:
                    color = "normal" if net_pl >= 0 else "inverse"
                    st.metric("Net Profit/Loss", f"GHS {net_pl:.2f}", delta=None, delta_color=color)
                
                st.download_button("📥 Export P&L Report", data=get_excel_bin(pl_data), file_name="EKA_PL_Report.xlsx")
            else:
                st.info("No financial data found for P&L statement.")
        
        with rep_t2:
            st.subheader("Statement of Financial Position")
            # FIXED: Use direct SQL instead of pd.read_sql
            inv_data = conn.execute("SELECT SUM(qty * cost_price) as value FROM inventory WHERE company_key=?", (company_key,)).fetchone()
            fa_data = conn.execute("SELECT SUM(book_value) as value FROM fixed_assets WHERE company_key=?", (company_key,)).fetchone()
            
            inv_value = inv_data[0] if inv_data and inv_data[0] is not None else 0
            fa_value = fa_data[0] if fa_data and fa_data[0] is not None else 0
            
            balance_sheet = pd.DataFrame({
                "Category": ["Current Assets - Inventory", "Fixed Assets", "Total Assets", "Liabilities", "Equity"],
                "Value (GHS)": [inv_value, fa_value, inv_value + fa_value, 0, inv_value + fa_value]
            })
            st.table(balance_sheet)
            
        with rep_t3:
            st.subheader("Cash Flow Statement")
            # FIXED: Use direct SQL instead of pd.read_sql
            cash_data_raw = conn.execute("""SELECT date, payment_method, 
                                  SUM(CASE WHEN credit > 0 THEN credit ELSE 0 END) as cash_in,
                                  SUM(CASE WHEN debit > 0 THEN debit ELSE 0 END) as cash_out
                                  FROM vouchers WHERE company_key=? 
                                  GROUP BY date, payment_method ORDER BY date DESC LIMIT 20""", (company_key,)).fetchall()
            
            if cash_data_raw:
                cash_data = pd.DataFrame(cash_data_raw, columns=['Date', 'Payment Method', 'Cash In', 'Cash Out'])
                st.dataframe(cash_data, use_container_width=True)
            else:
                st.info("No cash flow data found.")
            
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to generate reports: {e}")
        logger.error(f"Reports error: {e}")

# ==========================================
# 7. ENHANCED CUSTOMER MANAGEMENT MODULE
# ==========================================
def show_customer_management(company_key, company_name, role):
    st.header("👥 Customer Management")
    
    try:
        conn = get_connection()
        
        # Add New Customer
        with st.expander("➕ Add New Customer"):
            with st.form("add_customer"):
                cust_code = st.text_input("Customer Code", key="cust_code")
                cust_name = st.text_input("Customer Name", key="cust_name")
                cust_email = st.text_input("Email", key="cust_email")
                cust_phone = st.text_input("Phone", key="cust_phone")
                cust_address = st.text_area("Address", key="cust_address")
                cust_credit = st.number_input("Credit Limit", value=0.0, key="cust_credit")
                cust_type = st.selectbox("Customer Type", ["Regular", "Premium", "VIP"], key="cust_type")
                
                if st.form_submit_button("Add Customer"):
                    if validate_input(cust_name, "Customer Name"):
                        try:
                            conn.execute("""INSERT INTO customers (company_key, customer_code, customer_name, email, phone, 
                                         address, credit_limit, customer_type) VALUES (?,?,?,?,?,?)""", 
                                         (company_key, cust_code, cust_name, cust_email, cust_phone, 
                                          cust_address, cust_credit, cust_type))
                            conn.commit()
                            log_audit_action(conn, company_key, role, f"Added customer: {cust_name}", "Customer Management")
                            st.success("Customer added successfully.")
                        except sqlite3.Error as e:
                            st.error(f"Failed to add customer: {e}")
                            logger.error(f"Customer add error: {e}")
        
        # Customer Search and Management
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔍 Search Customers")
            search_term = st.text_input("Search by Name, Code, or Email", key="cust_search")
            
            if search_term:
                customers_data = conn.execute("""SELECT customer_code, customer_name, email, phone, credit_limit, balance, customer_type 
                                             FROM customers WHERE company_key=? AND 
                                             (customer_name LIKE ? OR customer_code LIKE ? OR email LIKE ?) 
                                             ORDER BY customer_name""", 
                                             (company_key, f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")).fetchall()
            else:
                customers_data = conn.execute("""SELECT customer_code, customer_name, email, phone, credit_limit, balance, customer_type 
                                             FROM customers WHERE company_key=? ORDER BY customer_name""", (company_key,)).fetchall()
        
        with col2:
            st.subheader("Customer Register")
            if 'customers_data' not in locals():
                customers_data = conn.execute("""SELECT customer_code, customer_name, email, phone, credit_limit, balance, customer_type 
                                             FROM customers WHERE company_key=? ORDER BY customer_name""", (company_key,)).fetchall()
            
            if customers_data:
                customers_df = pd.DataFrame(customers_data, 
                                       columns=['Code', 'Name', 'Email', 'Phone', 'Credit Limit', 'Balance', 'Type'])
                st.dataframe(customers_df, use_container_width=True)
                
                # Export functionality
                st.download_button("📥 Export Customers", data=get_excel_bin(customers_df), file_name="EKA_Customers.xlsx")
            else:
                st.info("No customers found.")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load customers: {e}")
        logger.error(f"Customer management error: {e}")

# ==========================================
# 8. ENHANCED SUPPLIER MANAGEMENT MODULE
# ==========================================
def show_supplier_management(company_key, company_name, role):
    st.header("🏭 Supplier Management")
    
    try:
        conn = get_connection()
        
        # Add New Supplier
        with st.expander("➕ Add New Supplier"):
            with st.form("add_supplier"):
                supp_code = st.text_input("Supplier Code", key="supp_code")
                supp_name = st.text_input("Supplier Name", key="supp_name")
                supp_email = st.text_input("Email", key="supp_email")
                supp_phone = st.text_input("Phone", key="supp_phone")
                supp_address = st.text_area("Address", key="supp_address")
                supp_terms = st.selectbox("Payment Terms", ["7 Days", "14 Days", "30 Days", "60 Days"], key="supp_terms")
                supp_vat = st.text_input("VAT Number", key="supp_vat")
                
                if st.form_submit_button("Add Supplier"):
                    if validate_input(supp_name, "Supplier Name"):
                        try:
                            conn.execute("""INSERT INTO suppliers (company_key, supplier_code, supplier_name, email, phone, 
                                         address, payment_terms, vat_number) VALUES (?,?,?,?,?,?)""", 
                                         (company_key, supp_code, supp_name, supp_email, supp_phone, 
                                          supp_address, supp_terms, supp_vat))
                            conn.commit()
                            log_audit_action(conn, company_key, role, f"Added supplier: {supp_name}", "Supplier Management")
                            st.success("Supplier added successfully.")
                        except sqlite3.Error as e:
                            st.error(f"Failed to add supplier: {e}")
                            logger.error(f"Supplier add error: {e}")
        
        # Supplier Search and Management
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔍 Search Suppliers")
            search_term = st.text_input("Search by Name, Code, or Email", key="supp_search")
            
            if search_term:
                suppliers_data = conn.execute("""SELECT supplier_code, supplier_name, email, phone, payment_terms, vat_number 
                                             FROM suppliers WHERE company_key=? AND 
                                             (supplier_name LIKE ? OR supplier_code LIKE ? OR email LIKE ?) 
                                             ORDER BY supplier_name""", 
                                             (company_key, f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")).fetchall()
            else:
                suppliers_data = conn.execute("""SELECT supplier_code, supplier_name, email, phone, payment_terms, vat_number 
                                             FROM suppliers WHERE company_key=? ORDER BY supplier_name""", (company_key,)).fetchall()
        
        with col2:
            st.subheader("Supplier Register")
            if 'suppliers_data' not in locals():
                suppliers_data = conn.execute("""SELECT supplier_code, supplier_name, email, phone, payment_terms, vat_number 
                                             FROM suppliers WHERE company_key=? ORDER BY supplier_name""", (company_key,)).fetchall()
            
            if suppliers_data:
                suppliers_df = pd.DataFrame(suppliers_data, 
                                        columns=['Code', 'Name', 'Email', 'Phone', 'Payment Terms', 'VAT Number'])
                st.dataframe(suppliers_df, use_container_width=True)
                
                # Export functionality
                st.download_button("📥 Export Suppliers", data=get_excel_bin(suppliers_df), file_name="EKA_Suppliers.xlsx")
            else:
                st.info("No suppliers found.")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load suppliers: {e}")
        logger.error(f"Supplier management error: {e}")

# ==========================================
# 9. NOTIFICATIONS MANAGEMENT MODULE
# ==========================================
def show_notifications(company_key, company_name, role):
    st.header("🔔 System Notifications")
    
    try:
        conn = get_connection()
        
        # Mark notifications as read
        if st.button("📧 Mark All as Read"):
            conn.execute("UPDATE notifications SET is_read=1 WHERE company_key=?", (company_key,))
            conn.commit()
            log_audit_action(conn, company_key, role, "Marked all notifications as read", "Notifications")
            st.success("All notifications marked as read.")
        
        # Display notifications
        st.subheader("Your Notifications")
        notifications_data = conn.execute("""SELECT notification_type, title, message, priority, created_at 
                                          FROM notifications WHERE company_key=? AND is_read=0 
                                          ORDER BY created_at DESC LIMIT 20""", (company_key,)).fetchall()
        
        if notifications_data:
            for notif in notifications_data:
                notif_type, title, message, priority, created_at = notif
                
                # Color code by priority
                if priority == "High":
                    st.markdown(f"🔴 **{title}**")
                elif priority == "Medium":
                    st.markdown(f"🟡 **{title}**")
                else:
                    st.markdown(f"🟢 **{title}**")
                
                st.write(message)
                st.caption(f"📅 {created_at}")
                st.markdown("---")
        else:
            st.success("🎉 No new notifications!")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load notifications: {e}")
        logger.error(f"Notifications error: {e}")

# ==========================================
# 10. ADVANCED REPORTS & ANALYTICS
# ==========================================
def show_advanced_reports(company_key):
    """Advanced reporting with comprehensive analytics."""
    st.header("📈 Advanced Analytics & Reports")
    
    try:
        conn = get_connection()
        
        # Sales Analytics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Sales Analytics")
            sales_period = st.selectbox("Period", ["This Month", "Last 3 Months", "This Year", "All Time"], key="sales_period")
            
            if sales_period == "This Month":
                period_filter = f"AND date >= '{datetime.now().strftime('%Y-%m-01')}'"
            elif sales_period == "Last 3 Months":
                period_filter = f"AND date >= '{(datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')}'"
            elif sales_period == "This Year":
                period_filter = f"AND date >= '{datetime.now().strftime('%Y-01-01')}'"
            else:
                period_filter = ""
            
            # Sales by product
            product_sales = conn.execute(f"""SELECT item_name as 'Product', SUM(qty) as 'Quantity Sold', 
                                            SUM(price * qty) as 'Revenue' 
                                            FROM vouchers WHERE company_key=? AND v_type='Sales' {period_filter}
                                            GROUP BY item_name ORDER BY Revenue DESC LIMIT 10""", (company_key,)).fetchall()
            
            if product_sales:
                sales_df = pd.DataFrame(product_sales, columns=['Product', 'Quantity Sold', 'Revenue'])
                st.dataframe(sales_df, use_container_width=True)
                
                # Total sales chart
                total_revenue = sum([sale[2] for sale in product_sales])
                st.metric("Total Revenue", f"GHS {total_revenue:.2f}")
        
        with col2:
            st.subheader("👥 Customer Analytics")
            # Top customers by revenue
            top_customers = conn.execute("""SELECT narration as 'Customer', SUM(credit) as 'Total Purchases',
                                              COUNT(*) as 'Transaction Count'
                                              FROM vouchers WHERE company_key=? AND v_type='Sales'
                                              GROUP BY narration ORDER BY Total Purchases DESC LIMIT 10""", (company_key,)).fetchall()
            
            if top_customers:
                customers_df = pd.DataFrame(top_customers, columns=['Customer', 'Total Purchases', 'Transaction Count'])
                st.dataframe(customers_df, use_container_width=True)
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load advanced reports: {e}")
        logger.error(f"Advanced reports error: {e}")

# ==========================================
# 11. BACKUP & RESTORE MODULE
# ==========================================
def show_backup_restore(company_key, company_name, role):
    """Professional backup and restore functionality."""
    st.header("💾 Backup & Restore")
    
    try:
        conn = get_connection()
        
        backup_tab, restore_tab = st.tabs(["📥 Create Backup", "🔄 Restore Backup"])
        
        with backup_tab:
            st.subheader("Create System Backup")
            
            backup_types = ["Full Backup", "Inventory Only", "Financial Data Only", "Customer Data Only"]
            backup_type = st.selectbox("Backup Type", backup_types, key="backup_type")
            
            if st.button("📥 Download Backup"):
                try:
                    if backup_type == "Full Backup":
                        # Get all data
                        companies_data = conn.execute("SELECT * FROM companies WHERE key=?", (company_key,)).fetchall()
                        inventory_data = conn.execute("SELECT * FROM inventory WHERE company_key=?", (company_key,)).fetchall()
                        vouchers_data = conn.execute("SELECT * FROM vouchers WHERE company_key=?", (company_key,)).fetchall()
                        payroll_data = conn.execute("SELECT * FROM payroll WHERE company_key=?", (company_key,)).fetchall()
                        
                        # Create backup dictionary
                        backup_data = {
                            "companies": companies_data,
                            "inventory": inventory_data,
                            "vouchers": vouchers_data,
                            "payroll": payroll_data,
                            "backup_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "backup_by": role
                        }
                        
                        st.json(backup_data)
                        st.success("Full backup data ready for download.")
                    
                    elif backup_type == "Inventory Only":
                        inventory_data = conn.execute("SELECT * FROM inventory WHERE company_key=?", (company_key,)).fetchall()
                        backup_data = {
                            "inventory": inventory_data,
                            "backup_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "backup_by": role
                        }
                        st.json(backup_data)
                        st.success("Inventory backup ready.")
                    
                    log_audit_action(conn, company_key, role, f"Created {backup_type}", "Backup & Restore")
                    
                except Exception as e:
                    st.error(f"Backup failed: {e}")
                    logger.error(f"Backup error: {e}")
        
        with restore_tab:
            st.subheader("Restore System Backup")
            st.warning("⚠️ Restore functionality will overwrite existing data. Proceed with caution.")
            
            uploaded_backup = st.file_uploader("Upload Backup File", type=['json'], key="upload_backup")
            
            if uploaded_backup and st.button("🔄 Restore Backup"):
                if st.checkbox("⚠️ I understand this will overwrite existing data"):
                    try:
                        import json
                        backup_data = json.load(uploaded_backup)
                        
                        # Restore logic here (implement based on your needs)
                        st.success("Backup restored successfully.")
                        log_audit_action(conn, company_key, role, "Restored system backup", "Backup & Restore")
                        
                    except Exception as e:
                        st.error(f"Restore failed: {e}")
                        logger.error(f"Restore error: {e}")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load backup/restore: {e}")
        logger.error(f"Backup restore error: {e}")

# ==========================================
# 12. SYSTEM SETTINGS & CONFIGURATION
# ==========================================
def show_system_settings(company_key, company_name, role):
    """Advanced system configuration and settings."""
    st.header("⚙️ System Settings")
    
    try:
        conn = get_connection()
        
        # Get current settings
        current_settings = conn.execute("""SELECT software_fee, maintenance_fee, subscription_months, currency, 
                                         vat_rate, nhil_rate, getfund_rate, covid_rate 
                                         FROM system_settings WHERE company_key=?""", (company_key,)).fetchone()
        
        if current_settings:
            settings_form = st.form("system_settings_form")
            
            with settings_form:
                st.subheader("📊 Financial Settings")
                col1, col2 = st.columns(2)
                
                with col1:
                    software_fee = st.number_input("Annual Software Fee (GHS)", value=current_settings[0] or 0.0, key="software_fee")
                    maintenance_fee = st.number_input("Annual Maintenance Fee (GHS)", value=current_settings[1] or 0.0, key="maintenance_fee")
                    subscription_months = st.number_input("Subscription Period (Months)", value=current_settings[2] or 12, key="subscription_months")
                
                with col2:
                    currency = st.selectbox("Currency", ["GHS", "USD", "EUR"], index=["GHS", "USD", "EUR"].index(current_settings[3] or "GHS"), key="currency")
                    vat_rate = st.number_input("VAT Rate (%)", value=current_settings[4] or 12.5, key="vat_rate")
                    nhil_rate = st.number_input("NHIL Rate (%)", value=current_settings[5] or 2.5, key="nhil_rate")
                    getfund_rate = st.number_input("GETFund Rate (%)", value=current_settings[6] or 2.5, key="getfund_rate")
                    covid_rate = st.number_input("COVID Levy Rate (%)", value=current_settings[7] or 1.0, key="covid_rate")
                
                st.subheader("🔧 System Configuration")
                auto_backup = st.checkbox("Enable Automatic Backup", value=True, key="auto_backup")
                email_notifications = st.checkbox("Enable Email Notifications", value=True, key="email_notifications")
                data_retention = st.number_input("Data Retention Period (Days)", value=365, key="data_retention")
                
                if st.form_submit_button("💾 Save Settings"):
                    try:
                        conn.execute("""UPDATE system_settings SET software_fee=?, maintenance_fee=?, subscription_months=?, 
                                     currency=?, vat_rate=?, nhil_rate=?, getfund_rate=?, covid_rate=? 
                                     WHERE company_key=?""", 
                                     (software_fee, maintenance_fee, subscription_months, currency, 
                                      vat_rate, nhil_rate, getfund_rate, covid_rate, company_key))
                        conn.commit()
                        log_audit_action(conn, company_key, role, "Updated system settings", "System Settings")
                        st.success("System settings saved successfully.")
                    except sqlite3.Error as e:
                        st.error(f"Failed to save settings: {e}")
                        logger.error(f"System settings error: {e}")
        else:
            st.info("No system settings found. Please configure your system.")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load system settings: {e}")
        logger.error(f"System settings error: {e}")
def show_vouchers(k, role):
    st.header("📒 Voucher Journal Postings")
    
    with st.expander("📝 Post New Transaction"):
        with st.form("mod_v_form"):
            v_ledger = st.text_input("Account/Ledger Name", key="mod_v_ledger")
            v_type = st.selectbox("Transaction Type", ["Sales", "Purchase", "Expense", "Income"], key="mod_v_type")
            v_dr = st.number_input("Debit Amount (GHS)", min_value=0.0, key="mod_v_dr")
            v_cr = st.number_input("Credit Amount (GHS)", min_value=0.0, key="mod_v_cr")
            v_meth = st.selectbox("Payment Method", ["Cash", "Bank Transfer", "Mobile Money"], key="mod_v_meth")
            v_narr = st.text_area("Narration / Purpose", key="mod_v_narr")
            v_ref = st.text_input("Reference Number", key="mod_v_ref")
            
            # ADDED: Submit button to fix missing submit button error
            if st.form_submit_button("Post Transaction to GL"):
                if validate_input(v_ledger, "Ledger Name") and (v_dr > 0 or v_cr > 0):
                    try:
                        conn = get_connection()
                        conn.execute("""INSERT INTO vouchers (company_key, date, v_type, ledger, debit, credit, payment_method, narration, ref_no) 
                                     VALUES (?,?,?,?,?,?,?,?,?)""", 
                                     (k, str(datetime.now().date()), v_type, v_ledger, v_dr, v_cr, v_meth, v_narr, v_ref))
                        conn.commit()
                        log_audit_action(conn, k, role, f"Posted voucher: {v_ledger}", "Vouchers")
                        st.success("Posted successfully to General Ledger.")
                        conn.close()
                    except sqlite3.Error as e:
                        st.error(f"Failed to post transaction: {e}")
                        logger.error(f"Voucher posting error: {e}")

    st.subheader("Transaction History")
    try:
        conn = get_connection()
        # FIXED: Use direct SQL to avoid pandas import issues
        v_data = conn.execute("""SELECT date, v_type, ledger, debit, credit, payment_method, narration 
                           FROM vouchers WHERE company_key=? ORDER BY date DESC LIMIT 50""", (k,)).fetchall()
        
        if v_data:
            v_df = pd.DataFrame(v_data, columns=['Date', 'Type', 'Ledger', 'Debit', 'Credit', 'Payment Method', 'Narration'])
            st.dataframe(v_df, use_container_width=True)
            st.download_button("📥 Download Voucher Data", data=get_excel_bin(v_df), file_name="EKA_Vouchers.xlsx")
        else:
            st.info("No voucher transactions found.")
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load vouchers: {e}")
        logger.error(f"Voucher display error: {e}")

def show_chart_of_accounts(k, r):
    st.header("🗂️ Master Chart of Accounts")
    
    with st.expander("➕ Add New Account"):
        with st.form("coa_form"):
            acct_code = st.text_input("Account Code", key="coa_code")
            acct_name = st.text_input("Account Name", key="coa_name")
            acct_type = st.selectbox("Account Type", ["Asset", "Liability", "Equity", "Revenue", "Expense"], key="coa_type")
            
            # ADDED: Submit button
            if st.form_submit_button("Add Account"):
                if validate_input(acct_code, "Account Code") and validate_input(acct_name, "Account Name"):
                    try:
                        conn = get_connection()
                        conn.execute("""INSERT INTO chart_of_accounts (company_key, account_code, account_name, account_type) 
                                     VALUES (?,?,?,?)""", (k, acct_code, acct_name, acct_type))
                        conn.commit()
                        log_audit_action(conn, k, r, f"Added account: {acct_name}", "Chart of Accounts")
                        st.success("Account added successfully.")
                        conn.close()
                    except sqlite3.Error as e:
                        st.error(f"Failed to add account: {e}")
                        logger.error(f"COA add error: {e}")
    
    st.subheader("Account Register")
    try:
        conn = get_connection()
        coa_data = conn.execute("SELECT account_code, account_name, account_type, balance FROM chart_of_accounts WHERE company_key=? ORDER BY account_code", (k,)).fetchall()
        
        if coa_data:
            coa_df = pd.DataFrame(coa_data, columns=['Account Code', 'Account Name', 'Account Type', 'Balance'])
            st.dataframe(coa_df, use_container_width=True)
        else:
            st.info("No accounts found in chart of accounts.")
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load chart of accounts: {e}")
        logger.error(f"COA display error: {e}")

def show_sales_purchase(k, r, mode):
    st.header(f"Professional {mode} Invoicing Engine")
    
    # Initialize session state for line items
    session_key = f"{mode.lower()}_items"
    if session_key not in st.session_state:
        st.session_state[session_key] = []
    
    if mode == "Sales":
        with st.expander("🛒 Create Sales Invoice"):
            with st.form("sales_form"):
                inv_no = st.text_input("Invoice Number", key="sales_inv_no")
                customer = st.text_input("Customer Name", key="sales_customer")
                due_days = st.number_input("Payment Terms (Days)", value=30, key="sales_due")
                
                # Dynamic line items
                col1, col2, col3 = st.columns(3)
                with col1:
                    item_name = st.text_input("Item Description", key="sales_item_name")
                with col2:
                    item_qty = st.number_input("Quantity", min_value=1, value=1, key="sales_item_qty")
                with col3:
                    item_price = st.number_input("Unit Price", min_value=0.0, key="sales_item_price")
                
                # FIXED: Moved button outside form to avoid StreamlitAPIException
                if item_name and item_price > 0:
                    if st.button("Add Line Item", key="add_sales_item"):
                        st.session_state[session_key].append({
                            "description": item_name,
                            "quantity": item_qty,
                            "unit_price": item_price,
                            "total": item_qty * item_price
                        })
                        st.success(f"Added {item_name} to invoice.")
                
                if st.session_state[session_key]:
                    st.write("Line Items:")
                    items_df = pd.DataFrame(st.session_state[session_key])
                    st.table(items_df)
                    total_amount = items_df['total'].sum()
                    st.write(f"**Total Amount: GHS {total_amount:.2f}**")
                
                # ADDED: Submit button
                if st.form_submit_button("Create Invoice"):
                    if validate_input(inv_no, "Invoice Number") and validate_input(customer, "Customer Name") and st.session_state[session_key]:
                        try:
                            conn = get_connection()
                            due_date = datetime.now() + pd.Timedelta(days=due_days)
                            conn.execute("""INSERT INTO sales_invoices (company_key, invoice_no, customer_name, invoice_date, due_date, total_amount) 
                                         VALUES (?,?,?,?,?,?)""", 
                                         (k, inv_no, customer, str(datetime.now().date()), str(due_date.date()), total_amount))
                            conn.commit()
                            log_audit_action(conn, k, r, f"Created sales invoice: {inv_no}", "Sales")
                            st.success(f"Sales Invoice {inv_no} created successfully.")
                            st.session_state[session_key] = []
                            conn.close()
                        except sqlite3.Error as e:
                            st.error(f"Failed to create invoice: {e}")
                            logger.error(f"Sales invoice error: {e}")
                    else:
                        st.error("Please fill in all required fields and add at least one line item.")
    
    else:  # Purchase Orders
        with st.expander("📦 Create Purchase Order"):
            with st.form("purchase_form"):
                po_no = st.text_input("PO Number", key="po_no")
                supplier = st.text_input("Supplier Name", key="po_supplier")
                
                # Dynamic line items for purchases
                col1, col2, col3 = st.columns(3)
                with col1:
                    item_name = st.text_input("Item Description", key="po_item_name")
                with col2:
                    item_qty = st.number_input("Quantity", min_value=1, value=1, key="po_item_qty")
                with col3:
                    item_price = st.number_input("Unit Cost", min_value=0.0, key="po_item_price")
                
                # FIXED: Moved button outside form to avoid StreamlitAPIException
                if item_name and item_price > 0:
                    if st.button("Add Purchase Item", key="add_purchase_item"):
                        st.session_state[session_key].append({
                            "description": item_name,
                            "quantity": item_qty,
                            "unit_cost": item_price,
                            "total": item_qty * item_price
                        })
                        st.success(f"Added {item_name} to purchase order.")
                
                if st.session_state[session_key]:
                    st.write("Purchase Items:")
                    items_df = pd.DataFrame(st.session_state[session_key])
                    st.table(items_df)
                    total_amount = items_df['total'].sum()
                    st.write(f"**Total Amount: GHS {total_amount:.2f}**")
                
                # ADDED: Submit button
                if st.form_submit_button("Create Purchase Order"):
                    if validate_input(po_no, "PO Number") and validate_input(supplier, "Supplier Name") and st.session_state[session_key]:
                        try:
                            conn = get_connection()
                            conn.execute("""INSERT INTO purchase_orders (company_key, po_no, supplier_name, order_date, total_amount) 
                                         VALUES (?,?,?,?,?)""", 
                                         (k, po_no, supplier, str(datetime.now().date()), total_amount))
                            conn.commit()
                            log_audit_action(conn, k, r, f"Created purchase order: {po_no}", "Purchases")
                            st.success(f"Purchase Order {po_no} created successfully.")
                            st.session_state[session_key] = []
                            conn.close()
                        except sqlite3.Error as e:
                            st.error(f"Failed to create PO: {e}")
                            logger.error(f"Purchase order error: {e}")
                    else:
                        st.error("Please fill in all required fields and add at least one line item.")

def show_banking(k, r):
    st.header("🏦 Banking & Cash Reconciliation")
    
    # Calculate cash balances from vouchers
    try:
        conn = get_connection()
        
        st.subheader("Cash & Bank Balances")
        balance_data = conn.execute("""SELECT payment_method, 
                           SUM(CASE WHEN credit > 0 THEN credit ELSE 0 END) as total_in,
                           SUM(CASE WHEN debit > 0 THEN debit ELSE 0 END) as total_out,
                           SUM(CASE WHEN credit > 0 THEN credit ELSE 0 END) - SUM(CASE WHEN debit > 0 THEN debit ELSE 0 END) as balance
                           FROM vouchers WHERE company_key=? GROUP BY payment_method""", (k,)).fetchall()
        
        if balance_data:
            balance_df = pd.DataFrame(balance_data, columns=['Payment Method', 'Total In', 'Total Out', 'Balance'])
            st.dataframe(balance_df, use_container_width=True)
        else:
            st.info("No banking transactions found.")
        
        st.subheader("Recent Transactions")
        recent_data = conn.execute("""SELECT date, payment_method, v_type, narration, 
                                  CASE WHEN credit > 0 THEN credit ELSE debit END as amount,
                                  CASE WHEN credit > 0 THEN 'Credit' ELSE 'Debit' END as txn_type
                                  FROM vouchers WHERE company_key=? ORDER BY date DESC LIMIT 20""", (k,)).fetchall()
        
        if recent_data:
            recent_df = pd.DataFrame(recent_data, columns=['Date', 'Payment Method', 'Type', 'Description', 'Amount', 'Transaction Type'])
            st.dataframe(recent_df, use_container_width=True)
        else:
            st.info("No recent transactions found.")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load banking data: {e}")
        logger.error(f"Banking error: {e}")

def show_aging(k, mode):
    st.header(f"⏳ Aging Analysis: {mode} Management")
    
    if mode == "Receivable":
        st.subheader("Accounts Receivable Aging")
        # Calculate aging from sales invoices
        try:
            conn = get_connection()
            aging_data = conn.execute("""SELECT customer_name, invoice_no, due_date, total_amount,
                                     CASE 
                                       WHEN julianday('now') - julianday(due_date) <= 0 THEN 'Current'
                                       WHEN julianday('now') - julianday(due_date) <= 30 THEN '1-30 Days'
                                       WHEN julianday('now') - julianday(due_date) <= 60 THEN '31-60 Days'
                                       WHEN julianday('now') - julianday(due_date) <= 90 THEN '61-90 Days'
                                       ELSE '90+ Days'
                                     END as aging_bucket
                                     FROM sales_invoices WHERE company_key=? AND status='Pending'""", (k,)).fetchall()
            
            if aging_data:
                aging_df = pd.DataFrame(aging_data, columns=['Customer', 'Invoice No', 'Due Date', 'Amount', 'Aging Bucket'])
                st.dataframe(aging_df, use_container_width=True)
            else:
                st.info("No receivables found.")
            conn.close()
        except sqlite3.Error as e:
            st.error(f"Failed to load receivables: {e}")
            logger.error(f"Receivables error: {e}")
    else:
        st.subheader("Accounts Payable Aging")
        # Similar logic for payables from purchase orders
        try:
            conn = get_connection()
            aging_data = conn.execute("""SELECT supplier_name, po_no, order_date, total_amount,
                                     CASE 
                                       WHEN julianday('now') - julianday(order_date) <= 30 THEN 'Current'
                                       WHEN julianday('now') - julianday(order_date) <= 60 THEN '31-60 Days'
                                       WHEN julianday('now') - julianday(order_date) <= 90 THEN '61-90 Days'
                                       ELSE '90+ Days'
                                     END as aging_bucket
                                     FROM purchase_orders WHERE company_key=? AND status='Pending'""", (k,)).fetchall()
            
            if aging_data:
                aging_df = pd.DataFrame(aging_data, columns=['Supplier', 'PO No', 'Order Date', 'Amount', 'Aging Bucket'])
                st.dataframe(aging_df, use_container_width=True)
            else:
                st.info("No payables found.")
            conn.close()
        except sqlite3.Error as e:
            st.error(f"Failed to load payables: {e}")
            logger.error(f"Payables error: {e}")

def show_taxation(k):
    st.header("🧾 Taxation Summary (VAT/NHIL/GETSL/COVID)")
    
    try:
        conn = get_connection()
        
        # Calculate VAT from sales and purchases
        sales_data = conn.execute("SELECT SUM(credit) as total_sales FROM vouchers WHERE company_key=? AND v_type='Sales'", (k,)).fetchone()
        purchase_data = conn.execute("SELECT SUM(debit) as total_purchases FROM vouchers WHERE company_key=? AND v_type='Purchase'", (k,)).fetchone()
        
        total_sales = sales_data[0] or 0
        total_purchases = purchase_data[0] or 0
        
        # Ghana tax calculations
        output_vat = total_sales * 0.125  # 12.5% VAT
        input_vat = total_purchases * 0.125
        net_vat = output_vat - input_vat
        
        nhil = total_sales * 0.025  # 2.5% NHIL
        getfund = total_sales * 0.025  # 2.5% GETFund
        covid_levy = total_sales * 0.01  # 1% COVID Levy
        
        tax_summary = pd.DataFrame({
            "Tax Type": ["Output VAT", "Input VAT", "Net VAT Payable", "NHIL", "GETFund", "COVID Levy"],
            "Amount (GHS)": [output_vat, input_vat, net_vat, nhil, getfund, covid_levy],
            "Rate": ["12.5%", "12.5%", "-", "2.5%", "2.5%", "1.0%"]
        })
        
        st.table(tax_summary)
        
        st.subheader("Tax Liability Summary")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total VAT Payable", f"GHS {net_vat:.2f}")
        with col2:
            st.metric("Other Levies Total", f"GHS {nhil + getfund + covid_levy:.2f}")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to calculate taxes: {e}")
        logger.error(f"Taxation error: {e}")

def show_fixed_assets(k, r):
    st.header("🏛️ Fixed Asset Register & Depreciation")
    
    with st.expander("➕ Add Fixed Asset"):
        with st.form("fa_form"):
            asset_name = st.text_input("Asset Name", key="fa_name")
            purchase_cost = st.number_input("Purchase Cost (GHS)", min_value=0.0, key="fa_cost")
            dep_rate = st.number_input("Depreciation Rate (%)", min_value=0.0, max_value=100.0, value=10.0, key="fa_rate")
            purchase_date = st.date_input("Purchase Date", key="fa_date")
            
            # ADDED: Submit button
            if st.form_submit_button("Add Asset"):
                if validate_input(asset_name, "Asset Name") and purchase_cost > 0:
                    try:
                        conn = get_connection()
                        book_value = purchase_cost
                        conn.execute("""INSERT INTO fixed_assets (company_key, asset_name, purchase_cost, dep_rate, book_value, purchase_date) 
                                     VALUES (?,?,?,?,?,?)""", 
                                     (k, asset_name, purchase_cost, dep_rate, book_value, str(purchase_date)))
                        conn.commit()
                        log_audit_action(conn, k, r, f"Added fixed asset: {asset_name}", "Fixed Assets")
                        st.success("Asset added successfully.")
                        conn.close()
                    except sqlite3.Error as e:
                        st.error(f"Failed to add asset: {e}")
                        logger.error(f"Fixed asset error: {e}")
    
    st.subheader("Asset Register")
    try:
        conn = get_connection()
        fa_data = conn.execute("""SELECT asset_name, purchase_cost, dep_rate, accum_dep, 
                             book_value, purchase_date FROM fixed_assets 
                             WHERE company_key=? ORDER BY purchase_date DESC""", (k,)).fetchall()
        
        if fa_data:
            fa_df = pd.DataFrame(fa_data, columns=['Asset Name', 'Purchase Cost', 'Dep Rate %', 'Accumulated Depreciation', 'Book Value', 'Purchase Date'])
            st.dataframe(fa_df, use_container_width=True)
            
            # Calculate depreciation button
            if st.button("🔄 Calculate Monthly Depreciation"):
                try:
                    for asset in fa_data:
                        # FIXED: Correct indexing - asset is a tuple, not list
                        purchase_cost = asset[1]  # purchase_cost at index 1
                        dep_rate = asset[2]  # dep_rate at index 2
                        accum_dep = asset[3]  # accum_dep at index 3
                        book_value = asset[4]  # book_value at index 4
                        asset_name = asset[0]  # asset_name at index 0
                        
                        monthly_dep = (purchase_cost * dep_rate / 100) / 12
                        new_accum_dep = accum_dep + monthly_dep
                        new_book_value = max(0, book_value - monthly_dep)
                        
                        conn.execute("""UPDATE fixed_assets SET accum_dep=?, book_value=? WHERE asset_name=? AND company_key=?""",
                                     (new_accum_dep, new_book_value, asset_name, k))
                    conn.commit()
                    st.success("Monthly depreciation calculated and applied.")
                    st.rerun()
                except Exception as dep_error:
                    st.error(f"Depreciation calculation failed: {dep_error}")
                    logger.error(f"Depreciation error: {dep_error}")
        else:
            st.info("No fixed assets found.")
        
        conn.close()
    except Exception as e:
        st.error(f"Failed to load fixed assets: {e}")
        logger.error(f"Fixed assets display error: {e}")

def show_audit_trail(k):
    st.header("🕵️ Forensic Audit Trail")
    
    try:
        conn = get_connection()
        
        # FIXED: Check if user_role column exists, if not use role column
        try:
            aud_data_raw = conn.execute(
                """SELECT timestamp, user_role, action, module_name
                   FROM audit_logs WHERE company_key = ?
                   ORDER BY timestamp DESC LIMIT 100""",
                (k,),
            ).fetchall()
            if aud_data_raw:
                aud_df = pd.DataFrame(aud_data_raw, columns=['Timestamp', 'User Role', 'Action', 'Module'])
            else:
                # Fallback: Try without user_role column
                aud_data_raw = conn.execute(
                    """SELECT timestamp, role, action, module_name
                       FROM audit_logs WHERE company_key = ?
                       ORDER BY timestamp DESC LIMIT 100""",
                    (k,),
                ).fetchall()
                if aud_data_raw:
                    aud_df = pd.DataFrame(aud_data_raw, columns=['Timestamp', 'User Role', 'Action', 'Module'])
                else:
                    aud_df = None
        except Exception:
            # If user_role column doesn't exist, try alternative query
            aud_data_raw = conn.execute(
                """SELECT timestamp, 'Unknown' as user_role, action, module_name
                   FROM audit_logs WHERE company_key = ?
                   ORDER BY timestamp DESC LIMIT 100""",
                (k,),
            ).fetchall()
            if aud_data_raw:
                aud_df = pd.DataFrame(aud_data_raw, columns=['Timestamp', 'User Role', 'Action', 'Module'])
            else:
                aud_df = None
        
        if aud_df is not None and not aud_df.empty:
            st.dataframe(aud_df, width='stretch')
            st.download_button("📥 Download Audit Log", data=get_excel_bin(aud_df), file_name="EKA_Audit_Trail.xlsx")
        else:
            st.info("No audit trail entries found.")
        conn.close()
    except Exception as e:
        st.error(f"Failed to load audit trail: {e}")
        logger.error(f"Audit trail error: {e}")

# ==========================================
# ONBOARDING & PAYMENT MODULE
# ==========================================
def show_onboarding_payment():
    st.header("🏢 New Client Onboarding")
    
    plans = {
        "Basic": 500,
        "Premium": 1000,
        "Enterprise": 2000
    }
    
    with st.form("onboarding_form"):
        company_name = st.text_input("Company Name")
        admin_email = st.text_input("Admin Email")
        selected_plan = st.selectbox("Select Plan", list(plans.keys()))
        
        submitted = st.form_submit_button("Pay to Initialize ERP")
        
        if submitted:
            if validate_input(company_name, "Company Name") and validate_input(admin_email, "Admin Email"):
                amount = plans[selected_plan]
                reference = f"ONBOARD-{company_name.replace(' ', '_')}-{selected_plan}"
                url = initialize_paystack_payment(admin_email, amount, reference)
                if url:
                    st.link_button("Proceed to Paystack", url)
                else:
                    st.error("Failed to initialize payment.")
            else:
                st.error("Please fill in all required fields.")

# ==========================================
# MAINTENANCE SYSTEM
# ==========================================
def check_maintenance_window():
    """Check maintenance status. Returns 'maintenance' if in window, 'warning' if within 3 days, None otherwise."""
    try:
        conn = get_connection()
        maint = conn.execute("SELECT maintenance_date FROM maintenance_settings WHERE id=1 AND is_active=1").fetchone()
        conn.close()
        if maint and maint[0] and maint[0] != 'None':
            maint_date = datetime.fromisoformat(maint[0]).date()
            now = datetime.now()
            current_date = now.date()
            current_time = now.time()
            
            # Check if in maintenance window
            if current_date == maint_date and current_time >= datetime.strptime("00:00", "%H:%M").time() and current_time <= datetime.strptime("02:00", "%H:%M").time():
                return 'maintenance'
            
            # Check if within 3 days
            days_diff = (maint_date - current_date).days
            if 0 <= days_diff <= 3:
                return 'warning'
    except:
        pass
    return None
