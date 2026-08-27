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
  offset = 0
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

  const res = await fetch(`${API_BASE}/photos?${params.toString()}`);
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
