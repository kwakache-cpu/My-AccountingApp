import sqlite3, os

paths = [
    r"D:\Emma\My AccountingApp\data\eka_enterprise_v3.db",
    r"D:\Emma\My AccountingApp\data\backups\eka_enterprise_v3_pre_migration_20260421_210443.db",
    r"D:\Emma\My AccountingApp\eka_enterprise_v3.db",
    r"D:\Emma\My AccountingApp\database.db",
]

tables = ["companies","users","branches","journal_entries","journal_lines","invoices","bills","payments","inventory","customers","suppliers","fixed_assets","payroll"]

for p in paths:
    print("\n" + "="*90)
    print(p)
    print("exists:", os.path.exists(p), "size:", os.path.getsize(p) if os.path.exists(p) else "missing")
    if not os.path.exists(p):
        continue
    try:
        con = sqlite3.connect(p)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in cur.fetchall()}
        print("table_count:", len(existing))
        for t in tables:
            if t in existing:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    print(f"{t}:", cur.fetchone()[0])
                except Exception as e:
                    print(f"{t}: ERROR {e}")
            else:
                print(f"{t}: missing")
        if "companies" in existing:
            try:
                cur.execute("SELECT * FROM companies LIMIT 5")
                rows = cur.fetchall()
                print("companies sample:", rows)
            except Exception as e:
                print("companies sample error:", e)
        con.close()
    except Exception as e:
        print("OPEN ERROR:", e)
