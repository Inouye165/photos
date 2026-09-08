"""
Exact and Perceptual Duplicate Detection & Clustering Engine for LuminaPhoto.
Detects identical files (SHA-256) and near-identical / burst / resized photos (pHash hamming distance).
Determines the optimal primary keeper based on resolution, metadata richness, and quality.
"""

import uuid
import sqlite3
from datetime import datetime
from collections import defaultdict, deque
from typing import List, Dict, Any, Tuple, Optional, Set
import imagehash
from backend.database import get_connection, DB_PATH, get_dismissed_pairs_set

def parse_photo_timestamp(date_str: Optional[str], mtime: Optional[float] = None) -> Optional[float]:
    """Extracts unix epoch timestamp (seconds) from photo date_taken string or fallback file_modified_at."""
    if date_str:
        cleaned = str(date_str).strip().replace("\x00", "")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y:%m:%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y:%m:%d",
            "%Y-%m-%d"
        ):
            try:
                return datetime.strptime(cleaned[:19], fmt).timestamp()
            except Exception:
                pass
        try:
            return datetime.fromisoformat(cleaned).timestamp()
        except Exception:
            pass
    if mtime is not None:
        try:
            return float(mtime)
        except Exception:
            pass
    return None

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

def run_deduplication_pass(db_path: Optional[str] = None, force_recluster: bool = False) -> int:
    """
    Performs fast, scalable duplicate clustering across indexed photos:
    1. Reconciles existing duplicate groups (preserves user curation & keeper choices).
    2. Exact match clustering via SHA-256.
    3. High-speed multi-index bucketing pHash clustering (Pigeonhole 8-band indexing).
    4. Respects user-dismissed duplicate pairs so dismissed false-positives are never re-grouped.
    Returns the total number of active duplicate groups.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Step 0: Load user-dismissed pairs (min_id, max_id)
    dismissed_pairs = get_dismissed_pairs_set(db_path)

    # Clean up any dead/stale groups that have <= 1 active non-trashed photos
    cursor.execute("SELECT id FROM duplicate_groups")
    existing_group_ids = [r["id"] for r in cursor.fetchall()]
    for gid in existing_group_ids:
        cursor.execute("""
            SELECT id FROM photos WHERE duplicate_group_id = ? AND is_trashed = 0
        """, (gid,))
        active_members = cursor.fetchall()
        if len(active_members) <= 1:
            cleanup_duplicate_group(gid, db_path)

    # If force_recluster is requested, uncluster items not part of protected groups
    if force_recluster:
        cursor.execute("""
            UPDATE photos 
            SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0
            WHERE is_trashed = 0
        """)
        cursor.execute("DELETE FROM duplicate_groups")
        conn.commit()

    # Step 1: Find Exact Hash duplicates (SHA-256) for unclustered photos
    cursor.execute("""
        SELECT sha256, COUNT(*) as count 
        FROM photos 
        WHERE sha256 IS NOT NULL 
          AND duplicate_group_id IS NULL
          AND classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') 
          AND is_trashed = 0
        GROUP BY sha256 
        HAVING count > 1
    """)
    exact_hash_groups = cursor.fetchall()

    for row in exact_hash_groups:
        sha = row["sha256"]
        cursor.execute("""
            SELECT id, file_path, file_size, width, height, classification, date_taken, camera_make
            FROM photos 
            WHERE sha256 = ? AND duplicate_group_id IS NULL AND is_trashed = 0
        """, (sha,))
        members = [dict(r) for r in cursor.fetchall()]
        if len(members) <= 1:
            continue

        # Filter out pairs that were dismissed by user
        allowed_members = []
        for m in members:
            # Check if this member is dismissed with all others
            is_dismissed_with_all = False
            for other in allowed_members:
                pair = (min(m["id"], other["id"]), max(m["id"], other["id"]))
                if pair in dismissed_pairs:
                    is_dismissed_with_all = True
                    break
            if not is_dismissed_with_all:
                allowed_members.append(m)

        if len(allowed_members) <= 1:
            continue

        group_id = f"exact_{uuid.uuid4().hex[:12]}"
        primary = select_best_primary(allowed_members)
        primary_id = primary["id"]
        wasted_bytes = sum(m["file_size"] for m in allowed_members if m["id"] != primary_id)
        
        cursor.execute("""
            INSERT INTO duplicate_groups (id, primary_photo_id, match_type, total_items, total_wasted_bytes, created_at)
            VALUES (?, ?, 'EXACT_HASH', ?, ?, strftime('%s', 'now'))
        """, (group_id, primary_id, len(allowed_members), wasted_bytes))

        for m in allowed_members:
            is_p = 1 if m["id"] == primary_id else 0
            cursor.execute("""
                UPDATE photos 
                SET duplicate_group_id = ?, is_primary = ?, duplicate_count = ?
                WHERE id = ?
            """, (group_id, is_p, len(allowed_members) - 1, m["id"]))

    conn.commit()

    # Step 2: High-Speed Multi-Index Bucketing for pHash near-duplicates
    cursor.execute("""
        SELECT id, file_path, file_size, width, height, classification, date_taken, file_modified_at, camera_make, phash
        FROM photos 
        WHERE phash IS NOT NULL 
          AND duplicate_group_id IS NULL 
          AND classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') 
          AND is_trashed = 0
    """)
    raw_phash_candidates = [dict(r) for r in cursor.fetchall()]

    # Parse hex to 64-bit integer
    phash_candidates = []
    for r in raw_phash_candidates:
        try:
            phash_candidates.append((r, int(r["phash"], 16)))
        except Exception:
            pass

    if len(phash_candidates) > 1:
        # 8-band bucket indexing: 64 bits divided into 8 1-byte chunks (0..255).
        # Any pair with Hamming distance <= 6 MUST have at least 8 - 6 = 2 identical chunks.
        # Indexing by (chunk_idx, byte_value) lets us compare only bucket-sharing candidates in O(N).
        buckets = defaultdict(list)
        for idx, (photo, hash_int) in enumerate(phash_candidates):
            for chunk_idx in range(8):
                byte_val = (hash_int >> (chunk_idx * 8)) & 0xFF
                buckets[(chunk_idx, byte_val)].append(idx)

        # Generate candidate pairs from buckets
        candidate_pairs = set()
        for idx_list in buckets.values():
            if len(idx_list) > 1:
                for i in range(len(idx_list)):
                    idx1 = idx_list[i]
                    for j in range(i + 1, len(idx_list)):
                        idx2 = idx_list[j]
                        pair = (idx1, idx2) if idx1 < idx2 else (idx2, idx1)
                        candidate_pairs.add(pair)

        # Verify candidate pairs against Hamming distance <= 6 and dismissed_pairs
        adjacency = defaultdict(set)
        for idx1, idx2 in candidate_pairs:
            p1, int1 = phash_candidates[idx1]
            p2, int2 = phash_candidates[idx2]
            pair_ids = (min(p1["id"], p2["id"]), max(p1["id"], p2["id"]))
            if pair_ids in dismissed_pairs:
                continue

            dist = (int1 ^ int2).bit_count()
            if dist <= 6:
                adjacency[idx1].add(idx2)
                adjacency[idx2].add(idx1)

        # Graph connected components for candidate clustering
        visited = set()
        for start_idx in adjacency:
            if start_idx in visited:
                continue

            cluster_indices = []
            queue = deque([start_idx])
            visited.add(start_idx)

            while queue:
                curr = queue.popleft()
                cluster_indices.append(curr)
                for neighbor in adjacency[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            if len(cluster_indices) > 1:
                cluster_photos = [phash_candidates[ci][0] for ci in cluster_indices]
                cluster_hashes = [phash_candidates[ci][1] for ci in cluster_indices]

                # Determine initial anchor / best primary
                initial_primary = select_best_primary(cluster_photos)
                initial_primary_id = initial_primary["id"]
                initial_primary_hash = next(
                    h for p, h in zip(cluster_photos, cluster_hashes) if p["id"] == initial_primary_id
                )

                # Extract unix timestamps for temporal window evaluation
                timestamps = [
                    parse_photo_timestamp(p.get("date_taken"), p.get("file_modified_at"))
                    for p in cluster_photos
                ]
                valid_ts = [ts for ts in timestamps if ts is not None]

                is_burst = False
                final_cluster = cluster_photos

                # Continuous Burst (Google-style Photo Stack) criteria:
                # 1. At least 2 photos with timestamps.
                # 2. Taken within <= 60 seconds of each other (or continuous burst interval <= 12s, max span <= 120s).
                # 3. Anti-drift rule: every photo in the burst stack must have tight perceptual similarity
                #    to the anchor photo (Hamming distance <= 5, ~92%+ match).
                #    Photos that drifted away (camera panned away, different direction/angle, or sports play
                #    progressing downfield) are excluded from the burst.
                if len(valid_ts) >= 2:
                    sorted_ts = sorted(valid_ts)
                    time_span = sorted_ts[-1] - sorted_ts[0]
                    max_consecutive_gap = max(
                        (sorted_ts[i + 1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)),
                        default=0
                    )
                    is_within_time_window = (time_span <= 60.0) or (time_span <= 120.0 and max_consecutive_gap <= 12.0)

                    if is_within_time_window:
                        tight_burst_photos = []
                        for p, h in zip(cluster_photos, cluster_hashes):
                            dist_to_anchor = fast_hamming(h, initial_primary_hash)
                            if dist_to_anchor <= 5:
                                tight_burst_photos.append(p)

                        if len(tight_burst_photos) > 1:
                            is_burst = True
                            final_cluster = tight_burst_photos

                # Enforce dismissed pairs across all members of candidate cluster
                allowed_cluster = []
                for m in final_cluster:
                    is_dismissed = False
                    for other in allowed_cluster:
                        pair = (min(m["id"], other["id"]), max(m["id"], other["id"]))
                        if pair in dismissed_pairs:
                            is_dismissed = True
                            break
                    if not is_dismissed:
                        allowed_cluster.append(m)
                final_cluster = allowed_cluster

                if len(final_cluster) > 1:
                    primary = select_best_primary(final_cluster)
                    primary_id = primary["id"]
                    wasted_bytes = sum(m["file_size"] for m in final_cluster if m["id"] != primary_id)

                    if is_burst:
                        match_type = 'BURST_SEQUENCE'
                        group_id = f"burst_{uuid.uuid4().hex[:12]}"
                    else:
                        match_type = 'PERCEPTUAL_PHASH'
                        group_id = f"phash_{uuid.uuid4().hex[:12]}"

                    cursor.execute("""
                        INSERT INTO duplicate_groups (id, primary_photo_id, match_type, total_items, total_wasted_bytes, created_at)
                        VALUES (?, ?, ?, ?, ?, strftime('%s', 'now'))
                    """, (group_id, primary_id, match_type, len(final_cluster), wasted_bytes))

                    for m in final_cluster:
                        is_p = 1 if m["id"] == primary_id else 0
                        cursor.execute("""
                            UPDATE photos 
                            SET duplicate_group_id = ?, is_primary = ?, duplicate_count = ?
                            WHERE id = ?
                        """, (group_id, is_p, len(final_cluster) - 1, m["id"]))

    conn.commit()

    # Return total active duplicate groups
    cursor.execute("SELECT COUNT(*) FROM duplicate_groups")
    total_groups = cursor.fetchone()[0]
    conn.close()
    return total_groups


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
