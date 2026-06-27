# PostgreSQL E2E Write Execution

**Generated at:** 2026-06-26T23:52:36.737633+00:00
**Branch:** `phase-5b17b-postgres-e2e-write-execution`
**Scope:** staged PostgreSQL end-to-end write workflow execution.

## Backend Diagnostics

- Active backend: `postgres`
- Configured backend: `postgres`
- `DATABASE_URL` present: `True`
- `ERP_ENABLE_POSTGRES_RUNTIME`: `1`
- `ERP_ENVIRONMENT`: `staging`
- Abort reason: None

## Execution Summary

- Overall status: **PASS**
- Cleanup status: **ROLLED_BACK**
- Test company key: `PG-E2E-5B17B-COMPANY`
- Test branch id: `PG-E2E-5B17B-BRANCH`

## Workflow Results

| Workflow | Status | Row IDs Created | Cleanup Status | Evidence |
|---|---|---|---|---|
| POS sale | PASS | pos_sale_id=9, journal_entry_id=29 | ROLLED_BACK | journal_balanced=True customer_balance=40.0 |
| inventory adjustment | PASS | stock_movement_id=1 | ROLLED_BACK | stock movement inserted and inventory quantity updated |
| customer invoice | PASS | invoice_id=2, journal_entry_id=30 | ROLLED_BACK | journal_balanced=True customer_balance=340.0 |
| customer payment | PASS | payment_id=9, journal_entry_id=31 | ROLLED_BACK | journal_balanced=True customer_balance=0.0 |
| supplier bill | PASS | bill_id=1, journal_entry_id=32 | ROLLED_BACK | journal_balanced=True supplier_balance=220.0 |
| supplier payment | PASS | payment_id=10, journal_entry_id=33 | ROLLED_BACK | journal_balanced=True supplier_balance=0.0 |
| general journal | PASS | journal_entry_id=34 | ROLLED_BACK | journal_balanced=True |
| payroll posting | PASS | payroll_id=2, journal_entry_id=35 | ROLLED_BACK | journal_balanced=True |
| asset depreciation | PASS | asset_id=1, acquisition_journal_entry_id=36, depreciation_journal_entry_id=37 | ROLLED_BACK | depreciation_count=1 acquisition_journal_balanced=True |
| admin/user update | PASS | user_id=4 | ROLLED_BACK | audit_count=1 |

## Execution Timeline

- Owned transaction started: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, expected_transaction_id=1458
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=identity sequence sync
- Company inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, company_key=PG-E2E-5B17B-COMPANY
- Company verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, company_key=PG-E2E-5B17B-COMPANY, company_visible=True
- Branch inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, branch_id=PG-E2E-5B17B-BRANCH
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=company and branch insert
- Customer inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, customer_id=3
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=customer insert
- Supplier inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, supplier_id=5
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=supplier insert
- Inventory inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, inventory_item_id=4
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=inventory insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=POS sale persistence
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=POS journal insert
- Company verified before audit: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, company_key=PG-E2E-5B17B-COMPANY, company_visible=True
- Audit inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, action=POS Sale, module_name=POS
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=POS audit insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=stock movement insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=customer invoice journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=customer payment journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=supplier bill journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=supplier payment journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=general journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=payroll journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=fixed asset insert before
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=fixed asset insert after
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset acquisition account lookup before
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset acquisition account lookup after
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset acquisition journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset depreciation account lookup before
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset depreciation account lookup after
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset depreciation journal insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=asset depreciation asset update
- Company verified before audit: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, company_key=PG-E2E-5B17B-COMPANY, company_visible=True
- Audit inserted: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, action=PostgreSQL E2E User Update, module_name=User Management
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=admin audit insert
- Transaction ownership verified: connection_id=0x215de2b5400, in_transaction=True, transaction_id=1458, after=workflow completion

## Transaction Ownership

- Expected transaction id: `1458`
- Status: **STABLE**
- Guard: PostgreSQL txid_current() remained stable across all guarded E2E seed, journal, and audit steps.

## Cleanup Strategy

All staged writes run inside one owned transaction and are rolled back at the end of certification.

## Schema Portability Notes

- Branch test-record seeding is schema-aware: the runner inspects `branches` columns and inserts only available columns.
- `branches.status` is optional for the E2E runner; schemas with only `branch_id`, `company_key`, and `branch_name` are supported.
- Integer primary keys for E2E-owned rows are generated by the database and read back through portable identity helpers.
- PostgreSQL staging identity sequences are synchronized before E2E inserts to avoid duplicate generated IDs after imported data.
- Accounting master identity sequences (`accounts`, `chart_of_accounts`, `account_categories`, `tax_codes`, `bank_accounts`) are included in E2E sequence sync before account lookup can create missing COA rows.
- POS line-item portability uses the canonical `pos_sale_lines` table; missing legacy aliases such as `pos_sale_items` are skipped during identity sync.
- Inventory stock movements use the generated and transaction-visible `inventory.id` returned from E2E inventory seeding.
- E2E audit events are inserted through the active certification transaction connection so the uncommitted test company remains visible.
- E2E audit inserts verify company visibility on the owning transaction before writing `audit_logs` rows.
- Transaction ownership is guarded by comparing PostgreSQL `txid_current()` after every critical E2E seed and audit step.
- Asset depreciation certification uses E2E-local journal and fixed-asset update writes instead of the production depreciation helper, preserving the owned transaction through depreciation.

## Blockers

- None recorded by this execution.

## Production Readiness Recommendation

