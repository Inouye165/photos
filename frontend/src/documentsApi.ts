/**
 * API client for LuminaDocuments backend services in TypeScript.
 * Completely isolated from photos API client.
 */

import {
  AllowedRootsResponse,
  WatchedFoldersResponse,
  AddWatchedFolderResponse,
  DocumentRecord,
  DocumentStats,
  ScanStatus,
  DocumentAnalysis,
  DocumentReviewStatus,
  InterestList
} from './types/documents';

const API_BASE = '/api/documents';

export interface FetchDocumentsParams {
  search?: string;
  fileExtension?: string | null;
  isTrashed?: boolean;
  sortBy?: string;
  sortOrder?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal | null;
}

export interface FetchDocumentsResponse {
  documents: DocumentRecord[];
  total: number;
  limit: number;
  offset: number;
}

export async function fetchDocuments({
  search = '',
  fileExtension = null,
  isTrashed = false,
  sortBy = 'modified_at',
  sortOrder = 'DESC',
  limit = 50,
  offset = 0,
  signal = null
}: FetchDocumentsParams = {}): Promise<FetchDocumentsResponse> {
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (fileExtension) params.append('file_extension', fileExtension);
  if (isTrashed) params.append('is_trashed', 'true');
  params.append('sort_by', sortBy);
  params.append('sort_order', sortOrder);
  params.append('limit', String(limit));
  params.append('offset', String(offset));

  const res = await fetch(`${API_BASE}?${params.toString()}`, { signal });
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

export async function searchDocumentsSemantically({
  q = '',
  topK = 30,
  signal = null
}: {
  q?: string;
  topK?: number;
  signal?: AbortSignal | null;
} = {}): Promise<{ results: DocumentRecord[]; total: number; query: string }> {
  const params = new URLSearchParams();
  params.append('q', q);
  params.append('top_k', String(topK));

  const res = await fetch(`${API_BASE}/search?${params.toString()}`, { signal });
  if (!res.ok) throw new Error('Failed to perform semantic document search');
  return res.json();
}

export async function fetchDocumentStats(): Promise<DocumentStats> {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to fetch document stats');
  return res.json();
}

export async function fetchScanRoots(): Promise<{ roots: string[]; default_library: string }> {
  const res = await fetch(`${API_BASE}/scan/default-roots`);
  if (!res.ok) throw new Error('Failed to fetch default scan roots');
  return res.json();
}

export async function fetchAllowedRoots(): Promise<AllowedRootsResponse> {
  const res = await fetch(`${API_BASE}/allowed-roots`);
  if (!res.ok) throw new Error('Failed to fetch allowed document roots');
  return res.json();
}

export async function fetchWatchedFolders(): Promise<WatchedFoldersResponse> {
  const res = await fetch(`${API_BASE}/watched-folders`);
  if (!res.ok) throw new Error('Failed to fetch watched document folders');
  return res.json();
}

export async function addWatchedFolder(folderPath: string): Promise<AddWatchedFolderResponse> {
  const res = await fetch(`${API_BASE}/watched-folders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_path: folderPath })
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to add watched folder');
  }
  return res.json();
}

export async function removeWatchedFolder(folderId: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/watched-folders/${folderId}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to remove watched folder');
  }
  return res.json();
}

export async function syncWatchedFolder(folderId: number): Promise<{ success: boolean; started: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/watched-folders/${folderId}/sync`, {
    method: 'POST'
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to sync watched folder');
  }
  return res.json();
}

export async function syncAllWatchedFolders(): Promise<{ success: boolean; message: string; folders_count: number }> {
  const res = await fetch(`${API_BASE}/watched-folders/sync`, {
    method: 'POST'
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to sync all watched folders');
  }
  return res.json();
}

export interface StartScanParams {
  folderPath?: string | null;
  customRoots?: string[] | null;
  targetLibrary?: string | null;
  recursive?: boolean;
}

export async function startDocumentsScan({
  folderPath = null,
  customRoots = null,
  targetLibrary = null,
  recursive = true
}: StartScanParams = {}): Promise<{ message: string; is_scanning: boolean; recursive: boolean; roots: string[] | null }> {
  const res = await fetch(`${API_BASE}/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_path: folderPath,
      custom_roots: customRoots,
      target_library: targetLibrary,
      recursive
    })
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to start document scan');
  }
  return res.json();
}

export async function stopDocumentsScan(): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/scan/stop`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to stop document scan');
  return res.json();
}

export async function fetchScanStatus(): Promise<ScanStatus> {
  const res = await fetch(`${API_BASE}/scan/status`);
  if (!res.ok) throw new Error('Failed to fetch scan status');
  return res.json();
}

export async function fetchDocumentDetails(docId: number): Promise<DocumentRecord> {
  const res = await fetch(`${API_BASE}/${docId}`);
  if (!res.ok) throw new Error('Failed to fetch document details');
  return res.json();
}

export async function analyzeDocument(docId: number, model = 'qwen3:8b'): Promise<DocumentAnalysis> {
  const res = await fetch(`${API_BASE}/${docId}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model })
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Local AI analysis failed');
  }
  return res.json();
}

export async function updateDocumentReview(docId: number, status: DocumentReviewStatus, note?: string): Promise<{ success: boolean; status: DocumentReviewStatus }> {
  const res = await fetch(`${API_BASE}/${docId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, note })
  });
  if (!res.ok) throw new Error('Failed to update document review status');
  return res.json();
}

export async function fetchInterestLists(): Promise<{ interest_lists: InterestList[] }> {
  const res = await fetch(`${API_BASE}/interest-lists`);
  if (!res.ok) throw new Error('Failed to fetch interest lists');
  return res.json();
}

export async function saveInterestList(name: string, description: string): Promise<InterestList> {
  const res = await fetch(`${API_BASE}/interest-lists`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description })
  });
  if (!res.ok) throw new Error('Failed to save interest list');
  return res.json();
}

