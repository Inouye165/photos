"""
Recursive Folder Scanner & Indexer for LuminaPhoto.
Crawls subfolders, extracts EXIF, classifies media, generates thumbnails, clusters duplicates,
and computes CLIP vector embeddings with real-time status reporting.
"""

import os
import time
import threading
from typing import Dict, Any, Optional, Callable
from backend.database import init_db, upsert_photo, get_connection, DB_PATH
from backend.metadata_extractor import (
    extract_metadata,
    SUPPORTED_PHOTO_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS
)
from backend.classifier import classify_media
from backend.deduplicator import run_deduplication_pass
from backend.thumbnails import generate_thumbnail
from backend.vector_engine import VectorEngine

IGNORED_NAMES = {
    ".ds_store", "thumbs.db", "desktop.ini", ".git", ".lumina_cache",
    "node_modules", ".vscode", ".idea", "$recycle.bin"
}

class ScanManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.is_scanning = False
        self.should_stop = False
        self.current_root = ""
        self.stats: Dict[str, Any] = {
            "status": "IDLE",  # 'IDLE', 'SCANNING', 'DEDUPLICATING', 'EMBEDDING', 'COMPLETED', 'STOPPED', 'ERROR'
            "current_file": "",
            "total_found": 0,
            "processed_count": 0,
            "photos_count": 0,
            "screenshots_count": 0,
            "system_assets_count": 0,
            "duplicates_count": 0,
            "embeddings_count": 0,
            "error_message": None,
            "start_time": None,
            "elapsed_seconds": 0
        }
        self.worker_thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(cls) -> "ScanManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ScanManager()
            return cls._instance

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            status = dict(self.stats)
            if self.is_scanning and self.stats.get("start_time"):
                status["elapsed_seconds"] = round(time.time() - self.stats["start_time"], 1)
            return status

    def start_scan(self, root_path: str) -> bool:
        with self._lock:
            if self.is_scanning:
                return False

            if not os.path.exists(root_path) or not os.path.isdir(root_path):
                self.stats["error_message"] = f"Directory not found: {root_path}"
                self.stats["status"] = "ERROR"
                return False

            self.is_scanning = True
            self.should_stop = False
            self.current_root = os.path.abspath(root_path)
            self.stats = {
                "status": "SCANNING",
                "current_file": "Initializing scan...",
                "total_found": 0,
                "processed_count": 0,
                "photos_count": 0,
                "screenshots_count": 0,
                "system_assets_count": 0,
                "duplicates_count": 0,
                "embeddings_count": 0,
                "error_message": None,
                "start_time": time.time(),
                "elapsed_seconds": 0
            }

            self.worker_thread = threading.Thread(
                target=self._scan_worker,
                args=(self.current_root,),
                daemon=True
            )
            self.worker_thread.start()
            return True

    def stop_scan(self):
        with self._lock:
            if self.is_scanning:
                self.should_stop = True
                self.stats["status"] = "STOPPING"

    def _scan_worker(self, root_path: str):
        init_db()
        all_candidate_files = []

        # 1. Discover all candidate files recursively
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Exclude hidden or ignored directories
            dirnames[:] = [d for d in dirnames if d.lower() not in IGNORED_NAMES and not d.startswith(".")]
            
            for fname in filenames:
                if fname.lower() in IGNORED_NAMES or fname.startswith("._"):
                    continue
                _, ext = os.path.splitext(fname)
                ext_lower = ext.lower()
                if ext_lower in SUPPORTED_PHOTO_EXTENSIONS or ext_lower in SUPPORTED_VIDEO_EXTENSIONS:
                    all_candidate_files.append(os.path.join(dirpath, fname))

        with self._lock:
            self.stats["total_found"] = len(all_candidate_files)

        newly_indexed_photos = []

        # 2. Extract metadata, classify, and generate thumbnails
        for fpath in all_candidate_files:
            if self.should_stop:
                with self._lock:
                    self.stats["status"] = "STOPPED"
                    self.is_scanning = False
                return

            with self._lock:
                self.stats["current_file"] = os.path.basename(fpath)

            try:
                meta = extract_metadata(fpath)
                classification, score, reason = classify_media(meta)
                
                meta["classification"] = classification
                meta["classification_score"] = score
                meta["classification_reason"] = reason
                meta["indexed_at"] = time.time()

                photo_id = upsert_photo(meta)

                # Generate thumbnail cache in background
                if classification in ("VERIFIED_PHOTO", "LIKELY_PHOTO", "SCREENSHOT", "SYSTEM_ASSET"):
                    generate_thumbnail(fpath, photo_id, "thumb")
                    generate_thumbnail(fpath, photo_id, "preview")

                if classification in ("VERIFIED_PHOTO", "LIKELY_PHOTO"):
                    newly_indexed_photos.append((photo_id, fpath))
                    with self._lock:
                        self.stats["photos_count"] += 1
                elif classification == "SCREENSHOT":
                    with self._lock:
                        self.stats["screenshots_count"] += 1
                elif classification == "SYSTEM_ASSET":
                    with self._lock:
                        self.stats["system_assets_count"] += 1

            except Exception as e:
                pass

            with self._lock:
                self.stats["processed_count"] += 1

        # 3. Deduplication pass
        with self._lock:
            self.stats["status"] = "DEDUPLICATING"
            self.stats["current_file"] = "Detecting exact and perceptual duplicates..."

        try:
            dup_groups = run_deduplication_pass()
            with self._lock:
                self.stats["duplicates_count"] = dup_groups
        except Exception:
            pass

        # 4. Multimodal Vector Embeddings pass
        with self._lock:
            self.stats["status"] = "EMBEDDING"
            self.stats["current_file"] = "Generating CLIP multimodal embeddings for semantic search..."

        try:
            vector_engine = VectorEngine.get_instance()
            
            # Fetch photos needing embedding
            conn = get_connection()
            cursor = conn.execute("""
            SELECT id, file_path 
            FROM photos 
            WHERE classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') AND has_embedding = 0
            """)
            need_embeddings = [(r["id"], r["file_path"]) for r in cursor.fetchall()]
            conn.close()

            def update_emb_progress(indexed, total):
                with self._lock:
                    self.stats["embeddings_count"] = indexed
                    self.stats["current_file"] = f"Embedding photo {indexed} of {total}..."

            if need_embeddings:
                vector_engine.batch_index_photos(need_embeddings, batch_size=16, progress_callback=update_emb_progress)
        except Exception as e:
            pass

        with self._lock:
            self.stats["status"] = "COMPLETED"
            self.stats["current_file"] = f"Scan complete. Indexed {self.stats['photos_count']} photos."
            self.is_scanning = False
