"""
Comprehensive Regression Test Suite for:
1. Document Trash Holding Folder functionality
2. Git Exclusion of documents_trash and documents_library (.gitignore verification)
3. Document Trash Lifecycle (Trash -> Holding Folder, Restore, Permanent Delete, Empty Trash)
4. Absolute Isolation: Zero modification or impact on Photos database (photos.db)
"""

import os
import sys
import tempfile
import time
import pytest

from backend.documents_db import (
    init_documents_db,
    insert_or_update_document,
    get_documents,
    get_document_stats,
    trash_document,
    restore_document,
    permanently_delete_document,
    empty_documents_trash,
    DEFAULT_DOCUMENTS_TRASH,
    DEFAULT_DOCUMENTS_LIBRARY
)
from backend.database import DB_PATH as PHOTOS_DB_PATH


def test_gitignore_protects_trash_and_documents():
    """Verify that documents_trash, documents_library, and documents.db are in .gitignore."""
    workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gitignore_path = os.path.join(workspace_root, ".gitignore")
    assert os.path.exists(gitignore_path), ".gitignore must exist in workspace root"
    
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "documents_trash/" in content, "documents_trash/ holding folder must be git ignored"
    assert "documents_library/" in content, "documents_library/ must be git ignored"
    assert "backend/documents.db" in content, "documents.db must be git ignored"


def test_document_trash_lifecycle():
    """
    Test moving a document copy to documents_trash holding folder,
    verifying original file remains safe, restoring it back to library,
    and permanently deleting it.
    """
    init_documents_db()
    
    # 1. Create a dummy original document file (simulating user's Documents folder)
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as orig:
        orig.write(b"Personal Secret Note Content For Trash Test")
        orig_path = orig.name

    # 2. Create a dummy copied file in documents_library
    os.makedirs(DEFAULT_DOCUMENTS_LIBRARY, exist_ok=True)
    os.makedirs(DEFAULT_DOCUMENTS_TRASH, exist_ok=True)
    
    copied_filename = f"test_trash_{int(time.time()*1000)}.txt"
    copied_path = os.path.join(DEFAULT_DOCUMENTS_LIBRARY, copied_filename)
    with open(copied_path, "wb") as f:
        f.write(b"Personal Secret Note Content For Trash Test")

    doc_id = None
    try:
        # Insert document record
        doc_id = insert_or_update_document(
            original_path=orig_path,
            copied_path=copied_path,
            file_name=copied_filename,
            file_size=len(b"Personal Secret Note Content For Trash Test"),
            file_extension=".txt",
            sha256=f"hash_{copied_filename}",
            created_at=time.time(),
            modified_at=time.time(),
            title="Test Note",
            extracted_text="Personal Secret Note Content For Trash Test"
        )
        assert doc_id is not None and doc_id > 0

        # Verify it appears in active documents and not in trashed
        active_docs, _ = get_documents(is_trashed=False)
        active_ids = [d["id"] for d in active_docs]
        assert doc_id in active_ids

        trashed_docs, _ = get_documents(is_trashed=True)
        trashed_ids = [d["id"] for d in trashed_docs]
        assert doc_id not in trashed_ids

        # 3. Action: Move document to trash
        res = trash_document(doc_id)
        assert res is True

        trashed_doc = [d for d in get_documents(is_trashed=True)[0] if d["id"] == doc_id][0]
        trashed_path = trashed_doc["trashed_path"]
        assert trashed_path and os.path.exists(trashed_path), "File must be moved to holding folder"
        assert not os.path.exists(copied_path), "File must no longer exist in documents_library"
        assert os.path.exists(orig_path), "Original file on user PC MUST remain safe and untouched"

        # Verify queries reflect trashed state
        active_docs_after, _ = get_documents(is_trashed=False)
        assert doc_id not in [d["id"] for d in active_docs_after]

        trashed_docs_after, _ = get_documents(is_trashed=True)
        assert doc_id in [d["id"] for d in trashed_docs_after]

        stats = get_document_stats()
        assert stats["trashed_count"] >= 1

        # 4. Action: Restore document from trash
        restore_res = restore_document(doc_id)
        assert restore_res is True
        restored_doc = [d for d in get_documents(is_trashed=False)[0] if d["id"] == doc_id][0]
        restored_path = restored_doc["copied_path"]
        assert os.path.exists(restored_path), "File must be moved back to documents_library"
        assert not os.path.exists(trashed_path), "File must no longer exist in trash folder"
        assert os.path.exists(orig_path), "Original file on user PC MUST still be safe"

        # Verify queries reflect active state again
        active_docs_restored, _ = get_documents(is_trashed=False)
        assert doc_id in [d["id"] for d in active_docs_restored]

        trashed_docs_restored, _ = get_documents(is_trashed=True)
        assert doc_id not in [d["id"] for d in trashed_docs_restored]

        # 5. Trash again, then permanently delete
        trash_document(doc_id)
        assert os.path.exists(trashed_path)

        del_res = permanently_delete_document(doc_id)
        assert del_res is True
        assert not os.path.exists(trashed_path), "File must be deleted from disk"
        assert os.path.exists(orig_path), "Original file on PC MUST STILL remain completely safe"

        active_docs_final, _ = get_documents(is_trashed=False)
        trashed_docs_final, _ = get_documents(is_trashed=True)
        assert doc_id not in [d["id"] for d in active_docs_final]
        assert doc_id not in [d["id"] for d in trashed_docs_final]

    finally:
        # Cleanup temp original file
        if os.path.exists(orig_path):
            os.remove(orig_path)
        if copied_path and os.path.exists(copied_path):
            os.remove(copied_path)


