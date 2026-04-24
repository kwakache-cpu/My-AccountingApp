from pathlib import Path
from unittest import mock

from test_support import ERPIsolatedTestCase


class _FakeBlob:
    def __init__(self, name, uploads):
        self.name = name
        self.uploads = uploads

    def upload_from_filename(self, filename):
        self.uploads.append((self.name, Path(filename).name))


class _FakeBucket:
    def __init__(self):
        self.uploads = []

    def blob(self, name):
        return _FakeBlob(name, self.uploads)


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
