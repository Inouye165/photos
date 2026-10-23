"""
SQLite database schema and data access layer for LuminaPhoto.
Stores photo records, complete EXIF metadata, duplicate groups, and vector embeddings.
"""

import sqlite3
import json
import os
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.environ.get("LUMINA_DB_PATH") or os.path.join(os.path.dirname(__file__), "photos.db")

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = os.environ.get("LUMINA_DB_PATH") or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db(db_path: Optional[str] = None):
    """Initializes the database schema."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_extension TEXT NOT NULL,
            file_created_at REAL,
            file_modified_at REAL,
            
            -- Dimensions & Format
            width INTEGER,
            height INTEGER,
            aspect_ratio REAL,
            color_mode TEXT,
            format TEXT,
            
            -- Classification (Real Camera Photo vs Computer Graphic / Screenshot)
            classification TEXT NOT NULL DEFAULT 'PENDING', -- 'VERIFIED_PHOTO', 'LIKELY_PHOTO', 'SCREENSHOT', 'SYSTEM_ASSET', 'VIDEO', 'UNSUPPORTED'
            classification_score REAL DEFAULT 0.0,
            classification_reason TEXT,
            is_manual_override INTEGER DEFAULT 0,
            
            -- Hashes for Deduplication
            sha256 TEXT NOT NULL,
            phash TEXT,
            dhash TEXT,
            duplicate_group_id TEXT,
            is_primary INTEGER DEFAULT 1,
            duplicate_count INTEGER DEFAULT 0,
            
            -- Key EXIF Metadata
            date_taken TEXT,
            camera_make TEXT,
            camera_model TEXT,
            lens_model TEXT,
            focal_length REAL,
            f_number REAL,
            exposure_time TEXT,
            iso INTEGER,
            flash TEXT,
            orientation INTEGER DEFAULT 1,
            software TEXT,
            
            -- GPS Coordinates
            latitude REAL,
            longitude REAL,
            altitude REAL,
            gps_location_name TEXT,
            
            -- Vector Embedding Status
            has_embedding INTEGER DEFAULT 0,
            
            -- Complete EXIF Dump (JSON)
            raw_exif_json TEXT,
            
            -- Trash Tagging (In-place deferred deletion)
            is_trashed INTEGER DEFAULT 0,
            trashed_at REAL,

            -- Google Drive Backup
            gdrive_file_id TEXT,
            gdrive_backup_status TEXT DEFAULT 'pending',
            gdrive_backed_up_at REAL,
            gdrive_error TEXT,
            
            indexed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_groups (
            id TEXT PRIMARY KEY,
            primary_photo_id INTEGER NOT NULL,
            match_type TEXT NOT NULL, -- 'EXACT_HASH' or 'BURST_SEQUENCE' or 'PERCEPTUAL_PHASH' or 'EMBEDDING'
            total_items INTEGER DEFAULT 1,
            total_wasted_bytes INTEGER DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY (primary_photo_id) REFERENCES photos (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scan_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root_path TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            status TEXT NOT NULL, -- 'RUNNING', 'COMPLETED', 'FAILED', 'STOPPED'
            total_scanned INTEGER DEFAULT 0,
            total_photos INTEGER DEFAULT 0,
            total_screenshots INTEGER DEFAULT 0,
            total_duplicates INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS trash_purge_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purged_at REAL NOT NULL,
            freed_bytes INTEGER NOT NULL,
            photo_count INTEGER NOT NULL,
            reason TEXT NOT NULL,
            message TEXT NOT NULL,
            deleted_files_json TEXT
        );

        CREATE TABLE IF NOT EXISTS dismissed_duplicates (
            photo_id_a INTEGER NOT NULL,
            photo_id_b INTEGER NOT NULL,
            dismissed_at REAL NOT NULL,
            PRIMARY KEY (photo_id_a, photo_id_b)
        );

        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'PERSON', -- 'PERSON', 'PET', 'OTHER'
            avatar_box_id INTEGER,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS detected_boxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            entity_id INTEGER,
            box_type TEXT NOT NULL DEFAULT 'FACE', -- 'FACE', 'PERSON', 'PET'
            label TEXT, -- 'person', 'dog', 'cat', etc.
            confidence REAL DEFAULT 1.0,
            x_min REAL NOT NULL,
            y_min REAL NOT NULL,
            x_max REAL NOT NULL,
            y_max REAL NOT NULL,
            embedding_json TEXT,
            candidate_entities_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'UNASSIGNED', -- 'UNASSIGNED', 'PENDING_REVIEW', 'CONFIRMED', 'REJECTED'
            match_confidence REAL DEFAULT 0.0,
            created_at REAL NOT NULL,
            reviewed_at REAL,
            FOREIGN KEY (photo_id) REFERENCES photos (id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_photos_classification ON photos(classification);
        CREATE INDEX IF NOT EXISTS idx_photos_sha256 ON photos(sha256);
        CREATE INDEX IF NOT EXISTS idx_photos_phash ON photos(phash);
        CREATE INDEX IF NOT EXISTS idx_photos_duplicate_group ON photos(duplicate_group_id);
        CREATE INDEX IF NOT EXISTS idx_photos_date_taken ON photos(date_taken);
        CREATE INDEX IF NOT EXISTS idx_photos_camera_make ON photos(camera_make);
        CREATE INDEX IF NOT EXISTS idx_photos_camera_model ON photos(camera_model);
        CREATE INDEX IF NOT EXISTS idx_photos_file_path ON photos(file_path);
        CREATE INDEX IF NOT EXISTS idx_photos_trashed_class ON photos(is_trashed, classification);
        CREATE INDEX IF NOT EXISTS idx_photos_effective_date ON photos(is_trashed, classification, COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')) DESC);
        CREATE INDEX IF NOT EXISTS idx_photos_dup_primary ON photos(duplicate_group_id, is_primary, is_trashed);
        CREATE INDEX IF NOT EXISTS idx_dismissed_dups ON dismissed_duplicates(photo_id_a, photo_id_b);
        CREATE INDEX IF NOT EXISTS idx_boxes_photo_id ON detected_boxes(photo_id);
        CREATE INDEX IF NOT EXISTS idx_boxes_entity_id ON detected_boxes(entity_id);
        CREATE INDEX IF NOT EXISTS idx_boxes_status ON detected_boxes(status);
        CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
        """)

        # Migration: Ensure is_trashed and trashed_at columns exist on existing DBs
        columns = [row[1] for row in conn.execute("PRAGMA table_info(photos)").fetchall()]
        if "is_trashed" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN is_trashed INTEGER DEFAULT 0")
        if "trashed_at" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN trashed_at REAL")
        if "gdrive_file_id" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN gdrive_file_id TEXT")
        if "gdrive_backup_status" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN gdrive_backup_status TEXT DEFAULT 'pending'")
        if "gdrive_backed_up_at" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN gdrive_backed_up_at REAL")
        if "gdrive_error" not in columns:
            conn.execute("ALTER TABLE photos ADD COLUMN gdrive_error TEXT")
        
        conn.execute("CREATE TABLE IF NOT EXISTS dismissed_duplicates (photo_id_a INTEGER NOT NULL, photo_id_b INTEGER NOT NULL, dismissed_at REAL NOT NULL, PRIMARY KEY (photo_id_a, photo_id_b))")
        conn.execute("CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, entity_type TEXT NOT NULL DEFAULT 'PERSON', avatar_box_id INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL)")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS detected_boxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            entity_id INTEGER,
            box_type TEXT NOT NULL DEFAULT 'FACE',
            label TEXT,
            confidence REAL DEFAULT 1.0,
            x_min REAL NOT NULL,
            y_min REAL NOT NULL,
            x_max REAL NOT NULL,
            y_max REAL NOT NULL,
            embedding_json TEXT,
            candidate_entities_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'UNASSIGNED',
            match_confidence REAL DEFAULT 0.0,
            created_at REAL NOT NULL,
            reviewed_at REAL,
            FOREIGN KEY (photo_id) REFERENCES photos (id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE SET NULL
        )
        """)

        box_columns = [row[1] for row in conn.execute("PRAGMA table_info(detected_boxes)").fetchall()]
        if "candidate_entities_json" not in box_columns:
            conn.execute("ALTER TABLE detected_boxes ADD COLUMN candidate_entities_json TEXT NOT NULL DEFAULT '[]'")

        # Google Drive Backup Settings & Folder Hierarchy Cache
        conn.execute("""
        CREATE TABLE IF NOT EXISTS backup_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            hourly_limit INTEGER DEFAULT 25,
            delay_seconds REAL DEFAULT 30.0,
            root_folder_name TEXT DEFAULT 'LuminaPhoto Backup',
            is_paused INTEGER DEFAULT 0,
            last_backup_at REAL
        )
        """)
        conn.execute("INSERT OR IGNORE INTO backup_settings (id, hourly_limit, delay_seconds, root_folder_name, is_paused) VALUES (1, 25, 30.0, 'LuminaPhoto Backup', 0)")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS gdrive_folder_cache (
            folder_path TEXT PRIMARY KEY,
            folder_id TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS gdrive_delete_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER,
            gdrive_file_id TEXT UNIQUE NOT NULL,
            file_name TEXT,
            queued_at REAL NOT NULL,
            attempts INTEGER DEFAULT 0,
            last_error TEXT
        )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_is_trashed ON photos(is_trashed)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_trashed_class ON photos(is_trashed, classification)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_effective_date ON photos(is_trashed, classification, COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')) DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_dup_primary ON photos(duplicate_group_id, is_primary, is_trashed)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_photos_gdrive_status ON photos(gdrive_backup_status, is_trashed)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dismissed_dups ON dismissed_duplicates(photo_id_a, photo_id_b)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_boxes_photo_id ON detected_boxes(photo_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_boxes_entity_id ON detected_boxes(entity_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_boxes_status ON detected_boxes(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
    conn.close()

ALLOWED_PHOTO_COLUMNS = {
    "file_path", "file_name", "file_size", "file_extension", "file_created_at", "file_modified_at",
    "width", "height", "aspect_ratio", "color_mode", "format",
    "classification", "classification_score", "classification_reason", "is_manual_override",
    "sha256", "phash", "dhash", "duplicate_group_id", "is_primary", "duplicate_count",
    "date_taken", "camera_make", "camera_model", "lens_model", "focal_length", "f_number",
    "exposure_time", "iso", "flash", "orientation", "software",
    "latitude", "longitude", "altitude", "gps_location_name",
    "has_embedding", "raw_exif_json", "is_trashed", "trashed_at",
    "gdrive_file_id", "gdrive_backup_status", "gdrive_backed_up_at", "gdrive_error",
    "indexed_at"
}

def upsert_photo(photo_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Inserts or updates a photo record.
    If the local file's SHA-256 content hash changed since the last scan, automatically
    resets gdrive_backup_status to 'pending' so the updated file is re-synced to Google Drive.
    """
    conn = get_connection(db_path)
    fields = [f for f in photo_data.keys() if f in ALLOWED_PHOTO_COLUMNS]
    if not fields or "file_path" not in fields:
        conn.close()
        raise ValueError("Invalid photo_data columns")
    placeholders = [f":{f}" for f in fields]
    manual_protected = {"classification", "classification_score", "classification_reason"}
    has_explicit_override = bool(photo_data.get("is_manual_override"))
    update_parts = []
    for f in fields:
        if f == "file_path":
            continue
        if f in manual_protected and not has_explicit_override:
            update_parts.append(
                f"{f} = CASE WHEN COALESCE(photos.is_manual_override, 0) = 1 THEN photos.{f} ELSE excluded.{f} END"
            )
        else:
            update_parts.append(f"{f} = excluded.{f}")
    if "sha256" in fields and "gdrive_backup_status" not in fields:
        update_parts.append(
            "gdrive_backup_status = CASE "
            "WHEN excluded.sha256 IS NOT NULL AND photos.sha256 IS NOT NULL AND excluded.sha256 != photos.sha256 "
            "THEN 'pending' ELSE photos.gdrive_backup_status END"
        )
    update_clause = ", ".join(update_parts)
    
    sql = f"""
    INSERT INTO photos ({', '.join(fields)})
    VALUES ({', '.join(placeholders)})
    ON CONFLICT(file_path) DO UPDATE SET
    {update_clause}
    RETURNING id;
    """
    
    with conn:
        cursor = conn.execute(sql, photo_data)
        photo_id = cursor.fetchone()[0]
    conn.close()
    return photo_id

