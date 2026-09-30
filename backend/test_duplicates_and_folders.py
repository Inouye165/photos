"""
Verification tests for:
1. Single folder scan with include_subfolders = False vs True
2. Duplicate location tracking across separate folders
"""

import os
import shutil
import tempfile
import time
from backend.documents_scanner import DocumentsScanManager
from backend.documents_db import (
    get_documents,
    get_document_by_id,
    delete_document,
    get_documents_connection,
    get_document_locations
)

def test_single_folder_and_duplicates():
    doc_root_dir = os.path.join(os.path.expanduser("~"), "Documents")
    os.makedirs(doc_root_dir, exist_ok=True)
    temp_base = tempfile.mkdtemp(prefix="doc_test_sub_", dir=doc_root_dir)
    try:
        folder_a = os.path.join(temp_base, "FolderA")
        subfolder_a = os.path.join(folder_a, "NestedSub")
        folder_b = os.path.join(temp_base, "FolderB")
        os.makedirs(subfolder_a, exist_ok=True)
        os.makedirs(folder_b, exist_ok=True)

        # File directly in FolderA
        doc_root = os.path.join(folder_a, "Meeting_Notes.txt")
        with open(doc_root, "w", encoding="utf-8") as f:
            f.write("Important quarterly roadmap notes and project milestones.")

        # File in subfolder
        doc_sub = os.path.join(subfolder_a, "Internal_Sub_Memo.txt")
        with open(doc_sub, "w", encoding="utf-8") as f:
            f.write("Confidential memo inside nested folder.")

        # Identical duplicate file in FolderB
        doc_dup = os.path.join(folder_b, "Meeting_Notes_Copy.txt")
        with open(doc_dup, "w", encoding="utf-8") as f:
            f.write("Important quarterly roadmap notes and project milestones.")

        manager = DocumentsScanManager.get_instance()

        # TEST 1: Single folder scan with recursive = False (should only find Meeting_Notes.txt, NOT Internal_Sub_Memo.txt)
        print("Testing single folder non-recursive scan...")
        manager.start_scan(custom_roots=[folder_a], recursive=False)
        st = manager.get_status()
        for _ in range(20):
            st = manager.get_status()
            if not st["is_scanning"]:
                break
            time.sleep(0.3)

        assert st["found_docs"] == 1, f"Expected 1 doc found without subfolders, got {st['found_docs']}"
        assert st["copied_docs"] == 1, f"Expected 1 doc copied, got {st['copied_docs']}"
        print("[PASS] Non-recursive scan correctly ignored subfolders!")

        # TEST 2: Single folder scan with recursive = True (should find Internal_Sub_Memo.txt)
        print("Testing single folder recursive scan...")
        manager.start_scan(custom_roots=[folder_a], recursive=True)
        for _ in range(20):
            st = manager.get_status()
            if not st["is_scanning"]:
                break
            time.sleep(0.3)

        # Now Internal_Sub_Memo.txt should be found
        conn = get_documents_connection()
        doc_memo = conn.execute("SELECT * FROM documents WHERE original_path = ?", (doc_sub,)).fetchone()
        assert doc_memo is not None, "Expected subfolder document to be cataloged"
        print("[PASS] Recursive scan correctly included subfolders!")

        # TEST 3: Scan FolderB containing an exact duplicate
        print("Testing duplicate tracking across separate folder...")
        manager.start_scan(custom_roots=[folder_b], recursive=False)
        for _ in range(20):
            st = manager.get_status()
            if not st["is_scanning"]:
                break
            time.sleep(0.3)

        # Retrieve the original document record
        doc_item = conn.execute("SELECT * FROM documents WHERE original_path = ?", (doc_root,)).fetchone()
        assert doc_item is not None
        full_doc = get_document_by_id(doc_item["id"])
        assert full_doc is not None, "Failed to retrieve full_doc by id"
        
        # Verify duplicate tracking
        assert full_doc["duplicate_count"] == 1, f"Expected duplicate_count 1, got {full_doc['duplicate_count']}"
        assert len(full_doc["locations"]) == 2, f"Expected 2 locations, got {len(full_doc['locations'])}"
        
        loc_paths = [loc["original_path"] for loc in full_doc["locations"]]
        assert doc_root in loc_paths
        assert doc_dup in loc_paths
        print(f"[PASS] Duplicate locations tracked accurately: {loc_paths}")

        # Clean up database records for these test files
        rows = conn.execute("SELECT id FROM documents WHERE original_path LIKE ?", (f"{temp_base}%",)).fetchall()
        for r in rows:
            delete_document(r["id"])
        conn.close()
        print("All tests PASSED successfully!")
    finally:
        shutil.rmtree(temp_base, ignore_errors=True)

if __name__ == "__main__":
    test_single_folder_and_duplicates()
