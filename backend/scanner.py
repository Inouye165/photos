"""
Recursive Folder Scanner & Indexer for LuminaPhoto.
Crawls subfolders, extracts EXIF, classifies media, generates thumbnails, clusters duplicates,
and computes CLIP vector embeddings with real-time status reporting.
"""

import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            try:
                from backend.folder_watcher import FolderWatcherManager
                FolderWatcherManager.get_instance().add_watch_path(self.current_root)
            except Exception:
                pass
            return True

    def start_embedding_backfill(self) -> bool:
        """Runs a lightweight background pass to generate missing CLIP embeddings from cached thumbnails."""
        with self._lock:
            if self.is_scanning:
                return False
            conn = get_connection()
            try:
                rows = conn.execute(
                    "SELECT id, file_path FROM photos "
                    "WHERE classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO') AND is_trashed = 0 AND has_embedding = 0"
                ).fetchall()
                need_embeddings = [(r["id"], r["file_path"]) for r in rows]
            finally:
                conn.close()

            if not need_embeddings:
                return False

            self.is_scanning = True
            self.should_stop = False
            self.stats = {
                "status": "EMBEDDING",
                "current_file": f"Indexing {len(need_embeddings)} photos for semantic search...",
                "total_found": len(need_embeddings),
                "processed_count": 0,
                "photos_count": len(need_embeddings),
                "screenshots_count": 0,
                "system_assets_count": 0,
                "duplicates_count": 0,
                "embeddings_count": 0,
                "error_message": None,
                "start_time": time.time(),
                "elapsed_seconds": 0
            }

            def _backfill_worker(items):
                try:
                    vector_engine = VectorEngine.get_instance()
                    def update_emb_progress(indexed, total):
                        with self._lock:
                            self.stats["embeddings_count"] = indexed
                            self.stats["processed_count"] = indexed
                            self.stats["current_file"] = f"Embedding photo {indexed} of {total}..."
                    vector_engine.batch_index_photos(items, batch_size=32, progress_callback=update_emb_progress)
                except Exception:
                    pass
                finally:
                    with self._lock:
                        self.stats["status"] = "COMPLETED"
                        self.stats["current_file"] = f"Semantic search index updated ({self.stats['embeddings_count']} photos)."
                        self.is_scanning = False

            self.worker_thread = threading.Thread(target=_backfill_worker, args=(need_embeddings,), daemon=True)
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

        # Preload existing indexed records to skip redundant full-file hashing on unchanged files
        existing_records = {}
        try:
            conn = get_connection()
            rows = conn.execute(
                "SELECT id, file_path, file_size, file_modified_at, classification, sha256, phash FROM photos"
            ).fetchall()
            conn.close()
            for r in rows:
                existing_records[os.path.abspath(r["file_path"])] = (
                    r["id"],
                    r["file_size"],
                    r["file_modified_at"],
                    r["classification"],
                    r["sha256"],
                    r["phash"]
                )
        except Exception:
            pass

        newly_indexed_photos = []

        # 2. Extract metadata, classify, and generate thumbnails in parallel
        def process_candidate(fpath: str):
            if self.should_stop:
                return None
            try:
                abs_fpath = os.path.abspath(fpath)
                existing = existing_records.get(abs_fpath)
                if existing is not None:
                    ex_id, ex_size, ex_mtime, ex_class, ex_sha, ex_phash = existing
                    try:
                        st = os.stat(abs_fpath)
                        if (
                            ex_sha
                            and ex_phash
                            and ex_class
                            and st.st_size == ex_size
                            and ex_mtime is not None
                            and abs(st.st_mtime - float(ex_mtime)) < 1.0
                        ):
                            if ex_class in ("VERIFIED_PHOTO", "LIKELY_PHOTO", "SCREENSHOT", "SYSTEM_ASSET"):
                                generate_thumbnail(abs_fpath, ex_id, "thumb")
                                generate_thumbnail(abs_fpath, ex_id, "preview")
                            return (ex_id, abs_fpath, ex_class)
                    except Exception:
                        pass

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

                return (photo_id, fpath, classification)
            except Exception:
                return None

        workers_count = max(2, min(8, (os.cpu_count() or 4)))
        with ThreadPoolExecutor(max_workers=workers_count) as executor:
            future_to_file = {executor.submit(process_candidate, f): f for f in all_candidate_files}
            for future in as_completed(future_to_file):
                if self.should_stop:
                    executor.shutdown(wait=False, cancel_futures=True)
                    with self._lock:
                        self.stats["status"] = "STOPPED"
                        self.is_scanning = False
                    return

                fpath = future_to_file[future]
                fname = os.path.basename(fpath)

                try:
                    result = future.result()
                    if result:
                        pid, ppath, pclass = result
                        if pclass in ("VERIFIED_PHOTO", "LIKELY_PHOTO"):
                            newly_indexed_photos.append((pid, ppath))
                            with self._lock:
                                self.stats["photos_count"] += 1
                        elif pclass == "SCREENSHOT":
                            with self._lock:
                                self.stats["screenshots_count"] += 1
                        elif pclass == "SYSTEM_ASSET":
                            with self._lock:
                                self.stats["system_assets_count"] += 1
                except Exception:
                    pass

                with self._lock:
                    self.stats["current_file"] = fname
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

        if newly_indexed_photos:
            try:
                from backend.backup_worker import BackupWorker
                BackupWorker.get_instance().trigger_wake()
            except Exception:
                pass
