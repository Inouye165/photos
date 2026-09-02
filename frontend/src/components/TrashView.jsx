import React, { useState, useEffect, useCallback } from 'react';
import {
  Trash2,
  RotateCcw,
  HardDrive,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Sparkles,
  Info,
  Calendar,
  Layers,
  ShieldAlert,
  ArrowRight,
  History,
  X
} from 'lucide-react';
import {
  fetchTrash,
  emptyTrash,
  restoreAllTrash,
  tagPhotoTrash,
  deletePhoto,
  fetchTrashSpaceStatus,
  purgeTrashForSpace,
  fetchPurgeLogs
} from '../api';

export default function TrashView({ onSelectPhoto, onLibraryUpdated }) {
  const [trashedPhotos, setTrashedPhotos] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);
  const [spaceInfo, setSpaceInfo] = useState(null);
  const [purgeLogs, setPurgeLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [recentNotification, setRecentNotification] = useState(null);
  const [showConfirmEmpty, setShowConfirmEmpty] = useState(false);
  const [showLogsModal, setShowLogsModal] = useState(false);
  const [thresholdGb, setThresholdGb] = useState(5.0);

  const loadTrashData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [trashData, spaceData, logsData] = await Promise.all([
        fetchTrash({ limit: 200, offset: 0 }),
        fetchTrashSpaceStatus(thresholdGb),
        fetchPurgeLogs(10)
      ]);
      setTrashedPhotos(trashData.photos || []);
      setTotalCount(trashData.total || 0);
      setTotalBytes(trashData.total_bytes || 0);
      setSpaceInfo(spaceData);
      setPurgeLogs(logsData.logs || []);
    } catch (err) {
      console.error('Error loading trash data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [thresholdGb]);

  useEffect(() => {
    loadTrashData();
  }, [loadTrashData]);

  const handleRestorePhoto = async (e, photo) => {
    e.stopPropagation();
    try {
      setIsActionLoading(true);
      await tagPhotoTrash(photo.id, false);
      await loadTrashData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Failed to restore photo: ' + err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handlePermanentDeleteOne = async (e, photo) => {
    e.stopPropagation();
    if (!window.confirm(`Permanently delete "${photo.file_name}" from disk?`)) return;
    try {
      setIsActionLoading(true);
      await deletePhoto(photo.id, true);
      await loadTrashData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Failed to delete photo: ' + err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleEmptyTrash = async () => {
    try {
      setIsActionLoading(true);
      const res = await emptyTrash(true);
      setShowConfirmEmpty(false);
      setRecentNotification({
        type: 'info',
        title: 'Trash Emptied',
        message: res.message
      });
      await loadTrashData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Failed to empty trash: ' + err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRestoreAll = async () => {
    try {
      setIsActionLoading(true);
      const res = await restoreAllTrash();
      setRecentNotification({
        type: 'success',
        title: 'All Photos Restored',
        message: res.message
      });
      await loadTrashData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Failed to restore photos: ' + err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handlePurgeForSpace = async (forceCount = null) => {
    try {
      setIsActionLoading(true);
      const res = await purgeTrashForSpace({
        minFreeGb: thresholdGb,
        forcePurgeCount: forceCount
      });
      if (res.purged) {
        setRecentNotification({
          type: 'alert',
          title: 'Disk Space Auto-Purge Notification',
          message: res.message
        });
      } else {
        setRecentNotification({
          type: 'info',
          title: 'Disk Space Check',
          message: res.message
        });
      }
      await loadTrashData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Space cleanup error: ' + err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  const formatMb = (bytes) => {
    if (!bytes) return '0 MB';
    const mb = bytes / (1024 * 1024);
    return mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(2)} MB`;
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <div className="trash-view-container">
      {/* Header Banner */}
      <div className="trash-header-card">
        <div className="trash-header-info">
          <div className="trash-title-row">
            <div className="trash-icon-pill">
              <Trash2 size={24} color="#f87171" />
            </div>
            <div>
              <h2 className="trash-title">Trash & Space Management</h2>
              <p className="trash-subtitle">
                Photos tagged for trash are <strong>kept safe in-place</strong> on your disk until you empty the trash or disk space is needed.
              </p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="trash-header-actions">
          <button
            className="btn-secondary"
            onClick={() => setShowLogsModal(true)}
            title="View permanent space deletion audit logs"
          >
            <History size={15} />
            <span>Audit History</span>
          </button>

          <button
            className="btn-secondary"
            onClick={handleRestoreAll}
            disabled={totalCount === 0 || isActionLoading}
            title="Restore all tagged photos back to active photo gallery"
          >
            <RotateCcw size={15} />
            <span>Restore All</span>
          </button>

          <button
            className="btn-primary"
            style={{ background: '#ef4444' }}
            onClick={() => setShowConfirmEmpty(true)}
            disabled={totalCount === 0 || isActionLoading}
          >
            <Trash2 size={15} />
            <span>Empty Trash</span>
          </button>
        </div>
      </div>

      {/* High-Visibility Permanent Space Purge Notification Banner */}
      {recentNotification && (
        <div className={`space-notification-banner banner-${recentNotification.type}`}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            {recentNotification.type === 'alert' ? (
              <AlertTriangle size={22} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
            ) : (
              <CheckCircle2 size={22} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
            )}
            <div>
              <div style={{ fontWeight: 600, fontSize: '0.95rem', color: '#ffffff', marginBottom: '2px' }}>
                {recentNotification.title}
              </div>
              <div style={{ fontSize: '0.85rem', color: '#e2e8f0', lineHeight: 1.4 }}>
                {recentNotification.message}
              </div>
            </div>
          </div>
          <button
            className="btn-close-banner"
            onClick={() => setRecentNotification(null)}
            title="Dismiss notice"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Storage & Space Manager Cards */}
      <div className="trash-metrics-grid">
        {/* Drive Storage Health */}
        <div className="metric-card">
          <div className="metric-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <HardDrive size={18} color="#38bdf8" />
              <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Drive Free Space</span>
            </div>
            {spaceInfo && (
              <span className={`status-pill ${spaceInfo.is_space_low ? 'pill-low' : 'pill-ok'}`}>
                {spaceInfo.is_space_low ? 'Low Space' : 'Healthy'}
              </span>
            )}
          </div>

          {spaceInfo ? (
            <>
              <div className="metric-value-row">
                <span className="metric-large-text">{spaceInfo.free_gb} GB</span>
                <span className="metric-sub-text">free of {spaceInfo.total_gb} GB</span>
              </div>

              {/* Progress Bar */}
              <div className="storage-bar-track">
                <div
                  className="storage-bar-fill"
                  style={{
                    width: `${Math.min(100, Math.max(5, 100 - spaceInfo.percent_free))}%`,
                    background: spaceInfo.is_space_low ? '#ef4444' : 'linear-gradient(90deg, #10b981, #06b6d4)'
                  }}
                />
              </div>

              <div className="space-footer-row">
                <span>{spaceInfo.percent_free}% available</span>
                <span>Threshold: &lt; {thresholdGb} GB</span>
              </div>
            </>
          ) : (
            <div style={{ color: '#94a3b8', fontSize: '0.85rem', padding: '1rem 0' }}>Reading drive stats...</div>
          )}
        </div>

        {/* Recoverable Trash Size */}
        <div className="metric-card">
          <div className="metric-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Trash2 size={18} color="#f87171" />
              <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Trash Recoverable Space</span>
            </div>
            <span className="nav-badge" style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5' }}>
              {totalCount} photos
            </span>
          </div>

          <div className="metric-value-row">
            <span className="metric-large-text" style={{ color: '#fca5a5' }}>{formatMb(totalBytes)}</span>
            <span className="metric-sub-text">ready to free</span>
          </div>

          <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '0.5rem', lineHeight: '1.4' }}>
            Original image files remain untouched until emptied or auto-purged if drive space is needed.
          </div>

          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '8px' }}>
            <button
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
              onClick={() => handlePurgeForSpace(null)}
              disabled={isActionLoading}
            >
              <RefreshCw size={12} className={isActionLoading ? 'spin-icon' : ''} />
              <span>Check Low Space</span>
            </button>

            <button
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem', borderColor: 'rgba(245, 158, 11, 0.3)', color: '#fbbf24' }}
              onClick={() => handlePurgeForSpace(1)}
              disabled={totalCount === 0 || isActionLoading}
              title="Test space auto-purge (purges 1 oldest trashed photo & generates notice)"
            >
              <AlertTriangle size={12} />
              <span>Simulate Low Space Purge</span>
            </button>
          </div>
        </div>
      </div>

      {/* Trashed Photos Grid */}
      <div className="trash-grid-section">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f1f5f9', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={18} color="#94a3b8" />
            <span>Tagged Photos in Trash ({totalCount})</span>
          </h3>
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Click photo to inspect details or restore
          </span>
        </div>

        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '4rem 0', color: '#94a3b8' }}>
            <Sparkles size={28} className="spin-icon" color="#10b981" />
            <p style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>Loading trash...</p>
          </div>
        ) : trashedPhotos.length === 0 ? (
          <div className="trash-empty-state">
            <Trash2 size={48} color="#475569" style={{ marginBottom: '1rem' }} />
            <h4 style={{ fontSize: '1.15rem', color: '#f1f5f9', marginBottom: '0.5rem' }}>
              Trash is Empty
            </h4>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', maxWidth: '440px', margin: '0 auto' }}>
              As you scroll through your library, click the trash icon on any photo to tag it for deferred deletion.
            </p>
          </div>
        ) : (
          <div className="photo-grid">
            {trashedPhotos.map((photo) => {
              const thumbUrl = `/api/photos/${photo.id}/thumbnail`;
              return (
                <div
                  key={photo.id}
                  className="photo-card trashed-card"
                  onClick={() => onSelectPhoto(photo)}
                >
                  <div className="photo-card-img-wrap">
                    <img
                      src={thumbUrl}
                      alt={photo.file_name}
                      className="photo-card-img"
                      loading="lazy"
                      onError={(e) => {
                        e.target.style.display = 'none';
                      }}
                    />

                    {/* Quick restore button */}
                    <button
                      className="quick-trash-btn is-active"
                      title="Restore photo back to gallery"
                      onClick={(e) => handleRestorePhoto(e, photo)}
                    >
                      <RotateCcw size={13} />
                    </button>

                    <div className="photo-badge-top-left">
                      <span className="badge-trash">
                        <Trash2 size={10} />
                        <span>Tagged</span>
                      </span>
                    </div>
                  </div>

                  <div className="photo-card-info">
                    <div className="photo-card-name" title={photo.file_name}>
                      {photo.file_name}
                    </div>
                    <div className="photo-card-meta">
                      <span>{formatMb(photo.file_size)}</span>
                      <span>{formatDate(photo.date_taken)}</span>
                    </div>
                  </div>

                  <div className="trashed-card-actions">
                    <button
                      className="btn-card-action btn-restore"
                      onClick={(e) => handleRestorePhoto(e, photo)}
                      title="Restore to active library"
                    >
                      <RotateCcw size={12} />
                      <span>Restore</span>
                    </button>
                    <button
                      className="btn-card-action btn-delete"
                      onClick={(e) => handlePermanentDeleteOne(e, photo)}
                      title="Permanently remove file from disk now"
                    >
                      <Trash2 size={12} />
                      <span>Delete</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Empty Trash Confirmation Modal */}
      {showConfirmEmpty && (
        <div className="modal-overlay" onClick={() => setShowConfirmEmpty(false)}>
          <div className="modal-card" style={{ maxWidth: '460px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', marginBottom: '1rem' }}>
              <AlertTriangle size={24} />
              <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#ffffff' }}>
                Empty Trash Permanently?
              </h3>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#cbd5e1', lineHeight: '1.5', marginBottom: '1rem' }}>
              This will permanently delete <strong>{totalCount} photo(s)</strong> ({formatMb(totalBytes)}) from your storage drive.
              This action cannot be undone.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button className="btn-secondary" onClick={() => setShowConfirmEmpty(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{ background: '#ef4444' }}
                onClick={handleEmptyTrash}
                disabled={isActionLoading}
              >
                <Trash2 size={15} />
                <span>{isActionLoading ? 'Emptying...' : `Delete ${totalCount} Photos`}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Space Purge Audit Logs Modal */}
      {showLogsModal && (
        <div className="modal-overlay" onClick={() => setShowLogsModal(false)}>
          <div className="modal-card" style={{ maxWidth: '640px', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <History size={20} color="#38bdf8" />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 600, color: '#ffffff' }}>
                  Permanent Deletions & Space Purge Log
                </h3>
              </div>
              <button className="btn-secondary" style={{ padding: '4px 8px' }} onClick={() => setShowLogsModal(false)}>
                <X size={16} />
              </button>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', paddingRight: '4px' }}>
              {purgeLogs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem 0', color: '#94a3b8', fontSize: '0.875rem' }}>
                  No permanent space-triggered purges logged yet.
                </div>
              ) : (
                purgeLogs.map((log) => (
                  <div key={log.id} className="purge-log-item">
                    <div className="purge-log-header">
                      <span className={`pill-reason pill-${log.reason.toLowerCase()}`}>
                        {log.reason === 'LOW_DISK_SPACE' ? 'Low Space Auto-Purge' : 'Empty Trash'}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                        {new Date(log.purged_at * 1000).toLocaleString()}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#e2e8f0', marginTop: '6px', lineHeight: 1.4 }}>
                      {log.message}
                    </div>
                    {log.deleted_files && log.deleted_files.length > 0 && (
                      <div className="purge-log-files">
                        <span style={{ fontWeight: 600, color: '#94a3b8' }}>Files ({log.deleted_files.length}): </span>
                        <span>{log.deleted_files.slice(0, 10).join(', ')}{log.deleted_files.length > 10 ? ` and ${log.deleted_files.length - 10} more` : ''}</span>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
