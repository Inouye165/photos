import React, { useState, useEffect } from 'react';
import {
  Copy,
  Star,
  HardDrive,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  RefreshCw,
  FolderOpen,
  CheckCheck
} from 'lucide-react';
import { fetchDuplicates, deletePhoto, dismissDuplicateGroup } from '../api';

export default function DuplicatesView({ onSelectPhoto, onLibraryUpdated }) {
  const [duplicateGroups, setDuplicateGroups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [dismissingGroupId, setDismissingGroupId] = useState(null);
  const [confirmModal, setConfirmModal] = useState(null); // { photo, groupIndex }

  const loadData = () => {
    setLoading(true);
    fetchDuplicates()
      .then((data) => {
        setDuplicateGroups(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(2)} MB` : `${Math.round(bytes / 1024)} KB`;
  };

  const totalWastedBytes = duplicateGroups.reduce((acc, g) => acc + (g.total_wasted_bytes || 0), 0);

  const handleDeleteClick = (e, photo, group) => {
    e.stopPropagation();
    setConfirmModal({ photo, group });
  };

  const handleConfirmDelete = async () => {
    if (!confirmModal?.photo) return;
    const pid = confirmModal.photo.id;
    try {
      setDeletingId(pid);
      setConfirmModal(null);
      await deletePhoto(pid);
      loadData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Error deleting duplicate: ' + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  const handleDismissGroup = async (e, groupId) => {
    e.stopPropagation();
    try {
      setDismissingGroupId(groupId);
      await dismissDuplicateGroup(groupId);
      loadData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Error dismissing group: ' + err.message);
    } finally {
      setDismissingGroupId(null);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '5rem 0', color: '#94a3b8' }}>
        <p>Analyzing duplicate clusters...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Overview Stat Banner */}
      <div className="stat-grid">
        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', fontSize: '0.85rem' }}>
            <Copy size={16} />
            <span>Duplicate Groups</span>
          </div>
          <div className="stat-val">{duplicateGroups.length}</div>
        </div>

        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#ef4444', fontSize: '0.85rem' }}>
            <HardDrive size={16} />
            <span>Redundant Storage</span>
          </div>
          <div className="stat-val">{formatFileSize(totalWastedBytes)}</div>
        </div>

        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', fontSize: '0.85rem' }}>
            <CheckCircle2 size={16} />
            <span>User-Controlled Actions</span>
          </div>
          <div style={{ fontSize: '0.85rem', color: '#a7f3d0', marginTop: '0.5rem', lineHeight: '1.4' }}>
            Choose which duplicate copy to delete (moves safely to Recycle Bin) or keep both.
          </div>
        </div>
      </div>

      {duplicateGroups.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '5rem 2rem',
          background: 'rgba(255, 255, 255, 0.02)',
          borderRadius: '16px',
          border: '1px dashed rgba(255, 255, 255, 0.1)',
          maxWidth: '600px',
          margin: '2rem auto'
        }}>
          <CheckCircle2 size={48} color="#10b981" style={{ marginBottom: '1rem' }} />
          <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>
            No Duplicates Found
          </h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
            All scanned photos in your library are unique.
          </p>
        </div>
      ) : (
        duplicateGroups.map((group, index) => {
          const primary = group.primary;
          const dups = group.duplicates;
          const matchLabel = group.match_type === 'EXACT_HASH' ? 'Exact SHA-256 Match' : 'Perceptual Visual Match';

          return (
            <div key={group.group_id} className="dup-group-card">
              <div className="dup-group-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '3px 9px',
                    borderRadius: '9999px',
                    background: group.match_type === 'EXACT_HASH' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(99, 102, 241, 0.2)',
                    color: group.match_type === 'EXACT_HASH' ? '#fde68a' : '#c7d2fe',
                    border: '1px solid rgba(255, 255, 255, 0.1)'
                  }}>
                    {matchLabel}
                  </span>
                  <span style={{ fontSize: '0.85rem', color: '#cbd5e1', fontWeight: 600 }}>
                    Group #{index + 1} ({group.total_items} copies)
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '0.8rem', color: '#f87171' }}>
                    Wasted: {formatFileSize(group.total_wasted_bytes)}
                  </span>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem' }}
                    onClick={(e) => handleDismissGroup(e, group.group_id)}
                    disabled={dismissingGroupId === group.group_id}
                    title="Keep all files and unmark as duplicate"
                  >
                    <CheckCheck size={13} color="#10b981" />
                    <span>Keep All</span>
                  </button>
                </div>
              </div>

              <div className="dup-items-row">
                {/* Primary Keeper */}
                {primary && (
                  <div
                    className="dup-item-card is-primary"
                    onClick={() => onSelectPhoto(primary)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="primary-badge">
                      <Star size={10} fill="#ffffff" style={{ display: 'inline', marginRight: '3px' }} />
                      Primary Keeper
                    </div>
                    <img
                      src={`/api/photos/${primary.id}/thumbnail`}
                      alt={primary.file_name}
                      style={{ width: '88px', height: '88px', objectFit: 'cover', borderRadius: '8px', flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {primary.file_name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#34d399', margin: '3px 0' }}>
                        {primary.width}×{primary.height} px • {formatFileSize(primary.file_size)}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: '#64748b', wordBreak: 'break-all' }}>
                        {primary.file_path}
                      </div>
                      <div style={{ marginTop: '6px', fontSize: '0.72rem', color: '#a7f3d0' }}>
                        ✓ Best Quality / Original EXIF
                      </div>
                    </div>
                  </div>
                )}

                {/* Duplicate Copies with Delete Option */}
                {dups.map((dup) => (
                  <div
                    key={dup.id}
                    className="dup-item-card"
                    onClick={() => onSelectPhoto(dup)}
                    style={{ cursor: 'pointer' }}
                  >
                    <img
                      src={`/api/photos/${dup.id}/thumbnail`}
                      alt={dup.file_name}
                      style={{ width: '88px', height: '88px', objectFit: 'cover', borderRadius: '8px', flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {dup.file_name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8', margin: '3px 0' }}>
                        {dup.width}×{dup.height} px • {formatFileSize(dup.file_size)}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: '#64748b', wordBreak: 'break-all' }}>
                        {dup.file_path}
                      </div>

                      {/* Action buttons */}
                      <div style={{ marginTop: '8px', display: 'flex', gap: '6px' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{
                            fontSize: '0.72rem',
                            padding: '0.3rem 0.65rem',
                            background: 'rgba(239, 68, 68, 0.15)',
                            borderColor: 'rgba(239, 68, 68, 0.3)',
                            color: '#fca5a5'
                          }}
                          disabled={deletingId === dup.id}
                          onClick={(e) => handleDeleteClick(e, dup, group)}
                        >
                          <Trash2 size={12} />
                          <span>{deletingId === dup.id ? 'Deleting...' : 'Delete Copy'}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="modal-overlay" onClick={() => setConfirmModal(null)}>
          <div className="modal-card" style={{ maxWidth: '450px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f87171', marginBottom: '1rem' }}>
              <AlertTriangle size={22} />
              <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff' }}>
                Delete Duplicate Copy?
              </h3>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#cbd5e1', marginBottom: '1rem', lineHeight: '1.4' }}>
              This will move the duplicate copy to the <strong>Windows Recycle Bin</strong>:
            </p>
            <div style={{
              background: '#161b28',
              padding: '0.75rem',
              borderRadius: '8px',
              fontSize: '0.78rem',
              color: '#94a3b8',
              wordBreak: 'break-all',
              marginBottom: '1.25rem'
            }}>
              {confirmModal.photo.file_path}
            </div>
            <p style={{ fontSize: '0.8rem', color: '#34d399', marginBottom: '1.25rem' }}>
              ✓ The primary keeper copy will be kept safe and untouched.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button className="btn-secondary" onClick={() => setConfirmModal(null)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{ background: '#ef4444' }}
                onClick={handleConfirmDelete}
              >
                <Trash2 size={15} />
                <span>Move to Recycle Bin</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
