import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import io
import sqlite3
from database import get_connection, log_audit_action, init_db
from datetime import datetime
import logging
import requests

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

                    # Store receipt for printing
                    st.session_state.last_receipt = {
                        'company_name': company_name,
                        'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'items': list(st.session_state.cart),
                        'total': grand_total
                    }
                    st.session_state.show_receipt = True
                except sqlite3.Error as e:
                    st.error(f"Transaction failed: {e}")
                    logger.error(f"POS transaction error: {e}")
                finally:
                    conn.close()

            if st.session_state.cart and st.button("🖨️ Print Customer Receipt", key="mod_pos_print_btn"):
                st.session_state.show_receipt = True

            if st.session_state.get('show_receipt') and st.session_state.get('last_receipt'):
                receipt = st.session_state['last_receipt']
                receipt_html = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                        .receipt {{ max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; }}
                        .header {{ text-align: center; margin-bottom: 20px; }}
                        .header h1 {{ margin: 0; font-size: 24px; }}
                        .header p {{ margin: 4px 0; font-size: 14px; }}
                        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                        th {{ background: #f7f7f7; }}
                        .total {{ text-align: right; margin-top: 20px; font-size: 18px; font-weight: bold; }}
                        .footer {{ text-align: center; margin-top: 30px; font-size: 14px; color: #555; }}
                        @media print {{
                            body {{ margin: 0; }}
                            .receipt {{ border: none; }}
                        }}
                    </style>
                </head>
                <body>
                    <div class="receipt">
                        <div class="header">
                            <h1><b>{receipt['company_name']}</b></h1>
                            <h2>CASH SALE RECEIPT</h2>
                            <p>{receipt['datetime']}</p>
                        </div>
                        <table>
                            <thead>
                                <tr>
                                    <th>Item</th>
                                    <th>Qty</th>
                                    <th>Price (GHS)</th>
                                    <th>Total (GHS)</th>
                                </tr>
                            </thead>
                            <tbody>
                """

                for item in receipt['items']:
                    receipt_html += f"""
                        <tr>
                            <td>{item['Product']}</td>
                            <td>{item['Qty']}</td>
                            <td>{item['Price']:.2f}</td>
                            <td>{item['Total']:.2f}</td>
                        </tr>
                    """

                receipt_html += f"""
                            </tbody>
                        </table>
                        <div class="total">Grand Total: GHS {receipt['total']:.2f}</div>
                        <div class="footer">Thank you for your business!</div>
                    </div>
                    <script>
                        window.print();
                    </script>
                </body>
                </html>
                """

                components.html(receipt_html, height=800)
                st.session_state.show_receipt = False

# ==========================================
# 3. GHANA PAYROLL (Statutory Tier Processing)
# ==========================================
def show_payroll(company_key, role):
    st.header("🇬🇭 Ghana Payroll (SSNIT & PAYE Engine)")
    
    # Demo Mode Check
    if st.session_state.get('demo_mode', False):
        st.info("🚀 Demo Mode Active: Showing sample payroll data.")
        demo_pr_df = pd.DataFrame({
            'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
            'Basic': [2000.0, 2500.0, 1800.0],
            'Tier 1': [270.0, 270.0, 243.0],
            'Tier 2': [100.0, 125.0, 90.0],
            'Taxable': [1900.0, 2375.0, 1710.0],
            'PAYE': [95.0, 118.75, 85.5],
            'Net Pay': [1805.0, 2256.25, 1624.5],
            'Period': ['March', 'March', 'March'],
            'Year': ['2026', '2026', '2026']
        })
        st.dataframe(demo_pr_df, use_container_width=True)
        st.download_button("📥 Export Sample Payroll Data", data=get_excel_bin(demo_pr_df), file_name="Demo_Payroll_Data.xlsx")
        return
    
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
            edited_payroll = st.data_editor(pr_df, use_container_width=True, key='payroll_editor')

            if st.button("Save Changes", key="payroll_save_changes"):
                try:
                    changed_mask = (edited_payroll != pr_df).any(axis=1)
                    changed_rows = edited_payroll[changed_mask]

                    if not changed_rows.empty:
                        for _, row in changed_rows.iterrows():
                            conn.execute(
                                """UPDATE payroll SET basic_salary=?, ssnit_t1=?, ssnit_t2=?, taxable_income=?, paye=?, net_salary=?
                                     WHERE company_key=? AND emp_name=? AND month=? AND year=?""",
                                (row['Basic'], row['Tier 1'], row['Tier 2'], row['Taxable'], row['PAYE'], row['Net Pay'],
                                 company_key, row['Name'], row['Period'], row['Year'])
                            )
                        conn.commit()
                        st.success("Payroll changes saved.")
                        log_audit_action(conn, company_key, role, "Updated payroll records", "Payroll")
                    else:
                        st.info("No changes detected.")
                except sqlite3.Error as e:
                    st.error(f"Failed to save payroll changes: {e}")
                    logger.error(f"Payroll save error: {e}")

            st.download_button("📥 Export Payroll Data (Excel)", data=get_excel_bin(edited_payroll), file_name="EKA_Payroll_Data.xlsx")
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
    
    # Demo Mode Check
    if st.session_state.get('demo_mode', False):
        st.info("🚀 Demo Mode Active: Showing sample inventory data.")
        demo_inv_df = pd.DataFrame({
            'Product': ['Product A', 'Product B', 'Product C'],
            'Stock Level': [100, 50, 75],
            'Selling Price': [10.0, 20.0, 15.0],
            'Cost Price': [8.0, 15.0, 12.0],
            'Warehouse': ['Main', 'Main', 'Secondary'],
            'Barcode': ['123456', '234567', '345678']
        })
        st.dataframe(demo_inv_df, use_container_width=True)
        st.download_button("📥 Download Sample Inventory", data=get_excel_bin(demo_inv_df), file_name="Demo_Stock_Master.xlsx")
        return
    
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
        try:
            inv_df = pd.read_sql(f"""SELECT item_name as 'Product', qty as 'Stock Level', 
                                 price as 'Selling Price', cost_price as 'Cost Price', 
                                 warehouse as 'Warehouse', barcode as 'Barcode'
                                 FROM inventory WHERE company_key=? ORDER BY item_name""", conn, params=(company_key,))
        except Exception:
            st.warning("Database schema might be outdated. Initializing...")
            init_db()
            inv_df = pd.read_sql(f"""SELECT item_name as 'Product', qty as 'Stock Level', 
                                 price as 'Selling Price', cost_price as 'Cost Price', 
                                 warehouse as 'Warehouse', barcode as 'Barcode'
                                 FROM inventory WHERE company_key=? ORDER BY item_name""", conn, params=(company_key,))
        edited_df = st.data_editor(inv_df, use_container_width=True, num_rows='dynamic', key='inventory_editor')
        if not edited_df.equals(inv_df):
            for index, row in edited_df.iterrows():
                conn.execute("""UPDATE inventory SET qty=?, price=?, cost_price=?, warehouse=?, barcode=? WHERE item_name=? AND company_key=?""",
                             (row['Stock Level'], row['Selling Price'], row['Cost Price'], row['Warehouse'], row['Barcode'], row['Product'], company_key))
            conn.commit()
            st.success("Inventory updated successfully.")
            log_audit_action(conn, company_key, role, "Updated inventory via data editor", "Inventory")
        st.download_button("📥 Download Master Inventory", data=get_excel_bin(edited_df), file_name="EKA_Stock_Master.xlsx")
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
            
            if st.session_state.get('demo_mode', False):
                st.info("🚀 Demo Mode Active: Showing sample P&L data.")
                demo_pl_data = pd.DataFrame({
                    'Account Head': ['Sales Revenue', 'Service Income', 'Operating Expenses', 'Cost of Goods Sold'],
                    'Revenue (Cr)': [50000.0, 10000.0, 0.0, 0.0],
                    'Expenses (Dr)': [0.0, 0.0, 25000.0, 20000.0]
                })
                st.table(demo_pl_data)
                
                revenue = 60000.0
                expenses = 45000.0
                net_pl = 15000.0
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Revenue", f"GHS {revenue:.2f}")
                with col2:
                    st.metric("Total Expenses", f"GHS {expenses:.2f}")
                with col3:
                    st.metric("Net Profit", f"GHS {net_pl:.2f}", delta=None, delta_color="normal")
                
                st.download_button("📥 Export Sample P&L Report", data=get_excel_bin(demo_pl_data), file_name="Demo_PL_Report.xlsx")
            else:
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
# 6. COMPREHENSIVE MODULE IMPLEMENTATIONS
# ==========================================
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
                customer_email = st.text_input("Customer Email", key="sales_customer_email")
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
                    if validate_input(inv_no, "Invoice Number") and validate_input(customer, "Customer Name") and validate_input(customer_email, "Customer Email") and st.session_state[session_key]:
                        try:
                            conn = get_connection()
                            due_date = datetime.now() + pd.Timedelta(days=due_days)
                            conn.execute("""INSERT INTO sales_invoices (company_key, invoice_no, customer_name, customer_email, invoice_date, due_date, total_amount) 
                                         VALUES (?,?,?,?,?,?,?)""", 
                                         (k, inv_no, customer, customer_email, str(datetime.now().date()), str(due_date.date()), total_amount))
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
    
    # Pending Sales Invoices with Pay Online
    st.subheader("Pending Sales Invoices")
    try:
        conn = get_connection()
        pending_invoices = conn.execute("""SELECT id, invoice_no, customer_name, customer_email, total_amount, due_date 
                                         FROM sales_invoices WHERE company_key=? AND status='Pending'""", (k,)).fetchall()
        conn.close()
        
        if pending_invoices:
            for inv in pending_invoices:
                inv_id, inv_no, cust_name, cust_email, amount, due_date = inv
                with st.expander(f"Invoice {inv_no} - {cust_name} - Due: {due_date}"):
                    st.write(f"**Amount:** GHS {amount:.2f}")
                    if st.button("Pay Online", key=f"pay_{inv_id}"):
                        url = initialize_paystack_payment(cust_email, amount, inv_no)
                        if url:
                            st.link_button("Proceed to Paystack", url)
                        else:
                            st.error("Failed to initialize payment.")
        else:
            st.info("No pending sales invoices.")
    except sqlite3.Error as e:
        st.error(f"Failed to load pending invoices: {e}")
        logger.error(f"Pending invoices error: {e}")
    
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
                for asset in fa_data:
                    monthly_dep = (asset[1] * asset[2] / 100) / 12  # purchase_cost * dep_rate / 100 / 12
                    new_accum_dep = asset[3] + monthly_dep
                    new_book_value = max(0, asset[4] - monthly_dep)
                    
                    conn.execute("""UPDATE fixed_assets SET accum_dep=?, book_value=? WHERE asset_name=? AND company_key=?""",
                                 (new_accum_dep, new_book_value, asset[0], k))
                conn.commit()
                st.success("Monthly depreciation calculated and applied.")
                st.rerun()
        else:
            st.info("No fixed assets found.")
        
        conn.close()
    except sqlite3.Error as e:
        st.error(f"Failed to load fixed assets: {e}")
        logger.error(f"Fixed assets display error: {e}")

def show_audit_trail(k):
    st.header("🕵️ Forensic Audit Trail")

    # Restrict Master Admin from seeing Dev logs
    current_role = st.session_state.get('user', {}).get('role')
    is_master_admin = current_role == "Master Admin"

    try:
        conn = get_connection()

        # Determine which role column exists
        role_col = "user_role"
        try:
            conn.execute("SELECT user_role FROM audit_logs LIMIT 1")
        except sqlite3.OperationalError:
            role_col = "role"

        filter_clause = ""
        params = [k]
        if is_master_admin:
            filter_clause = f" AND {role_col} != 'Dev'"

        sql = f"""SELECT timestamp, {role_col} as user_role, action, module_name 
                     FROM audit_logs WHERE company_key=? {filter_clause} 
                     ORDER BY timestamp DESC LIMIT 100"""

        aud_data_raw = conn.execute(sql, params).fetchall()
        aud_df = None
        if aud_data_raw:
            aud_df = pd.DataFrame(aud_data_raw, columns=['Timestamp', 'User Role', 'Action', 'Module'])

        if aud_df is not None and not aud_df.empty:
            st.dataframe(aud_df, use_container_width=True)
            st.download_button("📥 Download Audit Log", data=get_excel_bin(aud_df), file_name="EKA_Audit_Trail.xlsx")
        else:
            st.info("No audit trail entries found.")

        conn.close()
    except sqlite3.Error as e:
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
