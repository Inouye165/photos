import React, { useState, useEffect, useMemo } from 'react';
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
  Maximize2,
  Calendar,
  ArrowUpDown,
  Flame,
  Clock,
  Layers,
  Camera
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
  const [categoryFilter, setCategoryFilter] = useState('all'); // 'all' | 'exact' | 'burst' | 'similar'
  const [sortOption, setSortOption] = useState('duplicates_desc');
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

  const parseGroupDate = (group) => {
    const dt = group.date_taken || group.primary?.date_taken || group.duplicates?.[0]?.date_taken;
    if (dt) {
      const cleaned = String(dt).replace(/^(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3');
      const parsed = new Date(cleaned);
      if (!isNaN(parsed.getTime())) return parsed;
    }
    const mtime = group.file_modified_at || group.primary?.file_modified_at || group.duplicates?.[0]?.file_modified_at;
    if (mtime) return new Date(mtime * 1000);
    return null;
  };

  const formatDate = (dateVal) => {
    if (!dateVal) return null;
    const cleaned = String(dateVal).replace(/^(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3');
    const d = new Date(cleaned);
    if (isNaN(d.getTime())) return String(dateVal);
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatDateTime = (dateVal) => {
    if (!dateVal) return null;
    const cleaned = String(dateVal).replace(/^(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3');
    const d = new Date(cleaned);
    if (isNaN(d.getTime())) return String(dateVal);
    return d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const totalWastedBytes = duplicateGroups.reduce((acc, g) => acc + (g.total_wasted_bytes || 0), 0);
  const totalDupCopies = duplicateGroups.reduce((acc, g) => acc + (g.duplicates?.length || 0), 0);

  // Group counts per category
  const counts = useMemo(() => {
    let exact = 0;
    let burst = 0;
    let similar = 0;
    duplicateGroups.forEach((g) => {
      if (g.match_type === 'EXACT_HASH') exact++;
      else if (g.match_type === 'BURST_SEQUENCE') burst++;
      else similar++;
    });
    return { all: duplicateGroups.length, exact, burst, similar };
  }, [duplicateGroups]);

  // Filter groups by active category
  const filteredGroups = useMemo(() => {
    if (categoryFilter === 'exact') {
      return duplicateGroups.filter((g) => g.match_type === 'EXACT_HASH');
    }
    if (categoryFilter === 'burst') {
      return duplicateGroups.filter((g) => g.match_type === 'BURST_SEQUENCE');
    }
    if (categoryFilter === 'similar') {
      return duplicateGroups.filter((g) => g.match_type === 'PERCEPTUAL_PHASH' || (g.match_type !== 'EXACT_HASH' && g.match_type !== 'BURST_SEQUENCE'));
    }
    return duplicateGroups;
  }, [duplicateGroups, categoryFilter]);

  // Sorted duplicate groups based on current sortOption
  const sortedDuplicateGroups = useMemo(() => {
    const groups = [...filteredGroups];
    groups.sort((a, b) => {
      if (sortOption === 'duplicates_desc') {
        const diff = (b.duplicates?.length || 0) - (a.duplicates?.length || 0);
        if (diff !== 0) return diff;
        return (b.total_wasted_bytes || 0) - (a.total_wasted_bytes || 0);
      }
      if (sortOption === 'duplicates_asc') {
        const diff = (a.duplicates?.length || 0) - (b.duplicates?.length || 0);
        if (diff !== 0) return diff;
        return (a.total_wasted_bytes || 0) - (b.total_wasted_bytes || 0);
      }
      if (sortOption === 'date_asc') {
        const da = parseGroupDate(a);
        const db = parseGroupDate(b);
        if (!da && !db) return 0;
        if (!da) return 1;
        if (!db) return -1;
        return da.getTime() - db.getTime();
      }
      if (sortOption === 'date_desc') {
        const da = parseGroupDate(a);
        const db = parseGroupDate(b);
        if (!da && !db) return 0;
        if (!da) return 1;
        if (!db) return -1;
        return db.getTime() - da.getTime();
      }
      if (sortOption === 'size_desc') {
        return (b.total_wasted_bytes || 0) - (a.total_wasted_bytes || 0);
      }
      if (sortOption === 'size_asc') {
        return (a.total_wasted_bytes || 0) - (b.total_wasted_bytes || 0);
      }
      return 0;
    });
    return groups;
  }, [filteredGroups, sortOption]);

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

      {/* Category Tabs: All, Exact Clones, Continuous Bursts, Visually Similar */}
      {duplicateGroups.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          flexWrap: 'wrap',
          marginBottom: '1rem'
        }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setCategoryFilter('all')}
            style={{
              fontSize: '0.82rem',
              fontWeight: 600,
              padding: '0.45rem 0.9rem',
              borderRadius: '10px',
              background: categoryFilter === 'all' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(255, 255, 255, 0.03)',
              borderColor: categoryFilter === 'all' ? 'rgba(255, 255, 255, 0.3)' : 'rgba(255, 255, 255, 0.08)',
              color: categoryFilter === 'all' ? '#ffffff' : '#94a3b8',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span>All Categories</span>
            <span style={{
              fontSize: '0.72rem',
              padding: '2px 7px',
              borderRadius: '9999px',
              background: categoryFilter === 'all' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 255, 255, 0.06)',
              color: '#f8fafc'
            }}>{counts.all}</span>
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setCategoryFilter('exact')}
            style={{
              fontSize: '0.82rem',
              fontWeight: 600,
              padding: '0.45rem 0.9rem',
              borderRadius: '10px',
              background: categoryFilter === 'exact' ? 'rgba(245, 158, 11, 0.22)' : 'rgba(255, 255, 255, 0.03)',
              borderColor: categoryFilter === 'exact' ? 'rgba(245, 158, 11, 0.5)' : 'rgba(255, 255, 255, 0.08)',
              color: categoryFilter === 'exact' ? '#fde68a' : '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px'
            }}
            title="100% bit-for-bit identical SHA-256 duplicate files"
          >
            <Copy size={14} color="#f59e0b" />
            <span>Exact Clones</span>
            <span style={{
              fontSize: '0.72rem',
              padding: '2px 7px',
              borderRadius: '9999px',
              background: 'rgba(245, 158, 11, 0.2)',
              color: '#fde68a'
            }}>{counts.exact}</span>
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setCategoryFilter('burst')}
            style={{
              fontSize: '0.82rem',
              fontWeight: 600,
              padding: '0.45rem 0.9rem',
              borderRadius: '10px',
              background: categoryFilter === 'burst' ? 'rgba(6, 182, 212, 0.22)' : 'rgba(255, 255, 255, 0.03)',
              borderColor: categoryFilter === 'burst' ? 'rgba(6, 182, 212, 0.5)' : 'rgba(255, 255, 255, 0.08)',
              color: categoryFilter === 'burst' ? '#67e8f9' : '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px'
            }}
            title="Photos taken within 1 minute with tight composition similarity (Google-style Photo Stacks)"
          >
            <Layers size={14} color="#06b6d4" />
            <span>Continuous Bursts</span>
            <span style={{
              fontSize: '0.72rem',
              padding: '2px 7px',
              borderRadius: '9999px',
              background: 'rgba(6, 182, 212, 0.2)',
              color: '#67e8f9'
            }}>{counts.burst}</span>
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => setCategoryFilter('similar')}
            style={{
              fontSize: '0.82rem',
              fontWeight: 600,
              padding: '0.45rem 0.9rem',
              borderRadius: '10px',
              background: categoryFilter === 'similar' ? 'rgba(99, 102, 241, 0.22)' : 'rgba(255, 255, 255, 0.03)',
              borderColor: categoryFilter === 'similar' ? 'rgba(99, 102, 241, 0.5)' : 'rgba(255, 255, 255, 0.08)',
              color: categoryFilter === 'similar' ? '#c7d2fe' : '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px'
            }}
            title="Visually similar photos taken at different times or with looser similarity"
          >
            <Sparkles size={14} color="#818cf8" />
            <span>Visually Similar</span>
            <span style={{
              fontSize: '0.72rem',
              padding: '2px 7px',
              borderRadius: '9999px',
              background: 'rgba(99, 102, 241, 0.2)',
              color: '#c7d2fe'
            }}>{counts.similar}</span>
          </button>
        </div>
      )}

      {/* Sorting & Filter Controls Toolbar */}
      {duplicateGroups.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            padding: '0.75rem 1.25rem',
            borderRadius: '12px',
            marginBottom: '1.25rem',
            backdropFilter: 'blur(12px)'
          }}
        >
          {/* Quick preset sort chips */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 500, marginRight: '4px' }}>
              Quick Sort:
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSortOption('duplicates_desc')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '9999px',
                background: sortOption === 'duplicates_desc' ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                borderColor: sortOption === 'duplicates_desc' ? 'rgba(245, 158, 11, 0.5)' : 'rgba(255, 255, 255, 0.1)',
                color: sortOption === 'duplicates_desc' ? '#fde68a' : '#cbd5e1',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px'
              }}
              title="Sort by clusters with the highest number of photos"
            >
              <Flame size={13} color={sortOption === 'duplicates_desc' ? '#f59e0b' : '#94a3b8'} />
              <span>Most Takes / Copies</span>
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSortOption('date_asc')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '9999px',
                background: sortOption === 'date_asc' ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                borderColor: sortOption === 'date_asc' ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255, 255, 255, 0.1)',
                color: sortOption === 'date_asc' ? '#7dd3fc' : '#cbd5e1',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px'
              }}
              title="Compare older photos and historical duplicate clusters first"
            >
              <Clock size={13} color={sortOption === 'date_asc' ? '#38bdf8' : '#94a3b8'} />
              <span>Oldest First (By Age)</span>
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSortOption('date_desc')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '9999px',
                background: sortOption === 'date_desc' ? 'rgba(129, 140, 248, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                borderColor: sortOption === 'date_desc' ? 'rgba(129, 140, 248, 0.5)' : 'rgba(255, 255, 255, 0.1)',
                color: sortOption === 'date_desc' ? '#c7d2fe' : '#cbd5e1',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px'
              }}
              title="Compare newer and most recent duplicate clusters first"
            >
              <Sparkles size={13} color={sortOption === 'date_desc' ? '#a5b4fc' : '#94a3b8'} />
              <span>Newest First (By Age)</span>
            </button>

            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSortOption('size_desc')}
              style={{
                fontSize: '0.78rem',
                padding: '0.35rem 0.75rem',
                borderRadius: '9999px',
                background: sortOption === 'size_desc' ? 'rgba(239, 68, 68, 0.18)' : 'rgba(255, 255, 255, 0.05)',
                borderColor: sortOption === 'size_desc' ? 'rgba(239, 68, 68, 0.45)' : 'rgba(255, 255, 255, 0.1)',
                color: sortOption === 'size_desc' ? '#fca5a5' : '#cbd5e1',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px'
              }}
              title="Sort by largest disk space savings"
            >
              <HardDrive size={13} color={sortOption === 'size_desc' ? '#ef4444' : '#94a3b8'} />
              <span>Largest Redundant Size</span>
            </button>
          </div>

          {/* Full sort dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ArrowUpDown size={14} style={{ color: '#94a3b8' }} />
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Sort duplicates:</span>
            <select
              className="select-styled"
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value)}
              style={{ minWidth: '210px' }}
            >
              <option value="duplicates_desc">Most Duplicates / Takes</option>
              <option value="duplicates_asc">Fewest Duplicates / Takes</option>
              <option value="date_asc">Oldest Photos First (By Age)</option>
              <option value="date_desc">Newest Photos First (By Age)</option>
              <option value="size_desc">Largest Redundant Space</option>
              <option value="size_asc">Smallest Redundant Space</option>
            </select>
          </div>
        </div>
      )}

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
      ) : sortedDuplicateGroups.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '4rem 2rem',
          background: 'rgba(255, 255, 255, 0.02)',
          borderRadius: '16px',
          border: '1px dashed rgba(255, 255, 255, 0.1)',
          maxWidth: '600px',
          margin: '2rem auto'
        }}>
          <Layers size={44} color="#67e8f9" style={{ marginBottom: '1rem' }} />
          <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>
            No Photos in this Category
          </h3>
          <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
            There are currently no clusters matching the "{categoryFilter}" filter.
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setCategoryFilter('all')}
            style={{ fontSize: '0.85rem', padding: '0.4rem 1rem' }}
          >
            View All Categories ({counts.all})
          </button>
        </div>
      ) : (
        <>
          {sortedDuplicateGroups.slice(0, visibleCount).map((group, index) => {
          const primary = group.primary;
          const dups = group.duplicates || [];
          const isExact = group.match_type === 'EXACT_HASH';
          const isBurst = group.match_type === 'BURST_SEQUENCE';
          const matchLabel = isExact 
            ? 'Exact SHA-256 Match' 
            : isBurst 
            ? 'Continuous Burst' 
            : 'Visually Similar Match';
          const groupDate = parseGroupDate(group);
          const groupDateFormatted = formatDate(groupDate);

          return (
            <div key={group.group_id} className="dup-group-card">
              <div className="dup-group-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    padding: '3px 9px',
                    borderRadius: '9999px',
                    background: isExact 
                      ? 'rgba(245, 158, 11, 0.2)' 
                      : isBurst 
                      ? 'rgba(6, 182, 212, 0.2)' 
                      : 'rgba(99, 102, 241, 0.2)',
                    color: isExact 
                      ? '#fde68a' 
                      : isBurst 
                      ? '#67e8f9' 
                      : '#c7d2fe',
                    border: isExact 
                      ? '1px solid rgba(245, 158, 11, 0.4)' 
                      : isBurst 
                      ? '1px solid rgba(6, 182, 212, 0.4)' 
                      : '1px solid rgba(99, 102, 241, 0.4)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    {isBurst ? <Layers size={11} /> : isExact ? <Copy size={11} /> : <Sparkles size={11} />}
                    <span>{matchLabel}</span>
                  </span>
                  <span style={{ fontSize: '0.85rem', color: '#cbd5e1', fontWeight: 600 }}>
                    Group #{index + 1}
                  </span>

                  {/* Prominent count badge */}
                  <span style={{
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    padding: '3px 8px',
                    borderRadius: '9999px',
                    background: isBurst 
                      ? 'rgba(6, 182, 212, 0.15)' 
                      : isExact 
                      ? 'rgba(245, 158, 11, 0.15)' 
                      : 'rgba(99, 102, 241, 0.15)',
                    color: isBurst 
                      ? '#67e8f9' 
                      : isExact 
                      ? '#fde68a' 
                      : '#c7d2fe',
                    border: isBurst 
                      ? '1px solid rgba(6, 182, 212, 0.3)' 
                      : isExact 
                      ? '1px solid rgba(245, 158, 11, 0.3)' 
                      : '1px solid rgba(99, 102, 241, 0.3)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}>
                    {isBurst ? <Camera size={11} /> : <Copy size={11} />}
                    <span>
                      {isBurst 
                        ? `${dups.length} alternative take${dups.length === 1 ? '' : 's'}` 
                        : isExact 
                        ? `${dups.length} duplicate${dups.length === 1 ? '' : 's'} to remove` 
                        : `${dups.length} similar photo${dups.length === 1 ? '' : 's'}`}
                    </span>
                  </span>

                  {/* Prominent age / date badge */}
                  {groupDateFormatted && (
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 500,
                      padding: '3px 8px',
                      borderRadius: '9999px',
                      background: 'rgba(56, 189, 248, 0.12)',
                      color: '#7dd3fc',
                      border: '1px solid rgba(56, 189, 248, 0.25)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}
                    title={`Date taken: ${groupDateFormatted}`}
                    >
                      <Calendar size={11} />
                      <span>{groupDateFormatted}</span>
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{
                    fontSize: '0.8rem',
                    color: isExact ? '#f87171' : isBurst ? '#94a3b8' : '#cbd5e1',
                    fontWeight: 500
                  }}>
                    {isBurst ? 'Savings: ' : 'Wasted: '}{formatFileSize(group.total_wasted_bytes)}
                  </span>
                  
                  {/* Compare Group Studio Action */}
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{
                      fontSize: '0.75rem',
                      padding: '0.3rem 0.75rem',
                      background: isBurst ? 'rgba(6, 182, 212, 0.15)' : 'rgba(56, 189, 248, 0.14)',
                      borderColor: isBurst ? 'rgba(6, 182, 212, 0.4)' : 'rgba(56, 189, 248, 0.4)',
                      color: isBurst ? '#67e8f9' : '#7dd3fc',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '5px'
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setCompareGroup(group);
                      setCompareGroupIndex(index);
                    }}
                    title={isBurst ? "Open full-screen shootout studio to review burst takes and pick your favorites" : "Open full-screen shootout studio to compare, filter, and pick winners"}
                  >
                    <Maximize2 size={13} />
                    <span>{isBurst ? `Compare Burst (${group.total_items})` : `Compare Group (${group.total_items})`}</span>
                  </button>

                  {/* Group Trash Action */}
                  {dups.length > 0 && (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{
                        fontSize: '0.75rem',
                        padding: '0.3rem 0.75rem',
                        background: isBurst ? 'rgba(239, 68, 68, 0.12)' : 'rgba(239, 68, 68, 0.15)',
                        borderColor: 'rgba(239, 68, 68, 0.35)',
                        color: '#fca5a5'
                      }}
                      onClick={(e) => handleGroupTrashClick(e, group)}
                      disabled={actionInProgress}
                      title={isBurst ? "Keep the Top Pick and move unchosen burst takes to Trash" : "Move all duplicate copies in this group to Trash"}
                    >
                      <Trash2 size={13} />
                      <span>{isBurst ? `Keep Top Pick (Trash ${dups.length})` : `Trash Duplicates (${dups.length})`}</span>
                    </button>
                  )}

                  {/* Keep All */}
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.75rem', padding: '0.3rem 0.75rem' }}
                    onClick={(e) => handleDismissGroup(e, group.group_id)}
                    disabled={dismissingGroupId === group.group_id || actionInProgress}
                    title="Keep all files and unmark from duplicates/bursts"
                  >
                    <CheckCheck size={13} color="#10b981" />
                    <span>Keep All</span>
                  </button>
                </div>
              </div>

              <div className="dup-items-row">
                {/* Primary Keeper / Top Pick */}
                {primary && (
                  <div
                    className="dup-item-card is-primary"
                    onClick={() => onSelectPhoto(primary)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="primary-badge" style={isBurst ? {
                      background: 'linear-gradient(135deg, #059669 0%, #0d9488 100%)',
                      color: '#ffffff',
                      border: '1px solid rgba(52, 211, 153, 0.4)'
                    } : {}}>
                      <Star size={10} fill={isBurst ? "#fef08a" : "#ffffff"} color={isBurst ? "#fef08a" : "#ffffff"} style={{ display: 'inline', marginRight: '4px' }} />
                      {isBurst ? 'Top Pick' : 'Primary Keeper'}
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
                      {primary.date_taken && (
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '2px 0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Calendar size={11} color="#64748b" />
                          <span>{formatDateTime(primary.date_taken)}</span>
                        </div>
                      )}
                      <div style={{ fontSize: '0.7rem', color: '#64748b', wordBreak: 'break-all' }}>
                        {primary.file_path}
                      </div>
                      <div style={{ marginTop: '6px', fontSize: '0.72rem', color: '#a7f3d0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <ShieldCheck size={13} color="#34d399" />
                        <span>{isBurst ? 'Top Pick • Preserved in Main Library' : 'Preserved in Main Library'}</span>
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
                      {dup.date_taken && (
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8', margin: '2px 0', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Calendar size={11} color="#64748b" />
                          <span>{formatDateTime(dup.date_taken)}</span>
                        </div>
                      )}
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

          {visibleCount < sortedDuplicateGroups.length && (
            <div style={{ textAlign: 'center', margin: '2rem 0' }}>
              <button
                type="button"
                className="btn-secondary"
                style={{ padding: '0.6rem 1.5rem', fontSize: '0.875rem' }}
                onClick={() => setVisibleCount((prev) => prev + 20)}
              >
                Show More Duplicate Groups ({sortedDuplicateGroups.length - visibleCount} remaining)
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
          groups={sortedDuplicateGroups}
          onNavigateGroup={(nextIdx) => {
            if (nextIdx >= 0 && nextIdx < sortedDuplicateGroups.length) {
              setCompareGroup(sortedDuplicateGroups[nextIdx]);
              setCompareGroupIndex(nextIdx);
            }
          }}
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
