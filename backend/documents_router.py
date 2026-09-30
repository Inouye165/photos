"""
FastAPI APIRouter for LuminaDocuments.
Endpoints for document retrieval, semantic search, computer scanning, and file streaming.
Completely decoupled from photo endpoints.
"""

import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.documents_db import (
    get_documents,
    get_document_by_id,
    get_document_stats,
    delete_document,
    clear_all_documents,
    get_watched_folders,
    add_watched_folder,
    remove_watched_folder,
    trash_document,
    restore_document,
    permanently_delete_document,
    empty_documents_trash,
    DEFAULT_DOCUMENTS_TRASH,
    list_interest_lists,
    save_interest_list,
    delete_interest_list,
    update_document_review
)
from backend.document_ai import analyze_document
from backend.documents_scanner import (
    DocumentsScanManager,
    get_default_scan_roots,
    get_allowed_document_roots,
    is_path_in_allowed_document_roots,
    DEFAULT_DOCUMENTS_LIBRARY
)
from backend.documents_vector import DocumentVectorEngine
from backend.documents_watcher import DocumentWatcherManager

router = APIRouter(prefix="/api/documents", tags=["documents"])

class ScanRequest(BaseModel):
    folder_path: Optional[str] = None
    custom_roots: Optional[List[str]] = None
    target_library: Optional[str] = None
    recursive: bool = True

class PickFolderRequest(BaseModel):
    initial_dir: Optional[str] = None

class WatchedFolderRequest(BaseModel):
    folder_path: str

class InterestListRequest(BaseModel):
    name: str
    description: str

class ReviewRequest(BaseModel):
    status: str
    note: Optional[str] = None

class AnalyzeRequest(BaseModel):
    model: Optional[str] = None

def pick_folder_explorer(initial_dir: Optional[str] = None) -> Optional[str]:
    """
    Opens native Windows Explorer folder selection dialog.
    Runs via isolated PowerShell process to ensure native Windows Explorer appearance.
    """
    import subprocess
    import sys

    # Try PowerShell first for modern Windows Explorer folder picker
    init_path = initial_dir.replace("'", "''") if initial_dir and os.path.exists(initial_dir) else ""
    initial_code = f"$f.SelectedPath = '{init_path}'" if init_path else ""
    ps_cmd = f"""
    Add-Type -AssemblyName System.Windows.Forms
    $f = New-Object System.Windows.Forms.FolderBrowserDialog
    $f.Description = 'Select a folder to scan for personal documents'
    $f.AutoUpgradeEnabled = $true
    $f.ShowNewFolderButton = $false
    {initial_code}
    $res = $f.ShowDialog()
    if ($res -eq [System.Windows.Forms.DialogResult]::OK) {{
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        Write-Output $f.SelectedPath
    }}
    """
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180
        )
        selected = proc.stdout.strip()
        if selected and os.path.exists(selected):
            return selected
    except Exception as e:
        print(f"[DocumentsPicker] PowerShell dialog error: {e}")

    # Fallback to Tkinter subprocess
    try:
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
path = filedialog.askdirectory(initialdir={repr(initial_dir or '')}, title='Select a folder to scan for personal documents')
root.destroy()
if path:
    print(path)
"""
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180
        )
        selected = proc.stdout.strip()
        if selected and os.path.exists(selected):
            return selected
    except Exception as e:
        print(f"[DocumentsPicker] Tkinter fallback error: {e}")

    return None

@router.post("/pick-folder")
def pick_folder_endpoint(req: PickFolderRequest = Body(default=PickFolderRequest())):
    """Opens a native Windows Explorer folder selection dialog."""
    folder = pick_folder_explorer(req.initial_dir)
    return {"folder_path": folder, "selected": bool(folder)}

@router.get("")
def list_documents(
    search: Optional[str] = Query(None, description="Keyword search filter"),
    file_extension: Optional[str] = Query(None, description="Filter by extension e.g. .pdf"),
    is_trashed: bool = Query(False, description="Filter trashed documents"),
    sort_by: str = Query("modified_at", description="Field to sort by"),
    sort_order: str = Query("DESC", description="Sort order ASC or DESC"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Retrieves paginated list of cataloged personal documents."""
    docs, total = get_documents(
        search=search,
        file_extension=file_extension,
        is_trashed=is_trashed,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset
    )
    return {"documents": docs, "total": total, "limit": limit, "offset": offset, "is_trashed": is_trashed}

