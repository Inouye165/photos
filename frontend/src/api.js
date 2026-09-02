/**
 * API client for LuminaPhoto backend services.
 */

const API_BASE = '/api';

export async function fetchPhotos({
  query = '',
  classification = null,
  includeDuplicates = true,
  cameraMake = null,
  hasGps = null,
  year = null,
  sortBy = 'date_taken',
  sortOrder = 'DESC',
  limit = 60,
  offset = 0,
  knownTotal = null,
  signal = null
} = {}) {
  const params = new URLSearchParams();
  if (query) params.append('query', query);
  if (classification) params.append('classification', classification);
  params.append('include_duplicates', includeDuplicates ? 'true' : 'false');
  if (cameraMake) params.append('camera_make', cameraMake);
  if (hasGps !== null) params.append('has_gps', hasGps ? 'true' : 'false');
  if (year) params.append('year', year);
  params.append('sort_by', sortBy);
  params.append('sort_order', sortOrder);
  params.append('limit', limit);
  params.append('offset', offset);
  if (knownTotal !== null) params.append('known_total', knownTotal);

  const res = await fetch(`${API_BASE}/photos?${params.toString()}`, { signal });
  if (!res.ok) throw new Error('Failed to fetch photos');
  return res.json();
}

export async function fetchPhotoDetails(photoId) {
  const res = await fetch(`${API_BASE}/photos/${photoId}`);
  if (!res.ok) throw new Error('Failed to fetch photo details');
  return res.json();
}

export async function fetchDuplicates() {
  const res = await fetch(`${API_BASE}/duplicates`);
  if (!res.ok) throw new Error('Failed to fetch duplicates');
  return res.json();
}

export async function deletePhoto(photoId, permanent = false) {
  const res = await fetch(`${API_BASE}/photos/${photoId}?permanent=${permanent}`, {
    method: 'DELETE'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete photo');
  }
  return res.json();
}

export async function dismissDuplicateGroup(groupId) {
  const res = await fetch(`${API_BASE}/duplicates/group/${groupId}/dismiss`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to dismiss duplicate group');
  return res.json();
}

export async function trashAllDuplicates() {
  const res = await fetch(`${API_BASE}/duplicates/trash-all`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to move all duplicates to trash');
  return res.json();
}

export async function trashGroupDuplicates(groupId) {
  const res = await fetch(`${API_BASE}/duplicates/group/${groupId}/trash`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to move duplicate copies to trash');
  return res.json();
}

export async function tagPhotoTrash(photoId, isTrashed = true) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/trash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_trashed: isTrashed })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update trash status');
  }
  return res.json();
}

export async function batchTagTrash(photoIds, isTrashed = true) {
  const res = await fetch(`${API_BASE}/photos/batch-trash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ photo_ids: photoIds, is_trashed: isTrashed })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to batch update trash status');
  }
  return res.json();
}

export async function fetchTrash({ limit = 60, offset = 0 } = {}) {
  const res = await fetch(`${API_BASE}/trash?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error('Failed to fetch trash');
  return res.json();
}

export async function emptyTrash(permanent = true) {
  const res = await fetch(`${API_BASE}/trash/empty?permanent=${permanent}`, {
    method: 'POST'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to empty trash');
  }
  return res.json();
}

export async function restoreAllTrash() {
  const res = await fetch(`${API_BASE}/trash/restore-all`, {
    method: 'POST'
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to restore trash');
  }
  return res.json();
}

export async function fetchTrashSpaceStatus(minFreeGb = 5.0) {
  const res = await fetch(`${API_BASE}/trash/space-status?min_free_gb=${minFreeGb}`);
  if (!res.ok) throw new Error('Failed to fetch trash space status');
  return res.json();
}

export async function purgeTrashForSpace({ minFreeGb = 5.0, forcePurgeCount = null, targetBytesToFree = null } = {}) {
  const res = await fetch(`${API_BASE}/trash/purge-for-space`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      min_free_gb: minFreeGb,
      force_purge_count: forcePurgeCount,
      target_bytes_to_free: targetBytesToFree
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to purge space');
  }
  return res.json();
}

export async function fetchPurgeLogs(limit = 50) {
  const res = await fetch(`${API_BASE}/trash/purge-logs?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch purge logs');
  return res.json();
}

export async function fetchNetworkInfo() {
  const res = await fetch(`${API_BASE}/network-info`);
  if (!res.ok) throw new Error('Failed to fetch network info');
  return res.json();
}

export async function fetchFilteredAssets() {
  const res = await fetch(`${API_BASE}/filtered`);
  if (!res.ok) throw new Error('Failed to fetch filtered assets');
  return res.json();
}

export async function reclassifyPhoto(photoId, classification) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/reclassify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ classification })
  });
  if (!res.ok) throw new Error('Failed to reclassify photo');
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export async function fetchDefaultPath() {
  const res = await fetch(`${API_BASE}/default-path`);
  if (!res.ok) throw new Error('Failed to fetch default path');
  return res.json();
}

export async function fetchBrowseFolders(path = '') {
  const params = path ? `?path=${encodeURIComponent(path)}` : '';
  const res = await fetch(`${API_BASE}/browse-folders${params}`);
  if (!res.ok) throw new Error('Failed to browse folders');
  return res.json();
}

export async function clearCatalog() {
  const res = await fetch(`${API_BASE}/catalog/clear`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to clear catalog');
  return res.json();
}

export async function startScan(path) {
  const res = await fetch(`${API_BASE}/scan/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to start scan');
  }
  return res.json();
}

export async function stopScan() {
  const res = await fetch(`${API_BASE}/scan/stop`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to stop scan');
  return res.json();
}

export async function fetchScanStatus() {
  const res = await fetch(`${API_BASE}/scan/status`);
  if (!res.ok) throw new Error('Failed to fetch scan status');
  return res.json();
}
