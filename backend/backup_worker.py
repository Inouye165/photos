"""
Background Backup Worker for Google Drive.
Operates with conservative throttling:
- Strict hourly upload cap (e.g. 25 photos/hr)
- Spacing delay between uploads (e.g. 30s)
- Low-priority daemon thread with minimal CPU and network impact
- Automatic two-way sync for trashing/deleting photos
"""

import os
import time
import threading
from typing import Optional, Dict, Any, List
from collections import deque

from backend.gdrive_auth import is_authenticated, is_configured
from backend.gdrive_service import GDriveService
from backend.database import (
    get_backup_settings,
    update_backup_settings,
    get_photos_needing_backup,
    get_trashed_photos_needing_gdrive_sync,
    get_restored_photos_needing_gdrive_sync,
    get_pending_gdrive_deletes,
    remove_pending_gdrive_delete,
    record_gdrive_delete_error,
    reset_interrupted_uploads,
    reset_failed_backups,
    update_photo_gdrive_status,
    get_backup_stats
)


class BackupWorker:
    _instance: Optional['BackupWorker'] = None

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._recent_upload_timestamps = deque()  # stores epoch timestamps of uploads in last 3600s
        self._lock = threading.Lock()
        self._current_file: Optional[str] = None
        self._current_progress: int = 0
        self._force_immediate: bool = False
        self._status: str = "idle"  # idle, uploading, throttled, paused, unauthenticated, error
        self._status_message: str = ""

    @classmethod
    def get_instance(cls) -> 'BackupWorker':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self):
        """Starts the background worker thread if not already running."""
        try:
            recovered = reset_interrupted_uploads()
            if recovered:
                print(f"[GDrive Worker] Recovered {recovered} interrupted upload(s) back to pending.")
        except Exception as e:
            print(f"[GDrive Worker] Error resetting interrupted uploads: {e}")

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="GDriveBackupWorker", daemon=True)
            self._thread.start()
            print("[GDrive Worker] Background backup worker started.")

    def stop(self):
        """Signals the background worker to stop gracefully."""
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        print("[GDrive Worker] Background backup worker stopped.")

    def trigger_wake(self):
        """Wakes up the worker immediately (e.g. after settings change or OAuth completion)."""
        self._wake_event.set()

    def trigger_sync_now(self, retry_failed: bool = False) -> Dict[str, Any]:
        """
        Triggers an immediate backup pass, optionally resetting failed photos first
        and unpausing if paused.
        """
        retried = 0
        if retry_failed:
            retried = reset_failed_backups()
        reset_interrupted_uploads()
        with self._lock:
            self._force_immediate = True
        self._wake_event.set()
        return {"triggered": True, "retried_count": retried}

    def get_state(self) -> Dict[str, Any]:
        """Returns the real-time operational status of the worker."""
        self._prune_hourly_window()
        stats = get_backup_stats()
        settings = get_backup_settings()

        with self._lock:
            is_paused = bool(settings.get("is_paused", 0))
            authenticated = is_authenticated()
            configured = is_configured()

            effective_status = self._status
            if not configured:
                effective_status = "unconfigured"
            elif not authenticated:
                effective_status = "unauthenticated"
            elif is_paused:
                effective_status = "paused"

            state_payload = {
                "status": effective_status,
                "status_message": self._status_message,
                "current_file": self._current_file,
                "current_file_progress": self._current_progress,
                "uploads_this_hour": len(self._recent_upload_timestamps),
                "hourly_limit": settings.get("hourly_limit", 25),
                "delay_seconds": settings.get("delay_seconds", 30.0),
                "root_folder_name": settings.get("root_folder_name", "LuminaPhoto Backup"),
                "is_paused": is_paused,
                "is_authenticated": authenticated,
                "is_configured": configured,
                "stats": stats,
                "drive_quota": None
            }

        if authenticated:
            try:
                state_payload["drive_quota"] = GDriveService.get_instance().get_account_quota()
            except Exception:
                pass
        return state_payload

    def _prune_hourly_window(self):
        """Removes upload timestamps older than 1 hour (3600s)."""
        cutoff = time.time() - 3600.0
        with self._lock:
            while self._recent_upload_timestamps and self._recent_upload_timestamps[0] < cutoff:
                self._recent_upload_timestamps.popleft()

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._prune_hourly_window()
                settings = get_backup_settings()
                is_paused = bool(settings.get("is_paused", 0))
                hourly_limit = max(1, settings.get("hourly_limit", 25))
                delay_seconds = max(1.0, settings.get("delay_seconds", 30.0))

                # Check if paused
                if is_paused:
                    with self._lock:
                        self._status = "paused"
                        self._status_message = "Backup is paused by user"
                        self._current_file = None
                        self._current_progress = 0
                    self._wake_event.wait(timeout=10.0)
                    self._wake_event.clear()
                    continue

                # Check if authenticated
                if not is_authenticated():
                    with self._lock:
                        self._status = "unauthenticated"
                        self._status_message = "Awaiting Google Drive authentication"
                        self._current_file = None
                        self._current_progress = 0
                    self._wake_event.wait(timeout=15.0)
                    self._wake_event.clear()
                    continue

                # 1. Process Trashed & Restored Photo Sync first (two-way trash/restore)
                self._sync_trashed_photos()

                # 2. Check Hourly Rate Limit (unless user explicitly clicked Sync Now)
                with self._lock:
                    current_hourly_count = len(self._recent_upload_timestamps)
                    force_now = self._force_immediate
                    self._force_immediate = False

                if current_hourly_count >= hourly_limit and not force_now:
                    with self._lock:
                        self._status = "throttled"
                        self._status_message = f"Hourly cap reached ({current_hourly_count}/{hourly_limit} photos). Resting..."
                        self._current_file = None
                        self._current_progress = 0

                    # Sleep until oldest upload falls outside the 1-hour window or wake is triggered
                    with self._lock:
                        oldest = self._recent_upload_timestamps[0] if self._recent_upload_timestamps else time.time()
                    wait_time = max(5.0, min(60.0, 3600.0 - (time.time() - oldest) + 1.0))
                    self._wake_event.wait(timeout=wait_time)
                    self._wake_event.clear()
                    continue

                # 3. Check for next photo to back up
                photos_to_backup = get_photos_needing_backup(limit=5)
                if not photos_to_backup:
                    with self._lock:
                        self._status = "idle"
                        self._status_message = "All photos are backed up to Google Drive."
                        self._current_file = None
                        self._current_progress = 0
                    # Sleep when everything is backed up, waking if new photos are imported
                    self._wake_event.wait(timeout=30.0)
                    self._wake_event.clear()
                    continue

                # Pick the first photo that exists on disk; immediately mark missing files as failed without delay
                selected_photo = None
                for candidate in photos_to_backup:
                    fpath = candidate.get("file_path")
                    if not fpath or not os.path.exists(fpath):
                        update_photo_gdrive_status(
                            candidate["id"],
                            status="failed",
                            error=f"Local file does not exist: {fpath}"
                        )
                        continue
                    selected_photo = candidate
                    break

                if selected_photo is None:
                    # All fetched candidates were missing on disk; immediately loop to check remaining queue
                    continue

                self._upload_single_photo(selected_photo)

                # 4. Spacing delay between uploads to protect CPU/network
                self._wake_event.wait(timeout=delay_seconds)
                self._wake_event.clear()

            except Exception as e:
                print(f"[GDrive Worker Loop Error]: {e}")
                with self._lock:
                    self._status = "error"
                    self._status_message = f"Backup loop error: {e}"
                    self._current_progress = 0
                self._wake_event.wait(timeout=30.0)
                self._wake_event.clear()

    def _sync_trashed_photos(self):
        """
        Synchronizes:
        1. Locally trashed photos -> Google Drive Trash (preserving backup until Trash is emptied).
        2. Locally restored photos -> Untrashed on Google Drive (or re-uploaded if 404 on Drive).
        3. Permanently deleted photos (Empty Trash / Space Purge) -> Permanently deleted from Google Drive.
        """
        service = GDriveService.get_instance()

        # 1. Trash on Drive any photos trashed locally
        trashed_items = get_trashed_photos_needing_gdrive_sync(limit=20)
        for item in trashed_items:
            if self._stop_event.is_set():
                break
            gdrive_id = item.get("gdrive_file_id")
            photo_id = item.get("id")
            if gdrive_id and photo_id:
                try:
                    success = service.trash_photo(gdrive_id)
                    if success:
                        update_photo_gdrive_status(photo_id, status="trashed")
                except Exception as e:
                    print(f"[GDrive Worker] Failed to trash photo {photo_id} on Drive: {e}")

        # 2. Untrash on Drive any photos restored locally (e.g. via Restore All or Batch Restore)
        restored_items = get_restored_photos_needing_gdrive_sync(limit=20)
        for item in restored_items:
            if self._stop_event.is_set():
                break
            gdrive_id = item.get("gdrive_file_id")
            photo_id = item.get("id")
            if gdrive_id and photo_id:
                try:
                    success = service.untrash_photo(gdrive_id, photo_id=photo_id)
                    if success:
                        update_photo_gdrive_status(photo_id, status="backed_up")
                except Exception as e:
                    print(f"[GDrive Worker] Failed to untrash photo {photo_id} on Drive: {e}")

        # 3. Flush persistent permanent-deletion queue (from Empty Trash / Low-Space Purge)
        pending_deletes = get_pending_gdrive_deletes(limit=30)
        for item in pending_deletes:
            if self._stop_event.is_set():
                break
            gdrive_id = item.get("gdrive_file_id")
            if gdrive_id:
                try:
                    if service.delete_photo_permanently(gdrive_id):
                        remove_pending_gdrive_delete(gdrive_id)
                    else:
                        record_gdrive_delete_error(gdrive_id, "Google Drive delete_photo_permanently returned False")
                except Exception as e:
                    record_gdrive_delete_error(gdrive_id, str(e))

    def _upload_single_photo(self, photo: Dict[str, Any]):
        """Uploads one photo and records status, progress, & timestamps."""
        service = GDriveService.get_instance()
        photo_id = photo["id"]
        file_name = photo.get("file_name", f"photo_{photo_id}")
        is_trashed = bool(photo.get("is_trashed", 0))

        with self._lock:
            self._status = "uploading"
            self._current_file = file_name
            self._current_progress = 0
            self._status_message = f"Backing up {file_name}..."

        def on_progress(pct: int):
            with self._lock:
                self._current_progress = pct
                self._status_message = f"Backing up {file_name} ({pct}%)..."

        try:
            update_photo_gdrive_status(photo_id, status="uploading")
            drive_file_id = service.upload_photo(photo, progress_callback=on_progress)

            if is_trashed and drive_file_id:
                # Photo is in local Trash: keep its backup in Google Drive Trash until Empty Trash
                service.trash_photo(drive_file_id)
                update_photo_gdrive_status(photo_id, status="trashed", file_id=drive_file_id)
            else:
                update_photo_gdrive_status(photo_id, status="backed_up", file_id=drive_file_id)

            now = time.time()
            with self._lock:
                self._recent_upload_timestamps.append(now)
            update_backup_settings(last_backup_at=now)

            with self._lock:
                self._status = "idle"
                self._status_message = f"Backed up {file_name}"
                self._current_file = None
                self._current_progress = 100

        except Exception as e:
            err_msg = str(e)
            print(f"[GDrive Worker] Upload failed for photo {photo_id}: {err_msg}")
            update_photo_gdrive_status(photo_id, status="failed", error=err_msg)
            with self._lock:
                self._status = "error"
                self._status_message = f"Upload failed for {file_name}: {err_msg[:60]}"
                self._current_file = None
                self._current_progress = 0
