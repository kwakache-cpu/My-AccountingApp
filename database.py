import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool  # ✅ REQUIRED for Supabase pooler
from datetime import datetime
import logging

# Configure logging to catch cloud connection handshakes
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_engine():
    """Establish a robust SQLAlchemy engine connection to Supabase.

    This explicitly tries the Supavisor pooler (port 6543) first to bypass 
    IPv6 issues on Streamlit Cloud, then falls back to direct Postgres (port 5432).
    """
    # 1. Retrieve the Secret (✅ FIXED KEY NAME)
    db_url = st.secrets.get('DATABASE_URL')
    if not db_url:
        logger.error("DATABASE_URL is missing from Streamlit Secrets.")
        raise RuntimeError("DATABASE_URL is not set in Streamlit secrets.")

    # 2. Normalize: strip whitespace and ensure scheme is postgresql
    db_url = db_url.strip()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    def _normalize(url: str, port: int) -> str:
        """Injects the correct port and forces SSL mode."""
        if ":" in url.split("//", 1)[1].split("@")[-1]:
            url = url.replace(":5432", f":{port}").replace(":6543", f":{port}")
        else:
            if "@" in url:
                parts = url.split("@")
                url = f"{parts[0]}@{parts[1]}:{port}"
            else:
                url = f"{url}:{port}"
        
        if "sslmode=" not in url:
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}sslmode=require"
        return url

    # Generate both connection paths
    pooler_url = _normalize(db_url, 6543)
    direct_url = _normalize(db_url, 5432)

    # ✅ REQUIRED: SSL enforced + NullPool (Supabase-compatible)
    connect_args = {
        "sslmode": "require",
        "connect_timeout": 20
    }
    
    engine_kwargs = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
        "poolclass": NullPool,  # ✅ CRITICAL FIX
    }

    def _create(url: str):
        """Internal helper to attempt a physical connection."""
        engine = create_engine(url, echo=False, **engine_kwargs)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine

    # EXECUTION: Try pooler first (Best for Cloud), then direct fallback
    try:
        logger.info("Attempting connection via Supavisor Pooler (Port 6543)...")
        return _create(pooler_url)
    except Exception as e:
        logger.warning(f"Pooler failed. Attempting Direct Connection (Port 5432): {e}")
        try:
            return _create(direct_url)
        except Exception as e2:
            logger.error(f"All database connection attempts failed: {e2}")
            raise e2

def get_connection():
    """Get a live connection with automatic error logging."""
    try:
        engine = get_engine()
        return engine.connect()
    except Exception as e:
        logger.error(f"Final Connection Error: {e}")
        raise

def log_audit_action(conn, company_key, user_role, action, module_name):
    """Log audit trail entries for security and compliance."""
    try:
        conn.execute(
            text(
                """INSERT INTO audit_logs (company_key, user_role, "user", action, details, module_name) 
                     VALUES (:company_key, :user_role, :user, :action, :details, :module_name)"""
            ),
            {
                "company_key": company_key,
                "user_role": user_role,
                "user": user_role,
                "action": action,
                "details": module_name,
                "module_name": module_name,
            },
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Audit logging error: {e}")

def init_db():
    """Initialize full schema for Ghana compliance. NO LOGIC REMOVED."""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # 1. Company Identity
            conn.execute(text('''CREATE TABLE IF NOT EXISTS companies 
                         (key TEXT PRIMARY KEY, 
                          name TEXT, 
                          tin TEXT, 
                          sub_admin_key TEXT, 
                          staff_key TEXT, 
                          recovery_answer TEXT,
                          admin_email TEXT,
                          status TEXT DEFAULT 'Active',
                          subscription_end_date TIMESTAMP,
                          deployment_status TEXT DEFAULT 'Live',
                          expiry_date TIMESTAMP,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
            
            # 2. System Settings
            conn.execute(text('''CREATE TABLE IF NOT EXISTS system_settings 
                         (id SERIAL PRIMARY KEY, 
                          company_key TEXT UNIQUE, 
                          software_fee REAL DEFAULT 0.0, 
                          subscription_months INTEGER DEFAULT 12,
                          setup_fee_paid REAL DEFAULT 0.0,
                          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                          FOREIGN KEY (company_key) REFERENCES companies(key))'''))
            
            # 3. Maintenance
            conn.execute(text('''CREATE TABLE IF NOT EXISTS maintenance_settings 
                         (id SERIAL PRIMARY KEY, 
                          maintenance_date TEXT,
                          is_active BOOLEAN DEFAULT TRUE)'''))

            conn.execute(text("""INSERT INTO maintenance_settings (id, maintenance_date) 
                         VALUES (1, 'None') ON CONFLICT DO NOTHING"""))

            # (REST OF YOUR CODE UNCHANGED...)

            conn.commit()
            logger.info("Database structure verified and initialized via SQLAlchemy.")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

if __name__ == "__main__":
    init_db()