def get_photo_by_id(photo_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a single photo record by ID."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        data = dict(row)
        if data.get("raw_exif_json"):
            try:
                data["raw_exif"] = json.loads(data["raw_exif_json"])
            except Exception:
                data["raw_exif"] = {}
        return data
    return None

def tag_photo_trash(photo_id: int, is_trashed: bool = True, db_path: Optional[str] = None) -> bool:
    """Tags or untags a photo for the trash non-destructively."""
    import time
    conn = get_connection(db_path)
    trashed_val = 1 if is_trashed else 0
    trashed_at = time.time() if is_trashed else None
    with conn:
        cursor = conn.execute(
            "UPDATE photos SET is_trashed = ?, trashed_at = ? WHERE id = ?",
            (trashed_val, trashed_at, photo_id)
        )
        updated = cursor.rowcount > 0
    conn.close()
    return updated

def batch_tag_photo_trash(photo_ids: List[int], is_trashed: bool = True, db_path: Optional[str] = None) -> int:
    """Tags or untags multiple photos for the trash non-destructively."""
    import time
    if not photo_ids:
        return 0
    conn = get_connection(db_path)
    trashed_val = 1 if is_trashed else 0
    trashed_at = time.time() if is_trashed else None
    placeholders = ",".join("?" for _ in photo_ids)
    sql = f"UPDATE photos SET is_trashed = ?, trashed_at = ? WHERE id IN ({placeholders})"
    with conn:
        cursor = conn.execute(sql, [trashed_val, trashed_at, *photo_ids])
        count = cursor.rowcount
    conn.close()
    return count

def trash_all_duplicates(db_path: Optional[str] = None) -> Tuple[int, int]:
    """
    Tags all non-primary duplicate copies in the library as trashed (is_trashed = 1).
    Keeps all primary keeper photos safe and untouched.
    Returns (tagged_count, freed_bytes).
    """
    import time
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT id, file_size FROM photos
        WHERE duplicate_group_id IS NOT NULL
          AND is_primary = 0
          AND is_trashed = 0
    """).fetchall()
    
    if not rows:
        conn.close()
        return 0, 0
    
    pids = [r["id"] for r in rows]
    total_bytes = sum(r["file_size"] or 0 for r in rows)
    trashed_at = time.time()
    placeholders = ",".join("?" for _ in pids)
    with conn:
        conn.execute(f"UPDATE photos SET is_trashed = 1, trashed_at = ? WHERE id IN ({placeholders})", [trashed_at, *pids])
        # Immediately update surviving keeper photos so their duplicate status and badges clear in real-time
        conn.execute("""
            UPDATE photos
            SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0
            WHERE is_primary = 1
              AND duplicate_group_id IS NOT NULL
              AND duplicate_group_id NOT IN (
                  SELECT duplicate_group_id FROM photos WHERE is_primary = 0 AND is_trashed = 0 AND duplicate_group_id IS NOT NULL
              )
        """)
        conn.execute("""
            DELETE FROM duplicate_groups
            WHERE id NOT IN (
                SELECT DISTINCT duplicate_group_id FROM photos WHERE is_trashed = 0 AND duplicate_group_id IS NOT NULL
            )
        """)
    conn.close()
    return len(pids), total_bytes

def trash_group_duplicates(group_id: str, db_path: Optional[str] = None) -> Tuple[int, int]:
    """
    Tags all non-primary duplicate copies for a specific group as trashed.
    Keeps primary keeper photo safe.
    Returns (tagged_count, freed_bytes).
    """
    import time
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT id, file_size FROM photos
        WHERE duplicate_group_id = ?
          AND is_primary = 0
          AND is_trashed = 0
    """, (group_id,)).fetchall()
    
    if not rows:
        conn.close()
        return 0, 0
    
    pids = [r["id"] for r in rows]
    total_bytes = sum(r["file_size"] or 0 for r in rows)
    trashed_at = time.time()
    placeholders = ",".join("?" for _ in pids)
    with conn:
        conn.execute(f"UPDATE photos SET is_trashed = 1, trashed_at = ? WHERE id IN ({placeholders})", [trashed_at, *pids])
        # Check active non-trashed photos left in this group
        remaining = conn.execute("SELECT id FROM photos WHERE duplicate_group_id = ? AND is_trashed = 0", (group_id,)).fetchall()
        if len(remaining) <= 1:
            conn.execute("UPDATE photos SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0 WHERE duplicate_group_id = ?", (group_id,))
            conn.execute("DELETE FROM duplicate_groups WHERE id = ?", (group_id,))
        else:
            conn.execute("UPDATE photos SET duplicate_count = ? WHERE duplicate_group_id = ? AND is_trashed = 0", (len(remaining) - 1, group_id))
            conn.execute("UPDATE duplicate_groups SET total_items = ? WHERE id = ?", (len(remaining), group_id))
    conn.close()
    return len(pids), total_bytes

