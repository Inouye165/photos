"""
Isolated SQLite database schema and data access layer for LuminaDocuments.
Completely separate from photos.db to guarantee zero state or schema interference.
"""

import sqlite3
import json
import os
import shutil
import time
from typing import List, Dict, Any, Optional, Tuple

DOCUMENTS_DB_PATH = os.path.join(os.path.dirname(__file__), "documents.db")
DEFAULT_DOCUMENTS_TRASH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents_trash")
DEFAULT_DOCUMENTS_LIBRARY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents_library")

def get_documents_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DOCUMENTS_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_documents_db(db_path: Optional[str] = None):
    """Initializes the documents database schema."""
    conn = get_documents_connection(db_path)
    with conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT NOT NULL,
            original_path TEXT UNIQUE NOT NULL,
            copied_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            created_at REAL,
            modified_at REAL,
            page_count INTEGER DEFAULT 1,
            word_count INTEGER DEFAULT 0,
            title TEXT,
            extracted_text TEXT,
            summary TEXT,
            has_embedding INTEGER DEFAULT 0,
            indexed_at REAL,
            is_trashed INTEGER DEFAULT 0,
            trashed_at REAL,
            trashed_path TEXT,
            ai_summary TEXT,
            ai_analysis_json TEXT,
            ai_processed_at REAL,
            review_status TEXT DEFAULT 'unreviewed',
            review_note TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
        CREATE INDEX IF NOT EXISTS idx_documents_ext ON documents(file_extension);
        CREATE INDEX IF NOT EXISTS idx_documents_modified ON documents(modified_at DESC);
        CREATE INDEX IF NOT EXISTS idx_documents_indexed ON documents(indexed_at DESC);

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON document_chunks(document_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_index ON document_chunks(document_id, chunk_index);

        CREATE TABLE IF NOT EXISTS document_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            original_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            modified_at REAL,
            discovered_at REAL
        );

        CREATE INDEX IF NOT EXISTS idx_doc_locations_doc_id ON document_locations(document_id);
        CREATE INDEX IF NOT EXISTS idx_doc_locations_path ON document_locations(original_path);

        CREATE TABLE IF NOT EXISTS scan_status (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS watched_document_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT UNIQUE NOT NULL,
            added_at REAL,
            is_active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_watched_folders_path ON watched_document_folders(folder_path);

        CREATE TABLE IF NOT EXISTS document_interest_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            is_active INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_interest_lists_active ON document_interest_lists(is_active);
        """)

        # Migration: Ensure is_trashed, trashed_at, trashed_path columns exist on documents
        col_info = conn.execute("PRAGMA table_info(documents)").fetchall()
        col_names = {c["name"] for c in col_info}
        if "is_trashed" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN is_trashed INTEGER DEFAULT 0")
        if "trashed_at" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN trashed_at REAL")
        if "trashed_path" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN trashed_path TEXT")
        if "ai_summary" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN ai_summary TEXT")
        if "ai_analysis_json" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN ai_analysis_json TEXT")
        if "ai_processed_at" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN ai_processed_at REAL")
        if "review_status" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN review_status TEXT DEFAULT 'unreviewed'")
        if "review_note" not in col_names:
            conn.execute("ALTER TABLE documents ADD COLUMN review_note TEXT")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_trashed ON documents(is_trashed)")
    conn.close()

def add_document_location(
    document_id: int,
    original_path: str,
    file_name: str,
    file_size: int,
    modified_at: float
):
    """Registers an original PC file location for a document (primary or duplicate copy)."""
    conn = get_documents_connection()
    with conn:
        conn.execute("""
            INSERT INTO document_locations (document_id, original_path, file_name, file_size, modified_at, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(original_path) DO UPDATE SET
                document_id = excluded.document_id,
                file_name = excluded.file_name,
                file_size = excluded.file_size,
                modified_at = excluded.modified_at
        """, (document_id, original_path, file_name, file_size, modified_at, time.time()))
    conn.close()

def get_document_locations(document_id: int) -> List[Dict[str, Any]]:
    """Retrieves all PC file locations where identical copies of this document exist."""
    conn = get_documents_connection()
    rows = conn.execute("""
        SELECT * FROM document_locations
        WHERE document_id = ?
        ORDER BY discovered_at ASC
    """, (document_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_or_update_document(
    original_path: str,
    copied_path: str,
    file_name: str,
    file_size: int,
    file_extension: str,
    sha256: str,
    created_at: float,
    modified_at: float,
    title: Optional[str] = None,
    extracted_text: Optional[str] = None,
    summary: Optional[str] = None,
    page_count: int = 1,
    word_count: int = 0,
    has_embedding: int = 0
) -> int:
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("""
            INSERT INTO documents (
                original_path, copied_path, file_name, file_size, file_extension,
                sha256, created_at, modified_at, title, extracted_text, summary,
                page_count, word_count, has_embedding, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(original_path) DO UPDATE SET
                copied_path = excluded.copied_path,
                file_name = excluded.file_name,
                file_size = excluded.file_size,
                file_extension = excluded.file_extension,
                sha256 = excluded.sha256,
                created_at = excluded.created_at,
                modified_at = excluded.modified_at,
                title = excluded.title,
                extracted_text = excluded.extracted_text,
                summary = excluded.summary,
                page_count = excluded.page_count,
                word_count = excluded.word_count,
                has_embedding = excluded.has_embedding,
                indexed_at = excluded.indexed_at
        """, (
            original_path, copied_path, file_name, file_size, file_extension,
            sha256, created_at, modified_at, title, extracted_text, summary,
            page_count, word_count, has_embedding, time.time()
        ))
        
        doc_id = cursor.lastrowid
        if not doc_id:
            row = conn.execute("SELECT id FROM documents WHERE original_path = ?", (original_path,)).fetchone()
            doc_id = row["id"] if row else None

        if doc_id:
            conn.execute("""
                INSERT OR IGNORE INTO document_locations (
                    document_id, original_path, file_name, file_size, modified_at, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (doc_id, original_path, file_name, file_size, modified_at, time.time()))

    conn.close()
    return int(doc_id) if doc_id is not None else 0

def get_document_by_id(doc_id: int) -> Optional[Dict[str, Any]]:
    conn = get_documents_connection()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        return None
    doc = dict(row)
    locs = get_document_locations(doc_id)
    doc["locations"] = locs
    doc["duplicate_count"] = max(0, len(locs) - 1)
    return doc

def list_interest_lists(active_only: bool = True) -> List[Dict[str, Any]]:
    """Returns user-defined document categories used by local AI analysis."""
    conn = get_documents_connection()
    where = "WHERE is_active = 1" if active_only else ""
    rows = conn.execute(f"SELECT * FROM document_interest_lists {where} ORDER BY name").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def save_interest_list(name: str, description: str) -> Dict[str, Any]:
    """Creates or updates an interest list by name."""
    now = time.time()
    conn = get_documents_connection()
    with conn:
        conn.execute("""
            INSERT INTO document_interest_lists (name, description, created_at, updated_at, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET description = excluded.description,
                updated_at = excluded.updated_at, is_active = 1
        """, (name.strip(), description.strip(), now, now))
        row = conn.execute("SELECT * FROM document_interest_lists WHERE name = ?", (name.strip(),)).fetchone()
    conn.close()
    return dict(row)

def delete_interest_list(list_id: int) -> bool:
    """Disables an interest list without deleting its history."""
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("UPDATE document_interest_lists SET is_active = 0, updated_at = ? WHERE id = ?", (time.time(), list_id))
    conn.close()
    return cursor.rowcount > 0

def save_document_analysis(doc_id: int, summary: str, analysis: Dict[str, Any]) -> bool:
    """Stores local AI output and its evidence for a document."""
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("""
            UPDATE documents SET ai_summary = ?, ai_analysis_json = ?, ai_processed_at = ?
            WHERE id = ?
        """, (summary, json.dumps(analysis), time.time(), doc_id))
    conn.close()
    return cursor.rowcount > 0

def update_document_review(doc_id: int, status: str, note: Optional[str] = None) -> bool:
    """Updates human review status without moving or deleting any file."""
    if status not in {"unreviewed", "keep", "review", "remove"}:
        return False
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("UPDATE documents SET review_status = ?, review_note = ? WHERE id = ?", (status, note, doc_id))
    conn.close()
    return cursor.rowcount > 0

def get_document_by_sha256(sha256: str) -> Optional[Dict[str, Any]]:
    conn = get_documents_connection()
    row = conn.execute("SELECT * FROM documents WHERE sha256 = ?", (sha256,)).fetchone()
    conn.close()
    if not row:
        return None
    doc = dict(row)
    locs = get_document_locations(doc["id"])
    doc["locations"] = locs
    doc["duplicate_count"] = max(0, len(locs) - 1)
    return doc

def get_document_by_original_path(original_path: str) -> Optional[Dict[str, Any]]:
    conn = get_documents_connection()
    row = conn.execute("SELECT * FROM documents WHERE original_path = ?", (original_path,)).fetchone()
    conn.close()
    if not row:
        return None
    doc = dict(row)
    locs = get_document_locations(doc["id"])
    doc["locations"] = locs
    doc["duplicate_count"] = max(0, len(locs) - 1)
    return doc

def get_documents(
    search: Optional[str] = None,
    file_extension: Optional[str] = None,
    is_trashed: bool = False,
    sort_by: str = "modified_at",
    sort_order: str = "DESC",
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    conn = get_documents_connection()
    
    where_clauses = []
    params: List[Any] = []

    if is_trashed:
        where_clauses.append("is_trashed = 1")
    else:
        where_clauses.append("is_trashed = 0")
    
    if file_extension:
        ext = file_extension.lower().strip()
        if not ext.startswith("."):
            ext = f".{ext}"
        where_clauses.append("file_extension = ?")
        params.append(ext)
        
    if search:
        s_term = f"%{search.strip()}%"
        where_clauses.append("(file_name LIKE ? OR title LIKE ? OR extracted_text LIKE ?)")
        params.extend([s_term, s_term, s_term])
        
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    
    count_sql = f"SELECT COUNT(*) as total FROM documents {where_sql}"
    total = conn.execute(count_sql, params).fetchone()["total"]
    
    allowed_sort_fields = {"modified_at", "created_at", "file_name", "file_size", "indexed_at", "word_count", "trashed_at"}
    clean_sort_by = sort_by if sort_by in allowed_sort_fields else "modified_at"
    clean_order = "ASC" if sort_order.upper() == "ASC" else "DESC"
    
    query_sql = f"""
        SELECT id, file_name, original_path, copied_path, file_size, file_extension,
               sha256, created_at, modified_at, page_count, word_count, title,
               summary, ai_summary, ai_analysis_json, ai_processed_at, review_status, review_note,
               has_embedding, indexed_at, is_trashed, trashed_at, trashed_path,
               SUBSTR(extracted_text, 1, 300) as snippet,
               COALESCE((SELECT COUNT(*) - 1 FROM document_locations WHERE document_id = documents.id), 0) as duplicate_count
        FROM documents
        {where_sql}
        ORDER BY {clean_sort_by} {clean_order}
        LIMIT ? OFFSET ?
    """
    
    rows = conn.execute(query_sql, params + [limit, offset]).fetchall()
    conn.close()
    
    return [dict(r) for r in rows], total

def save_document_chunks(document_id: int, chunks_data: List[Tuple[int, str, Optional[List[float]]]]):
    """Saves text chunks and their embeddings for a document."""
    conn = get_documents_connection()
    with conn:
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        for idx, text, emb in chunks_data:
            emb_json = json.dumps(emb) if emb is not None else None
            conn.execute("""
                INSERT INTO document_chunks (document_id, chunk_index, chunk_text, embedding_json)
                VALUES (?, ?, ?, ?)
            """, (document_id, idx, text, emb_json))
        conn.execute("UPDATE documents SET has_embedding = 1 WHERE id = ?", (document_id,))
    conn.close()

def get_all_document_chunks_with_embeddings() -> List[Dict[str, Any]]:
    """Returns all document chunks that have embeddings for vector indexing."""
    conn = get_documents_connection()
    rows = conn.execute("""
        SELECT c.id, c.document_id, c.chunk_index, c.chunk_text, c.embedding_json,
               d.file_name, d.original_path, d.copied_path, d.file_extension, d.file_size,
               d.modified_at, d.title
        FROM document_chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding_json IS NOT NULL
          AND d.is_trashed = 0
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_document_stats() -> Dict[str, Any]:
    conn = get_documents_connection()
    total_docs = conn.execute("SELECT COUNT(*) as c FROM documents WHERE is_trashed = 0").fetchone()["c"]
    total_bytes = conn.execute("SELECT COALESCE(SUM(file_size), 0) as s FROM documents WHERE is_trashed = 0").fetchone()["s"]
    total_words = conn.execute("SELECT COALESCE(SUM(word_count), 0) as w FROM documents WHERE is_trashed = 0").fetchone()["w"]
    
    trashed_row = conn.execute("SELECT COUNT(*) as c, COALESCE(SUM(file_size), 0) as s FROM documents WHERE is_trashed = 1").fetchone()
    trashed_count = trashed_row["c"]
    trashed_bytes = trashed_row["s"]

    total_duplicates = conn.execute("""
        SELECT COUNT(*) as c FROM document_locations
        WHERE document_id IN (SELECT id FROM documents WHERE is_trashed = 0)
          AND id NOT IN (
            SELECT MIN(id) FROM document_locations GROUP BY document_id
        )
    """).fetchone()["c"]

    type_counts = {}
    for row in conn.execute("SELECT file_extension, COUNT(*) as c FROM documents WHERE is_trashed = 0 GROUP BY file_extension ORDER BY c DESC"):
        type_counts[row["file_extension"]] = row["c"]
        
    conn.close()
    return {
        "total_documents": total_docs,
        "total_bytes": total_bytes,
        "total_words": total_words,
        "total_duplicates": total_duplicates,
        "trashed_count": trashed_count,
        "trashed_bytes": trashed_bytes,
        "type_counts": type_counts
    }

def trash_document(doc_id: int) -> bool:
    """
    Moves a document's library copy to the workspace documents_trash holding folder
    and flags the document as trashed in SQLite. Original PC file remains untouched.
    """
    conn = get_documents_connection()
    with conn:
        row = conn.execute("SELECT copied_path, file_name FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            conn.close()
            return False

        copied_path = row["copied_path"]
        os.makedirs(DEFAULT_DOCUMENTS_TRASH, exist_ok=True)

        trashed_path = None
        if copied_path and os.path.exists(copied_path):
            base_name = os.path.basename(copied_path)
            trashed_path = os.path.join(DEFAULT_DOCUMENTS_TRASH, base_name)
            # If target exists in trash, avoid collision
            if os.path.exists(trashed_path) and trashed_path != copied_path:
                stem, ext = os.path.splitext(base_name)
                trashed_path = os.path.join(DEFAULT_DOCUMENTS_TRASH, f"{stem}_{int(time.time())}{ext}")
            shutil.move(copied_path, trashed_path)
        else:
            trashed_path = os.path.join(DEFAULT_DOCUMENTS_TRASH, row["file_name"])

        trashed_at = time.time()
        conn.execute(
            "UPDATE documents SET is_trashed = 1, trashed_at = ?, trashed_path = ? WHERE id = ?",
            (trashed_at, trashed_path, doc_id)
        )
    conn.close()
    return True

def restore_document(doc_id: int) -> bool:
    """
    Restores a trashed document back from the workspace holding folder into active documents_library.
    """
    conn = get_documents_connection()
    with conn:
        row = conn.execute("SELECT copied_path, trashed_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            conn.close()
            return False

        copied_path = row["copied_path"]
        trashed_path = row["trashed_path"]

        if trashed_path and os.path.exists(trashed_path) and copied_path:
            os.makedirs(os.path.dirname(copied_path), exist_ok=True)
            shutil.move(trashed_path, copied_path)

        conn.execute(
            "UPDATE documents SET is_trashed = 0, trashed_at = NULL, trashed_path = NULL WHERE id = ?",
            (doc_id,)
        )
    conn.close()
    return True

def permanently_delete_document(doc_id: int) -> bool:
    """
    Permanently deletes a document from documents_trash (or library) and removes record from documents.db.
    """
    conn = get_documents_connection()
    with conn:
        row = conn.execute("SELECT copied_path, trashed_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row:
            for p in (row["trashed_path"], row["copied_path"]):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        conn.execute("DELETE FROM document_locations WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.close()
    return True

def empty_documents_trash() -> int:
    """
    Purges all documents in the documents_trash holding folder and their database records.
    Returns the count of purged documents.
    """
    conn = get_documents_connection()
    purged_count = 0
    with conn:
        rows = conn.execute("SELECT id, copied_path, trashed_path FROM documents WHERE is_trashed = 1").fetchall()
        for r in rows:
            for p in (r["trashed_path"], r["copied_path"]):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            purged_count += 1
        conn.execute("DELETE FROM document_locations WHERE document_id IN (SELECT id FROM documents WHERE is_trashed = 1)")
        conn.execute("DELETE FROM document_chunks WHERE document_id IN (SELECT id FROM documents WHERE is_trashed = 1)")
        conn.execute("DELETE FROM documents WHERE is_trashed = 1")
    conn.close()

    # Clean up any lingering files in documents_trash directory
    if os.path.exists(DEFAULT_DOCUMENTS_TRASH):
        for fname in os.listdir(DEFAULT_DOCUMENTS_TRASH):
            fpath = os.path.join(DEFAULT_DOCUMENTS_TRASH, fname)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass

    return purged_count

def delete_document(doc_id: int) -> bool:
    """Backwards-compatible delete: permanently removes document."""
    return permanently_delete_document(doc_id)

def clear_all_documents(purge_copies: bool = True):
    """
    Clears all documents and duplicate location records from documents.db.
    Deletes copies in documents_library while leaving original computer files untouched.
    """
    conn = get_documents_connection()
    with conn:
        if purge_copies:
            rows = conn.execute("SELECT copied_path FROM documents").fetchall()
            for r in rows:
                p = r["copied_path"]
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        conn.execute("DELETE FROM document_locations")
        conn.execute("DELETE FROM document_chunks")
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM scan_status")
    conn.close()
    return True

def add_watched_folder(folder_path: str) -> int:
    """Adds a new folder to the watched documents folders table."""
    norm_path = os.path.normpath(os.path.abspath(folder_path))
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("""
            INSERT INTO watched_document_folders (folder_path, added_at, is_active)
            VALUES (?, ?, 1)
            ON CONFLICT(folder_path) DO UPDATE SET is_active = 1
        """, (norm_path, time.time()))
        row = conn.execute("SELECT id FROM watched_document_folders WHERE folder_path = ?", (norm_path,)).fetchone()
        folder_id = row["id"] if row else cursor.lastrowid
    conn.close()
    return int(folder_id) if folder_id is not None else 0

def remove_watched_folder(folder_id: int) -> bool:
    """Removes a folder from the watched documents folders table."""
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute("DELETE FROM watched_document_folders WHERE id = ?", (folder_id,))
        affected = cursor.rowcount > 0
    conn.close()
    return affected

def get_watched_folders() -> List[Dict[str, Any]]:
    """Retrieves all watched document folders and checks their current status on disk."""
    conn = get_documents_connection()
    rows = conn.execute("SELECT * FROM watched_document_folders ORDER BY added_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["is_active"] = bool(d["is_active"])
        d["exists"] = os.path.exists(d["folder_path"]) and os.path.isdir(d["folder_path"])
        result.append(d)
    return result

def set_watched_folder_active(folder_id: int, is_active: bool) -> bool:
    """Enables or disables watching on a specific folder."""
    conn = get_documents_connection()
    with conn:
        cursor = conn.execute(
            "UPDATE watched_document_folders SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, folder_id)
        )
        affected = cursor.rowcount > 0
    conn.close()
    return affected

