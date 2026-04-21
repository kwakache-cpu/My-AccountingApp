"""
Temporary persistence strategy notes for production continuity.

Local SQLite at DB_PATH remains the current runtime source of truth, but it is not
sufficient as the final enterprise production persistence layer on ephemeral hosting.
Cloud Vault auto-recovery is only a temporary continuity layer while the app is still
running on file-based storage.

TODO:
- Introduce a managed persistent database strategy (Postgres/Supabase or equivalent).
- Move runtime writes off local SQLite on ephemeral hosts.
- Keep Cloud Vault for backups/recovery after managed persistence is in place.
"""


RUNTIME_PERSISTENCE_MODE = "local_sqlite_with_cloud_recovery"
TARGET_PERSISTENCE_MODE = "managed_postgres"