@router.get("/search")
def search_documents_semantically(
    q: str = Query(..., description="Natural language semantic search query"),
    top_k: int = Query(30, ge=1, le=100)
):
    """
    Performs high-dimensional semantic search across all indexed document texts and chunks.
    Matches concepts, topics, and questions to relevant documents.
    """
    if not q.strip():
        return {"results": [], "total": 0, "query": q}
        
    engine = DocumentVectorEngine.get_instance()
    results = engine.search(q, top_k=top_k)
    return {"results": results, "total": len(results), "query": q}

@router.get("/stats")
def document_stats():
    """Returns library statistics: count, total bytes, word counts, and type distributions."""
    return get_document_stats()

@router.get("/interest-lists")
def get_interest_lists():
    """Returns the user's active document categories."""
    return {"interest_lists": list_interest_lists()}

@router.post("/interest-lists")
def create_interest_list(req: InterestListRequest):
    """Creates or updates a local document category."""
    if not req.name.strip() or not req.description.strip():
        raise HTTPException(status_code=400, detail="Name and description are required")
    return save_interest_list(req.name, req.description)

@router.delete("/interest-lists/{list_id}")
def remove_interest_list(list_id: int):
    """Disables a document category without changing documents."""
    return {"success": delete_interest_list(list_id)}

@router.get("/allowed-roots")
def get_allowed_roots():
    """Returns the strict allowed base folders for documents (Windows and OneDrive Documents and Downloads)."""
    roots_dict = get_allowed_document_roots()
    return {"roots": list(roots_dict.values())}

@router.get("/watched-folders")
def list_watched_folders():
    """Returns user-configured watched folders for personal documents."""
    folders = get_watched_folders()
    watcher_status = DocumentWatcherManager.get_instance().get_status()
    allowed_roots = list(get_allowed_document_roots().values())
    return {
        "watched_folders": folders,
        "watcher_status": watcher_status,
        "allowed_roots": allowed_roots
    }

