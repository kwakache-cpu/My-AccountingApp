# Testing

This ERP includes an isolated regression harness under `tests/`.

## How to Run

Preferred:

```bash
python -m pytest
```

Fallback runner:

```bash
python tests/run_regression_tests.py
```

## What the Tests Cover

- Accounting core validation
  - balanced vs unbalanced journals
  - posted-only reporting
  - draft/submitted documents excluded from balances
  - voided journal exclusion
- Posting workflow safety
  - invoice, bill, customer payment, supplier payment posting
  - duplicate-post blocking
- Reporting and period controls
  - trial balance balance check
  - balance sheet equation
  - AR/AP reconciliation mismatch detection
  - open/closed/locked period behavior
- Persistence safety
  - schema manifest readiness
  - backup overwrite protection for empty/non-production-ready databases
  - mocked cloud backup path without real Firebase credentials

## Safety Warning

Do not run tests against a production database.

The harness forces an isolated temporary `EKA_DATA_DIR` and reloads the ERP modules so test runs never target the live `DB_PATH` in the repository root or deployment environment.

## What Must Pass Before Push

- All regression tests in `tests/`
- Any targeted manual smoke tests for the feature area you changed
- No failures in the fallback runner or `pytest`