def test_empty_documents_trash():
    """Test emptying multiple documents from the documents_trash holding folder."""
    init_documents_db()
    
    created_ids = []
    created_files = []
    try:
        for i in range(3):
            fname = f"trash_bulk_test_{i}_{int(time.time()*1000)}.txt"
            cpath = os.path.join(DEFAULT_DOCUMENTS_LIBRARY, fname)
            with open(cpath, "wb") as f:
                f.write(f"bulk test {i}".encode())
            created_files.append(cpath)
            
            did = insert_or_update_document(
                original_path=cpath,
                copied_path=cpath,
                file_name=fname,
                file_size=10,
                file_extension=".txt",
                sha256=f"bulk_hash_{fname}",
                created_at=time.time(),
                modified_at=time.time(),
                title=f"Bulk {i}",
                extracted_text=f"bulk test {i}"
            )
            created_ids.append(did)
            trash_document(did)

        # Empty trash
        purged = empty_documents_trash()
        assert purged >= 3

        # Verify all are gone from trashed documents
        trashed_docs, _ = get_documents(is_trashed=True)
        trashed_ids = [d["id"] for d in trashed_docs]
        for did in created_ids:
            assert did not in trashed_ids

    finally:
        for cpath in created_files:
            if os.path.exists(cpath):
                os.remove(cpath)


def test_photos_isolation_from_documents_trash():
    """Verify that document trash operations never touch photos.db or photos table."""
    import sqlite3
    assert os.path.exists(PHOTOS_DB_PATH), "photos.db should exist"
    
    conn = sqlite3.connect(PHOTOS_DB_PATH)
    cur = conn.cursor()
    
    # Check that photos table is intact and has not had documents inserted into it
    cur.execute("PRAGMA table_info(photos)")
    photo_columns = [row[1] for row in cur.fetchall()]
    assert "file_path" in photo_columns
    assert "classification" in photo_columns
    assert "trashed_path" not in photo_columns, "trashed_path belongs exclusively to documents.db"
    
    # Check that document paths never appear in photos table
    cur.execute("SELECT COUNT(*) FROM photos WHERE file_path LIKE '%documents_trash%' OR file_path LIKE '%documents_library%'")
    doc_paths_in_photos = cur.fetchone()[0]
    assert doc_paths_in_photos == 0, "Photos table must never contain documents_trash or documents_library files"
    
    conn.close()