def get_trashed_photos(limit: int = 200, offset: int = 0, db_path: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int, int]:
    """Returns paginated trashed photos, total trashed count, and total recoverable bytes."""
    conn = get_connection(db_path)
    count_row = conn.execute("SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM photos WHERE is_trashed = 1").fetchone()
    total_count = count_row[0]
    total_bytes = count_row[1]

    cursor = conn.execute("""
    SELECT id, file_path, file_name, file_size, file_extension, width, height, aspect_ratio,
           classification, classification_score, classification_reason, is_manual_override,
           sha256, phash, duplicate_group_id, is_primary, duplicate_count,
           date_taken, camera_make, camera_model, lens_model, focal_length, f_number, exposure_time, iso,
           latitude, longitude, altitude, has_embedding, is_trashed, trashed_at,
           gdrive_file_id, gdrive_backup_status, gdrive_backed_up_at, gdrive_error, indexed_at
    FROM photos
    WHERE is_trashed = 1
    ORDER BY trashed_at DESC, id DESC
    LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows, total_count, total_bytes

def log_trash_purge(freed_bytes: int, photo_count: int, reason: str, message: str, deleted_files: list, db_path: Optional[str] = None) -> int:
    """Logs an automated or manual space purge event."""
    import time
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("""
        INSERT INTO trash_purge_logs (purged_at, freed_bytes, photo_count, reason, message, deleted_files_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            freed_bytes,
            photo_count,
            reason,
            message,
            json.dumps(deleted_files)
        ))
        log_id = cursor.lastrowid or 0
    conn.close()
    return log_id

def get_trash_purge_logs(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves history of permanent deletions and space purges."""
    conn = get_connection(db_path)
    cursor = conn.execute("""
    SELECT id, purged_at, freed_bytes, photo_count, reason, message, deleted_files_json
    FROM trash_purge_logs
    ORDER BY purged_at DESC, id DESC
    LIMIT ?
    """, (limit,))
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        try:
            d["deleted_files"] = json.loads(d["deleted_files_json"]) if d.get("deleted_files_json") else []
        except Exception:
            d["deleted_files"] = []
        rows.append(d)
    conn.close()
    return rows

def get_known_entity_folders(db_path: Optional[str] = None) -> List[str]:
    """Extracts distinct leaf directory names that represent user albums, entities, and subjects."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT file_path FROM photos LIMIT 5000")
    paths = [r["file_path"] for r in cursor.fetchall()]
    conn.close()

    ignored_names = {
        "users", "c:", "onedrive", "pictures", "photo", "photos", "desktop",
        "documents", "downloads", "camera roll", "test_folder", "appdata",
        "temp", "cache", ".lumina_cache", "node_modules", "system32", "windows"
    }

    folders = set()
    for p in paths:
        norm = os.path.normpath(p)
        dir_name = os.path.dirname(norm)
        for part in dir_name.split(os.sep):
            low = part.lower().strip()
            if len(low) >= 3 and low not in ignored_names and not low.startswith((".", "$")):
                folders.add(low)

    return sorted(list(folders))

