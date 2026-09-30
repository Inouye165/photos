"""
Intelligent personal document discovery, filtering, copying, and indexing engine.
Excludes Windows OS system files, installed software docs, SDK packages, and temp junk.
Guarantees original files are never altered or moved.
"""

import os
import sys
import shutil
import hashlib
import time
import threading
import string
from typing import List, Dict, Any, Optional, Set
from backend.documents_db import (
    init_documents_db,
    insert_or_update_document,
    get_document_by_sha256,
    get_document_by_original_path,
    add_document_location
)
from backend.documents_extractor import extract_document_text, chunk_document_text
from backend.documents_vector import DocumentVectorEngine

# Default storage destination for copied documents
DEFAULT_DOCUMENTS_LIBRARY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "documents_library")

import re

# Supported personal document extensions
PERSONAL_DOC_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".csv", ".xlsx", ".xls", ".pptx", ".ppt"
}

# Directories to strictly exclude (Windows OS, software installs, app data, dev caches, code repos)
EXCLUDED_DIR_NAMES = {
    # Operating system & hardware
    "windows", "program files", "program files (x86)", "programdata", "recovery",
    "$recycle.bin", "system volume information", "msocache", "perflogs", "intel", "amd", "nvidia",
    "appdata", "localappdata",

    # Package managers & virtual environments
    "node_modules", "bower_components", "venv", ".venv", "env", ".env", "virtualenv",
    "site-packages", "dist-packages", "__pycache__", ".pytest_cache", ".tox",
    ".cargo", ".rustup", ".nuget", ".gradle", ".m2", "gems", "vendor", "packages",

    # Version control & IDEs
    ".git", ".svn", ".hg", ".vscode", ".idea", ".devcontainer", ".github", ".gemini",

    # Software build outputs & libraries
    "target", "bin", "obj", "build", "dist", "out", "cmake", "debug", "release",
    "x64", "x86", "arm64", "deps", "dependencies", "submodules",

    # Code / Repo internals that contain rule/test/changelog assets
    "codeql", "change-notes", "release-notes", "changelog", "changelogs", "migrations",
    "fixtures", "spec", "specs", "mocks", "test", "tests", "rules", "queries", "experimental",

    # App internal library
    "documents_library", ".lumina_cache"
}

# Software project marker files indicating a directory is a code repository or package
REPO_MARKER_FILES = {
    ".git", ".github", ".devcontainer", "package.json", "tsconfig.json",
    "cargo.toml", "go.mod", "pom.xml", "build.gradle", "requirements.txt",
    "pyproject.toml", "setup.py", "qlpack.yml", "codeql-workspace.yml",
    "cmakelists.txt", "makefile", ".code-workspace", "gemfile", "nuget.config"
}

# Software documentation and system junk filenames to exclude
EXCLUDED_FILE_PATTERNS = {
    "license", "licence", "copying", "notice", "readme", "changelog", "changes",
    "authors", "contributing", "install", "installation", "third_party", "third_party_notices",
    "eula", "terms_of_service", "release_notes", "release", "privacy_policy", "manifest",
    "package", "package-lock", "yarn.lock", "requirements", "setup", "pom", "dockerfile",
    "code_of_conduct", "codeowners", "governance", "security", "pull_request_template",
    "issue_template", "authors", "maintainers", "acknowledgements"
}

# Regex to detect software version numbers e.g. "0.4.1", "0.4.10", "v1.2.3", "1.0.0-rc1"
VERSION_FILENAME_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?(-[a-z0-9.]+)?$", re.IGNORECASE)

# Regex to detect security vulnerability IDs, rules, and code patterns
CODE_SECURITY_RULE_RE = re.compile(r"^(cwe-\d+|cve-\d+|argumentinjection|commandinjection|sqlinjection|crosssitescripting|xss|csrf|ssrf|pathinjection|pathtraversal|bufferoverflow|useafterfree|codeql)", re.IGNORECASE)

