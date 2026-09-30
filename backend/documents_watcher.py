"""
Dedicated Real-Time Folder Watcher for LuminaDocuments.
Completely decoupled from photo watching.
Monitors user-configured watched folders that reside strictly within
Windows & OneDrive Documents and Downloads folders.
"""

import os
import time
import threading
from typing import Set, Dict, Any, List, Optional, Union
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from backend.documents_scanner import (
    is_personal_document,
    is_path_in_allowed_document_roots,
    DocumentsScanManager
)
from backend.documents_db import (
    get_watched_folders,
    add_watched_folder,
    remove_watched_folder,
    init_documents_db
)
from backend.documents_vector import DocumentVectorEngine

class DocumentEventHandler(FileSystemEventHandler):
    """File system event handler for document directory changes."""
    def __init__(self, pending_queue: Dict[str, float], lock: threading.Lock):
        super().__init__()
        self.pending_queue = pending_queue
        self.lock = lock

    def _enqueue(self, raw_path: Union[str, bytes, None]):
        if not raw_path:
            return
        path = raw_path.decode("utf-8", errors="replace") if isinstance(raw_path, bytes) else raw_path
        if is_path_in_allowed_document_roots(path) and is_personal_document(path):
            with self.lock:
                self.pending_queue[os.path.normpath(os.path.abspath(path))] = time.time()

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