@router.post("/watched-folders")
def add_watched_folder_endpoint(req: WatchedFolderRequest):
    """Adds a new folder to watch for documents. Must be strictly within Documents or Downloads (Windows or OneDrive)."""
    raw_path = req.folder_path.strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Folder path cannot be empty.")

    norm_path = os.path.normpath(os.path.abspath(raw_path))
    if not os.path.exists(norm_path) or not os.path.isdir(norm_path):
        raise HTTPException(status_code=400, detail=f"Directory does not exist on disk: {norm_path}")

    if not is_path_in_allowed_document_roots(norm_path):
        raise HTTPException(
            status_code=400,
            detail="Forbidden: Only folders within Documents and Downloads (in Windows or OneDrive) can be watched."
        )

    try:
        DocumentWatcherManager.get_instance().add_watch_path(norm_path, trigger_initial_scan=True)
        folders = get_watched_folders()
        added_item = next((f for f in folders if f["folder_path"].lower() == norm_path.lower()), None)
        return {
            "success": True,
            "message": f"Now watching folder and indexing existing files in background: {norm_path}",
            "folder": added_item,
            "initial_sync_started": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/watched-folders/sync")
def sync_all_watched_folders_endpoint():
    """Triggers an immediate background sync/scan across all active watched folders."""
    count = DocumentWatcherManager.get_instance().sync_all_watched_folders()
    return {
        "success": True,
        "message": f"Sync started for {count} watched folder(s)",
        "folders_count": count
    }

@router.post("/watched-folders/{folder_id}/sync")
def sync_single_watched_folder_endpoint(folder_id: int):
    """Triggers an immediate background sync/scan for a specific watched folder."""
    folders = get_watched_folders()
    target = next((f for f in folders if f["id"] == folder_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Watched folder not found.")

    started = DocumentWatcherManager.get_instance().sync_folder(target["folder_path"])
    return {
        "success": True,
        "started": started,
        "message": f"Background sync initiated for: {target['folder_path']}" if started else "Scan is already running."
    }

@router.delete("/watched-folders/{folder_id}")
def delete_watched_folder_endpoint(folder_id: int):
    """Removes a folder from document watching."""
    success = DocumentWatcherManager.get_instance().remove_watch_path(folder_id)
    return {"success": success, "message": "Folder removed from document watcher"}

@router.get("/scan/default-roots")
def get_scan_roots():
    """Returns the default personal folders detected on this Windows PC strictly within allowed roots."""
    roots = get_default_scan_roots()
    return {
        "roots": roots,
        "allowed_roots": list(get_allowed_document_roots().values()),
        "default_library": DEFAULT_DOCUMENTS_LIBRARY
    }

@router.post("/scan")
def start_scan(req: ScanRequest = Body(default=ScanRequest())):
    """Triggers background personal documents discovery and safe copying."""
    manager = DocumentsScanManager.get_instance()
    roots = None
    if req.folder_path and req.folder_path.strip():
        roots = [req.folder_path.strip()]
    elif req.custom_roots:
        roots = [r.strip() for r in req.custom_roots if r.strip()]

    try:
        started = manager.start_scan(
            custom_roots=roots,
            target_library=req.target_library,
            recursive=req.recursive
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not started:
        return {"message": "Scan is already running", "is_scanning": True}
    return {
        "message": "Personal documents scan started",
        "is_scanning": True,
        "recursive": req.recursive,
        "roots": roots
    }

@router.post("/scan/stop")
def stop_scan():
    """Requests running scan to cancel."""
    manager = DocumentsScanManager.get_instance()
    manager.stop_scan()
    return {"message": "Stop scan requested"}

@router.get("/scan/status")
def scan_status():
    """Returns real-time status of document scanning and indexing."""
    manager = DocumentsScanManager.get_instance()
    return manager.get_status()

@router.get("/{doc_id}")
def get_document(doc_id: int):
    """Returns complete metadata and extracted text for a document."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@router.post("/{doc_id}/analyze")
def analyze_document_endpoint(doc_id: int, req: AnalyzeRequest = Body(default=AnalyzeRequest())):
    """Runs local Ollama analysis and stores evidence-backed results."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        return analyze_document(doc, list_interest_lists(), req.model or "qwen3:8b")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

@router.post("/{doc_id}/review")
def review_document_endpoint(doc_id: int, req: ReviewRequest):
    """Records keep, review, or remove without deleting or moving a file."""
    if req.status not in {"unreviewed", "keep", "review", "remove"}:
        raise HTTPException(status_code=400, detail="Invalid review status")
    if not update_document_review(doc_id, req.status, req.note):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "status": req.status}

@router.get("/{doc_id}/file")
def get_document_file(doc_id: int):
    """Serves the copied document file for preview or download."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = doc["copied_path"]
    if not os.path.exists(file_path):
        # Fallback to original path if copy was removed
        if os.path.exists(doc["original_path"]):
            file_path = doc["original_path"]
        else:
            raise HTTPException(status_code=404, detail="Document file not found on disk")

    media_type_map = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
        ".rtf": "application/rtf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    ext = os.path.splitext(file_path)[1].lower()
    media_type = media_type_map.get(ext, "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        content_disposition_type="inline",
        filename=doc["file_name"]
    )

@router.post("/{doc_id}/open-system")
def open_in_system_app(doc_id: int):
    """Opens the document file in Windows default application (Word, Acrobat, Excel, etc.)."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_path = doc["copied_path"]
    if not os.path.exists(file_path):
        file_path = doc["original_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    try:
        os.startfile(file_path)
        return {"success": True, "message": "Opened in system application"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RevealPathRequest(BaseModel):
    path: str

@router.post("/reveal-path")
def reveal_path_endpoint(req: RevealPathRequest):
    """Opens Windows Explorer highlighting a path or opening its directory."""
    raw = req.path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Path cannot be empty")
    norm = os.path.normpath(raw)
    import subprocess
    if os.path.isfile(norm):
        subprocess.Popen(f'explorer /select,"{norm}"')
        return {"success": True, "mode": "file_select", "path": norm}
    elif os.path.isdir(norm):
        subprocess.Popen(f'explorer "{norm}"')
        return {"success": True, "mode": "folder_open", "path": norm}
    elif os.path.exists(os.path.dirname(norm)):
        parent = os.path.dirname(norm)
        subprocess.Popen(f'explorer "{parent}"')
        return {"success": True, "mode": "parent_open", "path": parent}
    raise HTTPException(status_code=404, detail=f"Path not found on disk: {norm}")

@router.post("/{doc_id}/reveal")
def reveal_in_explorer(doc_id: int):
    """Opens Windows Explorer with this document highlighted, or opens its containing folder."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    import subprocess
    orig_path = doc.get("original_path")
    if orig_path and os.path.exists(orig_path):
        norm = os.path.normpath(orig_path)
        subprocess.Popen(f'explorer /select,"{norm}"')
        return {"success": True, "mode": "file_select", "path": norm}

    copy_path = doc.get("copied_path")
    if copy_path and os.path.exists(copy_path):
        norm = os.path.normpath(copy_path)
        subprocess.Popen(f'explorer /select,"{norm}"')
        return {"success": True, "mode": "file_select", "path": norm}

    if orig_path:
        parent_dir = os.path.dirname(orig_path)
        if os.path.exists(parent_dir):
            norm = os.path.normpath(parent_dir)
            subprocess.Popen(f'explorer "{norm}"')
            return {"success": True, "mode": "folder_open", "path": norm}

    if copy_path:
        parent_dir = os.path.dirname(copy_path)
        if os.path.exists(parent_dir):
            norm = os.path.normpath(parent_dir)
            subprocess.Popen(f'explorer "{norm}"')
            return {"success": True, "mode": "folder_open", "path": norm}

    raise HTTPException(status_code=404, detail="Neither document file nor containing folder was found on disk")

@router.post("/{doc_id}/open-folder")
def open_document_folder(doc_id: int):
    """Explicitly opens the folder containing this document in Windows Explorer."""
    return reveal_in_explorer(doc_id)

@router.post("/{doc_id}/trash")
def trash_document_endpoint(doc_id: int):
    """
    Moves document copy to the workspace documents_trash holding folder and marks as trashed.
    Original file on PC remains 100% untouched.
    """
    success = trash_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "message": "Document moved to trash holding folder"}

@router.post("/{doc_id}/restore")
def restore_document_endpoint(doc_id: int):
    """
    Restores a trashed document copy back from documents_trash into active documents_library.
    """
    success = restore_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "message": "Document restored to active library"}

@router.delete("/{doc_id}/permanent")
def permanently_delete_document_endpoint(doc_id: int):
    """
    Permanently deletes a document from documents_trash and removes database record.
    """
    success = permanently_delete_document(doc_id)
    return {"success": success, "message": "Document permanently removed"}

@router.post("/trash/empty")
def empty_trash_endpoint():
    """
    Permanently deletes all documents in documents_trash and purges database records.
    """
    count = empty_documents_trash()
    return {"success": True, "purged_count": count, "message": f"Purged {count} document(s) from trash"}

@router.post("/trash/open-folder")
def open_trash_folder_endpoint():
    """
    Opens the workspace documents_trash holding folder in native Windows Explorer.
    """
    import subprocess
    os.makedirs(DEFAULT_DOCUMENTS_TRASH, exist_ok=True)
    norm_path = os.path.normpath(DEFAULT_DOCUMENTS_TRASH)
    subprocess.Popen(f'explorer "{norm_path}"')
    return {"success": True, "path": norm_path}

@router.delete("/{doc_id}")
def remove_document(doc_id: int):
    """
    Moves the document to documents_trash holding folder (or permanently deletes if already in trash).
    Does NOT modify or delete the original file on the user's computer.
    """
    doc = get_document_by_id(doc_id)
    if doc and doc.get("is_trashed"):
        success = permanently_delete_document(doc_id)
        return {"message": "Document permanently deleted", "success": success}
    else:
        success = trash_document(doc_id)
        return {"message": "Document moved to trash holding folder", "success": success}

@router.post("/clear-catalog")
def clear_documents_catalog():
    """
    Clears all cataloged documents and removes library copies.
    Original computer files are completely safe and untouched.
    """
    clear_all_documents(purge_copies=True)
    DocumentVectorEngine.get_instance().reset_index()
    return {"message": "Document catalog cleared successfully", "success": True}