def compute_file_sha256(file_path: str) -> str:
    """Computes SHA-256 hash in read-only streaming mode."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_allowed_document_roots() -> Dict[str, Dict[str, Any]]:
    """
    Returns the strict allowed base folders for personal documents:
    - Windows Documents
    - Windows Downloads
    - OneDrive Documents
    - OneDrive Downloads (if present in OneDrive)
    """
    home = os.path.expanduser("~")
    roots: Dict[str, Dict[str, Any]] = {}

    # 1. Windows Documents
    win_docs = os.path.normpath(os.path.join(home, "Documents"))
    roots["windows_documents"] = {
        "key": "windows_documents",
        "name": "Windows Documents",
        "path": win_docs,
        "exists": os.path.exists(win_docs) and os.path.isdir(win_docs),
        "source": "Windows"
    }

    # 2. Windows Downloads
    win_downloads = os.path.normpath(os.path.join(home, "Downloads"))
    roots["windows_downloads"] = {
        "key": "windows_downloads",
        "name": "Windows Downloads",
        "path": win_downloads,
        "exists": os.path.exists(win_downloads) and os.path.isdir(win_downloads),
        "source": "Windows"
    }

    # 3. OneDrive roots
    onedrive_candidates: List[str] = []
    for var in ["OneDrive", "OneDriveConsumer", "OneDriveCommercial"]:
        val = os.environ.get(var)
        if val and os.path.isdir(val):
            norm = os.path.normpath(val)
            if norm not in onedrive_candidates:
                onedrive_candidates.append(norm)

    fallback_od = os.path.normpath(os.path.join(home, "OneDrive"))
    if os.path.isdir(fallback_od) and fallback_od not in onedrive_candidates:
        onedrive_candidates.append(fallback_od)

    for idx, od in enumerate(onedrive_candidates):
        suffix = f"_{idx+1}" if len(onedrive_candidates) > 1 else ""
        od_name_suffix = f" ({os.path.basename(od)})" if len(onedrive_candidates) > 1 else ""

        od_docs = os.path.normpath(os.path.join(od, "Documents"))
        roots[f"onedrive_documents{suffix}"] = {
            "key": f"onedrive_documents{suffix}",
            "name": f"OneDrive Documents{od_name_suffix}",
            "path": od_docs,
            "exists": os.path.exists(od_docs) and os.path.isdir(od_docs),
            "source": "OneDrive"
        }

        od_downloads = os.path.normpath(os.path.join(od, "Downloads"))
        roots[f"onedrive_downloads{suffix}"] = {
            "key": f"onedrive_downloads{suffix}",
            "name": f"OneDrive Downloads{od_name_suffix}",
            "path": od_downloads,
            "exists": os.path.exists(od_downloads) and os.path.isdir(od_downloads),
            "source": "OneDrive"
        }

    return roots

def get_allowed_root_paths(only_existing: bool = True) -> List[str]:
    """Returns absolute paths of allowed document directories."""
    roots = get_allowed_document_roots()
    paths = []
    for r in roots.values():
        if not only_existing or r["exists"]:
            paths.append(r["path"])
    return paths

def is_path_in_allowed_document_roots(path: str) -> bool:
    """
    Validates whether a path is strictly located within
    Windows Documents, Windows Downloads, OneDrive Documents, or OneDrive Downloads.
    """
    if not path or not isinstance(path, str):
        return False
    try:
        norm_path = os.path.normpath(os.path.abspath(path)).lower()
    except Exception:
        return False

    allowed_paths = get_allowed_root_paths(only_existing=False)
    for root in allowed_paths:
        norm_root = os.path.normpath(os.path.abspath(root)).lower()
        if norm_path == norm_root or norm_path.startswith(norm_root + os.sep):
            return True
    return False

def get_user_root_dirs() -> Set[str]:
    """Returns the set of allowed personal document roots."""
    return {os.path.normpath(p).lower() for p in get_allowed_root_paths(only_existing=False)}

def is_developer_or_system_directory(dir_path: str) -> bool:
    """
    Checks if a directory is part of a code repository, software build,
    IDE configuration, or developer package.
    """
    dir_norm = os.path.normpath(dir_path).lower()
    user_roots = get_user_root_dirs()
    if dir_norm in user_roots:
        return False

    base = os.path.basename(dir_norm)
    if base in EXCLUDED_DIR_NAMES or base.startswith("."):
        return True

    # Check for common developer starter-kit, SDK, or repo naming patterns
    dev_name_prefixes = ("vscode-", "codeql-", "starter-", "template-", "sdk-")
    dev_name_suffixes = ("-starter", "-template", "-sdk", "-repo", "-submodule")
    if any(base.startswith(p) for p in dev_name_prefixes) or any(base.endswith(s) for s in dev_name_suffixes):
        return True

    # Quick non-recursive peek at entries in this directory for repository manifests
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.name.lower() in REPO_MARKER_FILES:
                    return True
    except (PermissionError, OSError):
        pass

    return False

def is_personal_document(file_path: str, scan_root: Optional[str] = None) -> bool:
    """
    Evaluates whether a file is a personal document rather than
    a system asset, software manual, code repo file, or developer document.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in PERSONAL_DOC_EXTENSIONS:
        return False

    # Strict folder boundary: only allow documents within Windows & OneDrive Documents & Downloads
    if not is_path_in_allowed_document_roots(file_path):
        return False

    base_name = os.path.basename(file_path).lower()
    stem = os.path.splitext(base_name)[0]

    # Exclude common software docs (e.g. LICENSE.txt, README.md, CODE_OF_CONDUCT.md)
    for pattern in EXCLUDED_FILE_PATTERNS:
        if pattern == stem or pattern in stem.split("_") or pattern in stem.split("-"):
            return False

    # Exclude version-numbered files e.g. 0.4.0.md, 0.4.1.md
    if VERSION_FILENAME_RE.match(stem):
        return False

    # Exclude vulnerability/rule documentation e.g. ArgumentInjectionMedium.md, CWE-088.md
    if CODE_SECURITY_RULE_RE.match(stem):
        return False

    # Check path components for excluded directory names
    norm_path = os.path.normpath(file_path).lower()
    if scan_root:
        try:
            rel = os.path.relpath(file_path, scan_root).lower()
            parts = rel.split(os.sep)
        except ValueError:
            parts = norm_path.split(os.sep)
    else:
        parts = norm_path.split(os.sep)

    for part in parts[:-1]:
        if part in EXCLUDED_DIR_NAMES:
            return False
        if any(part.startswith(p) for p in ("vscode-", "codeql-", "starter-", "sdk-")):
            return False
        if any(part.endswith(s) for s in ("-starter", "-template", "-sdk", "-repo")):
            return False

    # Walk up parent directories (up to 5 levels) to detect if inside a code repository
    user_roots = get_user_root_dirs()
    parent = os.path.dirname(file_path)
    levels = 0
    stop_at = os.path.normpath(scan_root).lower() if scan_root else None

    while parent and levels < 5:
        parent_norm = os.path.normpath(parent).lower()
        if stop_at and parent_norm == stop_at:
            break
        if parent_norm in user_roots:
            break

        # If this parent directory is a developer repo or contains repo markers
        try:
            with os.scandir(parent) as it:
                for entry in it:
                    if entry.name.lower() in REPO_MARKER_FILES:
                        return False
        except (PermissionError, OSError):
            pass

        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            break
        parent = next_parent
        levels += 1

    if os.path.exists(file_path):
        try:
            size = os.path.getsize(file_path)
            # Skip 0-byte files or massive dump files (> 120MB)
            if size == 0 or size > 120 * 1024 * 1024:
                return False
        except Exception:
            return False

    return True

