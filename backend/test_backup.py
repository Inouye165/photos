"""
Automated test suite for Google Drive Backup and Synchronization.
Verifies schema, settings, folder hierarchy, rate limiter, and deletion tracking.
"""

import os
import sys
import time
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backend.database as db_module
from backend.database import (
    init_db,
    get_connection,
    get_backup_settings,
    update_backup_settings,
    cache_gdrive_folder,
    get_cached_gdrive_folder,
    clear_gdrive_folder_cache,
    delete_cached_gdrive_folder,
    delete_cached_gdrive_folder_by_id,
    get_photos_needing_backup,
    update_photo_gdrive_status,
    get_trashed_photos_needing_gdrive_sync,
    get_backup_stats,
    tag_photo_trash
)
from backend.gdrive_service import MONTH_NAMES, GDriveService
from backend.backup_worker import BackupWorker
from googleapiclient.errors import HttpError
import httplib2


class TestGDriveBackup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test database so production photos.db is never touched
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_db = os.path.join(cls.temp_dir.name, "test_backup_photos.db")
        cls.orig_db_path = db_module.DB_PATH
        db_module.DB_PATH = cls.test_db

        init_db(cls.test_db)

        # Seed one sample photo for testing photo status and error handling
        conn = get_connection(cls.test_db)
        with conn:
            conn.execute("""
                INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, classification, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("C:\\fake_dir\\sample.jpg", "sample.jpg", 1024, ".jpg", "fake_sha_123", "VERIFIED_PHOTO", time.time()))
        conn.close()

    @classmethod
    def tearDownClass(cls):
        db_module.DB_PATH = cls.orig_db_path
        import gc
        gc.collect()
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_backup_settings_and_stats(self):
        settings = get_backup_settings()
        self.assertIn("hourly_limit", settings)
        self.assertIn("delay_seconds", settings)
        self.assertIn("root_folder_name", settings)

        updated = update_backup_settings(hourly_limit=30, delay_seconds=20.0)
        self.assertEqual(updated["hourly_limit"], 30)
        self.assertEqual(updated["delay_seconds"], 20.0)

        # Restore defaults
        update_backup_settings(hourly_limit=25, delay_seconds=30.0)

        stats = get_backup_stats()
        self.assertIn("total_photos", stats)
        self.assertIn("backed_up_count", stats)
        self.assertIn("pending_count", stats)
        self.assertIn("failed_count", stats)

    def test_folder_cache(self):
        try:
            clear_gdrive_folder_cache()
            self.assertIsNone(get_cached_gdrive_folder("root::LuminaPhoto Backup"))

            cache_gdrive_folder("root::LuminaPhoto Backup", "test_folder_id_123")
            cached = get_cached_gdrive_folder("root::LuminaPhoto Backup")
            self.assertEqual(cached, "test_folder_id_123")

            delete_cached_gdrive_folder("root::LuminaPhoto Backup")
            self.assertIsNone(get_cached_gdrive_folder("root::LuminaPhoto Backup"))

            cache_gdrive_folder("parent_abc::Subfolder", "child_xyz")
            delete_cached_gdrive_folder_by_id("child_xyz")
            self.assertIsNone(get_cached_gdrive_folder("parent_abc::Subfolder"))
        finally:
            clear_gdrive_folder_cache()

    def test_gdrive_404_cache_self_healing(self):
        """Verifies that 404 responses from Google Drive automatically clear stale folder caches."""
        service = GDriveService.get_instance()
        cache_gdrive_folder("root::LuminaPhoto Backup", "dead_parent_id_404")
        self.assertEqual(get_cached_gdrive_folder("root::LuminaPhoto Backup"), "dead_parent_id_404")

        # Mock HttpError with status 404
        resp = httplib2.Response({'status': '404'})
        http_404 = HttpError(resp, b'{"error": {"message": "File not found: ."}}')

        mock_drive = MagicMock()
        mock_drive.files().list.side_effect = http_404

        with patch.object(service, "get_drive_service", return_value=mock_drive):
            with self.assertRaises(HttpError):
                service.get_or_create_folder("2026", parent_id="dead_parent_id_404")

        # The stale parent ID should have been evicted by the 404 handler
        self.assertIsNone(get_cached_gdrive_folder("root::LuminaPhoto Backup"))

    def test_month_names_mapping(self):
        self.assertEqual(MONTH_NAMES[1], "01 - January")
        self.assertEqual(MONTH_NAMES[9], "09 - September")
        self.assertEqual(MONTH_NAMES[12], "12 - December")

    def test_worker_state_reporting(self):
        worker = BackupWorker.get_instance()
        state = worker.get_state()
        self.assertIn("status", state)
        self.assertIn("hourly_limit", state)
        self.assertIn("uploads_this_hour", state)
        self.assertIn("is_configured", state)
        self.assertTrue(state["is_configured"], "credentials.json should be detected")

    def test_photo_status_updates(self):
        conn = get_connection()
        sample = conn.execute("SELECT id FROM photos LIMIT 1").fetchone()
        conn.close()

        if sample:
            photo_id = sample["id"]
            # Test status update
            update_photo_gdrive_status(photo_id, "backed_up", file_id="drive_file_xyz999")
            
            conn = get_connection()
            updated_photo = conn.execute("SELECT gdrive_file_id, gdrive_backup_status, gdrive_backed_up_at FROM photos WHERE id = ?", (photo_id,)).fetchone()
            conn.close()

            self.assertEqual(updated_photo["gdrive_file_id"], "drive_file_xyz999")
            self.assertEqual(updated_photo["gdrive_backup_status"], "backed_up")
            self.assertIsNotNone(updated_photo["gdrive_backed_up_at"])

            # Test trash detection sync
            tag_photo_trash(photo_id, is_trashed=True)
            trashed_sync = get_trashed_photos_needing_gdrive_sync(limit=10)
            trashed_ids = [p["id"] for p in trashed_sync]
            self.assertIn(photo_id, trashed_ids)

            # Restore photo back to clean state
            tag_photo_trash(photo_id, is_trashed=False)
            update_photo_gdrive_status(photo_id, "pending", file_id=None)

    def test_error_handling_and_retry(self):
        """Verifies that failures record error messages, update stats, and reset on retry."""
        from backend.database import reset_failed_backups
        conn = get_connection()
        sample = conn.execute("SELECT id FROM photos LIMIT 1").fetchone()
        conn.close()

        if sample:
            photo_id = sample["id"]
            # Simulate a network/quota error
            test_err = "Google Drive API HTTP 429: Rate limit exceeded"
            update_photo_gdrive_status(photo_id, "failed", error=test_err)

            conn = get_connection()
            failed_photo = conn.execute("SELECT gdrive_backup_status, gdrive_error FROM photos WHERE id = ?", (photo_id,)).fetchone()
            conn.close()

            self.assertEqual(failed_photo["gdrive_backup_status"], "failed")
            self.assertEqual(failed_photo["gdrive_error"], test_err)

            stats = get_backup_stats()
            self.assertGreaterEqual(stats["failed_count"], 1)

            # Test reset/retry
            reset_count = reset_failed_backups()
            self.assertGreaterEqual(reset_count, 1)

            conn = get_connection()
            cleared_photo = conn.execute("SELECT gdrive_backup_status, gdrive_error FROM photos WHERE id = ?", (photo_id,)).fetchone()
            conn.close()

            self.assertEqual(cleared_photo["gdrive_backup_status"], "pending")
            self.assertIsNone(cleared_photo["gdrive_error"])

    def test_missing_file_handling(self):
        """Verifies that worker handles missing files on disk safely without crashing."""
        from backend.gdrive_service import GDriveService
        service = GDriveService.get_instance()
        fake_photo = {
            "id": 999999,
            "file_path": "C:\\nonexistent_dir_123\\missing_photo.jpg",
            "file_name": "missing_photo.jpg"
        }
        with self.assertRaises(FileNotFoundError):
            service.upload_photo(fake_photo)

    def test_unconfigured_credentials_error_message(self):
        """Verifies that clear 400 error messages are returned when credentials.json is missing."""
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from backend.app import app

        with patch("backend.gdrive_auth.is_configured", return_value=False), \
             patch("backend.backup_worker.is_configured", return_value=False):
            with TestClient(app) as client:
                # 1. Status endpoint should report unconfigured
                res = client.get("/api/backup/status")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertFalse(data.get("is_configured"))
                self.assertEqual(data.get("status"), "unconfigured")

                # 2. Auth URL request should return descriptive 400 error
                res = client.get("/api/backup/auth/url")
                self.assertEqual(res.status_code, 400)
                detail = res.json().get("detail", "")
                self.assertIn("credentials.json", detail)
                self.assertIn("README.md", detail)

                # 3. Start auth request should return descriptive 400 error
                res = client.post("/api/backup/auth/start")
                self.assertEqual(res.status_code, 400)
                detail = res.json().get("detail", "")
                self.assertIn("credentials.json", detail)

    def test_interrupted_uploads_recovery_and_queue_non_blocking(self):
        """Verifies that stuck 'uploading' photos are reset and 'failed' photos do not block 'pending' photos."""
        from backend.database import reset_interrupted_uploads
        conn = get_connection()
        with conn:
            cur1 = conn.execute("""
                INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, date_taken, classification, gdrive_backup_status, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("C:\\fake_dir\\newest_failed.jpg", "newest_failed.jpg", 2048, ".jpg", "sha_newest_fail", "2026-10-20T12:00:00", "VERIFIED_PHOTO", "failed", time.time()))
            failed_id = cur1.lastrowid

            cur2 = conn.execute("""
                INSERT INTO photos (file_path, file_name, file_size, file_extension, sha256, date_taken, classification, gdrive_backup_status, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("C:\\fake_dir\\older_stuck.jpg", "older_stuck.jpg", 2048, ".jpg", "sha_older_stuck", "2026-10-10T12:00:00", "VERIFIED_PHOTO", "uploading", time.time()))
            stuck_id = cur2.lastrowid
        conn.close()

        try:
            # 1. Reset interrupted uploads should transition stuck_id to 'pending'
            recovered = reset_interrupted_uploads()
            self.assertGreaterEqual(recovered, 1)

            # 2. get_photos_needing_backup(limit=1) should return 'pending' photos and NOT get blocked by newest_failed
            queue = get_photos_needing_backup(limit=10)
            queued_ids = [p["id"] for p in queue]
            self.assertIn(stuck_id, queued_ids)
            self.assertNotIn(failed_id, queued_ids)
        finally:
            conn = get_connection()
            with conn:
                conn.execute("DELETE FROM photos WHERE id IN (?, ?)", (failed_id, stuck_id))
            conn.close()

    def test_filename_collision_disambiguation(self):
        """Verifies that two different photos with the same filename in the same month do not collide on Drive."""
        service = GDriveService.get_instance()
        temp_file = os.path.join(self.temp_dir.name, "IMG_0001.JPG")
        with open(temp_file, "wb") as f:
            f.write(b"photo_content_device_b")

        mock_drive = MagicMock()
        # Simulate that IMG_0001.JPG already exists in the folder, but with a DIFFERENT sha256 (from Device A)
        mock_drive.files().list().execute.side_effect = [
            {"files": [{"id": "existing_device_a_id", "name": "IMG_0001.JPG", "size": "99999", "appProperties": {"sha256": "aaaa1111bbbb2222"}}]},
            {"files": []},  # disambiguated name check returns empty
        ]
        mock_drive.files().create().execute.return_value = {"id": "new_device_b_id", "name": "IMG_0001_cccc3333.JPG"}

        photo_data = {
            "id": 42,
            "file_path": temp_file,
            "file_name": "IMG_0001.JPG",
            "file_size": os.path.getsize(temp_file),
            "sha256": "cccc3333dddd4444",
            "date_taken": "2026-09-15T10:00:00",
        }

        with patch.object(service, "get_drive_service", return_value=mock_drive), \
             patch.object(service, "ensure_target_folder", return_value=("folder_sep_2026", "2026", "09 - September")):
            uploaded_id = service.upload_photo(photo_data)

        self.assertEqual(uploaded_id, "new_device_b_id")
        # Verify create was called with disambiguated name and appProperties
        _, create_kwargs = mock_drive.files().create.call_args
        self.assertEqual(create_kwargs["body"]["name"], "IMG_0001_cccc3333.JPG")
        self.assertEqual(create_kwargs["body"]["appProperties"]["sha256"], "cccc3333dddd4444")

    def test_restored_photos_gdrive_untrash_sync(self):
        """Verifies that batch-restored photos are detected and untrashed on Google Drive."""
        from backend.database import get_restored_photos_needing_gdrive_sync
        conn = get_connection()
        sample = conn.execute("SELECT id FROM photos LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(sample)
        photo_id = sample["id"]

        # Simulate a photo that was trashed on Drive and then restored locally via Restore All
        update_photo_gdrive_status(photo_id, status="trashed", file_id="gdrive_restored_123")
        tag_photo_trash(photo_id, is_trashed=False)

        restored_list = get_restored_photos_needing_gdrive_sync()
        restored_ids = [p["id"] for p in restored_list]
        self.assertIn(photo_id, restored_ids)

        worker = BackupWorker.get_instance()
        service = GDriveService.get_instance()
        with patch.object(service, "untrash_photo", return_value=True) as mock_untrash:
            worker._sync_trashed_photos()
            mock_untrash.assert_called_with("gdrive_restored_123", photo_id=photo_id)

        conn = get_connection()
        row = conn.execute("SELECT gdrive_backup_status FROM photos WHERE id = ?", (photo_id,)).fetchone()
        conn.close()
        self.assertEqual(row["gdrive_backup_status"], "backed_up")
        update_photo_gdrive_status(photo_id, status="pending", file_id=None)

    def test_save_credentials_json_validation(self):
        """Verifies that save_credentials_json validates OAuth structure."""
        from backend.gdrive_auth import save_credentials_json
        import backend.gdrive_auth as auth_mod

        with self.assertRaises(ValueError):
            save_credentials_json("not json")

        with self.assertRaises(ValueError):
            save_credentials_json('{"invalid": {}}')

        temp_creds = Path(self.temp_dir.name) / "test_credentials.json"
        with patch.object(auth_mod, "CREDENTIALS_FILE", temp_creds):
            res = save_credentials_json(
                '{"installed": {"client_id": "123.apps.googleusercontent.com", "client_secret": "sec_abc", "project_id": "lumina-test"}}'
            )
            self.assertTrue(res["configured"])
            self.assertEqual(res["client_type"], "installed")
            self.assertTrue(temp_creds.exists())

    def test_upload_size_mismatch_rejected_and_cleaned_up(self):
        """Verifies that a truncated/corrupted upload on Google Drive is rejected and deleted immediately."""
        service = GDriveService.get_instance()
        temp_file = os.path.join(self.temp_dir.name, "integrity_check.jpg")
        with open(temp_file, "wb") as f:
            f.write(b"0123456789" * 100)  # 1000 bytes

        mock_drive = MagicMock()
        mock_drive.files().list().execute.return_value = {"files": []}
        # Simulate Google Drive returning a truncated 500-byte file instead of 1000 bytes
        mock_drive.files().create().execute.return_value = {
            "id": "corrupted_remote_id",
            "name": "integrity_check.jpg",
            "size": "500"
        }

        photo_data = {
            "id": 77,
            "file_path": temp_file,
            "file_name": "integrity_check.jpg",
            "file_size": 1000,
            "sha256": "sha_integrity_1000"
        }

        with patch.object(service, "get_drive_service", return_value=mock_drive), \
             patch.object(service, "ensure_target_folder", return_value=("folder_id", "2026", "10 - October")), \
             patch.object(service, "delete_photo_permanently", return_value=True) as mock_del:
            with self.assertRaises(RuntimeError):
                service.upload_photo(photo_data)
            mock_del.assert_called_once_with("corrupted_remote_id")

    def test_modified_file_sha256_resets_backup_status_to_pending(self):
        """Verifies that modifying a backed-up photo on disk automatically resets gdrive_backup_status to 'pending'."""
        from backend.database import upsert_photo
        fpath = os.path.join(self.temp_dir.name, "editable_photo.jpg")
        pid = upsert_photo({
            "file_path": fpath,
            "file_name": "editable_photo.jpg",
            "file_size": 1024,
            "file_extension": ".jpg",
            "sha256": "original_hash_aaa",
            "classification": "VERIFIED_PHOTO",
            "indexed_at": time.time()
        })
        try:
            update_photo_gdrive_status(pid, "backed_up", file_id="drive_orig_id")
            # Re-upsert with SAME sha256 -> remains 'backed_up'
            upsert_photo({
                "file_path": fpath,
                "file_name": "editable_photo.jpg",
                "file_size": 1024,
                "file_extension": ".jpg",
                "sha256": "original_hash_aaa",
                "classification": "VERIFIED_PHOTO",
                "indexed_at": time.time()
            })
            conn = get_connection()
            status1 = conn.execute("SELECT gdrive_backup_status FROM photos WHERE id = ?", (pid,)).fetchone()[0]
            conn.close()
            self.assertEqual(status1, "backed_up")

            # Re-upsert with NEW sha256 (edited photo) -> automatically transitions to 'pending'
            upsert_photo({
                "file_path": fpath,
                "file_name": "editable_photo.jpg",
                "file_size": 2048,
                "file_extension": ".jpg",
                "sha256": "modified_hash_bbb",
                "classification": "VERIFIED_PHOTO",
                "indexed_at": time.time()
            })
            conn = get_connection()
            status2 = conn.execute("SELECT gdrive_backup_status FROM photos WHERE id = ?", (pid,)).fetchone()[0]
            conn.close()
            self.assertEqual(status2, "pending")
        finally:
            conn = get_connection()
            with conn:
                conn.execute("DELETE FROM photos WHERE id = ?", (pid,))
            conn.close()

    def test_durable_permanent_deletion_queue_and_remote_audit(self):
        """
        Verifies:
        1. Emptying trash when offline persists gdrive_file_id in gdrive_delete_queue and deletes it when online.
        2. Restoring a photo whose Drive Trash copy expired (404) automatically re-queues it for fresh upload.
        3. verify_backups() detects missing remote files (404) and re-queues them for upload.
        """
        from backend.database import (
            enqueue_gdrive_permanent_delete,
            get_pending_gdrive_deletes,
            upsert_photo
        )
        service = GDriveService.get_instance()
        worker = BackupWorker.get_instance()

        # 1. Durable permanent delete queue
        enqueue_gdrive_permanent_delete("offline_purge_fid_999", photo_id=888, file_name="purged.jpg")
        pending = [d["gdrive_file_id"] for d in get_pending_gdrive_deletes()]
        self.assertIn("offline_purge_fid_999", pending)

        # Simulate offline failure first
        with patch.object(service, "delete_photo_permanently", return_value=False):
            worker._sync_trashed_photos()
        still_pending = [d["gdrive_file_id"] for d in get_pending_gdrive_deletes()]
        self.assertIn("offline_purge_fid_999", still_pending)

        # Simulate online success -> removed from queue
        with patch.object(service, "delete_photo_permanently", return_value=True):
            worker._sync_trashed_photos()
        after_online = [d["gdrive_file_id"] for d in get_pending_gdrive_deletes()]
        self.assertNotIn("offline_purge_fid_999", after_online)

        # 2. Restore after 30-day Drive Trash expiry (404) -> re-queues photo as 'pending'
        pid = upsert_photo({
            "file_path": os.path.join(self.temp_dir.name, "expired_in_drive_trash.jpg"),
            "file_name": "expired_in_drive_trash.jpg",
            "file_size": 4096,
            "file_extension": ".jpg",
            "sha256": "sha_expired_404",
            "classification": "VERIFIED_PHOTO",
            "indexed_at": time.time()
        })
        try:
            update_photo_gdrive_status(pid, "trashed", file_id="expired_drive_id_404")
            resp_404 = httplib2.Response({'status': '404'})
            http_404 = HttpError(resp_404, b'{"error": {"message": "File not found"}}')

            mock_drive = MagicMock()
            mock_drive.files().update.side_effect = http_404
            with patch.object(service, "get_drive_service", return_value=mock_drive):
                result = service.untrash_photo("expired_drive_id_404", photo_id=pid)
                self.assertFalse(result)

            conn = get_connection()
            row = conn.execute("SELECT gdrive_file_id, gdrive_backup_status FROM photos WHERE id = ?", (pid,)).fetchone()
            conn.close()
            self.assertIsNone(row["gdrive_file_id"])
            self.assertEqual(row["gdrive_backup_status"], "pending")

            # 3. verify_backups() detects 404 on a supposedly 'backed_up' photo and re-queues it
            update_photo_gdrive_status(pid, "backed_up", file_id="deleted_on_web_id_404")
            mock_drive.files().get.side_effect = http_404
            with patch.object(service, "get_drive_service", return_value=mock_drive):
                report = service.verify_backups()
                self.assertGreaterEqual(report["requeued_missing"], 1)

            conn = get_connection()
            row2 = conn.execute("SELECT gdrive_file_id, gdrive_backup_status FROM photos WHERE id = ?", (pid,)).fetchone()
            conn.close()
            self.assertIsNone(row2["gdrive_file_id"])
            self.assertEqual(row2["gdrive_backup_status"], "pending")
        finally:
            conn = get_connection()
            with conn:
                conn.execute("DELETE FROM photos WHERE id = ?", (pid,))
            conn.close()


if __name__ == "__main__":
    unittest.main()