def get_photos(
    classification: Optional[str] = None,
    include_duplicates: bool = True,
    camera_make: Optional[str] = None,
    has_gps: Optional[bool] = None,
    year: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    folder_keyword: Optional[str] = None,
    entity_id: Optional[int] = None,
    sort_by: str = "date_taken",
    sort_order: str = "DESC",
    is_trashed: Optional[bool] = False,
    limit: int = 100,
    offset: int = 0,
    photo_ids: Optional[List[int]] = None,
    skip_count: bool = False,
    known_total: Optional[int] = None,
    db_path: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated photos with comprehensive metadata, date range, and entity filtering."""
    conn = get_connection(db_path)
    conditions = []
    params = []

    if entity_id is not None:
        conditions.append("id IN (SELECT photo_id FROM detected_boxes WHERE entity_id = ? AND status IN ('CONFIRMED', 'PENDING_REVIEW'))")
        params.append(entity_id)

    if photo_ids is not None:
        clean_ids = list(photo_ids)
        if not clean_ids:
            conn.close()
            return [], 0
        placeholders = ",".join("?" for _ in clean_ids)
        conditions.append(f"id IN ({placeholders})")
        params.extend(clean_ids)

    if is_trashed is not None:
        conditions.append("is_trashed = ?")
        params.append(1 if is_trashed else 0)

    if classification == "ALL":
        pass  # Don't filter by classification
    elif classification == "REAL_PHOTOS" or classification is None:
        # Default to showing genuine camera photos unless photo_ids or entity_id is explicitly provided
        if photo_ids is None and entity_id is None:
            conditions.append("classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO')")
    elif classification:
        conditions.append("classification = ?")
        params.append(classification)

    if not include_duplicates and photo_ids is None:
        conditions.append("(duplicate_group_id IS NULL OR is_primary = 1)")

    if camera_make:
        conditions.append("camera_make LIKE ?")
        params.append(f"%{camera_make}%")

    if has_gps is True:
        conditions.append("latitude IS NOT NULL AND longitude IS NOT NULL")
    elif has_gps is False:
        conditions.append("(latitude IS NULL OR longitude IS NULL)")

    if year:
        conditions.append("SUBSTR(COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')), 1, 4) = ?")
        params.append(year)

    if date_from:
        conditions.append("COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')) >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')) <= ?")
        params.append(date_to)

    if folder_keyword:
        conditions.append("(file_path LIKE ? OR file_name LIKE ?)")
        kw_param = f"%{folder_keyword}%"
        params.extend([kw_param, kw_param])

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Count total (skip if known or already constrained by photo_ids)
    if photo_ids is not None:
        total_count = len(photo_ids)
    elif skip_count and known_total is not None:
        total_count = known_total
    else:
        count_sql = f"SELECT COUNT(*) FROM photos {where_clause}"
        cursor = conn.execute(count_sql, params)
        total_count = cursor.fetchone()[0]

    # Handle custom sorting (matches idx_photos_effective_date index)
    allowed_sorts = {
        "date_taken": "COALESCE(date_taken, datetime(file_modified_at, 'unixepoch'))",
        "file_name": "file_name",
        "file_size": "file_size",
        "indexed_at": "indexed_at",
        "trashed_at": "trashed_at"
    }
    order_col = allowed_sorts.get(sort_by, "COALESCE(date_taken, datetime(file_modified_at, 'unixepoch'))")
    order_dir = "DESC" if sort_order.upper() == "DESC" else "ASC"

    # Query items
    query_sql = f"""
    SELECT id, file_path, file_name, file_size, file_extension, width, height, aspect_ratio,
           classification, classification_score, classification_reason, is_manual_override,
           sha256, phash, duplicate_group_id, is_primary, duplicate_count,
           date_taken, camera_make, camera_model, lens_model, focal_length, f_number, exposure_time, iso,
           latitude, longitude, altitude, has_embedding, is_trashed, trashed_at,
           gdrive_file_id, gdrive_backup_status, gdrive_backed_up_at, gdrive_error, indexed_at
    FROM photos
    {where_clause}
    ORDER BY {order_col} {order_dir}
    LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    cursor = conn.execute(query_sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows, total_count

def get_duplicate_groups(
    db_path: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves all duplicate groups with primary and duplicate members, with optional sorting and category filtering."""
    conn = get_connection(db_path)
    cursor = conn.execute("""
    SELECT dg.id as group_id, dg.match_type, dg.total_items, dg.total_wasted_bytes,
           p.id, p.file_path, p.file_name, p.file_size, p.width, p.height, p.date_taken,
           p.file_modified_at, p.camera_make, p.camera_model, p.is_primary, p.sha256, p.phash
    FROM duplicate_groups dg
    JOIN photos p ON p.duplicate_group_id = dg.id
    WHERE p.is_trashed = 0
    ORDER BY dg.total_wasted_bytes DESC, dg.id, p.is_primary DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    groups_map = {}
    for r in rows:
        gid = r["group_id"]
        if gid not in groups_map:
            groups_map[gid] = {
                "group_id": gid,
                "match_type": r["match_type"],
                "total_items": r["total_items"],
                "total_wasted_bytes": r["total_wasted_bytes"],
                "primary": None,
                "duplicates": []
            }
        item_data = {
            "id": r["id"],
            "file_path": r["file_path"],
            "file_name": r["file_name"],
            "file_size": r["file_size"],
            "width": r["width"],
            "height": r["height"],
            "date_taken": r["date_taken"],
            "file_modified_at": r["file_modified_at"] if "file_modified_at" in r.keys() else None,
            "camera_make": r["camera_make"],
            "camera_model": r["camera_model"],
            "is_primary": bool(r["is_primary"]),
            "sha256": r["sha256"],
            "phash": r["phash"]
        }
        if r["is_primary"]:
            groups_map[gid]["primary"] = item_data
        else:
            groups_map[gid]["duplicates"].append(item_data)

    valid_groups = [g for g in groups_map.values() if len(g["duplicates"]) > 0]

    # Compute helper fields: date_taken, duplicate_count, and effective sort key
    for g in valid_groups:
        g["duplicate_count"] = len(g["duplicates"])
        p = g.get("primary")
        effective_date = (p.get("date_taken") if p else None)
        effective_mtime = (p.get("file_modified_at") if p else None)
        if not effective_date:
            for d in g["duplicates"]:
                if d.get("date_taken"):
                    effective_date = d["date_taken"]
                    break
                if not effective_mtime and d.get("file_modified_at"):
                    effective_mtime = d["file_modified_at"]

        g["date_taken"] = effective_date
        g["file_modified_at"] = effective_mtime

    # Category filtering (e.g. 'all', 'exact', 'burst', 'similar')
    if category:
        cat = category.strip().lower()
        if cat in ("exact", "exact_hash"):
            valid_groups = [g for g in valid_groups if g.get("match_type") == "EXACT_HASH"]
        elif cat in ("burst", "burst_sequence", "bursts", "continuous"):
            valid_groups = [g for g in valid_groups if g.get("match_type") == "BURST_SEQUENCE"]
        elif cat in ("similar", "perceptual", "perceptual_phash"):
            valid_groups = [g for g in valid_groups if g.get("match_type") == "PERCEPTUAL_PHASH"]

    # Sorting
    if sort_by:
        s_by = sort_by.lower()
        s_order = (sort_order or "desc").lower()
        is_desc = s_order == "desc"

        if s_by in ("count", "duplicates", "num_duplicates", "duplicate_count"):
            valid_groups.sort(
                key=lambda x: (x.get("duplicate_count", 0), x.get("total_wasted_bytes", 0)),
                reverse=is_desc
            )
        elif s_by in ("date", "date_taken", "age"):
            def date_key(x):
                dt = x.get("date_taken")
                if dt:
                    return str(dt).replace(":", "-")
                mtime = x.get("file_modified_at")
                if mtime:
                    return f"mtime_{mtime}"
                return "0000" if is_desc else "9999"

            valid_groups.sort(key=date_key, reverse=is_desc)
        elif s_by in ("size", "wasted_bytes", "wasted_storage"):
            valid_groups.sort(
                key=lambda x: x.get("total_wasted_bytes", 0),
                reverse=is_desc
            )

    return valid_groups

def get_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves overall library statistics."""
    conn = get_connection(db_path)
    
    total_photos = conn.execute("SELECT COUNT(*) FROM photos WHERE classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') AND is_trashed = 0").fetchone()[0]
    total_screenshots = conn.execute("SELECT COUNT(*) FROM photos WHERE classification IN ('SCREENSHOT', 'SYSTEM_ASSET') AND is_trashed = 0").fetchone()[0]
    total_duplicates = conn.execute("SELECT COUNT(*) FROM photos WHERE is_primary = 0 AND is_trashed = 0").fetchone()[0]
    total_bytes = conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM photos WHERE is_trashed = 0").fetchone()[0]
    total_wasted = conn.execute("SELECT COALESCE(SUM(total_wasted_bytes), 0) FROM duplicate_groups").fetchone()[0]
    
    trash_row = conn.execute("SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM photos WHERE is_trashed = 1").fetchone()
    total_trashed = trash_row[0]
    trashed_bytes = trash_row[1]
    
    # Camera breakdown
    cameras = conn.execute("""
    SELECT camera_make, camera_model, COUNT(*) as count 
    FROM photos 
    WHERE camera_make IS NOT NULL AND camera_make != '' AND is_trashed = 0
    GROUP BY camera_make, camera_model 
    ORDER BY count DESC LIMIT 10
    """).fetchall()

    # Timeline years breakdown
    years = conn.execute("""
    SELECT SUBSTR(date_taken, 1, 4) as year, COUNT(*) as count
    FROM photos
    WHERE date_taken IS NOT NULL AND LENGTH(date_taken) >= 4 AND (year LIKE '20%' OR year LIKE '19%') AND is_trashed = 0
    GROUP BY year
    ORDER BY year DESC
    """).fetchall()

    conn.close()
    return {
        "total_photos": total_photos,
        "total_screenshots": total_screenshots,
        "total_duplicates": total_duplicates,
        "total_bytes": total_bytes,
        "total_wasted_bytes": total_wasted,
        "total_trashed": total_trashed,
        "trashed_bytes": trashed_bytes,
        "top_cameras": [dict(c) for c in cameras],
        "timeline_years": [dict(y) for y in years]
    }

def record_dismissed_pairs(pairs: List[Tuple[int, int]], db_path: Optional[str] = None):
    """Records pairwise photo IDs that the user has dismissed so they are never grouped again."""
    if not pairs:
        return
    import time
    now = time.time()
    conn = get_connection(db_path)
    with conn:
        for a, b in pairs:
            p1, p2 = (a, b) if a < b else (b, a)
            conn.execute(
                "INSERT OR IGNORE INTO dismissed_duplicates (photo_id_a, photo_id_b, dismissed_at) VALUES (?, ?, ?)",
                (p1, p2, now)
            )
    conn.close()

def get_dismissed_pairs_set(db_path: Optional[str] = None) -> set:
    """Returns a set of (min_id, max_id) tuples of user-dismissed duplicate pairs."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT photo_id_a, photo_id_b FROM dismissed_duplicates")
        return {(r[0], r[1]) for r in cursor.fetchall()}
    except Exception:
        return set()
    finally:
        conn.close()

# ---------------------------------------------------------
# People & Pets Entity and Bounding Box Operations
# ---------------------------------------------------------

def get_or_create_entity(name: str, entity_type: str = "PERSON", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Gets an existing entity by name (case-insensitive) or creates a new one."""
    import time
    name_clean = name.strip()
    if not name_clean:
        raise ValueError("Entity name cannot be empty")
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM entities WHERE LOWER(name) = LOWER(?)", (name_clean,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        
        now = time.time()
        with conn:
            cursor = conn.execute(
                "INSERT INTO entities (name, entity_type, created_at, updated_at) VALUES (?, ?, ?, ?) RETURNING id",
                (name_clean, entity_type.upper(), now, now)
            )
            new_id = cursor.fetchone()[0]
            cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (new_id,))
            return dict(cursor.fetchone())
    finally:
        conn.close()

def repair_entity_avatars(db_path: Optional[str] = None) -> int:
    """
    Repairs any entities whose avatar_box_id points to a deleted, rejected, or reassigned box
    by updating avatar_box_id to the entity's highest-confidence CONFIRMED (or PENDING_REVIEW) box, or NULL.
    """
    conn = get_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("""
            UPDATE entities
            SET avatar_box_id = (
                SELECT b2.id FROM detected_boxes b2
                WHERE b2.entity_id = entities.id AND b2.status IN ('CONFIRMED', 'PENDING_REVIEW')
                ORDER BY CASE WHEN b2.status = 'CONFIRMED' THEN 0 ELSE 1 END, b2.confidence DESC, b2.id ASC
                LIMIT 1
            )
            WHERE avatar_box_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM detected_boxes b_av
                  WHERE b_av.id = entities.avatar_box_id
                    AND b_av.entity_id = entities.id
                    AND b_av.status != 'REJECTED'
              )
            """)
            return cursor.rowcount
    finally:
        conn.close()

def list_entities(entity_type: Optional[str] = None, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists all entities with total photos count, confirmed count, pending review count, and validated avatar."""
    conn = get_connection(db_path)
    filter_sql = ""
    params: List[Any] = []
    if entity_type:
        filter_sql = "WHERE e.entity_type = ?"
        params.append(entity_type.upper())
    
    sql = f"""
    SELECT 
        e.id,
        e.name,
        e.entity_type,
        e.created_at,
        e.updated_at,
        CASE
            WHEN EXISTS (
                SELECT 1 FROM detected_boxes b_av
                WHERE b_av.id = e.avatar_box_id AND b_av.entity_id = e.id AND b_av.status != 'REJECTED'
            ) THEN e.avatar_box_id
            ELSE (
                SELECT b2.id FROM detected_boxes b2 
                WHERE b2.entity_id = e.id AND b2.status IN ('CONFIRMED', 'PENDING_REVIEW')
                ORDER BY CASE WHEN b2.status = 'CONFIRMED' THEN 0 ELSE 1 END, b2.confidence DESC, b2.id ASC LIMIT 1
            )
        END as avatar_box_id,
        COUNT(DISTINCT CASE WHEN b.status IN ('CONFIRMED', 'PENDING_REVIEW') THEN b.photo_id END) as total_photos,
        COUNT(CASE WHEN b.status = 'CONFIRMED' THEN 1 END) as confirmed_count,
        COUNT(CASE WHEN b.status = 'PENDING_REVIEW' THEN 1 END) as pending_count,
        (
            SELECT b2.id FROM detected_boxes b2 
            WHERE b2.entity_id = e.id AND b2.status IN ('CONFIRMED', 'PENDING_REVIEW')
            ORDER BY CASE WHEN b2.status = 'CONFIRMED' THEN 0 ELSE 1 END, b2.confidence DESC, b2.id ASC LIMIT 1
        ) as representative_box_id
    FROM entities e
    LEFT JOIN detected_boxes b ON b.entity_id = e.id
    {filter_sql}
    GROUP BY e.id
    ORDER BY confirmed_count DESC, total_photos DESC, e.name ASC
    """
    cursor = conn.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_entity_by_id(entity_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves single entity by ID."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_photo_tag_scores_for_entities(entity_ids: List[int], db_path: Optional[str] = None) -> Dict[int, float]:
    """
    Returns a map of {photo_id: tag_score} for photos tagged with the specified entity_ids
    (status IN ('CONFIRMED', 'PENDING_REVIEW')).
    If multiple entity_ids are requested and at least one photo contains all of them,
    returns only the intersection (photos containing all requested entities); otherwise returns the union.
    """
    unique_eids = list({int(eid) for eid in (entity_ids or []) if eid is not None})
    if not unique_eids:
        return {}

    conn = get_connection(db_path)
    try:
        placeholders = ",".join("?" for _ in unique_eids)
        sql = f"""
        SELECT photo_id, entity_id, status, match_confidence
        FROM detected_boxes
        WHERE entity_id IN ({placeholders})
          AND status IN ('CONFIRMED', 'PENDING_REVIEW')
        """
        cursor = conn.execute(sql, unique_eids)
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return {}

    photo_entities: Dict[int, set] = {}
    photo_scores: Dict[int, float] = {}

    for r in rows:
        pid = int(r["photo_id"])
        eid = int(r["entity_id"])
        status = r["status"]
        conf = float(r["match_confidence"] or 0.85)
        score = 1.0 if status == "CONFIRMED" else max(0.85, min(0.98, conf))

        if pid not in photo_entities:
            photo_entities[pid] = set()
        photo_entities[pid].add(eid)

        if pid not in photo_scores or score > photo_scores[pid]:
            photo_scores[pid] = round(score, 4)

    if len(unique_eids) > 1:
        target_count = len(unique_eids)
        intersection_scores = {
            pid: photo_scores[pid]
            for pid, eids in photo_entities.items()
            if len(eids) == target_count
        }
        if intersection_scores:
            return intersection_scores

    return photo_scores

def update_entity(entity_id: int, name: Optional[str] = None, entity_type: Optional[str] = None, avatar_box_id: Optional[int] = None, db_path: Optional[str] = None) -> bool:
    """Updates entity metadata."""
    import time
    conn = get_connection(db_path)
    updates = ["updated_at = ?"]
    params: List[Any] = [time.time()]
    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())
    if entity_type is not None:
        updates.append("entity_type = ?")
        params.append(entity_type.upper())
    if avatar_box_id is not None:
        updates.append("avatar_box_id = ?")
        params.append(avatar_box_id)
    params.append(entity_id)
    
    with conn:
        cursor = conn.execute(f"UPDATE entities SET {', '.join(updates)} WHERE id = ?", params)
        success = cursor.rowcount > 0
    conn.close()
    return success

def delete_entity(entity_id: int, db_path: Optional[str] = None) -> bool:
    """Deletes an entity and resets associated boxes to UNASSIGNED."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("UPDATE detected_boxes SET entity_id = NULL, status = 'UNASSIGNED' WHERE entity_id = ?", (entity_id,))
        cursor = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        success = cursor.rowcount > 0
    conn.close()
    return success

ALLOWED_BOX_COLUMNS = {
    "photo_id", "entity_id", "box_type", "label", "confidence",
    "x_min", "y_min", "x_max", "y_max",
    "embedding_json", "candidate_entities_json", "status", "match_confidence",
    "created_at", "reviewed_at"
}

def insert_detected_box(box_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """Inserts a detected bounding box."""
    import time
    conn = get_connection(db_path)
    if "created_at" not in box_data:
        box_data["created_at"] = time.time()
    fields = [f for f in box_data.keys() if f in ALLOWED_BOX_COLUMNS]
    if not fields or "photo_id" not in fields:
        conn.close()
        raise ValueError("Invalid box_data columns")
    placeholders = [f":{f}" for f in fields]
    sql = f"INSERT INTO detected_boxes ({', '.join(fields)}) VALUES ({', '.join(placeholders)}) RETURNING id;"
    with conn:
        cursor = conn.execute(sql, box_data)
        box_id = cursor.fetchone()[0]
    conn.close()
    return box_id

def get_boxes_for_photo(photo_id: int, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all detected boxes for a photo joined with entity name and type."""
    conn = get_connection(db_path)
    sql = """
    SELECT 
        b.*,
        e.name as entity_name,
        e.entity_type
    FROM detected_boxes b
    LEFT JOIN entities e ON b.entity_id = e.id
    WHERE b.photo_id = ? AND b.status != 'REJECTED'
    ORDER BY b.confidence DESC
    """
    cursor = conn.execute(sql, (photo_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_box_by_id(box_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves single box by ID with photo and entity information."""
    conn = get_connection(db_path)
    sql = """
    SELECT 
        b.*,
        p.file_path,
        p.file_name,
        p.width,
        p.height,
        e.name as entity_name,
        e.entity_type
    FROM detected_boxes b
    JOIN photos p ON b.photo_id = p.id
    LEFT JOIN entities e ON b.entity_id = e.id
    WHERE b.id = ?
    """
    cursor = conn.execute(sql, (box_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_box_entity(box_id: int, entity_id: Optional[int], status: str = "CONFIRMED", match_confidence: float = 1.0, db_path: Optional[str] = None) -> bool:
    """Assigns or updates entity and status for a detected box."""
    import time
    conn = get_connection(db_path)
    now = time.time()
    with conn:
        cursor = conn.execute(
            "UPDATE detected_boxes SET entity_id = ?, status = ?, match_confidence = ?, candidate_entities_json = '[]', reviewed_at = ? WHERE id = ?",
            (entity_id, status, match_confidence, now, box_id)
        )
        success = cursor.rowcount > 0
    conn.close()
    if success:
        repair_entity_avatars(db_path)
    return success

def update_box_dimensions(
    box_id: int,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    db_path: Optional[str] = None
) -> bool:
    """Updates the normalized boundary coordinates of a box."""
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            "UPDATE detected_boxes SET x_min = ?, y_min = ?, x_max = ?, y_max = ? WHERE id = ?",
            (x_min, y_min, x_max, y_max, box_id)
        )
        success = cursor.rowcount > 0
    conn.close()
    return success


def confirm_box(box_id: int, entity_id: Optional[int] = None, db_path: Optional[str] = None) -> bool:
    """Confirms an auto-tagged or manual box suggestion."""
    import time
    conn = get_connection(db_path)
    now = time.time()
    with conn:
        if entity_id is not None:
            cursor = conn.execute(
                "UPDATE detected_boxes SET entity_id = ?, status = 'CONFIRMED', candidate_entities_json = '[]', reviewed_at = ? WHERE id = ?",
                (entity_id, now, box_id)
            )
        else:
            cursor = conn.execute(
                "UPDATE detected_boxes SET status = 'CONFIRMED', candidate_entities_json = '[]', reviewed_at = ? WHERE id = ? AND entity_id IS NOT NULL",
                (now, box_id)
            )
        success = cursor.rowcount > 0
    conn.close()
    return success

def reject_box(box_id: int, db_path: Optional[str] = None) -> bool:
    """Rejects an auto-tagged box suggestion."""
    import time
    conn = get_connection(db_path)
    now = time.time()
    with conn:
        cursor = conn.execute(
            "UPDATE detected_boxes SET status = 'REJECTED', reviewed_at = ? WHERE id = ?",
            (now, box_id)
        )
        success = cursor.rowcount > 0
    conn.close()
    if success:
        repair_entity_avatars(db_path)
    return success

def batch_confirm_boxes(box_ids: List[int], db_path: Optional[str] = None) -> int:
    """Confirms multiple boxes at once."""
    if not box_ids:
        return 0
    import time
    now = time.time()
    conn = get_connection(db_path)
    placeholders = ",".join("?" for _ in box_ids)
    sql = f"UPDATE detected_boxes SET status = 'CONFIRMED', candidate_entities_json = '[]', reviewed_at = ? WHERE id IN ({placeholders}) AND entity_id IS NOT NULL"
    with conn:
        cursor = conn.execute(sql, [now] + box_ids)
        count = cursor.rowcount
    conn.close()
    return count

def confirm_all_pending_boxes(db_path: Optional[str] = None) -> int:
    """Confirms every currently pending auto-match in one database operation."""
    import time
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            "UPDATE detected_boxes SET status = 'CONFIRMED', candidate_entities_json = '[]', reviewed_at = ? "
            "WHERE status = 'PENDING_REVIEW' AND entity_id IS NOT NULL "
            "AND json_array_length(candidate_entities_json) <= 1",
            (time.time(),)
        )
        count = cursor.rowcount
    conn.close()
    return count

def get_pending_review_boxes(limit: int = 60, offset: int = 0, entity_id: Optional[int] = None, db_path: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves all high-confidence auto-matches waiting for user review."""
    conn = get_connection(db_path)
    filter_clause = "b.status = 'PENDING_REVIEW'"
    params: List[Any] = []
    if entity_id is not None:
        filter_clause += " AND b.entity_id = ?"
        params.append(entity_id)
    
    count_cursor = conn.execute(f"SELECT COUNT(*) FROM detected_boxes b WHERE {filter_clause}", params)
    total = count_cursor.fetchone()[0]

    sql = f"""
    SELECT 
        b.*,
        p.file_path,
        p.file_name,
        p.date_taken,
        e.name as entity_name,
        e.entity_type
    FROM detected_boxes b
    JOIN photos p ON b.photo_id = p.id
    JOIN entities e ON b.entity_id = e.id
    WHERE {filter_clause}
    ORDER BY b.match_confidence DESC, b.id DESC
    LIMIT ? OFFSET ?
    """
    cursor = conn.execute(sql, params + [limit, offset])
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return items, total

def delete_box(box_id: int, db_path: Optional[str] = None) -> bool:
    """Deletes a detected box and repairs any dangling avatar_box_id references."""
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM detected_boxes WHERE id = ?", (box_id,))
        success = cursor.rowcount > 0
    conn.close()
    if success:
        repair_entity_avatars(db_path)
    return success

def delete_boxes_for_photo(photo_id: int, db_path: Optional[str] = None) -> int:
    """Deletes all detected boxes for a photo and repairs any dangling avatar_box_id references."""
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM detected_boxes WHERE photo_id = ?", (photo_id,))
        count = cursor.rowcount
    conn.close()
    if count > 0:
        repair_entity_avatars(db_path)
    return count

def get_confirmed_embeddings_for_entities(
    db_path: Optional[str] = None,
    entity_type: Optional[str] = None
) -> Dict[int, List[List[float]]]:
    """Retrieves all confirmed 512-d embeddings grouped by entity_id for matching, optionally filtered by entity_type ('PERSON' or 'PET')."""
    conn = get_connection(db_path)
    params: List[Any] = []
    type_clause = ""
    if entity_type:
        type_clause = " AND e.entity_type = ?"
        params.append(entity_type.upper())

    sql = f"""
    SELECT b.entity_id, b.embedding_json 
    FROM detected_boxes b
    JOIN entities e ON e.id = b.entity_id
    WHERE b.status = 'CONFIRMED' AND b.entity_id IS NOT NULL AND b.embedding_json IS NOT NULL{type_clause}
    """
    cursor = conn.execute(sql, params)
    results: Dict[int, List[List[float]]] = {}
    for row in cursor.fetchall():
        eid = row["entity_id"]
        raw = row["embedding_json"]
        if raw:
            try:
                emb = json.loads(raw)
                if isinstance(emb, list) and len(emb) > 0:
                    if eid not in results:
                        results[eid] = []
                    results[eid].append(emb)
            except Exception:
                continue
    conn.close()
    return results

def get_unassigned_boxes(
    limit: int = 60,
    offset: int = 0,
    box_type: Optional[str] = None,
    db_path: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves detected face/pet boxes that are not yet named/assigned to an entity."""
    conn = get_connection(db_path)
    filter_clauses = ["(b.entity_id IS NULL OR b.status = 'UNASSIGNED') AND b.status != 'REJECTED'"]
    params: List[Any] = []
    if box_type and box_type != "ALL":
        filter_clauses.append("b.box_type = ?")
        params.append(box_type.upper())

    where_str = " WHERE " + " AND ".join(filter_clauses)
    
    count_cursor = conn.execute(f"SELECT COUNT(*) FROM detected_boxes b {where_str}", params)
    total = count_cursor.fetchone()[0]

    sql = f"""
    SELECT 
        b.*,
        p.file_path,
        p.file_name,
        p.date_taken,
        p.width,
        p.height
    FROM detected_boxes b
    JOIN photos p ON b.photo_id = p.id
    {where_str}
    ORDER BY b.confidence DESC, b.id DESC
    LIMIT ? OFFSET ?
    """
    cursor = conn.execute(sql, params + [limit, offset])
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows, total

def resolve_duplicate_photo_entity_assignments(db_path: Optional[str] = None) -> int:
    """
    Enforces the single-identity constraint per photo across the entire library.
    If multiple boxes in the same photo are assigned to the same entity, the box with
    the highest priority (CONFIRMED status > match_confidence > confidence > earlier id)
    retains the assignment. All other duplicate boxes for that entity in the same photo
    are unlinked and reset to UNASSIGNED.
    Returns the number of duplicate boxes that were resolved/unlinked.
    """
    conn = get_connection(db_path)
    cursor = conn.execute("""
        SELECT photo_id, entity_id, COUNT(*) as cnt
        FROM detected_boxes
        WHERE entity_id IS NOT NULL AND status != 'REJECTED'
        GROUP BY photo_id, entity_id
        HAVING cnt > 1
    """)
    duplicates = cursor.fetchall()
    unlinked_count = 0

    for row in duplicates:
        photo_id = row["photo_id"]
        entity_id = row["entity_id"]

        box_cursor = conn.execute("""
            SELECT id, status, match_confidence, confidence
            FROM detected_boxes
            WHERE photo_id = ? AND entity_id = ? AND status != 'REJECTED'
        """, (photo_id, entity_id))
        boxes = [dict(b) for b in box_cursor.fetchall()]

        def sort_key(b):
            is_confirmed = 1 if b.get("status") == "CONFIRMED" else 0
            match_conf = b.get("match_confidence") or 0.0
            det_conf = b.get("confidence") or 0.0
            return (is_confirmed, match_conf, det_conf, -b["id"])

        sorted_boxes = sorted(boxes, key=sort_key, reverse=True)
        loser_boxes = sorted_boxes[1:]
        for loser in loser_boxes:
            conn.execute("""
                UPDATE detected_boxes
                SET entity_id = NULL, status = 'UNASSIGNED', match_confidence = 0.0
                WHERE id = ?
            """, (loser["id"],))
            unlinked_count += 1

    conn.commit()
    conn.close()
    return unlinked_count


# =========================================================================
# Google Drive Backup & Sync Operations
# =========================================================================

def get_backup_settings(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieves current Google Drive backup configuration."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT * FROM backup_settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "id": 1,
        "hourly_limit": 25,
        "delay_seconds": 30.0,
        "root_folder_name": "LuminaPhoto Backup",
        "is_paused": 0,
        "last_backup_at": None
    }


def update_backup_settings(
    hourly_limit: Optional[int] = None,
    delay_seconds: Optional[float] = None,
    root_folder_name: Optional[str] = None,
    is_paused: Optional[int] = None,
    last_backup_at: Optional[float] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """Updates backup settings."""
    conn = get_connection(db_path)
    updates = []
    params = []
    if hourly_limit is not None:
        updates.append("hourly_limit = ?")
        params.append(hourly_limit)
    if delay_seconds is not None:
        updates.append("delay_seconds = ?")
        params.append(delay_seconds)
    if root_folder_name is not None:
        updates.append("root_folder_name = ?")
        params.append(root_folder_name)
    if is_paused is not None:
        updates.append("is_paused = ?")
        params.append(is_paused)
    if last_backup_at is not None:
        updates.append("last_backup_at = ?")
        params.append(last_backup_at)

    if updates:
        sql = f"UPDATE backup_settings SET {', '.join(updates)} WHERE id = 1"
        with conn:
            conn.execute(sql, params)
    conn.close()
    return get_backup_settings(db_path)


def get_cached_gdrive_folder(folder_path: str, db_path: Optional[str] = None) -> Optional[str]:
    """Retrieves Google Drive folder ID from cache for a given logical path."""
    conn = get_connection(db_path)
    cursor = conn.execute("SELECT folder_id FROM gdrive_folder_cache WHERE folder_path = ?", (folder_path,))
    row = cursor.fetchone()
    conn.close()
    return row["folder_id"] if row else None


def cache_gdrive_folder(folder_path: str, folder_id: str, db_path: Optional[str] = None):
    """Caches a Google Drive folder ID for a given logical path."""
    import time
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO gdrive_folder_cache (folder_path, folder_id, created_at) VALUES (?, ?, ?)",
            (folder_path, folder_id, time.time())
        )
    conn.close()


def clear_gdrive_folder_cache(db_path: Optional[str] = None):
    """Clears cached Google Drive folder mappings."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM gdrive_folder_cache")
    conn.close()


def delete_cached_gdrive_folder(folder_path: str, db_path: Optional[str] = None):
    """Removes a specific cached folder path from the Google Drive folder cache."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM gdrive_folder_cache WHERE folder_path = ?", (folder_path,))
    conn.close()


def delete_cached_gdrive_folder_by_id(folder_id: str, db_path: Optional[str] = None):
    """Removes any cache entry associated with a specific Google Drive folder ID."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM gdrive_folder_cache WHERE folder_id = ?", (folder_id,))
    conn.close()


def reset_interrupted_uploads(db_path: Optional[str] = None) -> int:
    """Resets any photos stuck in 'uploading' state (e.g. after app restart) back to 'pending'."""
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            "UPDATE photos SET gdrive_backup_status = 'pending' WHERE gdrive_backup_status = 'uploading'"
        )
        count = cursor.rowcount
    conn.close()
    return count


def get_photos_needing_backup(
    limit: int = 25,
    include_failed: bool = False,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Returns photos that need backing up to Google Drive.
    Prioritizes active photos (is_trashed = 0) first, followed by trashed photos that have never
    been uploaded yet (is_trashed = 1 AND gdrive_file_id IS NULL) so that even photos in Trash
    retain a cloud backup until the Trash is emptied.
    By default excludes 'failed' photos so a single failing file never blocks the queue.
    """
    conn = get_connection(db_path)
    if include_failed:
        status_clause = "(gdrive_backup_status IS NULL OR gdrive_backup_status IN ('pending', 'failed'))"
    else:
        status_clause = "(gdrive_backup_status IS NULL OR gdrive_backup_status = 'pending')"

    cursor = conn.execute(f"""
        SELECT id, file_path, file_name, file_size, sha256, date_taken, file_modified_at,
               is_trashed, gdrive_file_id, gdrive_backup_status, gdrive_backed_up_at, gdrive_error
        FROM photos
        WHERE (is_trashed = 0 OR (is_trashed = 1 AND gdrive_file_id IS NULL))
          AND {status_clause}
        ORDER BY
            is_trashed ASC,
            CASE WHEN gdrive_backup_status = 'failed' THEN 1 ELSE 0 END ASC,
            COALESCE(date_taken, datetime(file_modified_at, 'unixepoch')) DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_trashed_photos_needing_gdrive_sync(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns photos marked as trashed locally that still have a Google Drive file ID
    and haven't been trashed on Google Drive yet.
    """
    conn = get_connection(db_path)
    cursor = conn.execute("""
        SELECT id, file_path, file_name, gdrive_file_id, gdrive_backup_status
        FROM photos
        WHERE is_trashed = 1
          AND gdrive_file_id IS NOT NULL
          AND (gdrive_backup_status != 'trashed' AND gdrive_backup_status != 'deleted')
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_restored_photos_needing_gdrive_sync(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns photos that were restored locally (is_trashed = 0) while still marked
    as 'trashed' on Google Drive so they can be untrashed on Drive.
    """
    conn = get_connection(db_path)
    cursor = conn.execute("""
        SELECT id, file_path, file_name, gdrive_file_id, gdrive_backup_status
        FROM photos
        WHERE is_trashed = 0
          AND gdrive_file_id IS NOT NULL
          AND gdrive_backup_status = 'trashed'
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def update_photo_gdrive_status(
    photo_id: int,
    status: str,
    file_id: Optional[str] = None,
    error: Optional[str] = None,
    db_path: Optional[str] = None
):
    """Updates Google Drive backup status and timestamp for a single photo."""
    import time
    conn = get_connection(db_path)
    updates = ["gdrive_backup_status = ?"]
    params = [status]

    if file_id is not None:
        updates.append("gdrive_file_id = ?")
        params.append(file_id)

    if status == "backed_up":
        updates.append("gdrive_backed_up_at = ?")
        params.append(time.time())
        updates.append("gdrive_error = NULL")
    elif error is not None:
        updates.append("gdrive_error = ?")
        params.append(error)

    params.append(photo_id)
    sql = f"UPDATE photos SET {', '.join(updates)} WHERE id = ?"
    with conn:
        conn.execute(sql, params)
    conn.close()


def clear_photo_gdrive_file_id(photo_id: int, db_path: Optional[str] = None):
    """Clears a stale/deleted Google Drive file ID and marks the photo 'pending' for re-upload."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "UPDATE photos SET gdrive_file_id = NULL, gdrive_backup_status = 'pending', gdrive_error = NULL WHERE id = ?",
            (photo_id,)
        )
    conn.close()


def enqueue_gdrive_permanent_delete(
    gdrive_file_id: str,
    photo_id: Optional[int] = None,
    file_name: Optional[str] = None,
    db_path: Optional[str] = None
):
    """
    Records a Google Drive file ID in the persistent deletion ledger so it is guaranteed
    to be permanently deleted from Google Drive even if the app is offline when Trash is emptied.
    """
    import time
    if not gdrive_file_id:
        return
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT OR IGNORE INTO gdrive_delete_queue (photo_id, gdrive_file_id, file_name, queued_at, attempts)
            VALUES (?, ?, ?, ?, 0)
        """, (photo_id, gdrive_file_id, file_name or "", time.time()))
    conn.close()


def get_pending_gdrive_deletes(limit: int = 50, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns queued permanent Google Drive deletions."""
    conn = get_connection(db_path)
    cursor = conn.execute("""
        SELECT id, photo_id, gdrive_file_id, file_name, queued_at, attempts, last_error
        FROM gdrive_delete_queue
        WHERE attempts < 10
        ORDER BY queued_at ASC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def remove_pending_gdrive_delete(gdrive_file_id: str, db_path: Optional[str] = None):
    """Removes a Google Drive file ID from the permanent deletion queue once confirmed deleted."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM gdrive_delete_queue WHERE gdrive_file_id = ?", (gdrive_file_id,))
    conn.close()


def record_gdrive_delete_error(gdrive_file_id: str, error: str, db_path: Optional[str] = None):
    """Increments retry count and records the error when a permanent Drive delete fails."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE gdrive_delete_queue
            SET attempts = attempts + 1, last_error = ?
            WHERE gdrive_file_id = ?
        """, (error, gdrive_file_id))
    conn.close()


def reset_failed_backups(db_path: Optional[str] = None) -> int:
    """Resets all failed backup attempts back to pending so they can be retried."""
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            "UPDATE photos SET gdrive_backup_status = 'pending', gdrive_error = NULL WHERE gdrive_backup_status = 'failed'"
        )
        count = cursor.rowcount
        conn.execute("UPDATE gdrive_delete_queue SET attempts = 0 WHERE attempts >= 10")
    conn.close()
    return count


def get_backup_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Computes overall statistics for Google Drive backups."""
    conn = get_connection(db_path)
    total_row = conn.execute("SELECT COUNT(*) FROM photos WHERE is_trashed = 0").fetchone()
    total_photos = total_row[0] if total_row else 0

    backed_up_row = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE is_trashed = 0 AND gdrive_backup_status = 'backed_up'"
    ).fetchone()
    backed_up_count = backed_up_row[0] if backed_up_row else 0

    failed_row = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE is_trashed = 0 AND gdrive_backup_status = 'failed'"
    ).fetchone()
    failed_count = failed_row[0] if failed_row else 0

    pending_count = max(0, total_photos - backed_up_count - failed_count)

    trashed_pending_sync_row = conn.execute("""
        SELECT COUNT(*) FROM photos
        WHERE is_trashed = 1 AND gdrive_file_id IS NOT NULL AND gdrive_backup_status NOT IN ('trashed', 'deleted')
    """).fetchone()
    trashed_pending_sync = trashed_pending_sync_row[0] if trashed_pending_sync_row else 0

    trashed_backed_up_row = conn.execute("""
        SELECT COUNT(*) FROM photos
        WHERE is_trashed = 1 AND gdrive_file_id IS NOT NULL
    """).fetchone()
    trashed_backed_up_count = trashed_backed_up_row[0] if trashed_backed_up_row else 0

    pending_delete_row = conn.execute("SELECT COUNT(*) FROM gdrive_delete_queue WHERE attempts < 10").fetchone()
    pending_permanent_deletes = pending_delete_row[0] if pending_delete_row else 0

    conn.close()
    settings = get_backup_settings(db_path)

    return {
        "total_photos": total_photos,
        "backed_up_count": backed_up_count,
        "pending_count": pending_count,
        "failed_count": failed_count,
        "trashed_pending_sync": trashed_pending_sync,
        "trashed_backed_up_count": trashed_backed_up_count,
        "pending_permanent_deletes": pending_permanent_deletes,
        "hourly_limit": settings.get("hourly_limit", 25),
        "delay_seconds": settings.get("delay_seconds", 30.0),
        "root_folder_name": settings.get("root_folder_name", "LuminaPhoto Backup"),
        "is_paused": bool(settings.get("is_paused", 0)),
        "last_backup_at": settings.get("last_backup_at")
    }

