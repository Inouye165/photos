"""
FastAPI REST API & Web Application Server for LuminaPhoto.
Exposes photo queries, semantic vector search, deduplication inspector, EXIF metadata,
and live folder scanning progress.
"""

import os
import sys
import threading
import logging
from typing import Optional, List, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks, Response
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/backup/status" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

from backend.database import (
    init_db,
    get_photos,
    get_photo_by_id,
    get_duplicate_groups,
    get_stats,
    get_connection,
    tag_photo_trash,
    batch_tag_photo_trash,
    trash_all_duplicates,
    trash_group_duplicates,
    get_trashed_photos,
    log_trash_purge,
    get_trash_purge_logs,
    get_known_entity_folders,
    record_dismissed_pairs,
    get_or_create_entity,
    list_entities,
    get_entity_by_id,
    update_entity,
    delete_entity,
    insert_detected_box,
    get_boxes_for_photo,
    get_box_by_id,
    update_box_entity,
    update_box_dimensions,
    confirm_box,
    reject_box,
    batch_confirm_boxes,
    get_pending_review_boxes,
    get_unassigned_boxes,
    delete_box,
    get_confirmed_embeddings_for_entities,
    resolve_duplicate_photo_entity_assignments,
    DB_PATH
)
from backend.scanner import ScanManager
from backend.thumbnails import get_thumbnail_path, generate_thumbnail
from backend.vector_engine import VectorEngine
from backend.deduplicator import run_deduplication_pass, cleanup_duplicate_group
from backend.query_parser import QueryParser
from backend.face_pet_detector import (
    FacePetDetector,
    CROPS_CACHE_DIR,
    STRICT_HIGH_CONFIDENCE_THRESHOLD
)
from backend.backup_worker import BackupWorker
from backend.gdrive_service import GDriveService
from backend.database import update_backup_settings, update_photo_gdrive_status, reset_failed_backups

import shutil
from contextlib import asynccontextmanager

# Ensure DB is initialized
init_db()

