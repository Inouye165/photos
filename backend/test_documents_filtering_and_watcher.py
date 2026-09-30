"""
Comprehensive Regression Test Suite for:
1. Allowed Document Roots Filtering (strictly Documents & Downloads in Windows and OneDrive)
2. Watched Document Folders Management (DB & Watcher)
3. Total Isolation from Photos (Zero changes/impact on Photos)
"""

import os
import sys
import sqlite3
import tempfile
import pytest

from backend.documents_scanner import (
    get_allowed_document_roots,
    get_allowed_root_paths,
    is_path_in_allowed_document_roots,
    is_personal_document,
    get_default_scan_roots
)
from backend.documents_db import (
    init_documents_db,
    add_watched_folder,
    get_watched_folders,
    remove_watched_folder,
    set_watched_folder_active,
    DOCUMENTS_DB_PATH
)
from backend.documents_watcher import DocumentWatcherManager
from backend.database import DB_PATH as PHOTOS_DB_PATH

def test_allowed_document_roots_detection():
    print("Testing allowed document roots detection...")
    roots = get_allowed_document_roots()
    assert "windows_documents" in roots, "Windows Documents root missing"
    assert "windows_downloads" in roots, "Windows Downloads root missing"
    
    # Check that Windows Documents ends with Documents and Downloads ends with Downloads
    assert os.path.basename(roots["windows_documents"]["path"]).lower() == "documents"
    assert os.path.basename(roots["windows_downloads"]["path"]).lower() == "downloads"
    
    # Check OneDrive keys
    onedrive_keys = [k for k in roots if k.startswith("onedrive_")]
    assert len(onedrive_keys) >= 2, "OneDrive roots should include Documents and Downloads"
    
    for k in onedrive_keys:
        bname = os.path.basename(roots[k]["path"]).lower()
        assert bname in ("documents", "downloads"), f"OneDrive allowed root must be documents or downloads, got: {bname}"
    print("Allowed document roots detection OK.")

def test_is_path_in_allowed_document_roots():
    print("Testing path validation against allowed roots...")
    home = os.path.expanduser("~")
    
    # 1. Allowed paths
    assert is_path_in_allowed_document_roots(os.path.join(home, "Documents")) == True
    assert is_path_in_allowed_document_roots(os.path.join(home, "Documents", "Work", "Report.pdf")) == True
    assert is_path_in_allowed_document_roots(os.path.join(home, "Downloads")) == True
    assert is_path_in_allowed_document_roots(os.path.join(home, "Downloads", "Receipt.docx")) == True
    
    onedrive = os.environ.get("OneDrive", os.path.join(home, "OneDrive"))
    assert is_path_in_allowed_document_roots(os.path.join(onedrive, "Documents")) == True
    assert is_path_in_allowed_document_roots(os.path.join(onedrive, "Documents", "Archive", "Taxes.pdf")) == True
    
    # 2. Strictly REJECTED paths (Desktop, Root drives, Program Files, Windows, etc.)
    assert is_path_in_allowed_document_roots(os.path.join(home, "Desktop")) == False
    assert is_path_in_allowed_document_roots(os.path.join(home, "Desktop", "Notes.txt")) == False
    assert is_path_in_allowed_document_roots(os.path.join(onedrive, "Desktop", "Notes.txt")) == False
    assert is_path_in_allowed_document_roots("C:\\Windows\\System32\\license.rtf") == False
    assert is_path_in_allowed_document_roots("C:\\Program Files\\App\\Manual.pdf") == False
    assert is_path_in_allowed_document_roots(os.path.join(home, "AppData", "Local", "doc.txt")) == False
    assert is_path_in_allowed_document_roots("C:\\") == False
    
    # 3. Traversal attack prevention
    assert is_path_in_allowed_document_roots(os.path.join(home, "Documents", "..", "Desktop", "leak.pdf")) == False
    print("Path validation against allowed roots OK.")

def test_is_personal_document_enforces_allowed_roots():
    print("Testing is_personal_document strict folder boundary enforcement...")
    home = os.path.expanduser("~")
    
    # Personal doc inside Documents -> Allowed
    valid_doc = os.path.join(home, "Documents", "MyResume_2026.pdf")
    assert is_personal_document(valid_doc) == True
    
    # Personal doc inside Downloads -> Allowed
    valid_download = os.path.join(home, "Downloads", "Bank_Statement.pdf")
    assert is_personal_document(valid_download) == True
    
    # Personal doc inside Desktop -> STRICTLY REJECTED under new policy!
    desktop_doc = os.path.join(home, "Desktop", "Financial_Planning.docx")
    assert is_personal_document(desktop_doc) == False
    
    # System doc -> REJECTED
    assert is_personal_document("C:\\Windows\\System32\\license.rtf") == False
    print("is_personal_document boundary enforcement OK.")

def test_watched_folders_db_crud():
    print("Testing watched document folders database CRUD...")
    init_documents_db()
    home = os.path.expanduser("~")
    test_folder = os.path.normpath(os.path.join(home, "Documents", "_Test_Watch_Folder_Regression"))
    
    # Add folder
    folder_id = add_watched_folder(test_folder)
    assert folder_id is not None
    assert folder_id > 0
    
    # Get folders
    folders = get_watched_folders()
    found = [f for f in folders if f["folder_path"] == test_folder]
    assert len(found) == 1
    assert found[0]["is_active"] == True
    
    # Toggle active
    set_watched_folder_active(folder_id, False)
    folders = get_watched_folders()
    found = [f for f in folders if f["folder_path"] == test_folder]
    assert found[0]["is_active"] == False
    
    # Remove folder
    removed = remove_watched_folder(folder_id)
    assert removed == True
    folders = get_watched_folders()
    found = [f for f in folders if f["folder_path"] == test_folder]
    assert len(found) == 0
    print("Watched document folders DB CRUD OK.")

def test_document_watcher_validation():
    print("Testing DocumentWatcherManager path validation...")
    home = os.path.expanduser("~")
    watcher = DocumentWatcherManager.get_instance()
    
    # Reject Desktop
    with pytest.raises(ValueError) as excinfo:
        watcher.add_watch_path(os.path.join(home, "Desktop"))
    assert "Forbidden" in str(excinfo.value)
    
    # Reject non-existent or root
    with pytest.raises(ValueError):
        watcher.add_watch_path("C:\\NonExistentFolder12345")
        
    print("DocumentWatcherManager validation OK.")

def test_photos_isolation_and_integrity():
    print("Verifying 100% Photos isolation and database integrity...")
    assert os.path.exists(PHOTOS_DB_PATH), "photos.db does not exist"
    
    conn = sqlite3.connect(PHOTOS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    
    # Photos DB must NOT contain any documents tables
    assert "documents" not in tables, "Documents table leaked into photos.db!"
    assert "watched_document_folders" not in tables, "watched_document_folders leaked into photos.db!"
    assert "photos" in tables, "photos table must exist in photos.db"
    
    # Check folder_watcher.py in photos
    from backend.folder_watcher import FolderWatcherManager
    photo_watcher = FolderWatcherManager.get_instance()
    assert hasattr(photo_watcher, "watched_paths"), "Photos FolderWatcherManager intact"
    print("Photos database and photo watcher completely isolated and intact!")

if __name__ == "__main__":
    test_allowed_document_roots_detection()
    test_is_path_in_allowed_document_roots()
    test_is_personal_document_enforces_allowed_roots()
    test_watched_folders_db_crud()
    test_document_watcher_validation()
    test_photos_isolation_and_integrity()
    print("\nALL BACKEND DOCUMENT FILTERING & WATCHER REGRESSION TESTS PASSED!")
