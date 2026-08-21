"""
SQLite database schema and data access layer for LuminaPhoto.
Stores photo records, complete EXIF metadata, duplicate groups, and vector embeddings.
"""

import sqlite3
import json
import os
from typing import List, Dict, Any, Optional, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "photos.db")

def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db(db_path: str = DB_PATH):
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
            
            indexed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_groups (
            id TEXT PRIMARY KEY,
            primary_photo_id INTEGER NOT NULL,
            match_type TEXT NOT NULL, -- 'EXACT_HASH' or 'PERCEPTUAL_PHASH' or 'EMBEDDING'
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

        CREATE INDEX IF NOT EXISTS idx_photos_classification ON photos(classification);
        CREATE INDEX IF NOT EXISTS idx_photos_sha256 ON photos(sha256);
        CREATE INDEX IF NOT EXISTS idx_photos_phash ON photos(phash);
        CREATE INDEX IF NOT EXISTS idx_photos_duplicate_group ON photos(duplicate_group_id);
        CREATE INDEX IF NOT EXISTS idx_photos_date_taken ON photos(date_taken);
        CREATE INDEX IF NOT EXISTS idx_photos_camera_make ON photos(camera_make);
        CREATE INDEX IF NOT EXISTS idx_photos_camera_model ON photos(camera_model);
        CREATE INDEX IF NOT EXISTS idx_photos_file_path ON photos(file_path);
        """)
    conn.close()

def upsert_photo(photo_data: Dict[str, Any], db_path: str = DB_PATH) -> int:
    """Inserts or updates a photo record."""
    conn = get_connection(db_path)
    fields = list(photo_data.keys())
    placeholders = [f":{f}" for f in fields]
    update_clause = ", ".join([f"{f} = excluded.{f}" for f in fields if f != "file_path"])
    
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

def get_photo_by_id(photo_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
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

def get_photos(
    classification: Optional[str] = None,
    include_duplicates: bool = True,
    camera_make: Optional[str] = None,
    has_gps: Optional[bool] = None,
    sort_by: str = "date_taken",
    sort_order: str = "DESC",
    limit: int = 100,
    offset: int = 0,
    photo_ids: Optional[List[int]] = None,
    db_path: str = DB_PATH
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated photos with filtering options."""
    conn = get_connection(db_path)
    conditions = []
    params = []

    if photo_ids is not None:
        clean_ids = [int(x) for x in photo_ids]
        if not clean_ids:
            conn.close()
            return [], 0
        placeholders = ",".join("?" for _ in clean_ids)
        conditions.append(f"id IN ({placeholders})")
        params.extend(clean_ids)
    else:
        if classification:
            conditions.append("classification = ?")
            params.append(classification)
        elif classification is None:
            # Default to showing real photos unless specified
            conditions.append("classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO')")

        if not include_duplicates:
            conditions.append("(duplicate_group_id IS NULL OR is_primary = 1)")

        if camera_make:
            conditions.append("camera_make LIKE ?")
            params.append(f"%{camera_make}%")

        if has_gps is True:
            conditions.append("latitude IS NOT NULL AND longitude IS NOT NULL")
        elif has_gps is False:
            conditions.append("(latitude IS NULL OR longitude IS NULL)")

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    
    # Count total
    count_sql = f"SELECT COUNT(*) FROM photos {where_clause}"
    cursor = conn.execute(count_sql, params)
    total_count = cursor.fetchone()[0]

    # Handle custom sorting
    allowed_sorts = {
        "date_taken": "COALESCE(date_taken, file_modified_at)",
        "file_name": "file_name",
        "file_size": "file_size",
        "indexed_at": "indexed_at"
    }
    order_col = allowed_sorts.get(sort_by, "COALESCE(date_taken, file_modified_at)")
    order_dir = "DESC" if sort_order.upper() == "DESC" else "ASC"

    # Query items
    query_sql = f"""
    SELECT id, file_path, file_name, file_size, file_extension, width, height, aspect_ratio,
           classification, classification_score, classification_reason, is_manual_override,
           sha256, phash, duplicate_group_id, is_primary, duplicate_count,
           date_taken, camera_make, camera_model, lens_model, focal_length, f_number, exposure_time, iso,
           latitude, longitude, altitude, has_embedding, indexed_at
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

def get_duplicate_groups(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all duplicate groups with primary and duplicate members."""
    conn = get_connection(db_path)
    cursor = conn.execute("""
    SELECT dg.id as group_id, dg.match_type, dg.total_items, dg.total_wasted_bytes,
           p.id, p.file_path, p.file_name, p.file_size, p.width, p.height, p.date_taken,
           p.camera_make, p.camera_model, p.is_primary, p.sha256, p.phash
    FROM duplicate_groups dg
    JOIN photos p ON p.duplicate_group_id = dg.id
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

    return list(groups_map.values())

def get_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Retrieves overall library statistics."""
    conn = get_connection(db_path)
    
    total_photos = conn.execute("SELECT COUNT(*) FROM photos WHERE classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO')").fetchone()[0]
    total_screenshots = conn.execute("SELECT COUNT(*) FROM photos WHERE classification IN ('SCREENSHOT', 'SYSTEM_ASSET')").fetchone()[0]
    total_duplicates = conn.execute("SELECT COUNT(*) FROM photos WHERE is_primary = 0").fetchone()[0]
    total_bytes = conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM photos").fetchone()[0]
    total_wasted = conn.execute("SELECT COALESCE(SUM(total_wasted_bytes), 0) FROM duplicate_groups").fetchone()[0]
    
    # Camera breakdown
    cameras = conn.execute("""
    SELECT camera_make, camera_model, COUNT(*) as count 
    FROM photos 
    WHERE camera_make IS NOT NULL AND camera_make != ''
    GROUP BY camera_make, camera_model 
    ORDER BY count DESC LIMIT 10
    """).fetchall()

    # Timeline years breakdown
    years = conn.execute("""
    SELECT SUBSTR(date_taken, 1, 4) as year, COUNT(*) as count
    FROM photos
    WHERE date_taken IS NOT NULL AND LENGTH(date_taken) >= 4 AND (year LIKE '20%' OR year LIKE '19%')
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
        "top_cameras": [dict(c) for c in cameras],
        "timeline_years": [dict(y) for y in years]
    }
