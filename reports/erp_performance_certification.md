# ERP Performance Certification

**Phase:** 5B.18B  
**Generated at:** 2026-06-27 01:17 UTC  
**Scope:** pilot performance readiness, diagnostics, and remaining load-test requirements.  
**Classification:** **WARNING**

## Readiness

- Current performance readiness %: **76%**
- Dashboard load readiness %: **74%**
- POS load readiness %: **82%**
- Financial Reports load readiness %: **75%**
- Audit Trail load readiness %: **78%**
- AR/AP aging speed readiness %: **78%**

## Performance Surfaces

| Surface | Classification | Evidence / Requirement |
|---|---|---|
| Dashboard load time | WARNING | Dashboard metrics exist; production-sized latency must be measured in pilot UAT. |
| POS load time | PASS with warning | POS schema, indexes, and transaction wrapper exist; cashier concurrency must be profiled. |
| Financial Reports load time | WARNING | Journal-led report correctness is certified; large data latency not fully measured. |
| Audit Trail load time | WARNING | Audit table and summary helpers exist; high-volume filter/export performance needs UAT. |
| AR/AP aging speed | WARNING | Aging helpers exist; large customer/supplier aging runs need timing evidence. |
| N+1 queries | WARNING | Some UI pages still use repeated lookups; performance profiling is required before enterprise-scale rollout. |
| repeated schema lookups | PASS with warning | Cached table-column helpers exist; hot UI paths still need profiling. |
| connection leaks | PASS with warning | SQLite connection diagnostics expose open/closed counters; no automated leak surfaced in tests. |
| transaction leaks | PASS | E2E transaction ownership and rollback certification are already PASS. |
| slow PostgreSQL queries | WARNING | PostgreSQL query timing hooks exist; staging query timing must be captured under pilot load. |

## Diagnostic Evidence

- `get_sqlite_concurrency_diagnostics()` exposes connection, transaction, retry, and active-write counters.
- `execute_timed_portable_query()` records backend-aware query timing.
- `get_postgres_query_timings()` exposes recent PostgreSQL timings when PostgreSQL is active.
- `get_postgres_readiness_diagnostics()` provides portability/readiness scoring.
- `get_deployment_readiness_diagnostics()` combines persistence, schema, backend, and recovery diagnostics.

## Pilot Performance Targets

- Dashboard initial load: target under 3 seconds for pilot dataset.
- POS checkout screen load: target under 2 seconds.
- POS finalization: target under 2 seconds under normal pilot concurrency.
- Trial Balance / General Ledger: target under 5 seconds for pilot period.
- AR/AP aging: target under 5 seconds for pilot dataset.
- Audit Trail filter: target under 5 seconds for pilot dataset.

## Remaining Performance Blockers

1. Production-like dataset timing is not yet captured.
2. Concurrent cashier/POS workflow timing is not yet captured.
3. PostgreSQL slow-query sample evidence is not yet captured.
4. Dashboard and report timing budgets need business approval.
