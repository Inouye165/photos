"""
Verification test suite for LuminaDocuments functionality and Photos isolation.
"""

import os
import sys
import shutil
import tempfile
import sqlite3
import time

# 1. Test Database Initialization
from backend.documents_db import (
    init_documents_db,
    insert_or_update_document,
    get_documents,
    get_document_by_id,
    get_document_stats,
    delete_document,
    DOCUMENTS_DB_PATH
)
from backend.documents_extractor import extract_document_text, chunk_document_text
from backend.documents_scanner import is_personal_document, compute_file_sha256
from backend.documents_vector import DocumentVectorEngine

def test_documents_db():
    print("Testing isolated Documents database...")
    init_documents_db()
    assert os.path.exists(DOCUMENTS_DB_PATH), "Documents DB file was not created"
    
    doc_id = insert_or_update_document(
        file_name="Tax_Return_2024.pdf",
        original_path="C:\\Users\\inouy\\Documents\\Tax_Return_2024.pdf",
        copied_path="C:\\Users\\inouy\\photos\\documents_library\\Tax_Return_2024.pdf",
        file_size=245000,
        file_extension=".pdf",
        sha256="fake_sha256_hash_123456",
        created_at=1700000000,
        modified_at=1700001000,
        title="2024 Federal and State Tax Return",
        extracted_text="Income, deductions, standard deduction, total tax liability $4,500.",
        summary="2024 tax filing records with deduction details.",
        page_count=3,
        word_count=50
    )
    assert doc_id is not None, "Failed to insert test document"
    
    doc = get_document_by_id(doc_id)
    assert doc is not None, "Failed to retrieve document by id"
    assert doc["title"] == "2024 Federal and State Tax Return"
    
    docs, total = get_documents(search="deduction")
    assert total >= 1, "Failed to search document by keyword"
    
    stats = get_document_stats()
    assert stats["total_documents"] >= 1
    print("Documents database OK.")

def test_extractor_and_chunking():
    print("Testing text extractor and chunking...")
    sample_text = "This is a comprehensive lease agreement for the apartment. The tenant agrees to pay monthly rent."
    chunks = chunk_document_text(sample_text, chunk_size_words=10, overlap_words=2)
    assert len(chunks) >= 1
    print(f"Chunking OK ({len(chunks)} chunks).")

def test_personal_filtering():
    print("Testing personal document filtering heuristics...")
    # Should accept (within Windows & OneDrive Documents and Downloads):
    assert is_personal_document("C:\\Users\\inouy\\Documents\\Resume_2025.pdf") == True
    assert is_personal_document("C:\\Users\\inouy\\OneDrive\\Documents\\Financial_Planning.docx") == True
    assert is_personal_document("C:\\Users\\inouy\\Downloads\\Mortgage_Statement.pdf") == True
    
    # Should reject (Desktop is outside allowed roots):
    assert is_personal_document("C:\\Users\\inouy\\Desktop\\Financial_Planning.docx") == False
    
    # Should reject (System / Program / App / Developer junk):
    assert is_personal_document("C:\\Windows\\System32\\license.rtf") == False
    assert is_personal_document("C:\\Program Files\\App\\README.txt") == False
    assert is_personal_document("C:\\Users\\inouy\\AppData\\Local\\Temp\\cache.txt") == False
    assert is_personal_document("C:\\Users\\inouy\\project\\node_modules\\pkg\\LICENSE") == False
    assert is_personal_document("C:\\Users\\inouy\\project\\.git\\description.txt") == False
    assert is_personal_document("C:\\Users\\inouy\\project\\venv\\site-packages\\docs\\notice.txt") == False
    print("Filtering heuristics OK.")

def test_semantic_search():
    doc_id = insert_or_update_document(
        file_name="Tax_Return_2024.pdf",
        original_path="C:\\Users\\inouy\\Documents\\Tax_Return_2024.pdf",
        copied_path="C:\\Users\\inouy\\photos\\documents_library\\Tax_Return_2024.pdf",
        file_size=250000,
        file_extension=".pdf",
        sha256="test_sha256_tax_return",
        created_at=time.time(),
        modified_at=time.time(),
        title="2024 Tax Filing",
        extracted_text="Income tax return with deductions",
        page_count=2,
        word_count=100
    )
    print("Testing semantic vector search...")
    engine = DocumentVectorEngine.get_instance()
    engine.index_document(doc_id, [
        "Income tax return 2024 with standard deductions and federal refund calculation.",
        "Mortgage interest rate and property tax statements."
    ])
    
    results = engine.search("IRS taxes and deductions", top_k=5)
    assert len(results) > 0, "Semantic search returned no results"
    assert results[0]["id"] == doc_id
    print(f"Semantic search OK (top score: {results[0].get('score')})")

def test_photos_integrity():
    print("Verifying Photos database integrity and isolation...")
    from backend.database import DB_PATH as PHOTOS_DB_PATH
    assert os.path.exists(PHOTOS_DB_PATH)
    conn = sqlite3.connect(PHOTOS_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    assert "photos" in tables
    assert "documents" not in tables, "Documents table should NOT be in photos.db"
    conn.close()
    print("Photos database isolated and intact!")

if __name__ == "__main__":
    test_documents_db()
    test_extractor_and_chunking()
    test_personal_filtering()
    test_semantic_search()
    test_photos_integrity()
    print("All verification tests PASSED!")
