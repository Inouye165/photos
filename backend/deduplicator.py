"""
Exact and Perceptual Duplicate Detection & Clustering Engine for LuminaPhoto.
Detects identical files (SHA-256) and near-identical / burst / resized photos (pHash hamming distance).
Determines the optimal primary keeper based on resolution, metadata richness, and quality.
"""

import uuid
import sqlite3
from typing import List, Dict, Any, Tuple, Optional
import imagehash
from backend.database import get_connection, DB_PATH

def fast_hamming(int1: int, int2: int) -> int:
    """Computes bitwise Hamming distance between two pre-converted integer hashes in nanoseconds."""
    return (int1 ^ int2).bit_count()

def hamming_distance(hex_hash1: str, hex_hash2: str) -> int:
    """Computes Hamming distance between two hex perceptual hashes."""
    if not hex_hash1 or not hex_hash2 or len(hex_hash1) != len(hex_hash2):
        return 999
    try:
        return (int(hex_hash1, 16) ^ int(hex_hash2, 16)).bit_count()
    except Exception:
        try:
            h1 = imagehash.hex_to_hash(hex_hash1)
            h2 = imagehash.hex_to_hash(hex_hash2)
            return int(h1 - h2)
        except Exception:
            return 999

def select_best_primary(photos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Selects the best photo to be the primary keeper in a duplicate cluster:
    1. Verified photo with camera EXIF over likely photo
    2. Higher pixel area (width * height)
    3. Larger file size (less compression / higher bit depth)
    4. Earliest date taken
    """
    def score_photo(p: Dict[str, Any]) -> Tuple[int, int, int, int]:
        exif_score = 2 if p.get("classification") == "VERIFIED_PHOTO" else 1
        res_score = (p.get("width") or 0) * (p.get("height") or 0)
        size_score = p.get("file_size") or 0
        date_str = p.get("date_taken") or "9999"
        return (exif_score, res_score, size_score, -len(date_str))

    return max(photos, key=score_photo)

def run_deduplication_pass(db_path: Optional[str] = None) -> int:
    """
    Performs full deduplication clustering across indexed photos:
    1. Exact match clustering via SHA-256.
    2. Perceptual match clustering via pHash (hamming distance <= 6).
    Updates `photos` table and `duplicate_groups` table.
    Returns the number of duplicate groups created or updated.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Reset existing duplicate state for fresh clustering
    cursor.execute("""
    UPDATE photos 
    SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0
    """)
    cursor.execute("DELETE FROM duplicate_groups")
    conn.commit()

    # Step 1: Find Exact Hash duplicates (SHA-256)
    cursor.execute("""
    SELECT sha256, COUNT(*) as count 
    FROM photos 
    WHERE sha256 IS NOT NULL AND classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') AND is_trashed = 0
    GROUP BY sha256 
    HAVING count > 1
    """)
    exact_hash_groups = cursor.fetchall()

    created_groups_count = 0

    for row in exact_hash_groups:
        sha = row["sha256"]
        cursor.execute("""
        SELECT id, file_path, file_size, width, height, classification, date_taken, camera_make
        FROM photos 
        WHERE sha256 = ? AND is_trashed = 0
        """, (sha,))
        members = [dict(r) for r in cursor.fetchall()]
        if len(members) <= 1:
            continue

        group_id = f"exact_{uuid.uuid4().hex[:12]}"
        primary = select_best_primary(members)
        primary_id = primary["id"]

        wasted_bytes = sum(m["file_size"] for m in members if m["id"] != primary_id)
        
        cursor.execute("""
        INSERT INTO duplicate_groups (id, primary_photo_id, match_type, total_items, total_wasted_bytes, created_at)
        VALUES (?, ?, 'EXACT_HASH', ?, ?, strftime('%s', 'now'))
        """, (group_id, primary_id, len(members), wasted_bytes))

        # Update member photos
        for m in members:
            is_p = 1 if m["id"] == primary_id else 0
            cursor.execute("""
            UPDATE photos 
            SET duplicate_group_id = ?, is_primary = ?, duplicate_count = ?
            WHERE id = ?
            """, (group_id, is_p, len(members) - 1, m["id"]))

        created_groups_count += 1

    conn.commit()

    # Step 2: Find Perceptual pHash near-duplicates (for items not already in an exact duplicate group)
    cursor.execute("""
    SELECT id, file_path, file_size, width, height, classification, date_taken, camera_make, phash
    FROM photos 
    WHERE phash IS NOT NULL AND duplicate_group_id IS NULL AND classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') AND is_trashed = 0
    """)
    raw_phash_candidates = [dict(r) for r in cursor.fetchall()]

    # Pre-parse hex hashes to integers for ultra-fast bitwise comparisons
    phash_candidates = []
    for r in raw_phash_candidates:
        try:
            phash_candidates.append((r, int(r["phash"], 16)))
        except Exception:
            pass

    visited_ids = set()
    for i in range(len(phash_candidates)):
        p1, int1 = phash_candidates[i]
        if p1["id"] in visited_ids:
            continue

        cluster = [p1]
        for j in range(i + 1, len(phash_candidates)):
            p2, int2 = phash_candidates[j]
            if p2["id"] in visited_ids:
                continue

            dist = (int1 ^ int2).bit_count()
            if dist <= 6:  # Strict visual resemblance threshold
                cluster.append(p2)
                visited_ids.add(p2["id"])

        if len(cluster) > 1:
            visited_ids.add(p1["id"])
            group_id = f"phash_{uuid.uuid4().hex[:12]}"
            primary = select_best_primary(cluster)
            primary_id = primary["id"]
            wasted_bytes = sum(m["file_size"] for m in cluster if m["id"] != primary_id)

            cursor.execute("""
            INSERT INTO duplicate_groups (id, primary_photo_id, match_type, total_items, total_wasted_bytes, created_at)
            VALUES (?, ?, 'PERCEPTUAL_PHASH', ?, ?, strftime('%s', 'now'))
            """, (group_id, primary_id, len(cluster), wasted_bytes))

            for m in cluster:
                is_p = 1 if m["id"] == primary_id else 0
                cursor.execute("""
                UPDATE photos 
                SET duplicate_group_id = ?, is_primary = ?, duplicate_count = ?
                WHERE id = ?
                """, (group_id, is_p, len(cluster) - 1, m["id"]))

            created_groups_count += 1

    conn.commit()
    conn.close()
    return created_groups_count

def cleanup_duplicate_group(group_id: Optional[str], db_path: Optional[str] = None) -> None:
    """
    Incrementally reconciles a single duplicate group after photo deletion or trashing.
    Runs in O(1) time without triggering an expensive full-library rescan.
    """
    if not group_id:
        return
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, file_path, file_size, width, height, classification, date_taken, camera_make, is_primary
        FROM photos
        WHERE duplicate_group_id = ? AND is_trashed = 0
    """, (group_id,))
    remaining = [dict(r) for r in cursor.fetchall()]

    if len(remaining) <= 1:
        # 0 or 1 item left - no longer a duplicate group
        cursor.execute("DELETE FROM duplicate_groups WHERE id = ?", (group_id,))
        if len(remaining) == 1:
            cursor.execute("""
                UPDATE photos 
                SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0
                WHERE id = ?
            """, (remaining[0]["id"],))
    else:
        # Check if primary is still in remaining, else pick best primary
        has_primary = any(m["is_primary"] for m in remaining)
        primary = select_best_primary(remaining) if not has_primary else next(m for m in remaining if m["is_primary"])
        primary_id = primary["id"]
        wasted_bytes = sum(m["file_size"] for m in remaining if m["id"] != primary_id)
        
        cursor.execute("""
            UPDATE duplicate_groups
            SET primary_photo_id = ?, total_items = ?, total_wasted_bytes = ?
            WHERE id = ?
        """, (primary_id, len(remaining), wasted_bytes, group_id))

        for m in remaining:
            is_p = 1 if m["id"] == primary_id else 0
            cursor.execute("""
                UPDATE photos
                SET is_primary = ?, duplicate_count = ?
                WHERE id = ?
            """, (is_p, len(remaining) - 1, m["id"]))

    conn.commit()
    conn.close()