def ensure_all_embeddings_in_background():
    try:
        conn = get_connection()
        rows = conn.execute("SELECT id, file_path FROM photos WHERE has_embedding = 0").fetchall()
        conn.close()
        if rows:
            items = [(r["id"], r["file_path"]) for r in rows if os.path.exists(r["file_path"])]
            if items:
                VectorEngine.get_instance().batch_index_photos(items, batch_size=16)
    except Exception as e:
        print(f"Background embedding error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=ensure_all_embeddings_in_background, daemon=True).start()
    try:
        resolve_duplicate_photo_entity_assignments()
    except Exception as e:
        print(f"Error resolving duplicate entity assignments on startup: {e}")
    # Start background Google Drive backup worker
    BackupWorker.get_instance().start()
    yield
    BackupWorker.get_instance().stop()

app = FastAPI(
    title="LuminaPhoto API",
    description="Semantic Photo Discovery, Deduplication & EXIF Management System",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32"><defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#10b981"/><stop offset="50%" stop-color="#06b6d4"/><stop offset="100%" stop-color="#6366f1"/></linearGradient></defs><rect width="32" height="32" rx="8" fill="#0f172a"/><circle cx="16" cy="17" r="8" fill="none" stroke="url(#g)" stroke-width="2.5"/><circle cx="16" cy="17" r="4" fill="url(#g)"/><circle cx="23" cy="9" r="1.5" fill="#10b981"/><path d="M11 9h3l1.5-2h5l1.5 2h3a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1h-16a1 1 0 0 1-1-1v-1a2 2 0 0 1 2-2z" fill="url(#g)" opacity="0.6"/></svg>"""

@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def get_favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")

@app.api_route("/api/training/{action:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], include_in_schema=False)
def handle_legacy_training(action: str):
    return {"status": "idle", "active": False}

class ScanRequest(BaseModel):
    path: str

class ReclassifyRequest(BaseModel):
    classification: str

class TrashToggleRequest(BaseModel):
    is_trashed: bool = True

class BatchTrashRequest(BaseModel):
    photo_ids: List[int]
    is_trashed: bool = True

class PurgeSpaceRequest(BaseModel):
    min_free_gb: Optional[float] = 5.0
    force_purge_count: Optional[int] = None
    target_bytes_to_free: Optional[int] = None

class CreateEntityRequest(BaseModel):
    name: str
    entity_type: str = "PERSON"

class UpdateEntityRequest(BaseModel):
    name: Optional[str] = None
    entity_type: Optional[str] = None
    avatar_box_id: Optional[int] = None

class CreateBoxRequest(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    box_type: str = "FACE"
    label: str = "person"
    entity_name: Optional[str] = None
    entity_type: Optional[str] = "PERSON"

class UpdateBoxRequest(BaseModel):
    entity_name: Optional[str] = None
    entity_type: Optional[str] = "PERSON"
    status: Optional[str] = None
    x_min: Optional[float] = None
    y_min: Optional[float] = None
    x_max: Optional[float] = None
    y_max: Optional[float] = None

class AssignBoxRequest(BaseModel):
    entity_name: str
    entity_type: Optional[str] = "PERSON"
    set_as_avatar: Optional[bool] = True

class BatchConfirmRequest(BaseModel):
    box_ids: List[int]

class BackupSettingsRequest(BaseModel):
    hourly_limit: Optional[int] = None
    delay_seconds: Optional[float] = None
    root_folder_name: Optional[str] = None
    is_paused: Optional[bool] = None

class ExchangeCodeRequest(BaseModel):
    code: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = "http://localhost:8500/api/backup/auth/callback"

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_drive_space_info(target_dir: Optional[str] = None, min_free_gb: float = 5.0):
    if not target_dir:
        target_dir = WORKSPACE_DIR
    drive_path = target_dir if os.path.exists(target_dir) else os.path.expanduser("~")
    try:
        usage = shutil.disk_usage(drive_path)
        total_bytes = usage.total
        used_bytes = usage.used
        free_bytes = usage.free
    except Exception:
        total_bytes = 100 * (1024 ** 3)
        free_bytes = 50 * (1024 ** 3)
        used_bytes = 50 * (1024 ** 3)
    
    conn = get_connection()
    trash_row = conn.execute("SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM photos WHERE is_trashed = 1").fetchone()
    conn.close()
    
    total_trashed = trash_row[0]
    trashed_bytes = trash_row[1]
    
    threshold_bytes = int(min_free_gb * (1024 ** 3))
    is_space_low = free_bytes < threshold_bytes
    
    return {
        "drive_path": drive_path,
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "total_gb": round(total_bytes / (1024 ** 3), 2),
        "used_gb": round(used_bytes / (1024 ** 3), 2),
        "free_gb": round(free_bytes / (1024 ** 3), 2),
        "percent_free": round((free_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0,
        "trashed_count": total_trashed,
        "trashed_bytes": trashed_bytes,
        "trashed_mb": round(trashed_bytes / (1024 ** 2), 2),
        "low_space_threshold_gb": min_free_gb,
        "is_space_low": is_space_low
    }

@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "LuminaPhoto"}

@app.get("/api/default-path")
def get_default_path():
    """Returns sensible default paths on the host system."""
    user_home = os.path.expanduser("~")
    pictures_dir = os.path.join(user_home, "Pictures")
    photos_workspace = WORKSPACE_DIR
    
    suggested = photos_workspace if os.path.exists(photos_workspace) else (pictures_dir if os.path.exists(pictures_dir) else user_home)
    return {
        "suggested_path": suggested,
        "home": user_home,
        "pictures": pictures_dir
    }

@app.get("/api/browse-folders")
def browse_folders(path: Optional[str] = None):
    """Lists subdirectories within a given path for folder & subfolder browsing."""
    target_path = path.strip() if path and path.strip() else WORKSPACE_DIR
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        target_path = os.path.expanduser("~")
        
    subfolders = []
    parent = os.path.dirname(os.path.abspath(target_path)) if target_path != os.path.dirname(os.path.abspath(target_path)) else None
    
    try:
        with os.scandir(target_path) as it:
            for entry in it:
                if entry.is_dir() and not entry.name.startswith(('.', '$')) and entry.name not in ('node_modules', '.git', '.lumina_cache', 'venv', '__pycache__'):
                    subfolders.append({
                        "name": entry.name,
                        "path": entry.path
                    })
    except Exception:
        pass
        
    subfolders.sort(key=lambda x: x["name"].lower())
    
    return {
        "current_path": os.path.abspath(target_path),
        "parent_path": parent,
        "subfolders": subfolders
    }

@app.post("/api/catalog/clear")
def clear_catalog():
    """Clears indexed catalog records and embeddings for a fresh scan."""
    conn = get_connection()
    conn.execute("DELETE FROM duplicate_groups")
    conn.execute("DELETE FROM photos")
    conn.commit()
    conn.close()
    
    VectorEngine.get_instance().clear_index()
    return {"message": "Catalog cleared successfully."}

@app.post("/api/scan/start")
def start_scan(req: ScanRequest):
    """Starts recursive indexing of a folder and its subfolders."""
    manager = ScanManager.get_instance()
    success = manager.start_scan(req.path)
    if not success:
        status = manager.get_status()
        raise HTTPException(status_code=400, detail=status.get("error_message") or "Scan already in progress")
    return {"message": "Scan started", "path": req.path}

@app.post("/api/scan/stop")
def stop_scan():
    """Stops the currently active scan."""
    manager = ScanManager.get_instance()
    manager.stop_scan()
    return {"message": "Scan stopping..."}

@app.get("/api/scan/status")
def get_scan_status():
    """Returns real-time scan progress and counters."""
    manager = ScanManager.get_instance()
    return manager.get_status()

@app.post("/api/deduplicate/refresh")
def refresh_duplicates():
    """Manually re-runs deduplication clustering across the photo library."""
    count = run_deduplication_pass()
    return {"message": f"Deduplication completed. Found {count} duplicate groups."}

@app.get("/api/photos")
def list_photos(
    query: Optional[str] = Query(None, description="Natural language semantic search query"),
    classification: Optional[str] = Query(None, description="Filter by classification (VERIFIED_PHOTO, LIKELY_PHOTO, SCREENSHOT, SYSTEM_ASSET, ALL)"),
    include_duplicates: bool = Query(True, description="Whether to include duplicate copies"),
    include_trashed: bool = Query(False, description="Whether to include photos tagged for trash"),
    camera_make: Optional[str] = Query(None, description="Filter by camera make"),
    has_gps: Optional[bool] = Query(None, description="Filter by presence of GPS geotag"),
    year: Optional[str] = Query(None, description="Filter by year (e.g. 2026, 2025)"),
    entity_id: Optional[int] = Query(None, description="Filter by Person or Pet entity ID"),
    sort_by: str = Query("date_taken", description="Sort field: date_taken, file_name, file_size, indexed_at"),
    sort_order: str = Query("DESC", description="Sort direction: ASC, DESC"),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    known_total: Optional[int] = Query(None, description="Cached library count to skip full table scan on scroll")
):
    """
    Returns paginated photos. If `query` is provided, performs natural language semantic vector search
    with CLIP embeddings and returns ranked matches.
    """
    actual_limit = limit
    actual_offset = offset
    clean_year = year if isinstance(year, str) and year.strip() else None
    clean_camera = camera_make if isinstance(camera_make, str) and camera_make.strip() else None
    clean_gps = has_gps if isinstance(has_gps, bool) else None
    clean_class = classification if isinstance(classification, str) and classification.strip() else None

    if query and query.strip():
        # 1. Parse natural language intent, entities, dates, and visual prompt
        known_folders = get_known_entity_folders()
        parser = QueryParser(known_folders=known_folders)
        parsed = parser.parse(query.strip())
        
        target_class = clean_class if clean_class else parsed.classification

        # 2. Check if there are explicit or parsed metadata constraints
        has_temporal_constraints = bool(parsed.date_from or parsed.date_to or clean_year)
        has_metadata_constraints = bool(clean_camera or (clean_gps is not None) or (target_class and target_class != "ALL"))

        allowed_candidate_ids = None
        date_fallback_applied = False

        if has_temporal_constraints or has_metadata_constraints:
            matched_photos, _ = get_photos(
                classification=target_class,
                date_from=parsed.date_from,
                date_to=parsed.date_to,
                year=clean_year,
                camera_make=clean_camera,
                has_gps=clean_gps,
                is_trashed=None if include_trashed else False,
                limit=100000,
                offset=0
            )
            allowed_candidate_ids = {p["id"] for p in matched_photos}

            # If strict temporal filter yielded 0 results, smoothly fall back to ranking across all dates
            if not allowed_candidate_ids and has_temporal_constraints:
                date_fallback_applied = True
                fallback_photos, _ = get_photos(
                    classification=target_class,
                    year=clean_year,
                    camera_make=clean_camera,
                    has_gps=clean_gps,
                    is_trashed=None if include_trashed else False,
                    limit=100000,
                    offset=0
                )
                allowed_candidate_ids = {p["id"] for p in fallback_photos} if fallback_photos else None

        # 3. Perform Semantic Vector Search with pre-filtered candidate subset
        search_prompt = parsed.visual_prompt or query.strip()
        vector_engine = VectorEngine.get_instance()
        
        top_k_candidates = max(250, (actual_limit + actual_offset) * 4)
        search_results = vector_engine.search_text(
            search_prompt,
            top_k=top_k_candidates,
            allowed_photo_ids=allowed_candidate_ids
        )
        
        if not search_results:
            return {
                "photos": [],
                "total": 0,
                "offset": offset,
                "limit": limit,
                "query": query,
                "parsed_query": parsed.to_dict()
            }

        photo_id_to_score = {r["photo_id"]: r["similarity_score"] for r in search_results}
        candidate_ids = [r["photo_id"] for r in search_results]

        photos, _ = get_photos(
            classification="ALL",
            photo_ids=candidate_ids,
            is_trashed=None if include_trashed else False,
            limit=len(candidate_ids),
            offset=0
        )

        # 4. Hybrid scoring: apply entity/folder keyword boost
        scored_photos = []
        for p in photos:
            base_score = photo_id_to_score.get(p["id"], 0.15)
            # Folder boost: if photo path or filename contains any parsed folder keyword, boost score
            boost = 0.0
            if parsed.folder_keywords:
                p_path_lower = p["file_path"].lower()
                if any(kw in p_path_lower for kw in parsed.folder_keywords):
                    boost = 0.09  # Significant boost for entity/folder match
            p["similarity_score"] = round(base_score + boost, 4)
            scored_photos.append(p)

        # Re-sort descending by final hybrid score
        scored_photos.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)

        paged_photos = scored_photos[actual_offset:actual_offset + actual_limit]

        parsed_dict = parsed.to_dict()
        parsed_dict["fallback_applied"] = date_fallback_applied
        if date_fallback_applied:
            period_name = parsed.date_label or "the specified period"
            parsed_dict["fallback_message"] = (
                f"No photos found matching '{parsed.visual_prompt}' in {period_name}. "
                f"Showing closest visual matches across your entire library."
            )

        return {
            "photos": paged_photos,
            "total": len(scored_photos),
            "offset": actual_offset,
            "limit": actual_limit,
            "query": query,
            "parsed_query": parsed_dict
        }

    # Standard database filtering
    class_filter = None if clean_class == "ALL" else clean_class
    photos, total = get_photos(
        classification=class_filter,
        include_duplicates=include_duplicates,
        camera_make=clean_camera,
        has_gps=clean_gps,
        year=clean_year,
        entity_id=entity_id,
        sort_by=sort_by,
        sort_order=sort_order,
        is_trashed=None if include_trashed else False,
        limit=actual_limit,
        offset=actual_offset,
        skip_count=(known_total is not None),
        known_total=known_total
    )

    return {
        "photos": photos,
        "total": total,
        "offset": actual_offset,
        "limit": actual_limit,
        "query": None
    }

@app.get("/api/photos/{photo_id}")
def get_photo_details(photo_id: int):
    """Returns complete metadata, EXIF tags, GPS coordinates, and duplicate status for a photo."""
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo

IMMUTABLE_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable"
}

@app.get("/api/photos/{photo_id}/thumbnail")
def get_photo_thumbnail(photo_id: int):
    """Serves the cached WebP micro-thumbnail with high-speed disk fast-path and HTTP caching."""
    thumb_path = get_thumbnail_path(photo_id, "thumb")
    if os.path.exists(thumb_path):
        return FileResponse(thumb_path, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)

    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if os.path.exists(photo["file_path"]):
        generated = generate_thumbnail(photo["file_path"], photo_id, "thumb")
        if generated and os.path.exists(generated):
            return FileResponse(generated, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
        return FileResponse(photo["file_path"], headers={"Cache-Control": "public, max-age=86400"})

    raise HTTPException(status_code=404, detail="Thumbnail not available")

@app.get("/api/photos/{photo_id}/preview")
@app.get("/api/photos/{photo_id}/file")
def get_photo_preview(photo_id: int):
    """Serves the HD WebP preview image with high-speed disk fast-path and HTTP caching."""
    preview_path = get_thumbnail_path(photo_id, "preview")
    if os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)

    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if os.path.exists(photo["file_path"]):
        generated = generate_thumbnail(photo["file_path"], photo_id, "preview")
        if generated and os.path.exists(generated):
            return FileResponse(generated, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
        return FileResponse(photo["file_path"], headers={"Cache-Control": "public, max-age=86400"})

    raise HTTPException(status_code=404, detail="Preview not available")

@app.get("/api/photos/{photo_id}/original")
def get_photo_original(photo_id: int):
    """Serves the pristine original photo file (read-only)."""
    photo = get_photo_by_id(photo_id)
    if not photo or not os.path.exists(photo["file_path"]):
        raise HTTPException(status_code=404, detail="Original photo file not found on disk")

    return FileResponse(
        photo["file_path"],
        filename=photo["file_name"],
        media_type="application/octet-stream"
    )

@app.get("/api/photos/{photo_id}/full")
def get_photo_full(photo_id: int):
    """Serves high-detail 4K resolution image for deep face inspection."""
    full_path = get_thumbnail_path(photo_id, "full")
    if os.path.exists(full_path):
        return FileResponse(full_path, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)

    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if os.path.exists(photo["file_path"]):
        ext = os.path.splitext(photo["file_path"])[1].lower()
        if ext in (".jpg", ".jpeg"):
            return FileResponse(photo["file_path"], media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
        elif ext == ".png":
            return FileResponse(photo["file_path"], media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
        
        generated = generate_thumbnail(photo["file_path"], photo_id, "full")
        if generated and os.path.exists(generated):
            return FileResponse(generated, media_type="image/webp", headers=IMMUTABLE_CACHE_HEADERS)
        return FileResponse(photo["file_path"], headers={"Cache-Control": "public, max-age=86400"})

    raise HTTPException(status_code=404, detail="Photo file not available")

import socket

try:
    import send2trash  # type: ignore
except Exception:
    send2trash = None

def get_local_ip_addresses():
    """Detects local IPv4 addresses on Wi-Fi / Ethernet."""
    ip_list = []
    try:
        # Connect to an external address briefly to identify the active outbound interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and not primary_ip.startswith("127."):
            ip_list.append(primary_ip)
    except Exception:
        pass

    # Fallback to gethostbyname_ex
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ip not in ip_list:
                ip_list.append(ip)
    except Exception:
        pass

    if not ip_list:
        ip_list = ["127.0.0.1"]
    return ip_list

@app.get("/api/network-info")
def get_network_info():
    """Returns local network IP addresses for home Wi-Fi and mobile phone access."""
    port = 8500
    ips = get_local_ip_addresses()
    urls = [f"http://{ip}:{port}" for ip in ips]
    return {
        "hostname": socket.gethostname(),
        "port": port,
        "ips": ips,
        "primary_url": urls[0],
        "all_urls": urls
    }

@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id: int, permanent: bool = False):
    """
    Safely deletes a photo file (moves to Windows Recycle Bin by default)
    and removes it from database & thumbnail cache.
    """
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_path = photo["file_path"]
    dup_group_id = photo.get("duplicate_group_id")

    # 1. Delete physical file (Trash / Recycle Bin preferred)
    if os.path.exists(file_path):
        try:
            if not permanent and send2trash is not None:
                send2trash.send2trash(file_path)
            else:
                os.remove(file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file from disk: {str(e)}")

    # Clean up cached thumbnails
    for size_type in ("thumb", "preview"):
        t_path = get_thumbnail_path(photo_id, size_type)
        if os.path.exists(t_path):
            try:
                os.remove(t_path)
            except Exception:
                pass

    # Permanently delete from Google Drive if backed up
    if photo.get("gdrive_file_id"):
        try:
            GDriveService.get_instance().delete_photo_permanently(photo["gdrive_file_id"])
        except Exception as e:
            print(f"Error deleting photo {photo_id} from Google Drive: {e}")

    # 3. Remove from database
    conn = get_connection()
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()
    conn.close()

    # 4. Reconcile sibling clusters incrementally in O(1)
    if dup_group_id:
        cleanup_duplicate_group(dup_group_id)

    return {
        "message": f"Successfully deleted '{photo['file_name']}' from disk and catalog",
        "file_path": file_path,
        "sent_to_trash": not permanent and (send2trash is not None)
    }

@app.post("/api/photos/{photo_id}/trash")
def toggle_photo_trash(photo_id: int, req: TrashToggleRequest = Body(...)):
    """
    Tags or untags a photo for the trash without deleting it from disk.
    The file remains untouched until the trash is emptied or space is needed.
    """
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    success = tag_photo_trash(photo_id, req.is_trashed)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update trash status")

    dup_group_id = photo.get("duplicate_group_id")
    if dup_group_id:
        try:
            cleanup_duplicate_group(dup_group_id)
        except Exception:
            pass

    # Sync trash status to Google Drive
    if not req.is_trashed and photo.get("gdrive_file_id"):
        try:
            GDriveService.get_instance().untrash_photo(photo["gdrive_file_id"])
            update_photo_gdrive_status(photo_id, status="backed_up")
        except Exception as e:
            print(f"Error untrashing photo on Google Drive: {e}")
    
    # Wake worker to process sync
    BackupWorker.get_instance().trigger_wake()

    action = "tagged for trash (file left in place)" if req.is_trashed else "restored from trash"
    return {
        "message": f"'{photo['file_name']}' {action}",
        "id": photo_id,
        "is_trashed": req.is_trashed
    }

@app.post("/api/photos/batch-trash")
def batch_trash_photos(req: BatchTrashRequest = Body(...)):
    """Batch tags or untags multiple photos for the trash non-destructively."""
    affected_groups = []
    if req.photo_ids:
        try:
            conn = get_connection()
            placeholders = ",".join("?" for _ in req.photo_ids)
            rows = conn.execute(
                f"SELECT DISTINCT duplicate_group_id FROM photos WHERE id IN ({placeholders}) AND duplicate_group_id IS NOT NULL",
                req.photo_ids
            ).fetchall()
            affected_groups = [r[0] for r in rows if r[0]]
            conn.close()
        except Exception:
            pass

    count = batch_tag_photo_trash(req.photo_ids, req.is_trashed)

    # Wake backup worker to sync trash/untrash
    BackupWorker.get_instance().trigger_wake()

    for gid in affected_groups:
        try:
            cleanup_duplicate_group(gid)
        except Exception:
            pass

    action = "tagged for trash" if req.is_trashed else "restored from trash"
    return {
        "message": f"{count} photos {action}",
        "count": count,
        "is_trashed": req.is_trashed
    }

@app.get("/api/trash")
def list_trash(
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Retrieves all photos currently tagged for the trash with recoverable disk space stats."""
    photos, total, total_bytes = get_trashed_photos(limit=limit, offset=offset)
    space_info = get_drive_space_info()
    return {
        "photos": photos,
        "total": total,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 ** 2), 2),
        "offset": offset,
        "limit": limit,
        "space_info": space_info
    }

