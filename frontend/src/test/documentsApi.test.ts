import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchAllowedRoots,
  fetchWatchedFolders,
  addWatchedFolder,
  removeWatchedFolder,
  syncWatchedFolder,
  syncAllWatchedFolders,
  trashDocument,
  restoreDocument,
  permanentlyDeleteDocument,
  emptyDocumentsTrash,
  openDocumentsTrashFolder,
  fetchDocuments
} from '../documentsApi';

describe('documentsApi - TypeScript API Client Regression Tests', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('trashDocument sends POST to /api/documents/:id/trash', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, message: 'Document moved to trash', trashed_path: 'C:\\trash\\doc.pdf' })
    });

    const res = await trashDocument(42);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/42/trash',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.success).toBe(true);
    expect(res.trashed_path).toBe('C:\\trash\\doc.pdf');
  });

  it('restoreDocument sends POST to /api/documents/:id/restore', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, message: 'Document restored', restored_path: 'C:\\lib\\doc.pdf' })
    });

    const res = await restoreDocument(42);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/42/restore',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.success).toBe(true);
  });

  it('permanentlyDeleteDocument sends DELETE to /api/documents/:id/permanent', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, message: 'Document permanently deleted' })
    });

    const res = await permanentlyDeleteDocument(42);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/42/permanent',
      expect.objectContaining({ method: 'DELETE' })
    );
    expect(res.success).toBe(true);
  });

  it('emptyDocumentsTrash sends POST to /api/documents/trash/empty', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, purged_count: 5, message: 'Emptied documents trash' })
    });

    const res = await emptyDocumentsTrash();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/trash/empty',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.purged_count).toBe(5);
  });

  it('openDocumentsTrashFolder sends POST to /api/documents/trash/open-folder', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, path: 'C:\\workspace\\documents_trash' })
    });

    const res = await openDocumentsTrashFolder();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/trash/open-folder',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.success).toBe(true);
    expect(res.path).toBe('C:\\workspace\\documents_trash');
  });

  it('fetchDocuments passes is_trashed parameter correctly', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ documents: [], total: 0 })
    });

    await fetchDocuments({ isTrashed: true });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('is_trashed=true'),
      expect.anything()
    );
  });

  it('fetchAllowedRoots calls /api/documents/allowed-roots', async () => {
    const mockData = {
      roots: [
        { key: 'windows_documents', name: 'Windows Documents', path: 'C:\\Users\\inouy\\Documents', exists: true, source: 'Windows' }
      ]
    };

    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockData
    });

    const res = await fetchAllowedRoots();
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/documents/allowed-roots');
    expect(res.roots).toHaveLength(1);
    expect(res.roots[0].name).toBe('Windows Documents');
  });

  it('fetchWatchedFolders calls /api/documents/watched-folders', async () => {
    const mockData = {
      watched_folders: [
        { id: 1, folder_path: 'C:\\Users\\inouy\\Documents', added_at: 1700000000, is_active: true, exists: true }
      ],
      watcher_status: {
        is_running: true,
        watched_paths: ['C:\\Users\\inouy\\Documents'],
        processed_count: 0,
        pending_queue_count: 0,
        last_event_time: null,
        last_processed_file: ''
      },
      allowed_roots: []
    };

    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockData
    });

    const res = await fetchWatchedFolders();
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/documents/watched-folders');
    expect(res.watched_folders).toHaveLength(1);
    expect(res.watcher_status.is_running).toBe(true);
  });

  it('addWatchedFolder sends POST with folder_path', async () => {
    const mockResponse = {
      success: true,
      message: 'Now watching folder: C:\\Users\\inouy\\Documents\\Taxes',
      folder: { id: 2, folder_path: 'C:\\Users\\inouy\\Documents\\Taxes', added_at: 1700000010, is_active: true, exists: true }
    };

    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockResponse
    });

    const res = await addWatchedFolder('C:\\Users\\inouy\\Documents\\Taxes');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/watched-folders',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: 'C:\\Users\\inouy\\Documents\\Taxes' })
      })
    );
    expect(res.success).toBe(true);
  });

  it('addWatchedFolder throws descriptive error when rejected by server', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Forbidden: Only folders within Documents and Downloads can be watched.' })
    });

    await expect(addWatchedFolder('C:\\Users\\inouy\\Desktop')).rejects.toThrow(
      'Forbidden: Only folders within Documents and Downloads can be watched.'
    );
  });

  it('removeWatchedFolder sends DELETE to /api/documents/watched-folders/:id', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, message: 'Folder removed' })
    });

    const res = await removeWatchedFolder(5);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/watched-folders/5',
      expect.objectContaining({ method: 'DELETE' })
    );
    expect(res.success).toBe(true);
  });

  it('syncWatchedFolder sends POST to /api/documents/watched-folders/:id/sync', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, started: true, message: 'Sync started' })
    });

    const res = await syncWatchedFolder(3);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/watched-folders/3/sync',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.started).toBe(true);
  });

  it('syncAllWatchedFolders sends POST to /api/documents/watched-folders/sync', async () => {
    (globalThis.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true, message: 'Sync started for 2 folders', folders_count: 2 })
    });

    const res = await syncAllWatchedFolders();
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/documents/watched-folders/sync',
      expect.objectContaining({ method: 'POST' })
    );
    expect(res.folders_count).toBe(2);
  });
});
