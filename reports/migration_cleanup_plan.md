# Migration Data Cleanup Plan

**Generated at:** 2026-06-01 11:29:02 UTC
**Database:** `D:\Emma\My AccountingApp\data\eka_enterprise_v3.db`
**Mode:** read-only analysis (no data modified)

## Summary

- **Total warning rows analyzed:** 11
- **Safe to auto-fix later:** 1
- **Manual decision required:** 10
- **No action needed:** 0

## Cleanup Readiness

Migration remains **GO WITH WARNINGS** until manual items are resolved or accepted as exceptions.

## A. POS Sales Missing branch_id

### Row `pos_sales`.1 — PERFECTO PREMIUM / receipt POS-20260507103918

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.2 — PERFECTO PREMIUM / receipt POS-20260520135510

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.3 — PERFECTO PREMIUM / receipt POS-20260520155403

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.4 — PERFECTO PREMIUM / receipt POS-20260523232118

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.5 — PERFECTO PREMIUM / receipt POS-20260526234318

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.6 — PERFECTO PREMIUM / receipt POS-20260527122525

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.7 — PERFECTO PREMIUM / receipt POS-20260527144853

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```

### Row `pos_sales`.8 — PERFECTO PREMIUM / receipt POS-20260527145115

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `—` |
| current bad value | branch_id='' |
| recommended fix | Assign branch_id manually after confirming sale location. |
| risk level | **MEDIUM** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Multiple active branches (2): KOFORIDUA (ADMIN-PERFECTO-123-koforidua), KUMASI (ADMIN-PERFECTO-123-kumasi). Cashier 'Master Admin' is not branch-scoped.

**Proposed SQL (dry-run only):**

```sql
-- manual review required; no auto SQL proposed
```


## C. Missing manager_user_id

### Row `branches`.ADMIN-PERFECTO-123-koforidua — KOFORIDUA (ADMIN-PERFECTO-123-koforidua)

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `ADMIN-PERFECTO-123-koforidua` |
| current bad value | branch_manager='KIN', manager_user_id=NULL |
| recommended fix | Assign branch manager manually in Branch Management UI. |
| risk level | **LOW** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** No user match for branch_manager 'KIN'. Branch staff: JADON (Staff).

**Proposed SQL (dry-run only):**

```sql
-- manual review required
```

### Row `branches`.ADMIN-PERFECTO-123-kumasi — KUMASI (ADMIN-PERFECTO-123-kumasi)

| Field | Value |
|-------|-------|
| company_key | `ADMIN-PERFECTO-123` |
| branch_id | `ADMIN-PERFECTO-123-kumasi` |
| current bad value | branch_manager='BEATRICE', manager_user_id=NULL |
| recommended fix | User 'BEATRICE' matches branch_manager text but has NULL user_id. Assign user_id first, then set branches.manager_user_id. |
| risk level | **LOW** |
| auto-fix safe | **No** |
| manual decision needed | **Yes** |

**Notes:** Matched by name only; manager_user_id column requires users.user_id.

**Proposed SQL (dry-run only):**

```sql
-- manual: assign users.user_id for matched user before branch manager link
```


## D. Payments Without Source Reference

### Row `payments`.4 — BELINDA AND DAUGHTERS / Customer Receipt GHS 50000.00 on 2026-04-27

| Field | Value |
|-------|-------|
| company_key | `ADMIN-BELINDA-123` |
| branch_id | `—` |
| current bad value | invoice_id=NULL, bill_id=NULL, customer_id=None, supplier_id=None, reference='' |
| recommended fix | Set customer_id=2 and reference from journal description. |
| risk level | **MEDIUM** |
| auto-fix safe | **Yes** |
| manual decision needed | **No** |

**Notes:** Journal #7: Customer receipt - BOA Matched customer 'BOA' (id=2) from journal text.

**Proposed SQL (dry-run only):**

```sql
UPDATE payments SET customer_id = 2, reference = 'Customer receipt - BOA' WHERE id = 4 AND company_key = 'ADMIN-BELINDA-123';
```

## Execution Policy

- Run `python scripts/plan_migration_data_cleanup.py` to refresh the plan and JSON export.
- Run `python scripts/apply_migration_data_cleanup.py --dry-run --plan reports/migration_cleanup_plan.json` to preview guarded apply.
- Apply changes only with `scripts/apply_migration_data_cleanup.py --apply --confirm ...` (payment reference fix only).
