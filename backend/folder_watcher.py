"""
Real-Time Folder Watcher for LuminaPhoto.
Uses watchdog to monitor library and upload directories, automatically indexing
newly added, modified, and deleted photos in the background with debounced batching.
"""

import os
import time
import queue
import threading
from typing import Set, Dict, Any, List, Optional, Union
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from backend.metadata_extractor import (
    extract_metadata,
    SUPPORTED_PHOTO_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS
)
from backend.classifier import classify_media
from backend.database import upsert_photo, get_connection, tag_photo_trash
from backend.thumbnails import generate_thumbnail

ALL_SUPPORTED = SUPPORTED_PHOTO_EXTENSIONS.union(SUPPORTED_VIDEO_EXTENSIONS)
IGNORED_DIR_NAMES = {
    ".lumina_cache", ".git", "__pycache__", "node_modules", ".vscode",
    "$recycle.bin", ".thumbnails", "temp", "tmp"
}

def is_valid_media_file(path: str) -> bool:
    """Checks if a file has a supported extension and is not in an ignored directory."""
    if not path or not os.path.isfile(path):
        return False
    parts = path.replace("\\", "/").lower().split("/")
    if any(ign in parts for ign in IGNORED_DIR_NAMES):
        return False
    fname = os.path.basename(path).lower()
    if fname.startswith((".", "~$", "thumbs.db", "desktop.ini")):
        return False
    ext = os.path.splitext(fname)[1]
    return ext in ALL_SUPPORTED

def index_single_photo(file_path: str) -> Optional[int]:
    """
    Extracts metadata, classifies, caches thumbnail, and indexes a single photo.
    Returns photo ID if successfully indexed.
    """
    if not os.path.exists(file_path):
        return None

    # Wait briefly if file is being written to (size stabilization)
    initial_size = -1
    for _ in range(5):
        try:
            current_size = os.path.getsize(file_path)
            if current_size > 0 and current_size == initial_size:
                break
            initial_size = current_size
        except Exception:
            pass
        time.sleep(0.3)

    try:
        # 1. Metadata extraction & hashing
        meta = extract_metadata(file_path)
        if not meta:
            return None

        # 2. Heuristic Classification
        classification, score, reason = classify_media(meta)
        meta["classification"] = classification
        meta["classification_score"] = score
        meta["classification_reason"] = reason
        meta["indexed_at"] = time.time()

        # 3. Insert or update database
        photo_id = upsert_photo(meta)

        # 4. Generate WebP Micro-thumbnail & Preview non-destructively
        if classification != "UNSUPPORTED":
            generate_thumbnail(file_path, photo_id, "thumb")
            generate_thumbnail(file_path, photo_id, "preview")

        # 5. Multimodal CLIP Vector Embedding
        if classification in ("VERIFIED_PHOTO", "LIKELY_PHOTO"):
            try:
                from backend.vector_engine import VectorEngine
                VectorEngine.get_instance().batch_index_photos([(photo_id, file_path)], batch_size=1)
            except Exception as e:
                print(f"[DEBUG] Vector embedding error for {file_path}: {e}")

        return photo_id
    except Exception as e:
        print(f"[WARN] Error indexing watched photo '{file_path}': {e}")
        return None

class LibraryEventHandler(FileSystemEventHandler):
    def __init__(self, pending_queue: Dict[str, float], lock: threading.Lock):
        super().__init__()
        self.pending_queue = pending_queue
        self.lock = lock

    def _enqueue(self, raw_path: Union[str, bytes, None]):
        if not raw_path:
            return
        path = raw_path.decode("utf-8", errors="replace") if isinstance(raw_path, bytes) else raw_path
        ext = os.path.splitext(path.lower())[1]
        if ext in ALL_SUPPORTED:
            with self.lock:
                self.pending_queue[os.path.abspath(path)] = time.time()

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            dest_path = getattr(event, "dest_path", None)
            if dest_path:
                self._enqueue(dest_path)

class FolderWatcherManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.observer: Optional[BaseObserver] = None
        self.watched_paths: Set[str] = set()
        self.pending_queue: Dict[str, float] = {}
        self.queue_lock = threading.Lock()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.processed_count = 0
        self.last_event_time: Optional[float] = None
        self.last_processed_file: str = ""

    @classmethod
    def get_instance(cls) -> "FolderWatcherManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = FolderWatcherManager()
            return cls._instance

    def start(self, paths: Optional[List[str]] = None):
        """Starts monitoring the specified directories for real-time changes."""
        with self._lock:
            if self.is_running:
                return

            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_watch = [
                os.path.join(repo_root, "uploads"),
                os.path.join(repo_root, "sample_library")
            ]

            initial_paths = paths or default_watch
            observer = Observer()
            self.observer = observer
            handler = LibraryEventHandler(self.pending_queue, self.queue_lock)

            for p in initial_paths:
                p_abs = os.path.abspath(p)
                if not os.path.exists(p_abs):
                    try:
                        os.makedirs(p_abs, exist_ok=True)
                    except Exception:
                        continue
                if os.path.isdir(p_abs):
                    observer.schedule(handler, p_abs, recursive=True)
                    self.watched_paths.add(p_abs)
                    print(f"[INFO] Folder Watcher active on: {p_abs}")

            if not self.watched_paths:
                print("[WARN] No valid folders to watch.")
                return

            self.is_running = True
            observer.start()

            # Start worker thread for debounced event processing
            self.worker_thread = threading.Thread(target=self._process_worker, daemon=True)
            self.worker_thread.start()
            print("[INFO] Real-time Library Watcher worker started.")

    def add_watch_path(self, path: str):
        """Adds an additional directory to the active watcher."""
        with self._lock:
            p_abs = os.path.abspath(path)
            if p_abs in self.watched_paths or not os.path.isdir(p_abs):
                return
            if self.observer and self.is_running:
                handler = LibraryEventHandler(self.pending_queue, self.queue_lock)
                self.observer.schedule(handler, p_abs, recursive=True)
            self.watched_paths.add(p_abs)
            print(f"[INFO] Added watched path: {p_abs}")

    def _process_worker(self):
        """Processes debounced file events sequentially."""
        debounce_seconds = 1.8
        while self.is_running:
            now = time.time()
            ready_paths = []

            with self.queue_lock:
                for path, timestamp in list(self.pending_queue.items()):
                    if now - timestamp >= debounce_seconds:
                        ready_paths.append(path)
                        del self.pending_queue[path]

            for path in ready_paths:
                if is_valid_media_file(path):
                    print(f"[WATCHER] Auto-indexing new/updated media: {os.path.basename(path)}")
                    pid = index_single_photo(path)
                    if pid:
                        self.processed_count += 1
                        self.last_event_time = time.time()
                        self.last_processed_file = os.path.basename(path)

            time.sleep(0.5)

    def stop(self):
        """Stops the watcher observer and processing thread."""
        with self._lock:
            if not self.is_running:
                return
            self.is_running = False
            if self.observer:
                try:
                    self.observer.stop()
                    self.observer.join(timeout=2.0)
                except Exception:
                    pass
                self.observer = None
            print("[INFO] Folder Watcher stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the current watcher status."""
        with self.queue_lock:
            pending_count = len(self.pending_queue)
        return {
            "is_running": self.is_running,
            "watched_paths": sorted(list(self.watched_paths)),
            "processed_count": self.processed_count,
            "pending_queue_count": pending_count,
            "last_event_time": self.last_event_time,
            "last_processed_file": self.last_processed_file
        }
