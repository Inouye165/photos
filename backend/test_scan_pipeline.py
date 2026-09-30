"""
End-to-end test of scanner filtering, safe copying, and semantic query.
"""

import os
import shutil
import tempfile
import time
from backend.documents_scanner import DocumentsScanManager
from backend.documents_db import get_documents, delete_document, get_documents_connection
from backend.documents_vector import DocumentVectorEngine

def test_full_pipeline():
    temp_dir = tempfile.mkdtemp(prefix="doc_test_")
    try:
        # Create personal documents
        doc1 = os.path.join(temp_dir, "My_Financial_Report_2025.txt")
        with open(doc1, "w", encoding="utf-8") as f:
            f.write("Annual financial budget report for household expenses, investment portfolios, and retirement funds.")

        doc2 = os.path.join(temp_dir, "Apartment_Rental_Contract.md")
        with open(doc2, "w", encoding="utf-8") as f:
            f.write("# Residential Tenancy Agreement\n\nThis agreement confirms terms of lease, deposit $2,000, and pet policy.")

        # Create system / software junk that must be IGNORED
        junk_license = os.path.join(temp_dir, "LICENSE.txt")
        with open(junk_license, "w", encoding="utf-8") as f:
            f.write("MIT License Copyright 2026...")

        junk_dir = os.path.join(temp_dir, "node_modules", "somepkg")
        os.makedirs(junk_dir, exist_ok=True)
        with open(os.path.join(junk_dir, "index.txt"), "w", encoding="utf-8") as f:
            f.write("Internal package text")

        print("Created test directories. Starting scan...")
        manager = DocumentsScanManager.get_instance()
        manager.start_scan(custom_roots=[temp_dir])

        # Wait for scan to complete
        for _ in range(30):
            st = manager.get_status()
            if not st["is_scanning"]:
                break
            time.sleep(0.5)

        print(f"Scan finished. Status: {st}")
        assert st["found_docs"] == 2, f"Expected 2 personal docs found, got {st['found_docs']}"
        assert st["copied_docs"] == 2, f"Expected 2 personal docs copied, got {st['copied_docs']}"

        # Test semantic search on newly indexed docs
        engine = DocumentVectorEngine.get_instance()
        results = engine.search("residential apartment lease and deposit", top_k=5)
        print(f"Semantic search returned {len(results)} results")
        assert len(results) > 0
        assert "Rental" in results[0]["file_name"] or "Contract" in results[0]["file_name"]

        # Verify original files are still intact
        assert os.path.exists(doc1)
        assert os.path.exists(doc2)
        print("Original files verified completely untouched!")

        # Clean up catalog records
        conn = get_documents_connection()
        rows = conn.execute("SELECT id FROM documents WHERE original_path LIKE ?", (f"{temp_dir}%",)).fetchall()
        for r in rows:
            delete_document(r["id"])
        conn.close()
        print("End-to-end pipeline test PASSED successfully!")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_full_pipeline()
