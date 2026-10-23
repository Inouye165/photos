"""
Google Drive Service for LuminaPhoto.
Handles folder hierarchy creation (Root -> Year -> Month),
photo uploading with rate limiting safeguards, and two-way trash deletion.
"""

import os
import mimetypes
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from backend.gdrive_auth import get_credentials, is_authenticated
from backend.database import (
    get_connection,
    get_backup_settings,
    get_cached_gdrive_folder,
    cache_gdrive_folder,
    clear_gdrive_folder_cache,
    delete_cached_gdrive_folder,
    delete_cached_gdrive_folder_by_id,
    clear_photo_gdrive_file_id,
    update_photo_gdrive_status
)

MONTH_NAMES = {
    1: "01 - January",
    2: "02 - February",
    3: "03 - March",
    4: "04 - April",
    5: "05 - May",
    6: "06 - June",
    7: "07 - July",
    8: "08 - August",
    9: "09 - September",
    10: "10 - October",
    11: "11 - November",
    12: "12 - December"
}


def _escape_gdrive_query_value(value: str) -> str:
    """Escapes backslashes and single quotes for Google Drive API search queries."""
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


class GDriveService:
    _instance: Optional['GDriveService'] = None

    def __init__(self):
        self._service = None
        self._local = threading.local()
        self._generation = 0
        self._quota_cache: Optional[Dict[str, Any]] = None
        self._quota_cached_at: float = 0.0

    @classmethod
    def get_instance(cls) -> 'GDriveService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_drive_service(self):
        """
        Returns a thread-local authorized Google Drive API v3 client, or None.
        Automatically refreshes expired OAuth tokens before returning.
        """
        if self._service is not None:
            return self._service
        if not is_authenticated():
            return None

        local_gen = getattr(self._local, "generation", -1)
        local_service = getattr(self._local, "service", None)
        local_creds = getattr(self._local, "creds", None)

        needs_rebuild = (
            local_service is None
            or local_gen != self._generation
            or local_creds is None
            or not getattr(local_creds, "valid", False)
            or getattr(local_creds, "expired", False)
        )

        if needs_rebuild:
            creds = get_credentials()
            if not creds:
                self._local.service = None
                self._local.creds = None
                return None
            local_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            self._local.service = local_service
            self._local.creds = creds
            self._local.generation = self._generation

        return local_service

    def reset_service(self):
        self._service = None
        self._generation += 1
        self._local = threading.local()
        self._quota_cache = None
        self._quota_cached_at = 0.0
        clear_gdrive_folder_cache()

    def get_account_quota(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetches the connected Google account email and real-time Google Drive storage quota
        (total, used, used in Drive Trash, and free bytes). Cached for 60s.
        """
        import time
        now = time.time()
        if not force_refresh and self._quota_cache is not None and (now - self._quota_cached_at) < 60.0:
            return self._quota_cache

        service = self.get_drive_service()
        if not service:
            return None

        try:
            about = service.about().get(fields="user(displayName,emailAddress),storageQuota").execute()
            if not isinstance(about, dict):
                return self._quota_cache
            user = about.get("user") or {}
            quota = about.get("storageQuota") or {}
            limit_bytes = int(quota.get("limit", 0)) if quota.get("limit") else 0
            usage_bytes = int(quota.get("usage", 0)) if quota.get("usage") else 0
            trash_bytes = int(quota.get("usageInDriveTrash", 0)) if quota.get("usageInDriveTrash") else 0
            free_bytes = max(0, limit_bytes - usage_bytes) if limit_bytes > 0 else 0

            info = {
                "email": user.get("emailAddress") or "",
                "display_name": user.get("displayName") or "",
                "limit_bytes": limit_bytes,
                "usage_bytes": usage_bytes,
                "trash_bytes": trash_bytes,
                "free_bytes": free_bytes,
                "limit_gb": round(limit_bytes / (1024 ** 3), 2) if limit_bytes > 0 else 0,
                "usage_gb": round(usage_bytes / (1024 ** 3), 2),
                "trash_mb": round(trash_bytes / (1024 ** 2), 2),
                "free_gb": round(free_bytes / (1024 ** 3), 2) if limit_bytes > 0 else 0,
            }
            self._quota_cache = info
            self._quota_cached_at = now
            return info
        except Exception:
            return self._quota_cache

    def get_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """
        Finds or creates a Google Drive folder under parent_id (or root if parent_id is None).
        Caches folder IDs to avoid redundant API queries.
        """
        cache_key = f"{parent_id or 'root'}::{folder_name}"
        cached_id = get_cached_gdrive_folder(cache_key)
        if cached_id:
            return cached_id

        service = self.get_drive_service()
        if not service:
            raise RuntimeError("Google Drive is not authenticated.")

        # Query existing folder
        safe_folder_name = _escape_gdrive_query_value(folder_name)
        query_parts = [
            f"name = '{safe_folder_name}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false"
        ]
        if parent_id:
            safe_parent_id = _escape_gdrive_query_value(parent_id)
            query_parts.append(f"'{safe_parent_id}' in parents")
        else:
            query_parts.append("'root' in parents")

        query = " and ".join(query_parts)

        try:
            response = service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
        except HttpError as e:
            if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                # Parent folder ID does not exist in Google Drive or was deleted
                if parent_id:
                    delete_cached_gdrive_folder_by_id(parent_id)
                delete_cached_gdrive_folder(cache_key)
            raise

        files = response.get('files', [])
        if files:
            folder_id = files[0]['id']
        else:
            # Create folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]

            try:
                created = service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = created.get('id')
            except HttpError as e:
                if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                    if parent_id:
                        delete_cached_gdrive_folder_by_id(parent_id)
                    delete_cached_gdrive_folder(cache_key)
                raise

        cache_gdrive_folder(cache_key, folder_id)
        return folder_id

    def ensure_target_folder(self, date_taken: Optional[str], file_modified_at: Optional[float], _retried: bool = False) -> Tuple[str, str, str]:
        """
        Resolves the Year and Month subfolders:
        Root Folder (e.g. 'LuminaPhoto Backup')
          -> Year (e.g. '2024')
             -> Month (e.g. '09 - September')

        Returns: (target_folder_id, year_str, month_str)
        """
        try:
            settings = get_backup_settings()
            root_name = settings.get("root_folder_name", "LuminaPhoto Backup")

            # 1. Root folder
            root_folder_id = self.get_or_create_folder(root_name, parent_id=None)

            # Parse year and month
            dt = None
            if date_taken:
                clean_date = str(date_taken).replace(":", "-").replace("/", "-")
                try:
                    dt = datetime.fromisoformat(clean_date[:19])
                except Exception:
                    pass

            if dt is None and file_modified_at:
                try:
                    dt = datetime.fromtimestamp(file_modified_at)
                except Exception:
                    pass

            if dt is None:
                dt = datetime.now()

            year_str = str(dt.year)
            month_str = MONTH_NAMES.get(dt.month, f"{dt.month:02d}")

            # 2. Year subfolder
            year_folder_id = self.get_or_create_folder(year_str, parent_id=root_folder_id)

            # 3. Month subfolder
            month_folder_id = self.get_or_create_folder(month_str, parent_id=year_folder_id)

            return month_folder_id, year_str, month_str
        except HttpError as e:
            if getattr(e, 'resp', None) is not None and e.resp.status == 404 and not _retried:
                # Parent folder ID was invalid or deleted on Google Drive.
                # Invalidate folder cache and retry once from root cleanly.
                print("[GDrive Service] Encountered 404 for folder hierarchy; clearing folder cache and retrying...")
                clear_gdrive_folder_cache()
                return self.ensure_target_folder(date_taken, file_modified_at, _retried=True)
            raise

    def upload_photo(
        self,
        photo_data: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        Uploads a photo to Google Drive inside the appropriate Year/Month subfolder.
        Prevents filename collisions when different photos share the same name in the same month
        by verifying SHA-256 / file size and disambiguating filenames when needed.
        Returns the created or matched Google Drive file ID.
        """
        file_path = photo_data.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Local file does not exist: {file_path}")

        service = self.get_drive_service()
        if not service:
            raise RuntimeError("Google Drive is not authenticated.")

        file_name = photo_data.get("file_name") or os.path.basename(file_path)
        date_taken = photo_data.get("date_taken")
        file_modified_at = photo_data.get("file_modified_at")
        sha256 = photo_data.get("sha256")
        file_size = photo_data.get("file_size")
        if file_size is None:
            try:
                file_size = os.path.getsize(file_path)
            except Exception:
                file_size = None

        target_folder_id, _, _ = self.ensure_target_folder(date_taken, file_modified_at)

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/jpeg"

        # Check if file with same name already exists in this folder
        safe_file_name = _escape_gdrive_query_value(file_name)
        safe_target_folder_id = _escape_gdrive_query_value(target_folder_id)
        existing_query = (
            f"name = '{safe_file_name}' and '{safe_target_folder_id}' in parents and trashed = false"
        )
        existing_resp = service.files().list(
            q=existing_query,
            spaces='drive',
            fields='files(id, name, size, appProperties)',
            pageSize=10
        ).execute()
        existing_files = existing_resp.get('files', [])

        upload_name = file_name
        if existing_files:
            for existing in existing_files:
                remote_props = existing.get("appProperties") or {}
                remote_sha = remote_props.get("sha256")
                remote_size = existing.get("size")

                if sha256 and remote_sha:
                    if str(remote_sha) == str(sha256):
                        if progress_callback:
                            progress_callback(100)
                        return existing["id"]
                elif remote_size is not None and file_size is not None:
                    try:
                        if int(remote_size) == int(file_size):
                            if progress_callback:
                                progress_callback(100)
                            return existing["id"]
                    except (ValueError, TypeError):
                        pass
                elif not remote_sha and remote_size is None:
                    # Fallback when remote metadata has neither appProperties nor size
                    if progress_callback:
                        progress_callback(100)
                    return existing["id"]

            # Another distinct photo with the same filename exists in this month folder!
            # Disambiguate filename using short SHA-256 or photo ID so neither overwrites or collides.
            stem, ext = os.path.splitext(file_name)
            suffix = str(sha256)[:8] if sha256 else str(photo_data.get("id", "copy"))
            upload_name = f"{stem}_{suffix}{ext}"

            safe_disambig_name = _escape_gdrive_query_value(upload_name)
            disambig_query = (
                f"name = '{safe_disambig_name}' and '{safe_target_folder_id}' in parents and trashed = false"
            )
            disambig_resp = service.files().list(
                q=disambig_query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            disambig_files = disambig_resp.get('files', [])
            if disambig_files:
                if progress_callback:
                    progress_callback(100)
                return disambig_files[0]['id']

        chunk_threshold = 5 * 1024 * 1024  # 5 MB
        use_chunks = bool(file_size and int(file_size) > chunk_threshold)
        media = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            chunksize=chunk_threshold if use_chunks else -1,
            resumable=True
        )
        file_metadata: Dict[str, Any] = {
            'name': upload_name,
            'parents': [target_folder_id]
        }
        app_props: Dict[str, str] = {}
        if sha256:
            app_props['sha256'] = str(sha256)
        if photo_data.get("id") is not None:
            app_props['lumina_photo_id'] = str(photo_data["id"])
        if app_props:
            file_metadata['appProperties'] = app_props

        if progress_callback:
            progress_callback(0)

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, size, md5Checksum'
        )

        created_file = None
        if use_chunks and hasattr(request, "next_chunk") and type(request).__name__ == "HttpRequest":
            while created_file is None:
                status, created_file = request.next_chunk()
                if status and progress_callback:
                    progress_callback(min(99, max(1, int(status.progress() * 100))))
        else:
            created_file = request.execute()

        created_dict = created_file or {}
        created_id = created_dict.get('id')
        remote_size = created_dict.get('size')
        if remote_size is not None and file_size is not None:
            try:
                if int(remote_size) != int(file_size):
                    if created_id:
                        self.delete_photo_permanently(created_id)
                    raise RuntimeError(
                        f"Upload integrity check failed: remote size ({remote_size}) != local size ({file_size})"
                    )
            except (ValueError, TypeError):
                pass

        if progress_callback:
            progress_callback(100)

        return created_id

    def trash_photo(self, gdrive_file_id: str) -> bool:
        """
        Moves a file to Google Drive trash (two-way sync soft-deletion).
        """
        service = self.get_drive_service()
        if not service or not gdrive_file_id:
            return False

        try:
            service.files().update(
                fileId=gdrive_file_id,
                body={'trashed': True}
            ).execute()
            return True
        except HttpError as e:
            if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                # File already doesn't exist on Drive
                return True
            print(f"[GDrive Service] Error trashing file {gdrive_file_id}: {e}")
            return False

    def untrash_photo(self, gdrive_file_id: str, photo_id: Optional[int] = None) -> bool:
        """
        Restores a file from Google Drive trash if untrashed locally.
        If the file was already purged from Google Drive Trash (HTTP 404) and photo_id is provided,
        clears gdrive_file_id and re-queues the local photo for a fresh backup upload.
        """
        service = self.get_drive_service()
        if not service or not gdrive_file_id:
            return False

        try:
            service.files().update(
                fileId=gdrive_file_id,
                body={'trashed': False}
            ).execute()
            return True
        except HttpError as e:
            if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                if photo_id is not None:
                    print(f"[GDrive Service] File {gdrive_file_id} not found on Drive during restore; re-queuing photo {photo_id} for upload.")
                    clear_photo_gdrive_file_id(photo_id)
                return False
            print(f"[GDrive Service] Error untrashing file {gdrive_file_id}: {e}")
            return False

    def delete_photo_permanently(self, gdrive_file_id: str) -> bool:
        """
        Permanently deletes a file from Google Drive (e.g. upon trash purge).
        """
        service = self.get_drive_service()
        if not service or not gdrive_file_id:
            return False

        try:
            service.files().delete(fileId=gdrive_file_id).execute()
            self._quota_cached_at = 0.0
            return True
        except HttpError as e:
            if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                self._quota_cached_at = 0.0
                return True
            print(f"[GDrive Service] Error deleting file {gdrive_file_id}: {e}")
            return False

    def verify_backups(self, limit: int = 500, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Audits backed-up and trashed photos against Google Drive to guarantee:
        1. Every photo marked 'backed_up' locally actually exists on Google Drive with matching file size
           and is not in Drive Trash (if missing or size-mismatched, re-queues for upload).
        2. Every photo in local Trash with a Drive backup is in Drive Trash (or re-queued if missing).
        """
        service = self.get_drive_service()
        if not service:
            raise RuntimeError("Google Drive is not authenticated.")

        conn = get_connection(db_path)
        rows = conn.execute("""
            SELECT id, file_name, file_size, is_trashed, gdrive_file_id, gdrive_backup_status
            FROM photos
            WHERE gdrive_file_id IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()

        checked = 0
        verified_ok = 0
        requeued_missing = 0
        trashed_synced = 0
        restored_on_drive = 0

        for row in rows:
            checked += 1
            pid = row["id"]
            fid = row["gdrive_file_id"]
            is_trashed = bool(row["is_trashed"])
            local_size = row["file_size"]

            try:
                meta = service.files().get(
                    fileId=fid,
                    fields="id, name, size, trashed"
                ).execute()
            except HttpError as e:
                if getattr(e, 'resp', None) is not None and e.resp.status == 404:
                    clear_photo_gdrive_file_id(pid, db_path=db_path)
                    requeued_missing += 1
                    continue
                raise

            remote_trashed = bool(meta.get("trashed", False))
            remote_size = meta.get("size")

            if remote_size is not None and local_size is not None:
                try:
                    if int(remote_size) != int(local_size):
                        clear_photo_gdrive_file_id(pid, db_path=db_path)
                        requeued_missing += 1
                        continue
                except (ValueError, TypeError):
                    pass

            if is_trashed and not remote_trashed:
                if self.trash_photo(fid):
                    update_photo_gdrive_status(pid, status="trashed", db_path=db_path)
                    trashed_synced += 1
            elif not is_trashed and remote_trashed:
                if self.untrash_photo(fid, photo_id=pid):
                    update_photo_gdrive_status(pid, status="backed_up", db_path=db_path)
                    restored_on_drive += 1
            else:
                verified_ok += 1

        return {
            "checked": checked,
            "verified_ok": verified_ok,
            "requeued_missing": requeued_missing,
            "trashed_synced": trashed_synced,
            "restored_on_drive": restored_on_drive
        }