class DocumentWatcherManager:
    """Singleton manager for real-time document folder monitoring."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.observer: Optional[BaseObserver] = None
        self.watch_descriptors: Dict[str, Any] = {} # path -> watch object
        self.pending_queue: Dict[str, float] = {}
        self.queue_lock = threading.Lock()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.processed_count = 0
        self.last_event_time: Optional[float] = None
        self.last_processed_file: str = ""
        init_documents_db()

    @classmethod
    def get_instance(cls) -> "DocumentWatcherManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DocumentWatcherManager()
            return cls._instance

    def start(self):
        """Starts monitoring all active user-configured watched folders."""
        with self._lock:
            if self.is_running:
                return

            observer = Observer()
            self.observer = observer
            handler = DocumentEventHandler(self.pending_queue, self.queue_lock)

            db_folders = get_watched_folders()
            for item in db_folders:
                if not item.get("is_active"):
                    continue
                path = item.get("folder_path")
                if path and is_path_in_allowed_document_roots(path) and os.path.isdir(path):
                    try:
                        norm = os.path.normpath(os.path.abspath(path))
                        watch = observer.schedule(handler, norm, recursive=True)
                        self.watch_descriptors[norm] = watch
                        print(f"[DocumentWatcher] Monitoring folder: {norm}")
                    except Exception as e:
                        print(f"[DocumentWatcher] Error scheduling watch on {path}: {e}")

            self.is_running = True
            observer.start()

            self.worker_thread = threading.Thread(target=self._process_worker, daemon=True)
            self.worker_thread.start()
            print("[DocumentWatcher] Real-time document watcher started.")

            # If there are active watched folders in DB, trigger background catch-up sync
            if db_folders:
                def _delayed_initial_sync():
                    time.sleep(2.0)
                    self.sync_all_watched_folders()
                threading.Thread(target=_delayed_initial_sync, daemon=True).start()

    def sync_folder(self, folder_path: str) -> bool:
        """Triggers an immediate background discovery & indexing scan of a watched folder."""
        norm_path = os.path.normpath(os.path.abspath(folder_path))
        if not is_path_in_allowed_document_roots(norm_path) or not os.path.isdir(norm_path):
            return False
        try:
            scan_mgr = DocumentsScanManager.get_instance()
            if not scan_mgr.is_scanning:
                scan_mgr.start_scan(custom_roots=[norm_path], recursive=True)
                print(f"[DocumentWatcher] Started background catch-up scan on: {norm_path}")
                return True
            else:
                print(f"[DocumentWatcher] Scan already running; skipped starting scan for {norm_path}")
                return False
        except Exception as e:
            print(f"[DocumentWatcher] Error starting sync scan on {norm_path}: {e}")
            return False

    def sync_all_watched_folders(self) -> int:
        """Triggers a background scan covering all active watched folders."""
        folders = get_watched_folders()
        active_paths = [
            f["folder_path"] for f in folders
            if f.get("is_active") and os.path.isdir(f.get("folder_path", "")) and is_path_in_allowed_document_roots(f.get("folder_path", ""))
        ]
        if not active_paths:
            return 0
        try:
            scan_mgr = DocumentsScanManager.get_instance()
            if not scan_mgr.is_scanning:
                scan_mgr.start_scan(custom_roots=active_paths, recursive=True)
                print(f"[DocumentWatcher] Started background catch-up scan for {len(active_paths)} watched folders.")
                return len(active_paths)
            else:
                print(f"[DocumentWatcher] Scan already in progress; skipped starting sync_all.")
                return 0
        except Exception as e:
            print(f"[DocumentWatcher] Error syncing all watched folders: {e}")
            return 0

    def add_watch_path(self, folder_path: str, trigger_initial_scan: bool = True) -> bool:
        """Adds and schedules a new directory to the active document watcher and indexes existing files."""
        norm_path = os.path.normpath(os.path.abspath(folder_path))
        if not is_path_in_allowed_document_roots(norm_path):
            raise ValueError(
                "Forbidden: Only folders within Documents and Downloads (in Windows or OneDrive) can be watched."
            )
        if not os.path.isdir(norm_path):
            raise ValueError(f"Directory not found on disk: {norm_path}")

        with self._lock:
            # Save to DB
            add_watched_folder(norm_path)

            if self.observer and self.is_running and norm_path not in self.watch_descriptors:
                handler = DocumentEventHandler(self.pending_queue, self.queue_lock)
                watch = self.observer.schedule(handler, norm_path, recursive=True)
                self.watch_descriptors[norm_path] = watch
                print(f"[DocumentWatcher] Added live watch on: {norm_path}")

        if trigger_initial_scan:
            self.sync_folder(norm_path)

        return True

    def remove_watch_path(self, folder_id: int) -> bool:
        """Removes a folder from watching."""
        with self._lock:
            folders = get_watched_folders()
            target_path = None
            for f in folders:
                if f["id"] == folder_id:
                    target_path = f["folder_path"]
                    break

            remove_watched_folder(folder_id)

            if target_path and target_path in self.watch_descriptors and self.observer:
                try:
                    watch = self.watch_descriptors.pop(target_path)
                    self.observer.unschedule(watch)
                    print(f"[DocumentWatcher] Removed live watch on: {target_path}")
                except Exception as e:
                    print(f"[DocumentWatcher] Error unscheduling {target_path}: {e}")
            return True

    def _process_worker(self):
        """Processes debounced document file events in background thread."""
        debounce_seconds = 1.5
        while self.is_running:
            now = time.time()
            ready_paths = []

            with self.queue_lock:
                for path, timestamp in list(self.pending_queue.items()):
                    if now - timestamp >= debounce_seconds:
                        ready_paths.append(path)
                        del self.pending_queue[path]

            if ready_paths:
                scan_mgr = DocumentsScanManager.get_instance()
                vector_engine = DocumentVectorEngine.get_instance()
                for path in ready_paths:
                    if os.path.exists(path) and is_personal_document(path):
                        try:
                            print(f"[DocumentWatcher] Auto-indexing watched document: {os.path.basename(path)}")
                            scan_mgr._process_single_document(path, vector_engine)
                            self.processed_count += 1
                            self.last_event_time = time.time()
                            self.last_processed_file = os.path.basename(path)
                        except Exception as e:
                            print(f"[DocumentWatcher] Error indexing {path}: {e}")

            time.sleep(0.5)

    def stop(self):
        """Stops the document watcher observer."""
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
            self.watch_descriptors.clear()
            print("[DocumentWatcher] Real-time document watcher stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Returns current watcher status and monitored paths."""
        with self.queue_lock:
            pending_count = len(self.pending_queue)
        with self._lock:
            watched_dirs = sorted(list(self.watch_descriptors.keys()))
        return {
            "is_running": self.is_running,
            "watched_paths": watched_dirs,
            "processed_count": self.processed_count,
            "pending_queue_count": pending_count,
            "last_event_time": self.last_event_time,
            "last_processed_file": self.last_processed_file
        }
