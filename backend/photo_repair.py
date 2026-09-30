"""Background repair for legacy photo records with incomplete image metadata."""

import logging
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

from backend.classifier import classify_media
from backend.database import DB_PATH, get_connection, upsert_photo
from backend.metadata_extractor import SUPPORTED_PHOTO_EXTENSIONS, extract_metadata
from backend.thumbnails import generate_thumbnail, get_thumbnail_path

logger = logging.getLogger(__name__)

# Hash gaps indexed before this repair shipped are retried once. Core decode gaps
# remain eligible until they are repaired or explicitly marked unsupported.
LEGACY_REPAIR_CUTOFF = 1789603200.0
DISPLAYABLE_CLASSIFICATIONS = {
    "VERIFIED_PHOTO",
    "LIKELY_PHOTO",
    "SCREENSHOT",
    "SYSTEM_ASSET",
}


def _get_incomplete_rows(db_path: str) -> list[Dict[str, Any]]:
    extensions = sorted(SUPPORTED_PHOTO_EXTENSIONS)
    placeholders = ", ".join("?" for _ in extensions)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT *
            FROM photos
            WHERE file_extension IN ({placeholders})
              AND classification != 'UNSUPPORTED'
              AND (
                    width IS NULL
                    OR height IS NULL
                    OR format IS NULL
                    OR ((phash IS NULL OR dhash IS NULL) AND indexed_at < ?)
              )
            ORDER BY id
            """,
            [*extensions, LEGACY_REPAIR_CUTOFF],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _mark_missing_source(photo_id: int, db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE photos
                SET classification = 'UNSUPPORTED',
                    classification_score = 1.0,
                    classification_reason = 'Source file is missing or unavailable',
                    format = COALESCE(format, 'UNREADABLE'),
                    indexed_at = ?
                WHERE id = ?
                """,
                (time.time(), photo_id),
            )
    finally:
        conn.close()


def repair_incomplete_photos(
    db_path: str = DB_PATH,
    generate_thumbnails: bool = True,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Repair legacy incomplete rows without changing healthy catalog records."""
    started_at = time.time()
    rows = _get_incomplete_rows(db_path)
    report: Dict[str, Any] = {
        "total": len(rows),
        "processed": 0,
        "repaired": 0,
        "unsupported": 0,
        "missing": 0,
        "failed": 0,
        "thumbnail_failures": 0,
        "current_file": "",
        "status": "REPAIRING",
    }

    for row in rows:
        if should_stop and should_stop():
            report["status"] = "STOPPED"
            break

        photo_id = int(row["id"])
        file_path = row["file_path"]
        had_core_decode_gap = row["width"] is None or row["height"] is None or row["format"] is None
        report["current_file"] = os.path.basename(file_path)

        try:
            if not os.path.isfile(file_path):
                _mark_missing_source(photo_id, db_path)
                report["missing"] += 1
            else:
                metadata = extract_metadata(file_path)
                classification, score, reason = classify_media(metadata)

                if row.get("is_manual_override") and classification != "UNSUPPORTED":
                    classification = row["classification"]
                    score = row["classification_score"]
                    reason = row["classification_reason"]

                metadata["classification"] = classification
                metadata["classification_score"] = score
                metadata["classification_reason"] = reason
                metadata["indexed_at"] = time.time()
                repaired_id = upsert_photo(metadata, db_path)

                if classification == "UNSUPPORTED":
                    report["unsupported"] += 1
                else:
                    report["repaired"] += 1
                    if generate_thumbnails and classification in DISPLAYABLE_CLASSIFICATIONS:
                        cached_thumb = get_thumbnail_path(repaired_id, "thumb")
                        if (had_core_decode_gap or not os.path.exists(cached_thumb)) and not generate_thumbnail(
                            file_path,
                            repaired_id,
                            "thumb",
                            force=had_core_decode_gap,
                        ):
                            report["thumbnail_failures"] += 1
        except Exception as exc:
            report["failed"] += 1
            logger.warning("Could not repair photo %s (%s): %s", photo_id, file_path, exc, exc_info=True)

        report["processed"] += 1
        if progress_callback:
            progress_callback(dict(report))

    if report["status"] == "REPAIRING":
        report["status"] = "COMPLETED"
    report["elapsed_seconds"] = round(time.time() - started_at, 1)
    return report


class PhotoRepairManager:
    _instance: Optional["PhotoRepairManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._status: Dict[str, Any] = {
            "status": "IDLE",
            "is_running": False,
            "total": 0,
            "processed": 0,
            "repaired": 0,
            "unsupported": 0,
            "missing": 0,
            "failed": 0,
            "thumbnail_failures": 0,
            "current_file": "",
        }

    @classmethod
    def get_instance(cls) -> "PhotoRepairManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def start(self) -> bool:
        with self._lock:
            if self._status["is_running"]:
                return False
            self._stop_event.clear()
            self._status = {
                **self._status,
                "status": "STARTING",
                "is_running": True,
                "processed": 0,
                "repaired": 0,
                "unsupported": 0,
                "missing": 0,
                "failed": 0,
                "thumbnail_failures": 0,
                "current_file": "",
            }
            self._thread = threading.Thread(target=self._run, daemon=True, name="photo-catalog-repair")
            self._thread.start()
            return True

    def stop(self) -> None:
        self._stop_event.set()

    def _update_progress(self, report: Dict[str, Any]) -> None:
        with self._lock:
            self._status.update(report)
            self._status["is_running"] = True

    def _run(self) -> None:
        try:
            report = repair_incomplete_photos(
                progress_callback=self._update_progress,
                should_stop=self._stop_event.is_set,
            )

            if not self._stop_event.is_set() and report["repaired"]:
                with self._lock:
                    self._status["status"] = "DEDUPLICATING"
                    self._status["current_file"] = "Refreshing duplicate groups..."
                from backend.deduplicator import run_deduplication_pass

                run_deduplication_pass()

            if not self._stop_event.is_set():
                with self._lock:
                    self._status["status"] = "EMBEDDING"
                    self._status["current_file"] = "Filling missing semantic embeddings..."
                self._fill_missing_embeddings()

            with self._lock:
                self._status.update(report)
                self._status["status"] = "STOPPED" if self._stop_event.is_set() else "COMPLETED"
        except Exception as exc:
            logger.exception("Photo catalog repair failed: %s", exc)
            with self._lock:
                self._status["status"] = "ERROR"
                self._status["error_message"] = str(exc)
        finally:
            with self._lock:
                self._status["is_running"] = False

    def _fill_missing_embeddings(self) -> None:
        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT id, file_path
                FROM photos
                WHERE has_embedding = 0
                  AND classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO')
                  AND width IS NOT NULL
                  AND height IS NOT NULL
                """
            ).fetchall()
        finally:
            conn.close()

        items = [(row["id"], row["file_path"]) for row in rows if os.path.isfile(row["file_path"])]
        if items:
            from backend.vector_engine import VectorEngine

            VectorEngine.get_instance().batch_index_photos(items, batch_size=16)