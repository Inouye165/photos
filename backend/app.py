"""
FastAPI REST API & Web Application Server for LuminaPhoto.
Exposes photo queries, semantic vector search, deduplication inspector, EXIF metadata,
and live folder scanning progress.
"""

import os
import sys
import threading
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    DB_PATH
)
from backend.scanner import ScanManager
from backend.thumbnails import get_thumbnail_path, generate_thumbnail
from backend.vector_engine import VectorEngine
from backend.deduplicator import run_deduplication_pass, cleanup_duplicate_group
from backend.query_parser import QueryParser

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
    yield

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

def get_drive_space_info(target_dir: str = r"C:\Users\inouy\photos", min_free_gb: float = 5.0):
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
    photos_workspace = r"C:\Users\inouy\photos"
    
    suggested = photos_workspace if os.path.exists(photos_workspace) else (pictures_dir if os.path.exists(pictures_dir) else user_home)
    return {
        "suggested_path": suggested,
        "home": user_home,
        "pictures": pictures_dir
    }

@app.get("/api/browse-folders")
def browse_folders(path: Optional[str] = None):
    """Lists subdirectories within a given path for folder & subfolder browsing."""
    target_path = path.strip() if path and path.strip() else r"C:\Users\inouy\photos"
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
    actual_limit = int(limit) if isinstance(limit, (int, float, str)) and str(limit).isdigit() else 60
    actual_offset = int(offset) if isinstance(offset, (int, float, str)) and str(offset).isdigit() else 0
    clean_year = year if isinstance(year, str) and year.strip() else None
    clean_camera = camera_make if isinstance(camera_make, str) and camera_make.strip() else None
    clean_gps = has_gps if isinstance(has_gps, bool) else None
    clean_class = classification if isinstance(classification, str) and classification.strip() else None

    if query and query.strip():
        # 1. Parse natural language intent, entities, dates, and visual prompt
        known_folders = get_known_entity_folders()
        parser = QueryParser(known_folders=known_folders)
        parsed = parser.parse(query.strip())
        
        target_class = clean_class
        if not target_class or target_class == "ALL":
            if parsed.classification != "ALL":
                target_class = parsed.classification

        # 2. Perform Semantic Vector Search with clean visual prompt
        search_prompt = parsed.visual_prompt or query.strip()
        vector_engine = VectorEngine.get_instance()
        
        # Pull enough candidates for candidate filtering and re-ranking
        top_k_candidates = max(250, (actual_limit + actual_offset) * 4)
        search_results = vector_engine.search_text(search_prompt, top_k=top_k_candidates)
        
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

        # 3. Attempt filtering with strict parsed date bounds if present
        date_fallback_applied = False
        photos, _ = get_photos(
            photo_ids=candidate_ids,
            classification=target_class,
            date_from=parsed.date_from,
            date_to=parsed.date_to,
            year=clean_year,
            camera_make=clean_camera,
            has_gps=clean_gps,
            is_trashed=None if include_trashed else False,
            limit=top_k_candidates,
            offset=0
        )

        # 4. If strict date filter yielded 0 results (e.g. no beach trip last month),
        # smoothly fall back to ranking candidates across all dates
        if not photos and (parsed.date_from or parsed.date_to):
            date_fallback_applied = True
            photos, _ = get_photos(
                photo_ids=candidate_ids,
                classification=target_class,
                year=clean_year,
                camera_make=clean_camera,
                has_gps=clean_gps,
                is_trashed=None if include_trashed else False,
                limit=top_k_candidates,
                offset=0
            )

        # 5. Hybrid scoring: apply entity/folder keyword boost
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

    # 2. Clean up cached thumbnails
    for size_type in ("thumb", "preview"):
        t_path = get_thumbnail_path(photo_id, size_type)
        if os.path.exists(t_path):
            try:
                os.remove(t_path)
            except Exception:
                pass

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

        # 3. Remove DB record
        conn.execute("DELETE FROM photos WHERE id = ?", (pid,))

    conn.commit()
    conn.close()

    # Re-run deduplication pass in background thread to avoid blocking HTTP response
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

        # Permanently delete physical file
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                actually_freed_bytes += fsize
                deleted_names.append(item["file_name"])
            except Exception as e:
                print(f"Error purging file {fpath}: {e}")
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

@app.get("/api/duplicates")
def list_duplicates():
    """Retrieves all duplicate clusters with primary and duplicate members."""
    return get_duplicate_groups()

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
    """Marks all items in a duplicate group as unique/dismissed without deleting any files."""
    conn = get_connection()
    conn.execute("UPDATE photos SET duplicate_group_id = NULL, is_primary = 1, duplicate_count = 0 WHERE duplicate_group_id = ?", (group_id,))
    conn.execute("DELETE FROM duplicate_groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return {"message": f"Duplicate group '{group_id}' dismissed. All files kept intact."}

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
    return get_stats()

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
