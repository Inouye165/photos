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
  entityId = null,
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
  if (entityId !== null && entityId !== undefined) params.append('entity_id', entityId);
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

export async function fetchDuplicates({ sortBy = null, sortOrder = null } = {}) {
  const params = new URLSearchParams();
  if (sortBy) params.append('sort_by', sortBy);
  if (sortOrder) params.append('sort_order', sortOrder);
  const queryStr = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`${API_BASE}/duplicates${queryStr}`);
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

// ---------------------------------------------------------
// People & Pets Recognition, Tagging & Confirmation Client API
// ---------------------------------------------------------

export async function fetchEntities(entityType = null) {
  const params = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : '';
  const res = await fetch(`${API_BASE}/people-pets/entities${params}`);
  if (!res.ok) throw new Error('Failed to fetch people and pets');
  return res.json();
}

export async function createEntity(name, entityType = 'PERSON') {
  const res = await fetch(`${API_BASE}/people-pets/entities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, entity_type: entityType })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create entity');
  }
  return res.json();
}

export async function updateEntity(entityId, data) {
  const res = await fetch(`${API_BASE}/people-pets/entities/${entityId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  if (!res.ok) throw new Error('Failed to update entity');
  return res.json();
}

export async function deleteEntity(entityId) {
  const res = await fetch(`${API_BASE}/people-pets/entities/${entityId}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error('Failed to delete entity');
  return res.json();
}

export async function fetchPendingReviews({ limit = 60, offset = 0, entityId = null } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (entityId) params.append('entity_id', entityId);
  const res = await fetch(`${API_BASE}/people-pets/pending?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch pending reviews');
  return res.json();
}

export async function confirmBox(boxId, entityId = null) {
  const params = entityId ? `?entity_id=${entityId}` : '';
  const res = await fetch(`${API_BASE}/people-pets/boxes/${boxId}/confirm${params}`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to confirm suggestion');
  return res.json();
}

export async function rejectBox(boxId) {
  const res = await fetch(`${API_BASE}/people-pets/boxes/${boxId}/reject`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to reject suggestion');
  return res.json();
}

export async function batchConfirmBoxes(boxIds) {
  const res = await fetch(`${API_BASE}/people-pets/boxes/batch-confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ box_ids: boxIds })
  });
  if (!res.ok) throw new Error('Failed to batch confirm suggestions');
  return res.json();
}

export async function confirmAllPendingReviews() {
  const res = await fetch(`${API_BASE}/people-pets/pending/confirm-all`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to confirm pending suggestions');
  return res.json();
}

export async function fetchPhotoBoxes(photoId) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/boxes`);
  if (!res.ok) throw new Error('Failed to fetch photo bounding boxes');
  return res.json();
}

export async function createPhotoBox(photoId, boxData) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/boxes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(boxData)
  });
  if (!res.ok) throw new Error('Failed to create bounding box');
  return res.json();
}

export async function updatePhotoBox(photoId, boxId, updateData) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/boxes/${boxId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updateData)
  });
  if (!res.ok) throw new Error('Failed to update bounding box');
  return res.json();
}

export async function deletePhotoBox(photoId, boxId) {
  const res = await fetch(`${API_BASE}/photos/${photoId}/boxes/${boxId}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error('Failed to delete bounding box');
  return res.json();
}

export async function startPeoplePetsScan() {
  const res = await fetch(`${API_BASE}/people-pets/scan`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to start people and pets scan');
  return res.json();
}

export async function fetchPeoplePetsScanStatus() {
  const res = await fetch(`${API_BASE}/people-pets/scan/status`);
  if (!res.ok) throw new Error('Failed to fetch scan status');
  return res.json();
}

export async function fetchUnassignedBoxes({ limit = 60, offset = 0, boxType = null } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (boxType && boxType !== 'ALL') params.append('box_type', boxType);
  const res = await fetch(`${API_BASE}/people-pets/unassigned?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch unassigned detected boxes');
  return res.json();
}

export async function assignBoxToEntity(boxId, { entityName, entityType = 'PERSON', setAsAvatar = true }) {
  const res = await fetch(`${API_BASE}/people-pets/boxes/${boxId}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity_name: entityName,
      entity_type: entityType,
      set_as_avatar: setAsAvatar
    })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to assign box to entity');
  }
  return res.json();
}

export async function setEntityAvatar(entityId, boxId) {
  const url = boxId != null
    ? `${API_BASE}/people-pets/entities/${entityId}/set-avatar?box_id=${boxId}`
    : `${API_BASE}/people-pets/entities/${entityId}/set-avatar`;
  const res = await fetch(url, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to set entity avatar');
  return res.json();
}

export async function unlinkBox(boxId) {
  const res = await fetch(`${API_BASE}/people-pets/boxes/${boxId}/unlink`, {
    method: 'POST'
  });
  if (!res.ok) throw new Error('Failed to unlink box');
  return res.json();
}

export async function fetchBackupStatus() {
  const res = await fetch(`${API_BASE}/backup/status`);
  if (!res.ok) throw new Error('Failed to fetch backup status');
  return res.json();
}

export async function fetchBackupAuthUrl() {
  const res = await fetch(`${API_BASE}/backup/auth/url`);
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to get authorization URL');
  }
  return res.json();
}

export async function exchangeBackupCode(code) {
  const res = await fetch(`${API_BASE}/backup/auth/exchange`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code })
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to exchange code');
  }
  return res.json();
}

export async function startBackupAuth() {
  const res = await fetch(`${API_BASE}/backup/auth/start`, { method: 'POST' });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to start Google Drive authentication');
  }
  return res.json();
}

export async function disconnectBackup() {
  const res = await fetch(`${API_BASE}/backup/auth/disconnect`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to disconnect Google Drive');
  return res.json();
}

export async function pauseBackup() {
  const res = await fetch(`${API_BASE}/backup/pause`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to pause backup');
  return res.json();
}

export async function resumeBackup() {
  const res = await fetch(`${API_BASE}/backup/resume`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to resume backup');
  return res.json();
}

export async function updateBackupSettings(settings) {
  const res = await fetch(`${API_BASE}/backup/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  });
  if (!res.ok) throw new Error('Failed to update backup settings');
  return res.json();
}

export async function retryFailedBackups() {
  const res = await fetch(`${API_BASE}/backup/retry-failed`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to retry backups');
  return res.json();
}

export async function uploadPhotos(files, onProgress) {
  const formData = new FormData();
  for (let i = 0; i < files.length; i++) {
    formData.append('files', files[i]);
  }
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/photos/upload`);
    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve({ status: 'ok' });
        }
      } else {
        let detail = `Upload failed with status ${xhr.status}`;
        try {
          detail = JSON.parse(xhr.responseText).detail || detail;
        } catch {}
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.send(formData);
  });
}

export async function fetchWatcherStatus() {
  const res = await fetch(`${API_BASE}/watcher/status`);
  if (!res.ok) throw new Error('Failed to fetch watcher status');
  return res.json();
}

export async function toggleWatcher(enabled) {
  const res = await fetch(`${API_BASE}/watcher/toggle`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled })
  });
  if (!res.ok) throw new Error('Failed to toggle watcher');
  return res.json();
}

export async function fetchDbBackupStatus() {
  const res = await fetch(`${API_BASE}/system/database-backup/status`);
  if (!res.ok) throw new Error('Failed to fetch database backup status');
  return res.json();
}

export async function triggerDbBackup() {
  const res = await fetch(`${API_BASE}/system/database-backup`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create database backup');
  return res.json();
}