def get_default_scan_roots() -> List[str]:
    """
    Finds primary personal document folders on Windows strictly within allowed roots:
    Windows Documents, Windows Downloads, OneDrive Documents, OneDrive Downloads.
    """
    return get_allowed_root_paths(only_existing=True)

class DocumentsScanManager:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.is_scanning = False
        self.stop_requested = False
        self.status: Dict[str, Any] = {
            "is_scanning": False,
            "scanned_dirs": 0,
            "found_docs": 0,
            "copied_docs": 0,
            "duplicate_docs": 0,
            "indexed_docs": 0,
            "current_file": "",
            "start_time": 0.0,
            "elapsed_seconds": 0.0,
            "errors": []
        }
        self.library_dir = DEFAULT_DOCUMENTS_LIBRARY
        os.makedirs(self.library_dir, exist_ok=True)
        init_documents_db()

    @classmethod
    def get_instance(cls) -> "DocumentsScanManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DocumentsScanManager()
            return cls._instance

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            st = dict(self.status)
            start_time = float(st.get("start_time") or 0.0)
            if self.is_scanning and start_time > 0:
                st["elapsed_seconds"] = round(time.time() - start_time, 1)
            return st

    def stop_scan(self):
        with self._lock:
            self.stop_requested = True

    def start_scan(
        self,
        custom_roots: Optional[List[str]] = None,
        target_library: Optional[str] = None,
        recursive: bool = True
    ) -> bool:
        # Validate that roots are strictly within allowed document roots
        raw_roots = custom_roots or get_default_scan_roots()
        scan_roots = []
        for r in raw_roots:
            if r and is_path_in_allowed_document_roots(r):
                scan_roots.append(os.path.normpath(os.path.abspath(r)))

        if not scan_roots:
            raise ValueError(
                "Invalid scan folder: Only folders within Documents and Downloads (in Windows or OneDrive) can be scanned."
            )

        with self._lock:
            if self.is_scanning:
                return False
            self.is_scanning = True
            self.stop_requested = False
            self.status = {
                "is_scanning": True,
                "scanned_dirs": 0,
                "found_docs": 0,
                "copied_docs": 0,
                "duplicate_docs": 0,
                "indexed_docs": 0,
                "recursive": recursive,
                "current_file": "Initializing personal documents scan...",
                "start_time": time.time(),
                "elapsed_seconds": 0,
                "errors": []
            }
            if target_library:
                self.library_dir = target_library
            os.makedirs(self.library_dir, exist_ok=True)

        threading.Thread(target=self._run_scan_thread, args=(scan_roots, recursive), daemon=True).start()
        return True

    def _run_scan_thread(self, scan_roots: List[str], recursive: bool = True):
        try:
            mode_desc = "recursive" if recursive else "single folder (no subfolders)"
            print(f"[DocumentsScanner] Starting scan across {len(scan_roots)} roots [{mode_desc}]: {scan_roots}")
            vector_engine = DocumentVectorEngine.get_instance()

            for root_dir in scan_roots:
                if self.stop_requested:
                    break
                if not os.path.exists(root_dir):
                    continue

                for root, dirs, files in os.walk(root_dir, topdown=True):
                    if self.stop_requested:
                        break

                    # If not recursive, do not descend into any subdirectories
                    if not recursive:
                        dirs.clear()
                    else:
                        # Prune excluded OS, software, and developer repository directories immediately
                        dirs[:] = [
                            d for d in dirs
                            if not is_developer_or_system_directory(os.path.join(root, d))
                        ]

                    with self._lock:
                        self.status["scanned_dirs"] += 1
                        self.status["current_file"] = root

                    for file in files:
                        if self.stop_requested:
                            break

                        full_path = os.path.join(root, file)
                        if not is_personal_document(full_path, scan_root=root_dir):
                            continue

                        self._process_single_document(full_path, vector_engine)

            print("[DocumentsScanner] Scan completed successfully.")
        except Exception as e:
            print(f"[DocumentsScanner] Unexpected scan error: {e}")
            with self._lock:
                self.status["errors"].append(str(e))
        finally:
            with self._lock:
                self.is_scanning = False
                self.status["is_scanning"] = False
                self.status["current_file"] = "Scan finished"

    def _process_single_document(self, original_path: str, vector_engine: DocumentVectorEngine):
        """Processes, copies, and indexes a single personal document safely."""
        try:
            with self._lock:
                self.status["found_docs"] += 1
                self.status["current_file"] = original_path

            # 1. Compute SHA-256 in read-only mode
            sha256 = compute_file_sha256(original_path)

            file_name = os.path.basename(original_path)
            stat = os.stat(original_path)
            created_at = getattr(stat, "st_birthtime", stat.st_mtime)
            modified_at = stat.st_mtime
            file_size = stat.st_size

            # 2. Check if already cataloged
            existing = get_document_by_sha256(sha256)
            if existing:
                # Content already indexed! Register this location as a duplicate copy
                existing_locations = [loc["original_path"] for loc in existing.get("locations", [])]
                if original_path not in existing_locations:
                    add_document_location(
                        document_id=existing["id"],
                        original_path=original_path,
                        file_name=file_name,
                        file_size=file_size,
                        modified_at=modified_at
                    )
                    with self._lock:
                        self.status["duplicate_docs"] = self.status.get("duplicate_docs", 0) + 1
                    print(f"[DocumentsScanner] Recorded duplicate copy of doc #{existing['id']} at {original_path}")
                return

            # 3. Determine safe destination in documents_library
            stem, ext = os.path.splitext(file_name)
            safe_filename = f"{stem}_{sha256[:8]}{ext}"
            copied_path = os.path.join(self.library_dir, safe_filename)

            # 4. Safe copy (never modifies original)
            if not os.path.exists(copied_path):
                shutil.copy2(original_path, copied_path)

            stat_copy = os.stat(copied_path)
            created_at = getattr(stat_copy, "st_birthtime", stat_copy.st_mtime)
            modified_at = stat_copy.st_mtime
            file_size = stat_copy.st_size

            with self._lock:
                self.status["copied_docs"] += 1

            # 5. Extract text from the copied file
            extracted = extract_document_text(copied_path)
            text = extracted.get("text", "")
            title = extracted.get("title", stem)
            summary = extracted.get("summary", "")
            page_count = extracted.get("page_count", 1)
            word_count = extracted.get("word_count", 0)

            # 6. Insert into documents.db
            doc_id = insert_or_update_document(
                original_path=original_path,
                copied_path=copied_path,
                file_name=file_name,
                file_size=file_size,
                file_extension=ext.lower(),
                sha256=sha256,
                created_at=created_at,
                modified_at=modified_at,
                title=title,
                extracted_text=text,
                summary=summary,
                page_count=page_count,
                word_count=word_count,
                has_embedding=0
            )

            # 7. Semantic chunking & embedding
            if text and doc_id:
                chunks = chunk_document_text(text, chunk_size_words=250, overlap_words=50)
                if chunks:
                    vector_engine.index_document(doc_id, chunks)

            with self._lock:
                self.status["indexed_docs"] += 1

        except Exception as e:
            print(f"[DocumentsScanner] Error processing {original_path}: {e}")
            with self._lock:
                self.status["errors"].append(f"{os.path.basename(original_path)}: {str(e)}")
