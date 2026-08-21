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
    DB_PATH
)
from backend.scanner import ScanManager
from backend.thumbnails import get_thumbnail_path, generate_thumbnail
from backend.vector_engine import VectorEngine
from backend.deduplicator import run_deduplication_pass

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

app = FastAPI(
    title="LuminaPhoto API",
    description="Semantic Photo Discovery, Deduplication & EXIF Management System",
    version="1.0.0"
)

@app.on_event("startup")
def on_startup():
    threading.Thread(target=ensure_all_embeddings_in_background, daemon=True).start()

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
    camera_make: Optional[str] = Query(None, description="Filter by camera make"),
    has_gps: Optional[bool] = Query(None, description="Filter by presence of GPS geotag"),
    sort_by: str = Query("date_taken", description="Sort field: date_taken, file_name, file_size, indexed_at"),
    sort_order: str = Query("DESC", description="Sort direction: ASC, DESC"),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """
    Returns paginated photos. If `query` is provided, performs natural language semantic vector search
    with CLIP embeddings and returns ranked matches.
    """
    if query and query.strip():
        # Perform Semantic Vector Search
        vector_engine = VectorEngine.get_instance()
        search_results = vector_engine.search_text(query.strip(), top_k=limit + offset)
        
        if not search_results:
            return {"photos": [], "total": 0, "offset": offset, "limit": limit, "query": query}

        photo_id_to_score = {r["photo_id"]: r["similarity_score"] for r in search_results}
        paged_ids = [r["photo_id"] for r in search_results[offset:offset + limit]]
        
        photos, _ = get_photos(photo_ids=paged_ids)
        # Attach similarity score and preserve ranking order
        photo_dict = {p["id"]: p for p in photos if p is not None}
        ranked_photos = []
        for pid in paged_ids:
            if pid in photo_dict:
                item = photo_dict[pid]
                item["similarity_score"] = photo_id_to_score.get(pid, 0.0)
                ranked_photos.append(item)

        return {
            "photos": ranked_photos,
            "total": len(search_results),
            "offset": offset,
            "limit": limit,
            "query": query
        }

    # Standard database filtering
    class_filter = None if classification == "ALL" else classification
    photos, total = get_photos(
        classification=class_filter,
        include_duplicates=include_duplicates,
        camera_make=camera_make,
        has_gps=has_gps,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )

    return {
        "photos": photos,
        "total": total,
        "offset": offset,
        "limit": limit,
        "query": None
    }

@app.get("/api/photos/{photo_id}")
def get_photo_details(photo_id: int):
    """Returns complete metadata, EXIF tags, GPS coordinates, and duplicate status for a photo."""
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo

@app.get("/api/photos/{photo_id}/thumbnail")
def get_photo_thumbnail(photo_id: int):
    """Serves the cached WebP micro-thumbnail (or generates on the fly)."""
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    thumb_path = get_thumbnail_path(photo_id, "thumb")
    if not os.path.exists(thumb_path):
        if os.path.exists(photo["file_path"]):
            thumb_path = generate_thumbnail(photo["file_path"], photo_id, "thumb")

    if thumb_path and os.path.exists(thumb_path):
        return FileResponse(thumb_path, media_type="image/webp")
    
    # Fallback to original if image
    if os.path.exists(photo["file_path"]):
        return FileResponse(photo["file_path"])

    raise HTTPException(status_code=404, detail="Thumbnail not available")

@app.get("/api/photos/{photo_id}/preview")
def get_photo_preview(photo_id: int):
    """Serves the HD WebP preview image."""
    photo = get_photo_by_id(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    preview_path = get_thumbnail_path(photo_id, "preview")
    if not os.path.exists(preview_path):
        if os.path.exists(photo["file_path"]):
            preview_path = generate_thumbnail(photo["file_path"], photo_id, "preview")

    if preview_path and os.path.exists(preview_path):
        return FileResponse(preview_path, media_type="image/webp")

    if os.path.exists(photo["file_path"]):
        return FileResponse(photo["file_path"])

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

import socket

try:
    import send2trash
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

    # 4. Re-run deduplication to update sibling clusters
    if dup_group_id:
        run_deduplication_pass()

    return {
        "message": f"Successfully deleted '{photo['file_name']}' from disk and catalog",
        "file_path": file_path,
        "sent_to_trash": not permanent and (send2trash is not None)
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
