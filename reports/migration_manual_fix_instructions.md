# Migration Manual Fix Instructions

**Database:** `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`  
**Phase:** 5B.5 admin UI + guarded cleanup  
**Last plan:** see `reports/migration_cleanup_plan.json`

Use **System Configuration → Migration Cleanup Review** (Dev / Master Admin only) for in-app fixes, or follow the steps below.

This document covers fixes that must be done manually in the application or via approved SQL after business review. The payment reference fix may be applied in-app or through the guarded CLI script.

---

## 1. POS sales missing `branch_id` (8 rows)

**Company:** PERFECTO PREMIUM (`ADMIN-PERFECTO-123`)  
**Issue:** All 8 POS sales have empty `branch_id`. Cashier is `Master Admin` (company-scoped), so the planner cannot infer KUMASI vs KOFORIDUA.

**Affected sale IDs:** 1–8 (receipts `POS-20260507103918` through `POS-20260527145115`)

### Steps

1. Open **POS** or **Branch Management** for PERFECTO PREMIUM.
2. For each sale, confirm which branch processed the transaction (KUMASI `ADMIN-PERFECTO-123-kumasi` or KOFORIDUA `ADMIN-PERFECTO-123-koforidua`).
3. Update `pos_sales.branch_id` for that sale only after confirmation.

**Example SQL (replace branch and id after review):**

```sql
UPDATE pos_sales
SET branch_id = 'ADMIN-PERFECTO-123-kumasi'
WHERE id = 1 AND company_key = 'ADMIN-PERFECTO-123';
```

4. Optionally align linked `journal_entries.branch_id` for the same `source_id` if branch reporting requires it.

**Do not** use `scripts/apply_migration_data_cleanup.py` for POS fixes — they remain manual-only.

---

## 2. Branch managers missing `manager_user_id` (2 branches)

### KUMASI (`ADMIN-PERFECTO-123-kumasi`)

- **Display name:** BEATRICE  
- **Issue:** User record exists but `users.user_id` is NULL — cannot set `branches.manager_user_id` until `user_id` is assigned.

**Steps:**

1. **Settings → Users** (or Branch Management → assign manager).
2. Ensure BEATRICE has a valid `user_id` (re-save user or use account recovery flow).
3. Assign BEATRICE as branch manager for KUMASI in the UI (uses `assign_branch_manager`).

### KOFORIDUA (`ADMIN-PERFECTO-123-koforidua`)

- **Display name:** KIN  
- **Issue:** No matching user; branch staff includes JADON (Staff).

**Steps:**

1. Create or identify the correct manager user for KOFORIDUA.
2. Assign via **Branch Management → Edit branch → Manager**.

**Do not** auto-apply manager links via the cleanup script.

---

## 3. Payment without source reference (1 row — guarded auto-fix available)

**Payment ID:** 4  
**Company:** BELINDA AND DAUGHTERS (`ADMIN-BELINDA-123`)  
**Type:** Customer Receipt, GHS 50,000, Bank, Posted  
**Journal #7:** “Customer receipt - BOA”  
**Proposed fix:** `customer_id = 2` (customer BOA), `reference = 'Customer receipt - BOA'`

### In-app (recommended)

1. Open **System Configuration**.
2. Use **Migration Cleanup Review → Payment reference** tab.
3. Confirm checkbox and type: `I confirm this payment reference fix`.
4. Click **Apply payment fix** (creates backup automatically).

### CLI dry-run (read-only)

```powershell
python scripts/apply_migration_data_cleanup.py --dry-run --plan reports/migration_cleanup_plan.json
```

### Apply (only after backup + explicit confirm)

```powershell
python scripts/apply_migration_data_cleanup.py --apply --confirm I_UNDERSTAND_THIS_WILL_MODIFY_THE_SQLITE_DATABASE --plan reports/migration_cleanup_plan.json
```

The script creates a timestamped backup via `db_upgrade_safety`, verifies the row still has empty reference and no invoice/bill, updates one row in a single transaction, and prints before/after state.

---

## 4. Expiry dates (audit false positive — fixed in 5B.4)

Inventory rows with ISO dates `2026-05-21` and `2026-05-23` are valid. The Phase 5B.2 audit used SQLite GLOB `_` (literal) instead of `?` (wildcard). The audit script now uses `????-??-??`.

**No inventory data changes required.**

---

## 5. Re-run validation after fixes

```powershell
python scripts/run_migration_integrity_audit.py
python scripts/plan_migration_data_cleanup.py
```

Review:

- `reports/migration_integrity_summary.md`
- `reports/migration_integrity_audit.md`
- `reports/migration_cleanup_plan.json`

**Target:** Overall **GO** (or **GO WITH WARNINGS** only for accepted exceptions) before PostgreSQL migration cutover.

---

## Safety reminders

- Never run `--apply` without reviewing dry-run output.
- Do not commit or push database files.
- Keep backups created under `data/backups/` until migration is verified.
