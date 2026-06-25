import sqlite3


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _column_exists(conn, table_name, column_name):
    if not _table_exists(conn, table_name):
        return False
    return any(row[1] == column_name for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall())


def _ensure_column(conn, table_name, column_name, column_def):
    if _column_exists(conn, table_name, column_name):
        return False
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
    return True


def _ensure_setting_defaults(conn, defaults):
    if not conn.execute("SELECT 1 FROM system_settings WHERE id = ?", (1,)).fetchone():
        conn.execute("INSERT INTO system_settings (id) VALUES (?)", (1,))
    for column_name, default_sql in defaults.items():
        if _ensure_column(conn, "system_settings", column_name, default_sql):
            continue
        conn.execute(
            f"""
            UPDATE system_settings
            SET {column_name} = COALESCE({column_name}, {default_sql.split('DEFAULT', 1)[1].strip()})
            WHERE id = 1
            """
        )


def _ensure_migration_history_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_history (
            migration_id TEXT PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _migration_applied(conn, migration_id):
    _ensure_migration_history_table(conn)
    row = conn.execute(
        "SELECT 1 FROM migration_history WHERE migration_id = ?",
        (migration_id,),
    ).fetchone()
    return bool(row)


def _record_migration(conn, migration_id, description):
    if not conn.execute("SELECT 1 FROM migration_history WHERE migration_id = ?", (migration_id,)).fetchone():
        conn.execute(
            "INSERT INTO migration_history (migration_id, description) VALUES (?, ?)",
            (migration_id, description),
        )


def _apply_migration(conn, migration_id, description, migration_fn, logger=None):
    if _migration_applied(conn, migration_id):
        return False
    savepoint_name = f"migration_{migration_id.replace('-', '_')}"
    conn.execute(f"SAVEPOINT {savepoint_name}")
    try:
        migration_fn(conn)
        _record_migration(conn, migration_id, description)
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        if logger:
            logger.info("Applied migration %s: %s", migration_id, description)
        return True
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        raise


def _migration_foundation_controls(conn):
    _ensure_setting_defaults(
        conn,
        {
            "journal_source_of_truth": "INTEGER DEFAULT 1",
            "legacy_mirror_mode": "TEXT DEFAULT 'mirror'",
            "enforce_document_approval": "INTEGER DEFAULT 0",
            "inventory_cost_method": "TEXT DEFAULT 'weighted_average'",
            "bank_reconciliation_mode": "TEXT DEFAULT 'journal_plus_payment'",
        },
    )


def _migration_document_traceability(conn):
    trace_columns = {
        "invoices": {
            "posted_entry_id": "INTEGER",
            "void_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
        },
        "bills": {
            "posted_entry_id": "INTEGER",
            "void_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
        },
        "payments": {
            "posted_entry_id": "INTEGER",
            "void_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
        },
        "stock_movements": {
            "posted_entry_id": "INTEGER",
            "void_entry_id": "INTEGER",
            "last_journal_sync_at": "TIMESTAMP",
        },
        "journal_entries": {
            "document_number": "TEXT",
            "document_type": "TEXT",
            "posted_at": "TIMESTAMP",
            "posted_by": "TEXT",
        },
    }
    for table_name, columns in trace_columns.items():
        if not _table_exists(conn, table_name):
            continue
        for column_name, column_def in columns.items():
            _ensure_column(conn, table_name, column_name, column_def)


def run_foundation_migrations(conn, logger=None):
    """
    Apply additive, idempotent ERP migrations.
    These migrations are intentionally non-destructive and safe to run on every boot.
    """
    _ensure_migration_history_table(conn)
    _apply_migration(
        conn,
        "2026-04-21-foundation-controls",
        "Add non-destructive system control flags for journal source-of-truth rollout.",
        _migration_foundation_controls,
        logger=logger,
    )
    _apply_migration(
        conn,
        "2026-04-21-document-traceability",
        "Add reverse journal traceability columns to source documents.",
        _migration_document_traceability,
        logger=logger,
    )