GO for final production-readiness review if this PASS result is produced on approved PostgreSQL staging; NO-GO if backend diagnostics are not PostgreSQL staging.

## Raw Execution Payload

```json
{
  "abort_reason": null,
  "backend_diagnostics": {
    "active_backend": "postgres",
    "configured_backend": "postgres",
    "database_url_present": true,
    "erp_enable_postgres_runtime": "1",
    "erp_environment": "staging"
  },
  "blockers": [],
  "cleanup_status": "ROLLED_BACK",
  "execution_timeline": [
    {
      "connection_id": "0x215de2b5400",
      "event": "Owned transaction started",
      "expected_transaction_id": 1458,
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "identity sequence sync",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "company_key": "PG-E2E-5B17B-COMPANY",
      "connection_id": "0x215de2b5400",
      "event": "Company inserted",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "company_key": "PG-E2E-5B17B-COMPANY",
      "company_visible": true,
      "connection_id": "0x215de2b5400",
      "event": "Company verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "branch_id": "PG-E2E-5B17B-BRANCH",
      "connection_id": "0x215de2b5400",
      "event": "Branch inserted",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "company and branch insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "connection_id": "0x215de2b5400",
      "customer_id": 3,
      "event": "Customer inserted",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "customer insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "connection_id": "0x215de2b5400",
      "event": "Supplier inserted",
      "in_transaction": true,
      "supplier_id": 5,
      "transaction_id": 1458
    },
    {
      "after": "supplier insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "connection_id": "0x215de2b5400",
      "event": "Inventory inserted",
      "in_transaction": true,
      "inventory_item_id": 4,
      "transaction_id": 1458
    },
    {
      "after": "inventory insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "POS sale persistence",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "POS journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "company_key": "PG-E2E-5B17B-COMPANY",
      "company_visible": true,
      "connection_id": "0x215de2b5400",
      "event": "Company verified before audit",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "action": "POS Sale",
      "connection_id": "0x215de2b5400",
      "event": "Audit inserted",
      "in_transaction": true,
      "module_name": "POS",
      "transaction_id": 1458
    },
    {
      "after": "POS audit insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "stock movement insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "customer invoice journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "customer payment journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "supplier bill journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "supplier payment journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "general journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "payroll journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "fixed asset insert before",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "fixed asset insert after",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset acquisition account lookup before",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset acquisition account lookup after",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset acquisition journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset depreciation account lookup before",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset depreciation account lookup after",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset depreciation journal insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "asset depreciation asset update",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "company_key": "PG-E2E-5B17B-COMPANY",
      "company_visible": true,
      "connection_id": "0x215de2b5400",
      "event": "Company verified before audit",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "action": "PostgreSQL E2E User Update",
      "connection_id": "0x215de2b5400",
      "event": "Audit inserted",
      "in_transaction": true,
      "module_name": "User Management",
      "transaction_id": 1458
    },
    {
      "after": "admin audit insert",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    },
    {
      "after": "workflow completion",
      "connection_id": "0x215de2b5400",
      "event": "Transaction ownership verified",
      "in_transaction": true,
      "transaction_id": 1458
    }
  ],
  "generated_at": "2026-06-26T23:52:36.737633+00:00",
  "overall_status": "PASS",
  "production_readiness_recommendation": "GO for final production-readiness review if this PASS result is produced on approved PostgreSQL staging; NO-GO if backend diagnostics are not PostgreSQL staging.",
  "transaction_ownership": {
    "expected_transaction_id": 1458,
    "guard": "PostgreSQL txid_current() remained stable across all guarded E2E seed, journal, and audit steps.",
    "status": "STABLE"
  },
  "workflows": [
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True customer_balance=40.0",
      "row_ids": {
        "journal_entry_id": 29,
        "pos_sale_id": 9
      },
      "status": "PASS",
      "workflow": "POS sale"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "stock movement inserted and inventory quantity updated",
      "row_ids": {
        "stock_movement_id": 1
      },
      "status": "PASS",
      "workflow": "inventory adjustment"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True customer_balance=340.0",
      "row_ids": {
        "invoice_id": 2,
        "journal_entry_id": 30
      },
      "status": "PASS",
      "workflow": "customer invoice"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True customer_balance=0.0",
      "row_ids": {
        "journal_entry_id": 31,
        "payment_id": 9
      },
      "status": "PASS",
      "workflow": "customer payment"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True supplier_balance=220.0",
      "row_ids": {
        "bill_id": 1,
        "journal_entry_id": 32
      },
      "status": "PASS",
      "workflow": "supplier bill"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True supplier_balance=0.0",
      "row_ids": {
        "journal_entry_id": 33,
        "payment_id": 10
      },
      "status": "PASS",
      "workflow": "supplier payment"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True",
      "row_ids": {
        "journal_entry_id": 34
      },
      "status": "PASS",
      "workflow": "general journal"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "journal_balanced=True",
      "row_ids": {
        "journal_entry_id": 35,
        "payroll_id": 2
      },
      "status": "PASS",
      "workflow": "payroll posting"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "depreciation_count=1 acquisition_journal_balanced=True",
      "row_ids": {
        "acquisition_journal_entry_id": 36,
        "asset_id": 1,
        "depreciation_journal_entry_id": 37
      },
      "status": "PASS",
      "workflow": "asset depreciation"
    },
    {
      "cleanup_status": "ROLLED_BACK",
      "evidence": "audit_count=1",
      "row_ids": {
        "user_id": 4
      },
      "status": "PASS",
      "workflow": "admin/user update"
    }
  ]
}
```