@app.post("/api/trash/empty")
def empty_trash_all(permanent: bool = True):
    """
    Permanently deletes all currently trashed photos from disk, thumbnail caches, and database.
    """
    photos, total_count, total_bytes = get_trashed_photos(limit=10000, offset=0)
    if total_count == 0:
        return {
            "message": "Trash is already empty.",
            "deleted_count": 0,
            "freed_bytes": 0
        }

    deleted_names = []
    freed_bytes = 0
    conn = get_connection()

    for photo in photos:
        pid = photo["id"]
        fpath = photo["file_path"]
        fsize = photo.get("file_size", 0)

        # 1. Delete physical file
        if os.path.exists(fpath):
            try:
                if not permanent and send2trash is not None:
                    send2trash.send2trash(fpath)
                else:
                    os.remove(fpath)
                freed_bytes += fsize
                deleted_names.append(photo["file_name"])
            except Exception as e:
                print(f"Error removing file {fpath}: {e}")
        else:
            deleted_names.append(photo["file_name"])

        # 2. Clean thumbnails
        for size_type in ("thumb", "preview"):
            t_path = get_thumbnail_path(pid, size_type)
            if os.path.exists(t_path):
                try:
                    os.remove(t_path)
                except Exception:
                    pass

        # Permanently delete from Google Drive if backed up
        if photo.get("gdrive_file_id"):
            try:
                GDriveService.get_instance().delete_photo_permanently(photo["gdrive_file_id"])
            except Exception as e:
                print(f"Error deleting photo {pid} from Google Drive: {e}")

        # 3. Remove DB record
        conn.execute("DELETE FROM photos WHERE id = ?", (pid,))

    # Immediately clean up any dead duplicate groups whose active non-trashed items <= 1
    conn.execute("""
        UPDATE photos
        SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0
        WHERE duplicate_group_id IS NOT NULL
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

    conn.commit()
    conn.close()

    # Re-run deduplication pass in background thread to discover new clusters
    try:
        threading.Thread(target=run_deduplication_pass, daemon=True).start()
    except Exception:
        pass

    freed_mb = freed_bytes / (1024 ** 2)
    message = f"Emptied trash: permanently removed {len(deleted_names)} photo(s), reclaiming {freed_mb:.2f} MB of disk space."
    
    log_trash_purge(
        freed_bytes=freed_bytes,
        photo_count=len(deleted_names),
        reason="MANUAL_EMPTY",
        message=message,
        deleted_files=deleted_names
    )

    return {
        "message": message,
        "deleted_count": len(deleted_names),
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_mb, 2),
        "deleted_files": deleted_names
    }

@app.post("/api/trash/restore-all")
def restore_all_trash():
    """Restores all trashed photos back to the active library."""
    conn = get_connection()
    cursor = conn.execute("UPDATE photos SET is_trashed = 0, trashed_at = NULL WHERE is_trashed = 1")
    count = cursor.rowcount
    conn.commit()
    conn.close()

    return {
        "message": f"Successfully restored {count} photo(s) to your photo library.",
        "restored_count": count
    }

@app.get("/api/trash/space-status")
def get_trash_space_status(min_free_gb: float = Query(5.0)):
    """Returns real-time drive space health, thresholds, and recoverable trash size."""
    return get_drive_space_info(min_free_gb=min_free_gb)

@app.post("/api/trash/purge-for-space")
def purge_trash_for_space(req: PurgeSpaceRequest = Body(...)):
    """
    Evaluates drive free space. If free space is below the threshold (or if force purge requested),
    it permanently deletes the oldest trashed photos to reclaim space and logs a mandatory notification message.
    """
    min_free_gb = req.min_free_gb if req.min_free_gb is not None else 5.0
    space_info = get_drive_space_info(min_free_gb=min_free_gb)

    # Check if space is actually low or if specific purge targets were requested
    needs_purge = space_info["is_space_low"] or (req.force_purge_count is not None and req.force_purge_count > 0) or (req.target_bytes_to_free is not None and req.target_bytes_to_free > 0)
    
    if not needs_purge:
        return {
            "purged": False,
            "count": 0,
            "freed_bytes": 0,
            "message": f"Disk space is sufficient ({space_info['free_gb']:.2f} GB free, threshold is {min_free_gb} GB). No photos purged.",
            "space_info": space_info
        }

    # Fetch trashed photos sorted oldest trashed first (FIFO)
    conn = get_connection()
    cursor = conn.execute("SELECT id, file_path, file_name, file_size FROM photos WHERE is_trashed = 1 ORDER BY trashed_at ASC, id ASC")
    trashed_candidates = [dict(r) for r in cursor.fetchall()]
    conn.close()

    if not trashed_candidates:
        return {
            "purged": False,
            "count": 0,
            "freed_bytes": 0,
            "message": "Disk space is low, but no photos are in Trash to reclaim space.",
            "space_info": space_info
        }

    # Determine how many photos to purge
    to_delete = []
    accumulated_bytes = 0
    target_bytes = req.target_bytes_to_free if req.target_bytes_to_free else int(min_free_gb * (1024 ** 3) - space_info["free_bytes"])
    max_count = req.force_purge_count if req.force_purge_count else len(trashed_candidates)

    for item in trashed_candidates:
        to_delete.append(item)
        accumulated_bytes += item.get("file_size", 0)
        if len(to_delete) >= max_count:
            break
        if target_bytes > 0 and accumulated_bytes >= target_bytes and len(to_delete) >= (req.force_purge_count or 1):
            break

    # Permanently delete selected candidates
    conn = get_connection()
    deleted_names = []
    actually_freed_bytes = 0

    for item in to_delete:
        pid = item["id"]
        fpath = item["file_path"]
        fsize = item.get("file_size", 0)

        # Remove physical file (prefer OS Recycle Bin for safety, fallback to os.remove)
        if os.path.exists(fpath):
            try:
                if send2trash is not None:
                    send2trash.send2trash(fpath)
                else:
                    os.remove(fpath)
                actually_freed_bytes += fsize
                deleted_names.append(item["file_name"])
            except Exception as e:
                try:
                    os.remove(fpath)
                    actually_freed_bytes += fsize
                    deleted_names.append(item["file_name"])
                except Exception as e2:
                    print(f"Error purging file {fpath}: {e2}")
        else:
            deleted_names.append(item["file_name"])

        # Delete cached thumbnails
        for size_type in ("thumb", "preview"):
            t_path = get_thumbnail_path(pid, size_type)
            if os.path.exists(t_path):
                try:
                    os.remove(t_path)
                except Exception:
                    pass

        # Permanently delete from Google Drive if backed up
        if item.get("gdrive_file_id"):
            try:
                GDriveService.get_instance().delete_photo_permanently(item["gdrive_file_id"])
            except Exception as e:
                print(f"Error deleting photo {pid} from Google Drive: {e}")

        # Remove from database
        conn.execute("DELETE FROM photos WHERE id = ?", (pid,))

    conn.commit()
    conn.close()

    freed_mb = actually_freed_bytes / (1024 ** 2)
    files_sample = ", ".join(deleted_names[:5]) + (f" and {len(deleted_names) - 5} more" if len(deleted_names) > 5 else "")
    
    # Mandatory notification message for permanent space reclamation
    notification_message = (
        f"CRITICAL DISK SPACE NOTICE: System permanently deleted {len(deleted_names)} photo(s) ({freed_mb:.2f} MB) "
        f"from Trash to reclaim disk space (Drive free: {space_info['free_gb']:.1f} GB). "
        f"Purged files: {files_sample}."
    )

    log_id = log_trash_purge(
        freed_bytes=actually_freed_bytes,
        photo_count=len(deleted_names),
        reason="LOW_DISK_SPACE",
        message=notification_message,
        deleted_files=deleted_names
    )

    # Recompute drive space
    updated_space = get_drive_space_info(min_free_gb=min_free_gb)

    return {
        "purged": True,
        "count": len(deleted_names),
        "freed_bytes": actually_freed_bytes,
        "freed_mb": round(freed_mb, 2),
        "message": notification_message,
        "deleted_files": deleted_names,
        "log_id": log_id,
        "space_info": updated_space
    }

@app.get("/api/trash/purge-logs")
def get_purge_history(limit: int = Query(50, ge=1, le=200)):
    """Retrieves audit logs of all permanent deletions performed due to space constraints or empty trash."""
    logs = get_trash_purge_logs(limit=limit)
    return {"logs": logs}

# =========================================================================
# Google Drive Backup & Sync Endpoints
# =========================================================================

@app.get("/api/backup/status")
def get_backup_status():
    """Returns real-time Google Drive backup state, quotas, and current progress."""
    return BackupWorker.get_instance().get_state()

@app.get("/api/backup/auth/url")
def get_backup_auth_url(redirect_uri: Optional[str] = None):
    """Generates the direct Google OAuth consent URL for the frontend."""
    from backend.gdrive_auth import is_configured, create_auth_url
    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Google Drive credentials file ('backend/credentials.json') is missing. "
                "Please download your OAuth 2.0 Client ID (Desktop App) from Google Cloud Console "
                "and save it as 'backend/credentials.json'. See README.md for setup instructions."
            )
        )
    uri = redirect_uri or "http://localhost:8500/api/backup/auth/callback"
    try:
        url, state = create_auth_url(redirect_uri=uri)
        return {"auth_url": url, "state": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate Google auth URL: {str(e)}")

@app.get("/api/backup/auth/callback", response_class=HTMLResponse)
def handle_backup_auth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handles OAuth redirect from Google, stores credentials token, and wakes worker."""
    if error:
        return HTMLResponse(
            f"<div style='font-family:sans-serif;padding:40px;background:#0f172a;color:#f8fafc;min-height:100vh;'>"
            f"<h2 style='color:#f87171;'>Google Authorization Failed</h2>"
            f"<p>{error}</p><a href='/' style='color:#38bdf8;'>Return to LuminaPhoto</a></div>",
            status_code=400
        )
    if not code:
        return HTMLResponse("<h3>Missing authorization code</h3><a href='/'>Return</a>", status_code=400)

    try:
        from backend.gdrive_auth import exchange_auth_code
        exchange_auth_code(code, state=state, redirect_uri="http://localhost:8500/api/backup/auth/callback")
        GDriveService.get_instance().reset_service()
        BackupWorker.get_instance().trigger_wake()
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
          <title>Google Drive Linked - LuminaPhoto</title>
          <meta http-equiv="refresh" content="2;url=/?backup_connected=true">
          <style>
            body { background: #0f172a; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; border: 1px solid rgba(255,255,255,0.1); padding: 36px 44px; border-radius: 16px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.6); max-width: 440px; }
            h2 { color: #34d399; margin-top: 0; font-size: 22px; }
            p { color: #cbd5e1; font-size: 15px; line-height: 1.5; }
            .btn { display: inline-block; margin-top: 16px; padding: 10px 20px; background: #10b981; color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px; }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>✓ Google Drive Connected!</h2>
            <p>Your Google Drive account has been linked successfully. LuminaPhoto background backup has started.</p>
            <p style="color: #94a3b8; font-size: 13px;">Returning to your photos...</p>
            <a href="/?backup_connected=true" class="btn">Return to Photos Now</a>
          </div>
        </body>
        </html>
        """)
    except Exception as e:
        return HTMLResponse(
            f"<div style='font-family:sans-serif;padding:40px;background:#0f172a;color:#f8fafc;min-height:100vh;'>"
            f"<h2 style='color:#f87171;'>Error Linking Google Drive</h2>"
            f"<p>{str(e)}</p><a href='/' style='color:#38bdf8;'>Return to LuminaPhoto</a></div>",
            status_code=500
        )

@app.post("/api/backup/auth/exchange")
def exchange_code_endpoint(req: ExchangeCodeRequest):
    """Allows manual or frontend programmatic code exchange."""
    from backend.gdrive_auth import exchange_auth_code
    exchange_auth_code(req.code, state=req.state, redirect_uri=req.redirect_uri or "http://localhost:8500/api/backup/auth/callback")
    GDriveService.get_instance().reset_service()
    BackupWorker.get_instance().trigger_wake()
    return {"message": "Google Drive connected successfully", "connected": True}

@app.post("/api/backup/auth/start")
def start_backup_auth():
    """Launches local OAuth flow in background so browser opens for user consent."""
    from backend.gdrive_auth import is_configured
    if not is_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "Google Drive credentials file ('backend/credentials.json') is missing. "
                "Please download your OAuth 2.0 Client ID (Desktop App) from Google Cloud Console "
                "and save it as 'backend/credentials.json'. See README.md for setup instructions."
            )
        )
    def auth_thread():
        try:
            from backend.gdrive_auth import run_local_auth_flow
            run_local_auth_flow()
            GDriveService.get_instance().reset_service()
            BackupWorker.get_instance().trigger_wake()
        except Exception as e:
            print(f"[GDrive Auth Background Error]: {e}")

    threading.Thread(target=auth_thread, daemon=True).start()
    return {"message": "Google Drive authentication flow initiated in browser"}

@app.post("/api/backup/auth/disconnect")
def disconnect_backup():
    """Disconnects Google Drive account and removes credentials token."""
    from backend.gdrive_auth import disconnect
    disconnect()
    GDriveService.get_instance().reset_service()
    BackupWorker.get_instance().trigger_wake()
    return {"message": "Disconnected from Google Drive"}

@app.post("/api/backup/pause")
def pause_backup():
    """Pauses background photo uploads."""
    update_backup_settings(is_paused=1)
    BackupWorker.get_instance().trigger_wake()
    return {"message": "Backup paused", "is_paused": True}

@app.post("/api/backup/resume")
def resume_backup():
    """Resumes background photo uploads."""
    update_backup_settings(is_paused=0)
    BackupWorker.get_instance().trigger_wake()
    return {"message": "Backup resumed", "is_paused": False}

@app.post("/api/backup/settings")
def save_backup_settings(req: BackupSettingsRequest):
    """Updates hourly limit, inter-file delay, or target root folder."""
    paused_val = 1 if req.is_paused else (0 if req.is_paused is False else None)
    settings = update_backup_settings(
        hourly_limit=req.hourly_limit,
        delay_seconds=req.delay_seconds,
        root_folder_name=req.root_folder_name,
        is_paused=paused_val
    )
    BackupWorker.get_instance().trigger_wake()
    return settings

@app.post("/api/backup/retry-failed")
def retry_failed_backups_endpoint():
    """Resets failed backup attempts to pending and wakes worker to re-attempt."""
    count = reset_failed_backups()
    BackupWorker.get_instance().trigger_wake()
    return {"message": f"Queued {count} failed photo(s) for retry", "retried_count": count}


@app.get("/api/duplicates")
def list_duplicates(
    sort_by: Optional[str] = Query(None, description="Field to sort duplicate groups by: count, date, size"),
    sort_order: Optional[str] = Query(None, description="Sort order: desc or asc"),
    category: Optional[str] = Query(None, description="Category filter: all, exact, burst, similar")
):
    """Retrieves all duplicate clusters with primary and duplicate members, optionally sorted and filtered."""
    return get_duplicate_groups(sort_by=sort_by, sort_order=sort_order, category=category)

@app.post("/api/duplicates/trash-all")
def trash_all_duplicates_endpoint():
    """
    Moves all duplicate copies across all duplicate groups to the in-app Trash.
    The primary keeper photo for each group remains in the main gallery.
    """
    count, freed_bytes = trash_all_duplicates()
    try:
        threading.Thread(target=run_deduplication_pass, daemon=True).start()
    except Exception:
        pass
    freed_mb = freed_bytes / (1024 ** 2)
    return {
        "message": f"Moved {count} duplicate photo(s) to Trash, staging {freed_mb:.2f} MB of disk space.",
        "count": count,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_mb, 2)
    }

@app.post("/api/duplicates/group/{group_id}/trash")
def trash_group_duplicates_endpoint(group_id: str):
    """
    Moves all non-primary duplicate copies in a specific group to the in-app Trash.
    The primary keeper photo remains safe in the main gallery.
    """
    count, freed_bytes = trash_group_duplicates(group_id)
    try:
        cleanup_duplicate_group(group_id)
    except Exception:
        pass
    freed_mb = freed_bytes / (1024 ** 2)
    return {
        "message": f"Moved {count} duplicate photo(s) in group to Trash.",
        "count": count,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_mb, 2)
    }

@app.post("/api/duplicates/group/{group_id}/dismiss")
def dismiss_duplicate_group(group_id: str):
    """Marks all items in a duplicate group as unique/dismissed and permanently remembers their dismissal."""
    conn = get_connection()
    # Fetch member photo IDs before dissolving group
    rows = conn.execute("SELECT id FROM photos WHERE duplicate_group_id = ?", (group_id,)).fetchall()
    member_ids = [r["id"] for r in rows]

    # Record all pairwise combinations as dismissed
    if len(member_ids) > 1:
        pairs = []
        for i in range(len(member_ids)):
            for j in range(i + 1, len(member_ids)):
                pairs.append((member_ids[i], member_ids[j]))
        record_dismissed_pairs(pairs)

    conn.execute("UPDATE photos SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0 WHERE duplicate_group_id = ?", (group_id,))
    conn.execute("DELETE FROM duplicate_groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return {"message": f"Duplicate group '{group_id}' dismissed. All files kept intact and pairs will not be re-clustered."}

@app.get("/api/filtered")
def get_filtered_assets(limit: int = 100, offset: int = 0):
    """Returns screenshots, system assets, and non-camera graphics excluded from the main gallery."""
    photos, total = get_photos(
        classification="SCREENSHOT",
        include_duplicates=True,
        limit=limit,
        offset=offset
    )
    assets, total_assets = get_photos(
        classification="SYSTEM_ASSET",
        include_duplicates=True,
        limit=limit,
        offset=offset
    )
    return {
        "screenshots": photos,
        "system_assets": assets,
        "total_screenshots": total,
        "total_system_assets": total_assets
    }

@app.post("/api/photos/{photo_id}/reclassify")
def reclassify_photo(photo_id: int, req: ReclassifyRequest):
    """Allows manual override of media classification."""
    valid = {"VERIFIED_PHOTO", "LIKELY_PHOTO", "SCREENSHOT", "SYSTEM_ASSET", "VIDEO"}
    if req.classification not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid classification. Must be one of {valid}")

    conn = get_connection()
    conn.execute("""
    UPDATE photos 
    SET classification = ?, is_manual_override = 1, classification_reason = 'Manual user override'
    WHERE id = ?
    """, (req.classification, photo_id))
    conn.commit()
    conn.close()

    return {"message": f"Photo {photo_id} reclassified as {req.classification}"}

@app.get("/api/stats")
def get_library_stats():
    """Returns overall library statistics."""
    stats = get_stats()
    # Augment with people & pets summary
    try:
        conn = get_connection()
        p_count = conn.execute("SELECT COUNT(*) FROM entities WHERE entity_type = 'PERSON'").fetchone()[0]
        pet_count = conn.execute("SELECT COUNT(*) FROM entities WHERE entity_type = 'PET'").fetchone()[0]
        pending_count = conn.execute("SELECT COUNT(*) FROM detected_boxes WHERE status = 'PENDING_REVIEW'").fetchone()[0]
        conn.close()
        stats["total_people"] = p_count
        stats["total_pets"] = pet_count
        stats["total_pending_boxes"] = pending_count
    except Exception:
        stats["total_people"] = 0
        stats["total_pets"] = 0
        stats["total_pending_boxes"] = 0
    return stats

# ---------------------------------------------------------
# People & Pets Background Scanner Manager
# ---------------------------------------------------------

class PeoplePetsScanManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.is_scanning = False
        self.total = 0
        self.processed = 0
        self.matches_found = 0
        self.stopped = False

    @classmethod
    def get_instance(cls) -> "PeoplePetsScanManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = PeoplePetsScanManager()
            return cls._instance

    def start_scan(self) -> bool:
        with self._lock:
            if self.is_scanning:
                return False
            self.is_scanning = True
            self.stopped = False
            self.processed = 0
            self.matches_found = 0
            threading.Thread(target=self._run, daemon=True).start()
            return True

    def stop_scan(self):
        self.stopped = True

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_scanning": self.is_scanning,
            "total": self.total,
            "processed": self.processed,
            "matches_found": self.matches_found,
            "progress_percent": round((self.processed / max(1, self.total)) * 100, 1) if self.total > 0 else 0.0
        }

    def _run(self):
        try:
            conn = get_connection()
            rows = conn.execute("""
                SELECT p.id, p.file_path FROM photos p
                LEFT JOIN detected_boxes b ON p.id = b.photo_id
                WHERE b.id IS NULL AND p.is_trashed = 0 AND p.classification IN ('VERIFIED_PHOTO', 'LIKELY_PHOTO')
                ORDER BY p.id DESC
            """).fetchall()
            conn.close()

            self.total = len(rows)
            detector = FacePetDetector.get_instance()
            entity_embeddings = get_confirmed_embeddings_for_entities()

            for r in rows:
                if self.stopped:
                    break
                pid, fpath = r["id"], r["file_path"]
                if os.path.exists(fpath):
                    boxes = detector.process_photo(pid, fpath, entity_embeddings=entity_embeddings)
                    pending_in_photo = sum(1 for b in boxes if b.get("status") == "PENDING_REVIEW")
                    self.matches_found += pending_in_photo
                self.processed += 1
        except Exception as e:
            print(f"People & pets scan error: {e}")
        finally:
            self.is_scanning = False

# ---------------------------------------------------------
# People & Pets REST Endpoints
# ---------------------------------------------------------

@app.get("/api/people-pets/entities")
def get_entities(entity_type: Optional[str] = Query(None, description="Filter by PERSON or PET")):
    """Lists all registered people and pets with photo and review counts."""
    return list_entities(entity_type=entity_type)

@app.post("/api/people-pets/entities")
def create_entity(req: CreateEntityRequest):
    """Creates a new person or pet entity."""
    return get_or_create_entity(req.name, req.entity_type)

@app.put("/api/people-pets/entities/{entity_id}")
def update_entity_endpoint(entity_id: int, req: UpdateEntityRequest):
    """Updates entity metadata."""
    success = update_entity(entity_id, req.name, req.entity_type, req.avatar_box_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"message": "Entity updated successfully"}

@app.delete("/api/people-pets/entities/{entity_id}")
def delete_entity_endpoint(entity_id: int):
    """Deletes an entity and clears associations."""
    success = delete_entity(entity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"message": "Entity deleted successfully"}

@app.get("/api/people-pets/pending")
def get_pending_reviews(
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    entity_id: Optional[int] = Query(None, description="Filter by specific entity")
):
    """Retrieves all strong match suggestions waiting for user confirmation."""
    items, total = get_pending_review_boxes(limit=limit, offset=offset, entity_id=entity_id)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }

def cleanup_redundant_boxes(photo_id: int, target_box_id: int):
    """
    Cleans up redundant unassigned boxes for a photo when a box is confirmed or named:
    - If target box is a PET (or named PET): removes any unassigned face boxes inside the pet.
    - If target box is a face named PET: removes any unassigned PET box enclosing it.
    - Removes any unassigned duplicate box with >= 70% IoU.
    """
    try:
        main_box = get_box_by_id(target_box_id)
        if not main_box:
            return

        all_boxes = get_boxes_for_photo(photo_id)
        for other in all_boxes:
            if other["id"] == target_box_id:
                continue
            # Only clean up unassigned boxes
            if other.get("entity_id") is not None and other.get("status") == "CONFIRMED":
                continue

            # Check if other is nested inside main_box
            cx = (other["x_min"] + other["x_max"]) / 2
            cy = (other["y_min"] + other["y_max"]) / 2
            is_inside_main = (
                (main_box["x_min"] - 0.03) <= cx <= (main_box["x_max"] + 0.03) and
                (main_box["y_min"] - 0.03) <= cy <= (main_box["y_max"] + 0.03)
            )

            # Check if main_box is inside other
            mcx = (main_box["x_min"] + main_box["x_max"]) / 2
            mcy = (main_box["y_min"] + main_box["y_max"]) / 2
            is_main_inside_other = (
                (other["x_min"] - 0.03) <= mcx <= (other["x_max"] + 0.03) and
                (other["y_min"] - 0.03) <= mcy <= (other["y_max"] + 0.03)
            )

            # Check IoU
            xA = max(main_box["x_min"], other["x_min"])
            yA = max(main_box["y_min"], other["y_min"])
            xB = min(main_box["x_max"], other["x_max"])
            yB = min(main_box["y_max"], other["y_max"])
            inter = max(0.0, xB - xA) * max(0.0, yB - yA)
            area1 = (main_box["x_max"] - main_box["x_min"]) * (main_box["y_max"] - main_box["y_min"])
            area2 = (other["x_max"] - other["x_min"]) * (other["y_max"] - other["y_min"])
            denom = area1 + area2 - inter
            iou = inter / denom if denom > 0 else 0.0

            should_delete = False
            # Case 1: Main box is PET (or entity is PET) and other is unassigned face inside it
            if (main_box.get("box_type") == "PET" or main_box.get("entity_type") == "PET") and is_inside_main:
                should_delete = True
            # Case 2: Main box is named face and other is unassigned PET box enclosing it
            elif (main_box.get("entity_type") == "PET" or main_box.get("entity_id")) and is_main_inside_other and other.get("box_type") == "PET":
                should_delete = True
            # Case 3: Duplicate detection with high overlap
            elif iou >= 0.70:
                should_delete = True

            if should_delete:
                delete_box(other["id"])
                crop_path = os.path.join(CROPS_CACHE_DIR, f"{other['id']}.jpg")
                if os.path.exists(crop_path):
                    try:
                        os.remove(crop_path)
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error in cleanup_redundant_boxes: {e}")

@app.post("/api/people-pets/boxes/{box_id}/confirm")
def confirm_box_endpoint(box_id: int, entity_id: Optional[int] = Query(None)):
    """Confirms an auto-tagged box suggestion."""
    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Detected box not found")

    target_eid = entity_id if entity_id is not None else box.get("entity_id")
    if target_eid is None:
        raise HTTPException(status_code=400, detail="Cannot confirm box without an associated entity")

    confirm_box(box_id, entity_id=target_eid)

    # Set avatar if entity does not have one yet
    entity = get_entity_by_id(target_eid)
    if entity and not entity.get("avatar_box_id"):
        update_entity(target_eid, avatar_box_id=box_id)

    # Clean up redundant unassigned boxes (e.g. unassigned face inside a named pet)
    cleanup_redundant_boxes(box["photo_id"], box_id)

    return {"message": "Box confirmed successfully", "box_id": box_id, "entity_id": target_eid}

@app.post("/api/people-pets/boxes/{box_id}/reject")
def reject_box_endpoint(box_id: int):
    """Rejects an auto-tagged box suggestion."""
    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Detected box not found")
    reject_box(box_id)
    return {"message": "Suggestion rejected", "box_id": box_id}

@app.post("/api/people-pets/boxes/batch-confirm")
def batch_confirm_endpoint(req: BatchConfirmRequest):
    """Confirms multiple suggestions at once."""
    count = batch_confirm_boxes(req.box_ids)
    return {"message": f"Confirmed {count} suggestions", "count": count}

@app.post("/api/people-pets/resolve-duplicates")
def resolve_duplicate_entities_endpoint():
    """Enforces single-identity constraint per photo across the entire library."""
    count = resolve_duplicate_photo_entity_assignments()
    return {"message": f"Resolved {count} duplicate entity assignments", "resolved_count": count}

@app.get("/api/people-pets/unassigned")
def get_unassigned_detected_boxes(
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    box_type: Optional[str] = Query(None, description="Filter by FACE, PERSON, PET, or ALL")
):
    """Returns all detected faces and pets across the library that have not yet been named."""
    items, total = get_unassigned_boxes(limit=limit, offset=offset, box_type=box_type)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.post("/api/people-pets/boxes/{box_id}/assign")
def assign_box_to_entity(box_id: int, req: AssignBoxRequest):
    """Assigns a detected face or pet crop to a named entity (e.g. Ron), sets as confirmed and avatar."""
    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Detected box not found")
    
    entity = get_or_create_entity(req.entity_name.strip(), req.entity_type or "PERSON")
    entity_id = entity["id"]

    update_box_entity(box_id, entity_id, status="CONFIRMED", match_confidence=1.0)

    # Set as avatar if requested or if entity has no avatar yet
    if req.set_as_avatar or not entity.get("avatar_box_id"):
        update_entity(entity_id, avatar_box_id=box_id)

    return {
        "message": f"Successfully tagged as {req.entity_name}",
        "box_id": box_id,
        "entity_id": entity_id,
        "entity_name": req.entity_name
    }

@app.post("/api/people-pets/entities/{entity_id}/set-avatar")
def set_entity_avatar(entity_id: int, box_id: Optional[int] = Query(None)):
    """Sets or clears the profile picture for an entity."""
    entity = get_entity_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    update_entity(entity_id, avatar_box_id=box_id)
    return {"message": "Avatar updated successfully", "entity_id": entity_id, "avatar_box_id": box_id}

@app.post("/api/people-pets/boxes/{box_id}/unlink")
def unlink_box(box_id: int):
    """Unlinks a box from its person/pet without deleting the detection."""
    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")
    if box.get("entity_id"):
        entity = get_entity_by_id(box["entity_id"])
        if entity and entity.get("avatar_box_id") == box_id:
            update_entity(box["entity_id"], avatar_box_id=None)
    update_box_entity(box_id, None, status="UNASSIGNED", match_confidence=0.0)
    return {"message": "Box unlinked successfully", "box_id": box_id}

@app.get("/api/photos/{photo_id}/boxes")
def get_photo_boxes(photo_id: int):
    """
    Returns all detected bounding boxes for a photo.
    Lazily runs high-precision detection on the fly if not yet scanned.
    """
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    detector = FacePetDetector.get_instance()
    boxes = detector.process_photo(photo_id, photo["file_path"])
    # Enrich with entity names
    enriched = get_boxes_for_photo(photo_id)
    return {"boxes": enriched if enriched else boxes}

@app.post("/api/photos/{photo_id}/boxes")
def create_manual_box(photo_id: int, req: CreateBoxRequest):
    """Allows user to manually draw a bounding box and assign a person or pet."""
    photo = get_photo_by_id(photo_id)
    if not photo or not os.path.exists(photo["file_path"]):
        raise HTTPException(status_code=404, detail="Photo file not found")

    detector = FacePetDetector.get_instance()
    entity_id = None
    if req.entity_name and req.entity_name.strip():
        entity = get_or_create_entity(req.entity_name.strip(), req.entity_type or "PERSON")
        entity_id = entity["id"]

    box_record = {
        "photo_id": photo_id,
        "entity_id": entity_id,
        "box_type": req.box_type,
        "label": req.label,
        "confidence": 1.0,
        "x_min": max(0.0, min(1.0, req.x_min)),
        "y_min": max(0.0, min(1.0, req.y_min)),
        "x_max": max(0.0, min(1.0, req.x_max)),
        "y_max": max(0.0, min(1.0, req.y_max)),
        "status": "CONFIRMED" if entity_id else "UNASSIGNED",
        "match_confidence": 1.0 if entity_id else 0.0
    }

    try:
        with Image.open(photo["file_path"]) as img:
            img_transposed = ImageOps.exif_transpose(img)
            emb, crop_pil = detector.extract_crop_embedding(img_transposed, box_record)
            box_record["embedding_json"] = json.dumps(emb)
    except Exception as e:
        print(f"Error computing crop embedding: {e}")
        crop_pil = None

    box_id = insert_detected_box(box_record)
    box_record["id"] = box_id

    if crop_pil is not None:
        crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
        crop_pil.thumbnail((320, 320), Image.Resampling.LANCZOS)
        crop_pil.save(crop_path, "JPEG", quality=90)

    if entity_id:
        entity = get_entity_by_id(entity_id)
        if entity and not entity.get("avatar_box_id"):
            update_entity(entity_id, avatar_box_id=box_id)

    return {"message": "Bounding box created", "box": box_record}

@app.put("/api/photos/{photo_id}/boxes/{box_id}")
def update_photo_box(photo_id: int, box_id: int, req: UpdateBoxRequest):
    """Updates the name / person assigned to a bounding box, or updates dimensions."""
    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")

    # Update dimensions if provided
    dimensions_changed = False
    if req.x_min is not None and req.y_min is not None and req.x_max is not None and req.y_max is not None:
        update_box_dimensions(box_id, req.x_min, req.y_min, req.x_max, req.y_max)
        dimensions_changed = True

    entity_id = box.get("entity_id")
    if req.entity_name is not None:
        if req.entity_name.strip():
            entity = get_or_create_entity(req.entity_name.strip(), req.entity_type or "PERSON")
            entity_id = entity["id"]
        else:
            entity_id = None

    status = req.status or (box["status"] if entity_id else "UNASSIGNED")
    if req.entity_name is not None or req.status is not None:
        update_box_entity(box_id, entity_id, status=status, match_confidence=1.0)

    if entity_id:
        entity = get_entity_by_id(entity_id)
        if entity and not entity.get("avatar_box_id"):
            update_entity(entity_id, avatar_box_id=box_id)
        # Clean up redundant unassigned boxes (e.g. unassigned face inside a named pet)
        cleanup_redundant_boxes(photo_id, box_id)

    # Re-extract crop and embedding if dimensions changed or newly assigned
    if dimensions_changed:
        try:
            photo = get_photo_by_id(photo_id)
            if photo and os.path.exists(photo["file_path"]):
                detector = FacePetDetector.get_instance()
                with Image.open(photo["file_path"]) as img:
                    img_t = ImageOps.exif_transpose(img)
                    updated_box = dict(box)
                    updated_box.update({"x_min": req.x_min, "y_min": req.y_min, "x_max": req.x_max, "y_max": req.y_max})
                    emb, crop_pil = detector.extract_crop_embedding(img_t, updated_box)
                    if crop_pil:
                        crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
                        crop_pil.thumbnail((320, 320), Image.Resampling.LANCZOS)
                        crop_pil.save(crop_path, "JPEG", quality=90)
                    conn = get_connection()
                    with conn:
                        conn.execute("UPDATE detected_boxes SET embedding_json = ? WHERE id = ?", (json.dumps(emb), box_id))
                    conn.close()
        except Exception as e:
            print(f"Error re-extracting resized box crop: {e}")

    return {"message": "Box updated successfully", "box_id": box_id, "entity_id": entity_id}

@app.delete("/api/photos/{photo_id}/boxes/{box_id}")
def delete_photo_box(photo_id: int, box_id: int):
    """Deletes a bounding box."""
    delete_box(box_id)
    crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
    if os.path.exists(crop_path):
        try:
            os.remove(crop_path)
        except Exception:
            pass
    return {"message": "Box deleted successfully"}

@app.get("/api/boxes/{box_id}/crop")
def get_box_crop(box_id: int):
    """Serves high-quality cropped thumbnail for an avatar or confirmation card."""
    crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
    if os.path.exists(crop_path):
        return FileResponse(crop_path, media_type="image/jpeg", headers=IMMUTABLE_CACHE_HEADERS)

    box = get_box_by_id(box_id)
    if not box:
        raise HTTPException(status_code=404, detail="Box not found")

    detector = FacePetDetector.get_instance()
    generated_path = detector.get_or_generate_crop(box)
    if generated_path and os.path.exists(generated_path):
        return FileResponse(generated_path, media_type="image/jpeg", headers=IMMUTABLE_CACHE_HEADERS)

    raise HTTPException(status_code=404, detail="Crop could not be generated")

@app.post("/api/people-pets/scan")
def trigger_people_pets_scan():
    """Starts background detection and high-confidence auto-matching across the library."""
    manager = PeoplePetsScanManager.get_instance()
    started = manager.start_scan()
    if not started:
        return {"message": "Scan already running", "is_scanning": True}
    return {"message": "Background People & Pets scan started", "is_scanning": True}

@app.get("/api/people-pets/scan/status")
def get_people_pets_scan_status():
    """Returns background People & Pets scan status and counters."""
    manager = PeoplePetsScanManager.get_instance()
    return manager.get_status()

# Mount frontend with full SPA fallback
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="API endpoint not found")

        target = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)

        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend index.html not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
