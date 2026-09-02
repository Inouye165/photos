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
  CheckCheck,
  ShieldCheck,
  ArchiveRestore,
  Maximize2
} from 'lucide-react';
import GroupCompareModal from './GroupCompareModal';
import {
  fetchDuplicates,
  tagPhotoTrash,
  trashAllDuplicates,
  trashGroupDuplicates,
  dismissDuplicateGroup
} from '../api';

export default function DuplicatesView({ onSelectPhoto, onLibraryUpdated }) {
  const [duplicateGroups, setDuplicateGroups] = useState([]);
  const [visibleCount, setVisibleCount] = useState(20);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState(false);
  const [dismissingGroupId, setDismissingGroupId] = useState(null);
  // confirmModal: { type: 'SINGLE' | 'GROUP' | 'ALL', photo?, group?, count?, bytes? }
  const [confirmModal, setConfirmModal] = useState(null);
  const [compareGroup, setCompareGroup] = useState(null);
  const [compareGroupIndex, setCompareGroupIndex] = useState(0);

  const loadData = () => {
    setLoading(true);
    fetchDuplicates()
      .then((data) => {
        setDuplicateGroups(data || []);
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
  const totalDupCopies = duplicateGroups.reduce((acc, g) => acc + (g.duplicates?.length || 0), 0);

  // Single copy trash click
  const handleSingleTrashClick = (e, photo, group) => {
    e.stopPropagation();
    setConfirmModal({
      type: 'SINGLE',
      photo,
      group
    });
  };

  // Group duplicate copies trash click
  const handleGroupTrashClick = (e, group) => {
    e.stopPropagation();
    setConfirmModal({
      type: 'GROUP',
      group
    });
  };

  // All duplicate copies trash click
  const handleAllTrashClick = () => {
    setConfirmModal({
      type: 'ALL',
      count: totalDupCopies,
      bytes: totalWastedBytes
    });
  };

  // Confirm and execute the trash action
  const handleConfirmTrash = async () => {
    if (!confirmModal) return;
    setActionInProgress(true);

    try {
      if (confirmModal.type === 'SINGLE') {
        await tagPhotoTrash(confirmModal.photo.id, true);
      } else if (confirmModal.type === 'GROUP') {
        await trashGroupDuplicates(confirmModal.group.group_id);
      } else if (confirmModal.type === 'ALL') {
        await trashAllDuplicates();
      }

      setConfirmModal(null);
      loadData();
      if (onLibraryUpdated) onLibraryUpdated();
    } catch (err) {
      alert('Error moving duplicates to trash: ' + err.message);
    } finally {
      setActionInProgress(false);
    }
  };

  // Dismiss group (keep both and unmark)
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
        <RefreshCw size={32} className="spin-slow" style={{ marginBottom: '1rem', color: '#38bdf8' }} />
        <p>Analyzing duplicate clusters and calculating redundant storage...</p>
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

        <div className="stat-card" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#10b981', fontSize: '0.85rem' }}>
              <ShieldCheck size={16} />
              <span>Safe Duplicate Cleanup</span>
            </div>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginTop: '0.35rem', lineHeight: '1.4' }}>
              Primary originals stay in library; duplicate copies safely stage to Trash.
            </div>
          </div>
          {totalDupCopies > 0 && (
            <button
              type="button"
              className="btn-primary"
              style={{
                marginTop: '0.75rem',
                background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                fontSize: '0.82rem',
                padding: '0.45rem 0.9rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                width: 'fit-content'
              }}
              onClick={handleAllTrashClick}
              disabled={actionInProgress}
            >
              <Trash2 size={14} />
              <span>Move All {totalDupCopies} Duplicates to Trash</span>
            </button>
          )}
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
        <>
          {duplicateGroups.slice(0, visibleCount).map((group, index) => {
          const primary = group.primary;
          const dups = group.duplicates || [];
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
                  <span style={{ fontSize: '0.8rem', color: '#f87171', fontWeight: 500 }}>
                    Wasted: {formatFileSize(group.total_wasted_bytes)}
                  </span>
                  
                  {/* Compare Group Studio Action */}
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.3rem 0.75rem',
                      background: 'rgba(56, 189, 248, 0.14)',
                      borderColor: 'rgba(56, 189, 248, 0.4)',
                      color: '#7dd3fc',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px'
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setCompareGroup(group);
                      setCompareGroupIndex(index);
                    }}
                    title="Open full-screen shootout studio to compare, filter, and pick winners"
                  >
                    <Maximize2 size={13} />
                    <span>Compare Group ({group.total_items})</span>
                  </button>

                  {/* Group Trash Action */}
                  {dups.length > 0 && (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{
                        fontSize: '0.75rem',
                        padding: '0.3rem 0.75rem',
                        background: 'rgba(239, 68, 68, 0.15)',
                        borderColor: 'rgba(239, 68, 68, 0.35)',
                        color: '#fca5a5'
                      }}
                      onClick={(e) => handleGroupTrashClick(e, group)}
                      disabled={actionInProgress}
                      title="Move all duplicate copies in this group to Trash"
                    >
                      <Trash2 size={13} />
                      <span>Trash Duplicates ({dups.length})</span>
                    </button>
                  )}

                  {/* Keep All */}
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem' }}
                    onClick={(e) => handleDismissGroup(e, group.group_id)}
                    disabled={dismissingGroupId === group.group_id || actionInProgress}
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
                      onError={(e) => { e.currentTarget.style.display = 'none'; }}
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
                      <div style={{ marginTop: '6px', fontSize: '0.72rem', color: '#a7f3d0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <ShieldCheck size={13} color="#34d399" />
                        <span>Preserved in Main Library</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Duplicate Copies with Move to Trash Option */}
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
                      onError={(e) => { e.currentTarget.style.display = 'none'; }}
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
                          disabled={actionInProgress}
                          onClick={(e) => handleSingleTrashClick(e, dup, group)}
                        >
                          <Trash2 size={12} />
                          <span>Move to Trash</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            );
          })}

          {visibleCount < duplicateGroups.length && (
            <div style={{ textAlign: 'center', margin: '2rem 0' }}>
              <button
                type="button"
                className="btn-secondary"
                style={{ padding: '0.6rem 1.5rem', fontSize: '0.875rem' }}
                onClick={() => setVisibleCount((prev) => prev + 20)}
              >
                Show More Duplicate Groups ({duplicateGroups.length - visibleCount} remaining)
              </button>
            </div>
          )}
        </>
      )}

      {/* Confirmation Modal */}
      {confirmModal && (
        <div className="modal-overlay" onClick={() => !actionInProgress && setConfirmModal(null)}>
          <div className="modal-card" style={{ maxWidth: '520px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', marginBottom: '1rem' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'rgba(239, 68, 68, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Trash2 size={22} color="#ef4444" />
              </div>
              <div>
                <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff', margin: 0 }}>
                  {confirmModal.type === 'SINGLE' && 'Move Duplicate to Trash?'}
                  {confirmModal.type === 'GROUP' && `Move ${confirmModal.group.duplicates.length} Duplicate Copies to Trash?`}
                  {confirmModal.type === 'ALL' && `Move All ${confirmModal.count} Duplicates to Trash?`}
                </h3>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
                  Safe non-destructive removal
                </div>
              </div>
            </div>

            {/* Target item / summary details */}
            {confirmModal.type === 'SINGLE' && (
              <div style={{
                background: '#161b28',
                padding: '0.85rem',
                borderRadius: '8px',
                fontSize: '0.8rem',
                color: '#cbd5e1',
                marginBottom: '1rem'
              }}>
                <div style={{ fontWeight: 600, color: '#f1f5f9', marginBottom: '4px' }}>
                  {confirmModal.photo.file_name} ({formatFileSize(confirmModal.photo.file_size)})
                </div>
                <div style={{ fontSize: '0.72rem', color: '#64748b', wordBreak: 'break-all' }}>
                  {confirmModal.photo.file_path}
                </div>
              </div>
            )}

            {confirmModal.type === 'GROUP' && (
              <div style={{
                background: '#161b28',
                padding: '0.85rem',
                borderRadius: '8px',
                fontSize: '0.82rem',
                color: '#cbd5e1',
                marginBottom: '1rem'
              }}>
                <div>Moving <strong>{confirmModal.group.duplicates.length} redundant duplicate copies</strong> to Trash.</div>
                <div style={{ color: '#f87171', fontSize: '0.78rem', marginTop: '4px' }}>
                  Wasted space to stage for trash: {formatFileSize(confirmModal.group.total_wasted_bytes)}
                </div>
              </div>
            )}

            {confirmModal.type === 'ALL' && (
              <div style={{
                background: '#161b28',
                padding: '0.85rem',
                borderRadius: '8px',
                fontSize: '0.82rem',
                color: '#cbd5e1',
                marginBottom: '1rem'
              }}>
                <div>Moving <strong>{confirmModal.count} duplicate copies</strong> across <strong>{duplicateGroups.length} groups</strong> to Trash.</div>
                <div style={{ color: '#f87171', fontSize: '0.78rem', marginTop: '4px' }}>
                  Total disk space staged for trash: {formatFileSize(confirmModal.bytes)}
                </div>
              </div>
            )}

            {/* Reassurance points */}
            <div style={{
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              borderRadius: '8px',
              padding: '0.85rem',
              marginBottom: '1.25rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem', color: '#34d399', fontWeight: 600, marginBottom: '4px' }}>
                <ShieldCheck size={16} />
                <span>Primary Original(s) Kept Safe</span>
              </div>
              <div style={{ fontSize: '0.78rem', color: '#a7f3d0', lineHeight: '1.4' }}>
                The best-quality photo in each cluster stays untouched in your library.
              </div>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '6px', lineHeight: '1.4' }}>
                Moved items are placed in the <strong>Trash</strong> tab and can be reviewed or restored at any time.
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                className="btn-secondary"
                onClick={() => setConfirmModal(null)}
                disabled={actionInProgress}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{
                  background: '#ef4444',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
                onClick={handleConfirmTrash}
                disabled={actionInProgress}
              >
                {actionInProgress ? (
                  <>
                    <RefreshCw size={14} className="spin-slow" />
                    <span>Moving to Trash...</span>
                  </>
                ) : (
                  <>
                    <Trash2 size={15} />
                    <span>Move to Trash</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Group Shootout Modal */}
      {compareGroup && (
        <GroupCompareModal
          group={compareGroup}
          groupIndex={compareGroupIndex}
          onClose={() => setCompareGroup(null)}
          onApplied={() => {
            loadData();
            if (onLibraryUpdated) onLibraryUpdated();
          }}
        />
      )}
    </div>
  );
}
