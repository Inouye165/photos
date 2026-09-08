"""
Automated test suite for Google Drive Backup and Synchronization.
Verifies schema, settings, folder hierarchy, rate limiter, and deletion tracking.
"""

import os
import sys
import time
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