export async function deleteDocumentRecord(docId: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/${docId}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error('Failed to delete document');
  return res.json();
}

export function getDocumentFileUrl(docId: number): string {
  return `${API_BASE}/${docId}/file`;
}

export async function pickFolderWithExplorer(
  initialDir: string | null = null
): Promise<{ folder_path: string | null; selected: boolean }> {
  const res = await fetch(`${API_BASE}/pick-folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initial_dir: initialDir })
  });
  if (!res.ok) throw new Error('Failed to open Explorer folder picker');
  return res.json();
}

export async function openDocumentInSystemApp(docId: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/${docId}/open-system`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to open document in system application');
  return res.json();
}

export async function revealDocumentInExplorer(docId: number): Promise<{ success: boolean; mode?: string; path?: string }> {
  const res = await fetch(`${API_BASE}/${docId}/reveal`, {
    method: 'POST'
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to reveal document in Explorer');
  }
  return res.json();
}

export async function openDocumentFolder(docId: number): Promise<{ success: boolean; mode?: string; path?: string }> {
  const res = await fetch(`${API_BASE}/${docId}/open-folder`, {
    method: 'POST'
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to open document folder');
  }
  return res.json();
}

export async function revealPathInExplorer(path: string): Promise<{ success: boolean; mode?: string; path?: string }> {
  const res = await fetch(`${API_BASE}/reveal-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to reveal path in Explorer');
  }
  return res.json();
}

export async function clearDocumentsCatalog(): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/clear-catalog`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to clear documents catalog');
  return res.json();
}

export async function trashDocument(docId: number): Promise<{ success: boolean; message: string; trashed_path?: string }> {
  const res = await fetch(`${API_BASE}/${docId}/trash`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to move document to trash');
  return res.json();
}

export async function restoreDocument(docId: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/${docId}/restore`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to restore document');
  return res.json();
}

export async function permanentlyDeleteDocument(docId: number): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/${docId}/permanent`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error('Failed to permanently delete document');
  return res.json();
}

export async function emptyDocumentsTrash(): Promise<{ success: boolean; purged_count: number; message: string }> {
  const res = await fetch(`${API_BASE}/trash/empty`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to empty documents trash');
  return res.json();
}

export async function openDocumentsTrashFolder(): Promise<{ success: boolean; path: string }> {
  const res = await fetch(`${API_BASE}/trash/open-folder`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to open trash holding folder');
  return res.json();
}
