# Deployment & Secrets Checklist

**Phase:** 5B.18D  
**Generated at:** 2026-06-27  
**Purpose:** Pre-deployment validation for Streamlit Cloud, Supabase, Firebase, secrets, and database backend switching.

---

## Deployment Platform

| Item | Requirement | Verified |
|---|---|---|
| Entry point | `app.py` | [ ] |
| Python dependencies | `requirements.txt` installed | [ ] |
| System packages | `packages.txt` (`libzbar0` for barcode) on Streamlit Cloud | [ ] |
| Production mode | `ERP_PRODUCTION_MODE=1` (default) | [ ] |
| Data directory | `EKA_DATA_DIR` persistent or Firebase backup enabled | [ ] |
| Git secrets excluded | `.gitignore` covers `firebase_key.json`, `.streamlit/secrets.toml`, `data/*.db` | [ ] |

---

## Streamlit Secrets Template

Create in **Streamlit Cloud → App settings → Secrets** (or local `.streamlit/secrets.toml`, gitignored).

### SQLite Default (Recommended for Pilot)

```toml
# Minimal pilot — SQLite runtime with Firebase cloud backup
ERP_PRODUCTION_MODE = "1"

# Firebase cloud backup (required for Streamlit Cloud data continuity)
FIREBASE_SERVICE_ACCOUNT = { type = "...", project_id = "...", ... }
FIREBASE_DATABASE_URL = "https://eka-erp-cloud-vault-default-rtdb.firebaseio.com/"
FIREBASE_STORAGE_BUCKET = "your-bucket.appspot.com"
FIREBASE_DB_BACKUP_OBJECT = "backups/eka_enterprise_v3.db"

# Optional integrations
PAYSTACK_SECRET_KEY = "sk_live_..."
PAYSTACK_PUBLIC_KEY = "pk_live_..."
PAYSTACK_CURRENCY = "GHS"
OPENAI_API_KEY = "sk-..."
# or GEMINI_API_KEY = "..."
AI_PROVIDER = "auto"
```

### PostgreSQL/Supabase Cutover (Guarded)

Requires all four cutover evidence reports current in `reports/`:

- `postgres_postdeploy_validation_results.md`
- `postcopy_reconciliation_report.md`
- `postgres_runtime_readiness_report.md`
- `postgres_runtime_dryrun_report.md`

```toml
DB_BACKEND = "postgres"
ERP_ENABLE_POSTGRES_RUNTIME = "1"
ERP_ENVIRONMENT = "staging"   # or "production" with approval below
DATABASE_URL = "postgresql://user:pass@host.pooler.supabase.com:6543/postgres?sslmode=require"

# Production PostgreSQL additionally requires:
# ERP_POSTGRES_PRODUCTION_APPROVED = "1"
# ERP_ENVIRONMENT = "production"
```

---

## Secret Resolution Order

1. **Environment variables** (`os.environ`) — highest priority
2. **Streamlit secrets** (`st.secrets`) — Streamlit Cloud and local `secrets.toml`

Helpers: `_read_runtime_secret()` in `database.py`; `_read_secret_or_env()` in `modules.py`.

---

## Firebase Checklist

| Secret / Config | Purpose | Verified |
|---|---|---|
| `FIREBASE_SERVICE_ACCOUNT` (structured TOML) | Preferred credential source | [ ] |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Legacy inline JSON alternative | [ ] |
| `FIREBASE_DATABASE_URL` | Realtime DB URL | [ ] |
| `FIREBASE_STORAGE_BUCKET` | Storage bucket for SQLite backups | [ ] |
| `FIREBASE_DB_BACKUP_OBJECT` | Backup object path (default: `backups/eka_enterprise_v3.db`) | [ ] |
| Bucket retention policy | History objects under `backups/history/` | [ ] |
| Service account IAM | Storage read/write on backup bucket | [ ] |

**Diagnostics (no secrets exposed):** `get_recovery_source_diagnostics()`, `get_persistence_diagnostics()`.

**Never commit:** `firebase_key.json`, `*-firebase-adminsdk-*.json`.

