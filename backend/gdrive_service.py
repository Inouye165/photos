"""
Google Drive Service for LuminaPhoto.
Handles folder hierarchy creation (Root -> Year -> Month),
photo uploading with rate limiting safeguards, and two-way trash deletion.
"""

import os
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from backend.gdrive_auth import get_credentials, is_authenticated
from backend.database import (
    get_backup_settings,
    get_cached_gdrive_folder,
    cache_gdrive_folder,
    clear_gdrive_folder_cache,
    delete_cached_gdrive_folder,
    delete_cached_gdrive_folder_by_id
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


class GDriveService:
    _instance: Optional['GDriveService'] = None

    def __init__(self):
        self._service = None

    @classmethod
    def get_instance(cls) -> 'GDriveService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_drive_service(self):
        """Returns an authorized Google Drive API v3 client, or None."""
        if not is_authenticated():
            return None
        if self._service is None:
            creds = get_credentials()
            if not creds:
                return None
            self._service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return self._service

    def reset_service(self):
        self._service = None
        clear_gdrive_folder_cache()

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
        query_parts = [
            f"name = '{folder_name}'",
            "mimeType = 'application/vnd.google-apps.folder'",
            "trashed = false"
        ]
        if parent_id:
            query_parts.append(f"'{parent_id}' in parents")
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

    def upload_photo(self, photo_data: Dict[str, Any]) -> str:
        """
        Uploads a photo to Google Drive inside the appropriate Year/Month subfolder.
        Returns the created Google Drive file ID.
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

        target_folder_id, _, _ = self.ensure_target_folder(date_taken, file_modified_at)

        # Determine MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "image/jpeg"

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file_metadata = {
            'name': file_name,
            'parents': [target_folder_id]
        }

        # Check if file already exists in this folder to avoid duplicates
        existing_query = (
            f"name = '{file_name}' and '{target_folder_id}' in parents and trashed = false"
        )
        existing_resp = service.files().list(
            q=existing_query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=1
        ).execute()
        existing_files = existing_resp.get('files', [])

        if existing_files:
            # File already exists in this folder, re-use existing file id
            return existing_files[0]['id']

        created_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()

        return created_file.get('id')

    def trash_photo(self, gdrive_file_id: str) -> bool:
        """
        Moves a file to Google Drive trash (two-way sync deletion).
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
            if e.resp.status == 404:
                # File already doesn't exist on Drive
                return True
            print(f"[GDrive Service] Error trashing file {gdrive_file_id}: {e}")
            return False

    def untrash_photo(self, gdrive_file_id: str) -> bool:
        """
        Restores a file from Google Drive trash if untrashed locally.
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
            return True
        except HttpError as e:
            if e.resp.status == 404:
                return True
            print(f"[GDrive Service] Error deleting file {gdrive_file_id}: {e}")
            return False
