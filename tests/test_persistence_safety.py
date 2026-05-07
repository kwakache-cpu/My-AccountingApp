from pathlib import Path
from unittest import mock
import shutil

from test_support import ERPIsolatedTestCase


class _FakeBlob:
    def __init__(self, name, uploads, source_path=None, exists=True):
        self.name = name
        self.uploads = uploads
        self.source_path = source_path
        self._exists = exists
        self.updated = None

    def upload_from_filename(self, filename):
        self.uploads.append((self.name, Path(filename).name))

    def download_to_filename(self, filename):
        if not self.source_path:
            raise FileNotFoundError(self.name)
        shutil.copy2(self.source_path, filename)

    def exists(self):
        return self._exists

    def reload(self):
        return None


class _FakeBucket:
    def __init__(self, blobs=None):
        self.uploads = []
        self._blobs = blobs or {}

    def blob(self, name):
        return self._blobs.get(name) or _FakeBlob(name, self.uploads, exists=False)

    def list_blobs(self, prefix=None):
        return [
            blob
            for name, blob in self._blobs.items()
            if not prefix or str(name).startswith(prefix)
        ]


class PersistenceSafetyTests(ERPIsolatedTestCase):
    def _seed_valid_local_backup(self):
        result = self.database.backup_runtime_database_to_cloud(force=True)
        self.assertTrue(Path(self.database.LOCAL_LATEST_BACKUP_PATH).exists())
        self.assertTrue(result["local_ok"])

    def test_schema_manifest_required_tables_pass(self):
        diagnostics = self.database.get_schema_manifest_diagnostics(self.conn)
        self.assertTrue(diagnostics["ok"])
        self.assertEqual(diagnostics["missing_source_of_truth_tables"], [])

    def test_empty_bootstrap_db_does_not_overwrite_valid_backup(self):
        self._seed_valid_local_backup()
        original_backup_health = self.database.get_database_health_snapshot(self.database.LOCAL_LATEST_BACKUP_PATH)
        self.conn.execute("DELETE FROM company_subscriptions WHERE company_key = ?", (self.company_key,))
        self.conn.execute("DELETE FROM companies WHERE key = ?", (self.company_key,))
        self.commit()
        result = self.database.backup_runtime_database_to_cloud(force=True)
        retained_backup_health = self.database.get_database_health_snapshot(self.database.LOCAL_LATEST_BACKUP_PATH)
        self.assertFalse(result["ok"])
        self.assertIn("companies table has no deployed company rows", result["reason"])
        self.assertEqual(original_backup_health["company_count"], retained_backup_health["company_count"])
        self.assertEqual(retained_backup_health["company_count"], 1)

    def test_non_production_ready_db_is_blocked_from_latest_backup_overwrite(self):
        self._seed_valid_local_backup()
        self.conn.execute("DELETE FROM company_subscriptions WHERE company_key = ?", (self.company_key,))
        self.conn.execute("DELETE FROM companies WHERE key = ?", (self.company_key,))
        self.commit()
        result = self.database.backup_runtime_database_to_cloud(force=True)
        self.assertFalse(result["ok"])
        self.assertNotIn("local_ok", result)
        self.assertIn("companies table has no deployed company rows", result["reason"])
        backup_diag = self.database.get_local_backup_diagnostics()
        self.assertEqual(backup_diag["company_count"], 1)

    def test_cloud_backup_can_be_mocked_without_real_credentials(self):
        fake_bucket = _FakeBucket()
        with mock.patch.object(self.database, "_get_firebase_recovery_bucket", return_value=fake_bucket):
            with mock.patch.object(
                self.database,
                "get_recovery_source_diagnostics",
                return_value={
                    "bucket_name": "fake-bucket",
                    "object_name": self.database.FIREBASE_OBJECT_NAME,
                    "credential_error": None,
                },
            ):
                result = self.database.backup_runtime_database_to_cloud(force=True, trigger_tables=["companies"])
        self.assertTrue(result["cloud_ok"])
        uploaded_objects = [name for name, _filename in fake_bucket.uploads]
        self.assertIn(self.database.FIREBASE_OBJECT_NAME, uploaded_objects)
        self.assertTrue(any(name.startswith("backups/history/eka_enterprise_v3_") for name in uploaded_objects))

    def test_valid_db_with_companies_starts_normally_not_bootstrap(self):
        result = self.database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["startup_mode"], "local_production_ready")
        self.assertFalse(result["bootstrap_needed"])
        self.assertEqual(result["company_count"], 1)

    def test_empty_structurally_valid_db_enters_bootstrap_mode(self):
        self.conn.execute("DELETE FROM company_subscriptions WHERE company_key = ?", (self.company_key,))
        self.conn.execute("DELETE FROM companies WHERE key = ?", (self.company_key,))
        self.commit()
        result = self.database.startup_database()
        self.assertTrue(result["ok"])
        self.assertEqual(result["startup_mode"], "bootstrap_mode")
        self.assertTrue(result["bootstrap_needed"])
        self.assertEqual(result["company_count"], 0)

    def test_database_identity_persists_across_startup(self):
        before = self.conn.execute("SELECT instance_id FROM database_identity LIMIT 1").fetchone()["instance_id"]
        result = self.database.startup_database()
        self.assertTrue(result["ok"])
        after = self.conn.execute("SELECT instance_id FROM database_identity LIMIT 1").fetchone()["instance_id"]
        self.assertEqual(before, after)

    def test_schema_self_heal_preserves_existing_company_rows(self):
        before_count = self.database.get_database_company_count(self.database.DB_PATH)
        self.database.ensure_schema()
        after_count = self.database.get_database_company_count(self.database.DB_PATH)
        self.assertEqual(before_count, 1)
        self.assertEqual(after_count, before_count)

    def test_valid_db_with_companies_is_not_overwritten_by_empty_cloud_backup(self):
        empty_backup = Path(self.database.DB_DIR) / "empty_cloud_candidate.db"
        source_conn = self.database._open_sqlite_connection(path=str(empty_backup))
        try:
            self.database._deploy_full_schema(source_conn)
            self.database._run_lightweight_integrity_checks(source_conn)
            source_conn.commit()
        finally:
            source_conn.close()
        original_identity = self.conn.execute("SELECT instance_id FROM database_identity LIMIT 1").fetchone()["instance_id"]
        fake_bucket = _FakeBucket(
            {
                self.database.FIREBASE_OBJECT_NAME: _FakeBlob(
                    self.database.FIREBASE_OBJECT_NAME,
                    [],
                    source_path=str(empty_backup),
                )
            }
        )
        with mock.patch.object(self.database, "_get_firebase_recovery_bucket", return_value=fake_bucket):
            result = self.database.restore_latest_cloud_backup_to_local()
        self.assertFalse(result["ok"])
        self.assertFalse(result["replacement_performed"])
        self.assertEqual(self.database.get_database_company_count(self.database.DB_PATH), 1)
        current_identity = self.conn.execute("SELECT instance_id FROM database_identity LIMIT 1").fetchone()["instance_id"]
        self.assertEqual(current_identity, original_identity)

    def test_missing_db_recovers_from_valid_cloud_backup(self):
        valid_backup = Path(self.database._create_runtime_snapshot_file(self.database.DB_PATH))
        self.conn.close()
        self.conn = None
        Path(self.database.DB_PATH).unlink()
        fake_bucket = _FakeBucket(
            {
                self.database.FIREBASE_OBJECT_NAME: _FakeBlob(
                    self.database.FIREBASE_OBJECT_NAME,
                    [],
                    source_path=str(valid_backup),
                )
            }
        )
        with mock.patch.object(self.database, "_get_firebase_recovery_bucket", return_value=fake_bucket):
            with mock.patch.object(self.database, "ERP_PRODUCTION_MODE", True):
                result = self.database.startup_database()
        self.assertTrue(result["ok"])
        self.assertTrue(result["recovery_succeeded"])
        self.assertEqual(result["startup_mode"], "restored_from_cloud")
        self.assertEqual(self.database.get_database_company_count(self.database.DB_PATH), 1)
        self.conn = self.database._open_sqlite_connection(path=self.database.DB_PATH)

    def test_safety_backup_created_before_cloud_replacement(self):
        valid_backup = Path(self.database._create_runtime_snapshot_file(self.database.DB_PATH))
        self.conn.close()
        self.conn = None
        Path(self.database.DB_PATH).write_text("not a sqlite database", encoding="utf-8")
        fake_bucket = _FakeBucket(
            {
                self.database.FIREBASE_OBJECT_NAME: _FakeBlob(
                    self.database.FIREBASE_OBJECT_NAME,
                    [],
                    source_path=str(valid_backup),
                )
            }
        )
        with mock.patch.object(self.database, "_get_firebase_recovery_bucket", return_value=fake_bucket):
            result = self.database.restore_latest_cloud_backup_to_local(explicit_recovery_mode=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["replacement_performed"])
        self.assertTrue(result.get("pre_restore_backup_path"))
        self.assertTrue(Path(result["pre_restore_backup_path"]).exists())
        self.assertEqual(self.database.get_database_company_count(self.database.DB_PATH), 1)
        self.conn = self.database._open_sqlite_connection(path=self.database.DB_PATH)