---

## Supabase / PostgreSQL Checklist

| Item | Requirement | Verified |
|---|---|---|
| `DATABASE_URL` | Pooler URL with `sslmode=require` | [ ] |
| `DB_BACKEND` | `postgres`, `supabase`, or `postgresql` | [ ] |
| `ERP_ENABLE_POSTGRES_RUNTIME` | Must be `"1"` | [ ] |
| `ERP_ENVIRONMENT` | `staging` or `production` + approval | [ ] |
| `ERP_POSTGRES_PRODUCTION_APPROVED` | `"1"` required for production Postgres | [ ] |
| Cutover reports | All four evidence reports current | [ ] |
| Supabase backup SOP | pg_dump or platform backup documented outside app | [ ] |
| Staging probe | `postgres_connection_probe.py` with `ERP_ENABLE_POSTGRES_PROBE=1` | [ ] |

**Note:** When Postgres runtime is active, Firebase SQLite restore is **blocked** (`postgres_runtime_recovery_blocked`). Recovery is operator-managed via Supabase.

---

## Paystack Checklist

| Secret | Verified |
|---|---|
| `PAYSTACK_SECRET_KEY` | [ ] |
| `PAYSTACK_PUBLIC_KEY` | [ ] |
| `PAYSTACK_CURRENCY` (default GHS) | [ ] |
| `PAYSTACK_CALLBACK_URL` | [ ] |
| `PAYSTACK_WEBHOOK_SECRET` | [ ] |

---

## AI Assistant Checklist

| Secret | Verified |
|---|---|
| `OPENAI_API_KEY` or `[openai] api_key` | [ ] |
| `GEMINI_API_KEY` or `[gemini] api_key` | [ ] |
| `AI_PROVIDER` (`openai`, `gemini`, `auto`) | [ ] |

---

## Database Backend Switching Validation

| Scenario | Expected Behavior | Verified |
|---|---|---|
| No `DB_BACKEND` set | SQLite runtime | [ ] |
| `DB_BACKEND=sqlite` | SQLite runtime | [ ] |
| Postgres configured but `ERP_ENABLE_POSTGRES_RUNTIME=0` | Safe fallback to SQLite | [ ] |
| Full Postgres flags + cutover reports | Postgres runtime startup | [ ] |
| Postgres active + cloud restore attempt | Blocked with `postgres_runtime_recovery_blocked` | [ ] |
| `get_startup_backend_diagnostics()` | Reports active backend and cutover evidence | [ ] |

---

## Pre-Deploy Validation Commands

```bash
python -m py_compile app.py database.py modules.py accounting_engine.py financials.py
python -m unittest discover -s tests
python tests/run_regression_tests.py
```

In-app: System Configuration → System Health → review `get_deployment_readiness_diagnostics()` output.

---

## Deployment Validation Checklist (Sign-Off)

### Before First Deploy

- [ ] All required secrets configured in Streamlit Cloud (not in repo)
- [ ] Firebase credentials load (`credentials_loaded=true` in diagnostics)
- [ ] Production mode enabled
- [ ] At least one company exists or onboarding path tested
- [ ] Admin user can log in
- [ ] Backup export permission restricted to System Admin / Master Admin

### After Deploy

- [ ] App loads without startup exception
- [ ] Dashboard renders for Owner role
- [ ] Cloud backup status shows recent upload (after first write)
- [ ] Trial balance balanced for pilot company
- [ ] POS sale completes and posts journal
- [ ] Audit trail records actions

### Postgres Cutover (If Applicable)

- [ ] Staging cutover completed and reports updated
- [ ] Row-count reconciliation matches SQLite source
- [ ] Financial reports reconcile on Postgres
- [ ] Supabase backup schedule configured
- [ ] Rollback to SQLite documented and tested in staging

---

## Security Notes

- Diagnostics redact passwords and service account payloads
- `export_backup` / `restore_backup` limited to System Admin and Master Admin
- Do not paste connection strings or API keys into reports or commits
- Developer role is fully privileged — restrict credential access in production
