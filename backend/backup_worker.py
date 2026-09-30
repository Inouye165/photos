"""
Background Backup Worker for Google Drive.
Operates with conservative throttling:
- Strict hourly upload cap (e.g. 25 photos/hr)
- Spacing delay between uploads (e.g. 30s)
- Low-priority daemon thread with minimal CPU and network impact
- Automatic two-way sync for trashing/deleting photos
"""

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
        self._status: str = "idle"  # idle, uploading, throttled, paused, unauthenticated, error
        self._status_message: str = ""

    @classmethod
    def get_instance(cls) -> 'BackupWorker':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self):
        """Starts the background worker thread if not already running."""
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

            return {
                "status": effective_status,
                "status_message": self._status_message,
                "current_file": self._current_file,
                "uploads_this_hour": len(self._recent_upload_timestamps),
                "hourly_limit": settings.get("hourly_limit", 25),
                "delay_seconds": settings.get("delay_seconds", 30.0),
                "is_paused": is_paused,
                "is_authenticated": authenticated,
                "is_configured": configured,
                "stats": stats
            }

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
                    self._wake_event.wait(timeout=10.0)
                    self._wake_event.clear()
                    continue

                # Check if authenticated
                if not is_authenticated():
                    with self._lock:
                        self._status = "unauthenticated"
                        self._status_message = "Awaiting Google Drive authentication"
                        self._current_file = None
                    self._wake_event.wait(timeout=15.0)
                    self._wake_event.clear()
                    continue

                # 1. Process Trashed Photo Sync first (two-way deletion)
                self._sync_trashed_photos()

                # 2. Check Hourly Rate Limit
                with self._lock:
                    current_hourly_count = len(self._recent_upload_timestamps)

                if current_hourly_count >= hourly_limit:
                    with self._lock:
                        self._status = "throttled"
                        self._status_message = f"Hourly cap reached ({current_hourly_count}/{hourly_limit} photos). Resting..."
                        self._current_file = None

                    # Sleep until oldest upload falls outside the 1-hour window or wake is triggered
                    with self._lock:
                        oldest = self._recent_upload_timestamps[0] if self._recent_upload_timestamps else time.time()
                    wait_time = max(5.0, min(60.0, 3600.0 - (time.time() - oldest) + 1.0))
                    self._wake_event.wait(timeout=wait_time)
                    self._wake_event.clear()
                    continue

                # 3. Check for next photo to back up
                photos_to_backup = get_photos_needing_backup(limit=1)
                if not photos_to_backup:
                    with self._lock:
                        self._status = "idle"
                        self._status_message = "All photos are backed up to Google Drive."
                        self._current_file = None
                    # Sleep when everything is backed up, waking if new photos are imported
                    self._wake_event.wait(timeout=30.0)
                    self._wake_event.clear()
                    continue

                photo = photos_to_backup[0]
                self._upload_single_photo(photo)

                # 4. Spacing delay between uploads to protect CPU/network
                self._wake_event.wait(timeout=delay_seconds)
                self._wake_event.clear()

            except Exception as e:
                print(f"[GDrive Worker Loop Error]: {e}")
                with self._lock:
                    self._status = "error"
                    self._status_message = f"Backup loop error: {e}"
                self._wake_event.wait(timeout=30.0)
                self._wake_event.clear()

    def _sync_trashed_photos(self):
        """Finds locally trashed photos that exist on Google Drive and trashes them there."""
        service = GDriveService.get_instance()
        trashed_items = get_trashed_photos_needing_gdrive_sync(limit=10)
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

    def _upload_single_photo(self, photo: Dict[str, Any]):
        """Uploads one photo and records status & timestamps."""
        service = GDriveService.get_instance()
        photo_id = photo["id"]
        file_name = photo.get("file_name", f"photo_{photo_id}")

        with self._lock:
            self._status = "uploading"
            self._current_file = file_name
            self._status_message = f"Backing up {file_name}..."

        try:
            update_photo_gdrive_status(photo_id, status="uploading")
            drive_file_id = service.upload_photo(photo)

            # Success
            update_photo_gdrive_status(photo_id, status="backed_up", file_id=drive_file_id)
            now = time.time()
            with self._lock:
                self._recent_upload_timestamps.append(now)
            update_backup_settings(last_backup_at=now)

            with self._lock:
                self._status = "idle"
                self._status_message = f"Backed up {file_name}"
                self._current_file = None

        except Exception as e:
            err_msg = str(e)
            print(f"[GDrive Worker] Upload failed for photo {photo_id}: {err_msg}")
            update_photo_gdrive_status(photo_id, status="failed", error=err_msg)
            with self._lock:
                self._status = "error"
                self._status_message = f"Upload failed for {file_name}: {err_msg[:60]}"
                self._current_file = None
