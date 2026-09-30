"""
Automated Database Backup & Snapshot Manager for LuminaPhoto.
Uses SQLite Online Backup API for lock-free, crash-safe live snapshots.
Maintains rolling backup history and automatic daily rotation.
"""

import os
import time
import sqlite3
import glob
from datetime import datetime
from typing import Dict, Any, List, Optional

from backend.database import DB_PATH, get_connection

BACKUPS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".lumina_cache",
    "db_backups"
)

def ensure_backup_dir() -> str:
    """Ensures the backup directory exists and returns its absolute path."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    return BACKUPS_DIR

def create_database_backup(
    db_path: Optional[str] = None,
    max_backups: int = 7
) -> Dict[str, Any]:
    """
    Creates a consistent live snapshot of the SQLite database using the official online backup API.
    Does not block active reads or writes.
    """
    if db_path is None:
        db_path = DB_PATH

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    backup_dir = ensure_backup_dir()
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"photos_backup_{timestamp_str}.db"
    backup_filepath = os.path.join(backup_dir, backup_filename)

    # Perform SQLite online backup
    source_conn = get_connection(db_path)
    target_conn = sqlite3.connect(backup_filepath)

    try:
        source_conn.backup(target_conn, pages=100, sleep=0.01)
    finally:
        target_conn.close()
        source_conn.close()

    # Get file stats
    file_size = os.path.getsize(backup_filepath)
    size_mb = round(file_size / (1024 * 1024), 2)

    # Prune old backups beyond max_backups
    prune_old_backups(max_backups=max_backups)

    return {
        "status": "SUCCESS",
        "filename": backup_filename,
        "path": backup_filepath,
        "size_bytes": file_size,
        "size_mb": size_mb,
        "created_at": time.time(),
        "created_at_iso": datetime.now().isoformat()
    }

def prune_old_backups(max_backups: int = 7):
    """Retains the most recent max_backups snapshots and deletes older ones."""
    backup_dir = ensure_backup_dir()
    pattern = os.path.join(backup_dir, "photos_backup_*.db")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    if len(backups) > max_backups:
        for old_file in backups[max_backups:]:
            try:
                os.remove(old_file)
                print(f"[INFO] Pruned old database backup: {os.path.basename(old_file)}")
            except Exception as e:
                print(f"[WARN] Error removing old backup {old_file}: {e}")

def list_database_backups() -> List[Dict[str, Any]]:
    """Returns a list of available database backups sorted newest first."""
    backup_dir = ensure_backup_dir()
    pattern = os.path.join(backup_dir, "photos_backup_*.db")
    backup_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    result = []
    for filepath in backup_files:
        try:
            stat = os.stat(filepath)
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            created_dt = datetime.fromtimestamp(stat.st_mtime)
            result.append({
                "filename": os.path.basename(filepath),
                "path": filepath,
                "size_bytes": stat.st_size,
                "size_mb": size_mb,
                "created_at": stat.st_mtime,
                "created_at_formatted": created_dt.strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception:
            pass
    return result

def get_backup_status() -> Dict[str, Any]:
    """Returns database backup status summary."""
    backups = list_database_backups()
    total_bytes = sum(b["size_bytes"] for b in backups)
    last_backup = backups[0] if backups else None

    # Current main DB size
    main_db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0

    return {
        "total_backups": len(backups),
        "total_backup_size_mb": round(total_bytes / (1024 * 1024), 2),
        "last_backup": last_backup,
        "main_db_size_mb": round(main_db_size / (1024 * 1024), 2),
        "backups": backups
    }

def ensure_daily_backup():
    """Checks if a backup was taken in the last 24 hours, and creates one if not."""
    try:
        backups = list_database_backups()
        one_day_ago = time.time() - 86400

        if not backups or backups[0]["created_at"] < one_day_ago:
            print("[INFO] Starting scheduled daily database backup...")
            res = create_database_backup()
            print(f"[INFO] Daily database backup completed: {res['filename']} ({res['size_mb']} MB)")
    except Exception as e:
        print(f"[WARN] Failed to create automated daily database backup: {e}")

if __name__ == "__main__":
    print("Creating test database backup...")
    res = create_database_backup()
    print("Result:", res)
    print("\nExisting backups:", list_database_backups())
