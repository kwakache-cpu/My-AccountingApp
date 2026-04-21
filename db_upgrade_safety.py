import os
import shutil
import sqlite3
from datetime import datetime


SQLITE_HEADER = b"SQLite format 3\x00"


def is_sqlite_file(path):
    if not path or not os.path.exists(path) or os.path.getsize(path) < len(SQLITE_HEADER):
        return False
    try:
        with open(path, "rb") as file_obj:
            return file_obj.read(len(SQLITE_HEADER)) == SQLITE_HEADER
    except OSError:
        return False


def ensure_backup_directory(db_path):
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def create_timestamped_backup(db_path, logger=None, reason="migration"):
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file does not exist: {db_path}")
    backup_dir = ensure_backup_directory(db_path)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_name = os.path.splitext(os.path.basename(db_path))[0]
    backup_path = os.path.join(backup_dir, f"{db_name}_{reason}_{timestamp}.db")
    shutil.copy2(db_path, backup_path)
    if not os.path.exists(backup_path) or os.path.getsize(backup_path) <= 0:
        raise RuntimeError(f"Backup verification failed for {backup_path}")
    if logger:
        logger.info("Created database backup: %s", backup_path)
    return backup_path


def restore_database_from_backup(backup_path, db_path, logger=None):
    if not backup_path or not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file does not exist: {backup_path}")
    if not is_sqlite_file(backup_path):
        raise RuntimeError(f"Backup file is not a valid SQLite database: {backup_path}")
    shutil.copy2(backup_path, db_path)
    if not is_sqlite_file(db_path):
        raise RuntimeError(f"Restore verification failed for {db_path}")
    if logger:
        logger.warning("Restored database from backup: %s", backup_path)


def table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def safe_table_count(conn, table_name):
    if not table_exists(conn, table_name):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {table_name}").fetchone()
    if row is None:
        return 0
    if isinstance(row, sqlite3.Row):
        return int(row["row_count"] or 0)
    return int(row[0] or 0)


def collect_row_counts(conn, table_names):
    return {table_name: safe_table_count(conn, table_name) for table_name in table_names}


def validate_row_counts(before_counts, after_counts):
    failures = []
    for table_name, before_count in before_counts.items():
        after_count = int(after_counts.get(table_name, 0))
        if after_count < int(before_count):
            failures.append((table_name, int(before_count), after_count))
    return failures
