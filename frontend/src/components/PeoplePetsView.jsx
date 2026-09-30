import React, { useState, useEffect, useCallback } from 'react';
import {
  User,
  Heart,
  Sparkles,
  Check,
  X,
  Plus,
  Search,
  Scan,
  CheckCheck,
  RefreshCw,
  MoreVertical,
  Trash2,
  Edit2,
  Calendar,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  Image as ImageIcon,
  Tag,
  Camera,
  Layers
} from 'lucide-react';
import {
  fetchEntities,
  createEntity,
  updateEntity,
  deleteEntity,
  fetchPendingReviews,
  fetchUnassignedBoxes,
  assignBoxToEntity,
  setEntityAvatar,
  confirmBox,
  rejectBox,
  confirmAllPendingReviews,
  startPeoplePetsScan,
  fetchPeoplePetsScanStatus
} from '../api';

export default function PeoplePetsView({ onSelectEntity, onOpenLightboxPhoto }) {
  const [viewMode, setViewMode] = useState('hub'); // 'hub' (Profiles) or 'tagger' (Face Tagger Studio)
  const [entities, setEntities] = useState([]);
  const [pendingReviews, setPendingReviews] = useState([]);
  const [totalPending, setTotalPending] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('ALL'); // 'ALL', 'PERSON', 'PET'
  const [searchQuery, setSearchQuery] = useState('');

  // Unassigned detected boxes state (Face Tagger Studio)
  const [unassignedBoxes, setUnassignedBoxes] = useState([]);
  const [totalUnassigned, setTotalUnassigned] = useState(0);
  const [unassignedTypeFilter, setUnassignedTypeFilter] = useState('ALL');
  const [taggerTargetEntity, setTaggerTargetEntity] = useState(null); // If user clicked "Assign Photo to Ron"
  const [activeTagInputBoxId, setActiveTagInputBoxId] = useState(null);
  const [inlineTagName, setInlineTagName] = useState('');
  const [inlineTagType, setInlineTagType] = useState('PERSON');
  const [taggingSuccessToast, setTaggingSuccessToast] = useState(null);

  // Scanning progress state
  const [scanStatus, setScanStatus] = useState(null);
  const [isScanning, setIsScanning] = useState(false);

  // Review Modal State
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [isProcessingAction, setIsProcessingAction] = useState(false);
  const [isLoadingMorePending, setIsLoadingMorePending] = useState(false);

  // Add Entity Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newEntityName, setNewEntityName] = useState('');
  const [newEntityType, setNewEntityType] = useState('PERSON');

  // Edit Entity Modal State
  const [editingEntity, setEditingEntity] = useState(null);
  const [editName, setEditName] = useState('');
  const [editType, setEditType] = useState('PERSON');

  // Load all entities, pending reviews, and unassigned detected boxes
  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchEntities(),
      fetchPendingReviews({ limit: 100 }),
      fetchUnassignedBoxes({ limit: 80, boxType: unassignedTypeFilter })
    ])
      .then(([entitiesData, pendingData, unassignedData]) => {
        setEntities(entitiesData || []);
        setPendingReviews(pendingData.items || []);
        setTotalPending(pendingData.total || 0);
        setUnassignedBoxes(unassignedData.items || []);
        setTotalUnassigned(unassignedData.total || 0);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error loading people & pets data:', err);
        setLoading(false);
      });
  }, [unassignedTypeFilter]);

  const handleLoadMorePending = async () => {
    if (isLoadingMorePending || pendingReviews.length >= totalPending) return;
    setIsLoadingMorePending(true);
    try {
      const page = await fetchPendingReviews({ limit: 100, offset: pendingReviews.length });
      setPendingReviews((current) => {
        const existingIds = new Set(current.map((item) => item.id));
        return [...current, ...(page.items || []).filter((item) => !existingIds.has(item.id))];
      });
      setTotalPending(page.total || 0);
    } catch (err) {
      alert('Failed to load more suggestions: ' + err.message);
    } finally {
      setIsLoadingMorePending(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Scan progress polling
  useEffect(() => {
    let interval;
    if (isScanning) {
      interval = setInterval(() => {
        fetchPeoplePetsScanStatus()
          .then((status) => {
            setScanStatus(status);
            if (!status.is_scanning) {
              setIsScanning(false);
              loadData();
            }
          })
          .catch(console.error);
      }, 1500);
    }
    return () => clearInterval(interval);
  }, [isScanning, loadData]);

  const handleStartScan = async () => {
    try {
      await startPeoplePetsScan();
      setIsScanning(true);
    } catch (err) {
      alert('Failed to start scan: ' + err.message);
    }
  };

  // Confirmation actions
  const handleConfirmSingle = async (boxId, entityId) => {
    try {
      setIsProcessingAction(true);
      await confirmBox(boxId, entityId);
      setPendingReviews((prev) => prev.filter((b) => b.id !== boxId));
      setTotalPending((prev) => Math.max(0, prev - 1));
      loadData();
      if (reviewIndex >= pendingReviews.length - 1) {
        setReviewIndex(Math.max(0, pendingReviews.length - 2));
      }
    } catch (err) {
      alert('Failed to confirm: ' + err.message);
    } finally {
      setIsProcessingAction(false);
    }
  };

  const handleRejectSingle = async (boxId) => {
    try {
      setIsProcessingAction(true);
      await rejectBox(boxId);
      setPendingReviews((prev) => prev.filter((b) => b.id !== boxId));
      setTotalPending((prev) => Math.max(0, prev - 1));
      if (reviewIndex >= pendingReviews.length - 1) {
        setReviewIndex(Math.max(0, pendingReviews.length - 2));
      }
    } catch (err) {
      alert('Failed to reject: ' + err.message);
    } finally {
      setIsProcessingAction(false);
    }
  };

  const handleConfirmAll = async () => {
    if (totalPending === 0) return;
    try {
      setIsProcessingAction(true);
      await confirmAllPendingReviews();
      setPendingReviews([]);
      setTotalPending(0);
      setIsReviewModalOpen(false);
      loadData();
    } catch (err) {
      alert('Failed to confirm all: ' + err.message);
    } finally {
      setIsProcessingAction(false);
    }
  };

  // Assign Box to Entity (From Face Tagger Studio)
  const handleAssignBox = async (boxId, targetName, targetType = 'PERSON') => {
    if (!targetName || !targetName.trim()) return;
    const cleanName = targetName.trim();
    try {
      setIsProcessingAction(true);
      await assignBoxToEntity(boxId, {
        entityName: cleanName,
        entityType: targetType,
        setAsAvatar: true
      });

      // Remove from unassigned list
      setUnassignedBoxes((prev) => prev.filter((b) => b.id !== boxId));
      setTotalUnassigned((prev) => Math.max(0, prev - 1));
      setActiveTagInputBoxId(null);
      setInlineTagName('');
      
      // Toast notification
      setTaggingSuccessToast(`Tagged face as "${cleanName}" and set as profile picture!`);
      setTimeout(() => setTaggingSuccessToast(null), 4000);

      loadData();

      // If we were targeting a specific entity (like Ron), we can exit target mode or stay
      if (taggerTargetEntity && taggerTargetEntity.name.toLowerCase() === cleanName.toLowerCase()) {
        // Return to profiles hub after assigning Ron's avatar
        setTimeout(() => {
          setTaggerTargetEntity(null);
          setViewMode('hub');
        }, 1200);
      }
    } catch (err) {
      alert('Failed to assign tag: ' + err.message);
    } finally {
      setIsProcessingAction(false);
    }
  };

  // Entity Creation & Management
  const handleCreateEntity = async (e) => {
    e.preventDefault();
    if (!newEntityName.trim()) return;
    try {
      const created = await createEntity(newEntityName.trim(), newEntityType);
      setNewEntityName('');
      setIsAddModalOpen(false);
      loadData();

      // Ask if they want to assign a photo right now
      if (confirm(`Created profile "${created.name}". Would you like to select a face photo for ${created.name} now?`)) {
        setTaggerTargetEntity(created);
        setViewMode('tagger');
      }
    } catch (err) {
      alert(err.message);
    }
  };

  const handleUpdateEntity = async (e) => {
    e.preventDefault();
    if (!editingEntity || !editName.trim()) return;
    try {
      await updateEntity(editingEntity.id, {
        name: editName.trim(),
        entity_type: editType
      });
      setEditingEntity(null);
      loadData();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDeleteEntity = async (entityId, entityName) => {
    if (!confirm(`Delete profile "${entityName}"? (Photos remain intact, only identity tags are untagged)`)) return;
    try {
      await deleteEntity(entityId);
      loadData();
    } catch (err) {
      alert('Failed to delete entity: ' + err.message);
    }
  };

  // Keyboard shortcut support in Review Modal
  useEffect(() => {
    if (!isReviewModalOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setIsReviewModalOpen(false);
      } else if (e.key === 'Enter') {
        const current = pendingReviews[reviewIndex];
        if (current) handleConfirmSingle(current.id, current.entity_id);
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        const current = pendingReviews[reviewIndex];
        if (current) handleRejectSingle(current.id);
      } else if (e.key === 'ArrowRight') {
        setReviewIndex((prev) => Math.min(pendingReviews.length - 1, prev + 1));
      } else if (e.key === 'ArrowLeft') {
        setReviewIndex((prev) => Math.max(0, prev - 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isReviewModalOpen, pendingReviews, reviewIndex]);

  // Filtered entities list
  const filteredEntities = entities.filter((ent) => {
    const matchesType =
      filterType === 'ALL' || ent.entity_type === filterType;
    const matchesQuery =
      !searchQuery ||
      ent.name.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesType && matchesQuery;
  });

  const activeReviewItem = pendingReviews[reviewIndex];
  const reviewConfidence = activeReviewItem && Number.isFinite(activeReviewItem.match_confidence)
    ? Math.round(Math.max(0, Math.min(1, activeReviewItem.match_confidence)) * 100)
    : null;

  return (
    <div className="people-pets-view">
      {/* Top Banner & Hub Controls */}
      <div className="view-header">
        <div>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.6rem', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>People & Pets</span>
            <span className="brand-badge" style={{ background: 'rgba(99, 102, 241, 0.2)', color: '#a5b4fc', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
              Visual Embeddings
            </span>
          </h2>
          <p style={{ fontSize: '0.875rem', color: '#94a3b8', marginTop: '4px' }}>
            Name loved ones and pets. LuminaPhoto automatically identifies strong matches in new photos for your confirmation.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn-secondary"
            onClick={handleStartScan}
            disabled={isScanning}
            title="Scan library for untagged people and pets"
          >
            <Scan size={15} />
            <span>{isScanning ? `Scanning (${scanStatus?.processed || 0}/${scanStatus?.total || 0})` : 'Scan Library for Faces & Pets'}</span>
          </button>

          <button
            className="btn-primary"
            onClick={() => setIsAddModalOpen(true)}
          >
            <Plus size={16} />
            <span>Add Person or Pet</span>
          </button>
        </div>
      </div>

      {/* Real-time Scan Progress Bar */}
      {isScanning && scanStatus && (
        <div className="scan-progress-banner glass-card" style={{ marginBottom: '1.5rem', padding: '1rem', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px', color: '#c7d2fe' }}>
            <span>Scanning library for faces and pets...</span>
            <span>{scanStatus.progress_percent}% ({scanStatus.processed} / {scanStatus.total} photos)</span>
          </div>
          <div style={{ height: '6px', width: '100%', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '3px', overflow: 'hidden' }}>
            <div
              style={{
                height: '100%',
                width: `${scanStatus.progress_percent}%`,
                background: 'linear-gradient(90deg, #6366f1, #10b981)',
                transition: 'width 0.3s ease'
              }}
            />
          </div>
          {scanStatus.matches_found > 0 && (
            <div style={{ fontSize: '0.78rem', color: '#a7f3d0', marginTop: '6px' }}>
              ✨ Found {scanStatus.matches_found} high-confidence match suggestions ready for review!
            </div>
          )}
        </div>
      )}

      {/* Toast Notification */}
      {taggingSuccessToast && (
        <div
          className="glass-card"
          style={{
            marginBottom: '1rem',
            padding: '0.75rem 1.25rem',
            background: 'rgba(16, 185, 129, 0.2)',
            border: '1px solid rgba(16, 185, 129, 0.5)',
            color: '#a7f3d0',
            fontSize: '0.875rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            borderRadius: '8px',
            animation: 'fadeIn 0.2s ease'
          }}
        >
          <Check size={18} color="#34d399" />
          <span>{taggingSuccessToast}</span>
        </div>
      )}

      {/* Review Queue Banner (Google-Grade Suggestion Tray) */}
      {totalPending > 0 && (
        <div className="review-queue-card glass-card">
          <div className="review-queue-content">
            <div className="review-queue-icon">
              <Sparkles size={24} color="#fbbf24" />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: '1.05rem', color: '#ffffff' }}>
                {totalPending} Strong Match{totalPending > 1 ? 'es' : ''} Ready for Confirmation
              </div>
              <div style={{ fontSize: '0.82rem', color: '#cbd5e1', marginTop: '2px' }}>
                Strict high-confidence auto-detection found matches. Confirm or reject each suggestion below.
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="btn-primary"
              style={{ background: '#059669', borderColor: '#10b981' }}
              onClick={handleConfirmAll}
              disabled={isProcessingAction}
            >
              <CheckCheck size={16} />
              <span>Confirm All ({totalPending})</span>
            </button>
            <button
              className="btn-secondary"
              style={{ borderColor: 'rgba(245, 158, 11, 0.4)', color: '#fde68a' }}
              onClick={() => {
                setReviewIndex(0);
                setIsReviewModalOpen(true);
              }}
            >
              <span>Review Loaded ({pendingReviews.length})</span>
              <ChevronRight size={15} />
            </button>
            {pendingReviews.length < totalPending && (
              <button
                className="btn-secondary"
                onClick={handleLoadMorePending}
                disabled={isLoadingMorePending}
              >
                {isLoadingMorePending ? 'Loading...' : `Load 100 More (${totalPending - pendingReviews.length} left)`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* View Mode Switcher (Profiles Hub vs Face Tagger Studio) */}
      <div className="view-mode-tabs" style={{ display: 'flex', gap: '10px', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.75rem' }}>
        <button
          className={`btn-secondary ${viewMode === 'hub' ? 'active-filter-btn' : ''}`}
          style={{
            padding: '0.5rem 1.25rem',
            fontSize: '0.85rem',
            borderColor: viewMode === 'hub' ? '#6366f1' : 'rgba(255,255,255,0.1)',
            color: viewMode === 'hub' ? '#ffffff' : '#94a3b8'
          }}
          onClick={() => {
            setViewMode('hub');
            setTaggerTargetEntity(null);
          }}
        >
          <User size={15} />
          <span>Profiles ({entities.length})</span>
        </button>

        <button
          className={`btn-secondary ${viewMode === 'tagger' ? 'active-filter-btn' : ''}`}
          style={{
            padding: '0.5rem 1.25rem',
            fontSize: '0.85rem',
            borderColor: viewMode === 'tagger' ? '#6366f1' : 'rgba(255,255,255,0.1)',
            color: viewMode === 'tagger' ? '#ffffff' : '#94a3b8'
          }}
          onClick={() => setViewMode('tagger')}
        >
          <Tag size={15} />
          <span>Tag Faces & Pets Studio</span>
          {totalUnassigned > 0 && (
            <span className="nav-badge" style={{ background: 'rgba(99, 102, 241, 0.3)', color: '#c7d2fe', marginLeft: '4px' }}>
              {totalUnassigned} ready
            </span>
          )}
        </button>
      </div>

      {/* ========================================================================= */}
      {/* MODE 1: PROFILES HUB                                                      */}
      {/* ========================================================================= */}
      {viewMode === 'hub' && (
        <>
          {/* Filter and Search Bar */}
          <div className="people-filters-bar">
            {/* Chips */}
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                className={`btn-secondary ${filterType === 'ALL' ? 'active-filter-btn' : ''}`}
                onClick={() => setFilterType('ALL')}
              >
                <span>All ({entities.length})</span>
              </button>
              <button
                className={`btn-secondary ${filterType === 'PERSON' ? 'active-filter-btn' : ''}`}
                onClick={() => setFilterType('PERSON')}
              >
                <User size={14} />
                <span>People</span>
              </button>
              <button
                className={`btn-secondary ${filterType === 'PET' ? 'active-filter-btn' : ''}`}
                onClick={() => setFilterType('PET')}
              >
                <Heart size={14} />
                <span>Pets</span>
              </button>
            </div>

            {/* Search */}
            <div className="search-input-wrapper" style={{ maxWidth: '280px', width: '100%' }}>
              <Search size={14} className="search-icon" />
              <input
                type="text"
                placeholder="Search by name..."
                className="input-styled"
                style={{ width: '100%', paddingLeft: '2rem', fontSize: '0.82rem' }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {/* Entities Cards Grid */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '4rem 0', color: '#94a3b8' }}>
              <RefreshCw size={24} className="spin-animation" style={{ margin: '0 auto 1rem' }} />
              <div>Loading People & Pets catalog...</div>
            </div>
          ) : filteredEntities.length === 0 ? (
            <div className="empty-entities-state glass-card">
              <div className="empty-icon-circle">
                <User size={36} color="#6366f1" />
              </div>
              <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff', marginBottom: '0.5rem' }}>
                No People or Pets Tagged Yet
              </h3>
              <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '440px', margin: '0 auto 1.5rem', lineHeight: '1.5' }}>
                Create profiles for loved ones and pets, or switch to the <strong>Tag Faces & Pets Studio</strong> to browse all detected faces and name them with 1 click.
              </p>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                <button className="btn-primary" onClick={() => setIsAddModalOpen(true)}>
                  <Plus size={15} />
                  <span>Create Person or Pet</span>
                </button>
                <button className="btn-secondary" onClick={() => setViewMode('tagger')}>
                  <Tag size={15} />
                  <span>Open Face Tagger Studio</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="entities-grid">
              {filteredEntities.map((ent) => {
                const isPet = ent.entity_type === 'PET';
                const avatarBoxId = ent.avatar_box_id || ent.representative_box_id;
                const avatarUrl = avatarBoxId ? `/api/boxes/${avatarBoxId}/crop` : null;

                return (
                  <div
                    key={ent.id}
                    className="entity-card glass-card"
                    onClick={() => onSelectEntity && onSelectEntity(ent)}
                  >
                    {/* Avatar */}
                    <div className="entity-avatar-container">
                      {avatarUrl ? (
                        <img
                          src={avatarUrl}
                          alt={ent.name}
                          className="entity-avatar-img"
                          loading="lazy"
                        />
                      ) : (
                        <div className="entity-avatar-placeholder">
                          {isPet ? <Heart size={26} color="#f472b6" /> : <User size={26} color="#818cf8" />}
                        </div>
                      )}

                      {/* Pending Badge on Avatar */}
                      {ent.pending_count > 0 && (
                        <span
                          className="entity-pending-badge"
                          title={`${ent.pending_count} suggestions waiting for review`}
                        >
                          {ent.pending_count}
                        </span>
                      )}
                    </div>

                    {/* Info */}
                    <div className="entity-info">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', justifyContent: 'center' }}>
                        <span className="entity-name">{ent.name}</span>
                        {isPet && <Heart size={12} color="#f472b6" />}
                      </div>
                      <div className="entity-count">
                        {ent.total_photos || 0} photo{ent.total_photos !== 1 ? 's' : ''}
                      </div>

                      {/* Prominent Button to Assign Photo if avatar is missing */}
                      {!avatarUrl && (
                        <button
                          className="btn-secondary"
                          style={{
                            marginTop: '8px',
                            fontSize: '0.72rem',
                            padding: '3px 8px',
                            borderColor: 'rgba(99, 102, 241, 0.4)',
                            color: '#a5b4fc',
                            borderRadius: '9999px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setTaggerTargetEntity(ent);
                            setViewMode('tagger');
                          }}
                          title={`Pick a face photo for ${ent.name}`}
                        >
                          <Camera size={11} />
                          <span>Assign Photo</span>
                        </button>
                      )}
                    </div>

                    {/* 3-Dots Action Menu */}
                    <div
                      className="entity-actions-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingEntity(ent);
                        setEditName(ent.name);
                        setEditType(ent.entity_type);
                      }}
                      title="Edit or Delete Profile"
                    >
                      <MoreVertical size={14} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ========================================================================= */}
      {/* MODE 2: TAG FACES & PETS STUDIO                                           */}
      {/* ========================================================================= */}
      {viewMode === 'tagger' && (
        <div className="tagger-studio-container">
          {/* Target Entity Banner if user is assigning avatar to e.g. Ron */}
          {taggerTargetEntity ? (
            <div
              className="glass-card"
              style={{
                marginBottom: '1.5rem',
                padding: '1rem 1.5rem',
                background: 'rgba(99, 102, 241, 0.18)',
                border: '1px solid #6366f1',
                borderRadius: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '10px'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{ width: '38px', height: '38px', borderRadius: '50%', background: 'rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Camera size={20} color="#818cf8" />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '1rem', color: '#ffffff' }}>
                    Select Face Photo for <span style={{ color: '#38bdf8' }}>{taggerTargetEntity.name}</span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#cbd5e1', marginTop: '2px' }}>
                    Click <strong>"Assign to {taggerTargetEntity.name}"</strong> on any face below to set it as their profile picture and tag them.
                  </div>
                </div>
              </div>

              <button
                className="btn-secondary"
                style={{ fontSize: '0.8rem', padding: '0.4rem 0.85rem' }}
                onClick={() => setTaggerTargetEntity(null)}
              >
                <span>Cancel Target Mode</span>
              </button>
            </div>
          ) : (
            <div style={{ marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
              <div>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#ffffff' }}>
                  Detected Faces & Pets ({totalUnassigned} Ready to Tag)
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '2px' }}>
                  Browse detected faces and pets across your photos. Click to assign to <strong>Ron</strong> or other people with 1 click.
                </p>
              </div>

              {/* Type Filter */}
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  className={`btn-secondary ${unassignedTypeFilter === 'ALL' ? 'active-filter-btn' : ''}`}
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
                  onClick={() => setUnassignedTypeFilter('ALL')}
                >
                  <span>All</span>
                </button>
                <button
                  className={`btn-secondary ${unassignedTypeFilter === 'FACE' ? 'active-filter-btn' : ''}`}
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
                  onClick={() => setUnassignedTypeFilter('FACE')}
                >
                  <User size={13} />
                  <span>Faces</span>
                </button>
                <button
                  className={`btn-secondary ${unassignedTypeFilter === 'PET' ? 'active-filter-btn' : ''}`}
                  style={{ padding: '0.35rem 0.75rem', fontSize: '0.78rem' }}
                  onClick={() => setUnassignedTypeFilter('PET')}
                >
                  <Heart size={13} />
                  <span>Pets</span>
                </button>
              </div>
            </div>
          )}

          {/* Unassigned Crops Grid */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '4rem 0', color: '#94a3b8' }}>
              <RefreshCw size={24} className="spin-animation" style={{ margin: '0 auto 1rem' }} />
              <div>Loading detected faces and pets...</div>
            </div>
          ) : unassignedBoxes.length === 0 ? (
            <div className="empty-entities-state glass-card">
              <div className="empty-icon-circle">
                <Scan size={36} color="#6366f1" />
              </div>
              <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff', marginBottom: '0.5rem' }}>
                No Untagged Faces or Pets Waiting
              </h3>
              <p style={{ fontSize: '0.85rem', color: '#94a3b8', maxWidth: '440px', margin: '0 auto 1.5rem', lineHeight: '1.5' }}>
                Run a scan across your photo library to detect faces and pets automatically. They will appear here ready to be tagged.
              </p>
              <button className="btn-primary" onClick={handleStartScan} disabled={isScanning}>
                <Scan size={15} />
                <span>{isScanning ? 'Scanning...' : 'Scan Photos for Faces & Pets'}</span>
              </button>
            </div>
          ) : (
            <div className="unassigned-crops-grid">
              {unassignedBoxes.map((box) => {
                const isPet = box.box_type === 'PET';
                const isInlineActive = activeTagInputBoxId === box.id;

                return (
                  <div key={box.id} className="tagger-crop-card glass-card">
                    {/* Crop Image */}
                    <div className="tagger-crop-img-wrap">
                      <img
                        src={`/api/boxes/${box.id}/crop`}
                        alt="Detected crop"
                        className="tagger-crop-img"
                        loading="lazy"
                      />
                      <span className="tagger-crop-badge">
                        {isPet ? <Heart size={10} color="#f472b6" /> : <User size={10} color="#67e8f9" />}
                        <span>{box.label || (isPet ? 'Pet' : 'Face')}</span>
                      </span>
                    </div>

                    {/* Meta */}
                    <div style={{ width: '100%', marginBottom: '8px', textAlign: 'center' }}>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={box.file_name}>
                        {box.file_name}
                      </div>
                      {box.date_taken && (
                        <div style={{ fontSize: '0.68rem', color: '#64748b', marginTop: '2px' }}>
                          {box.date_taken.split(' ')[0]}
                        </div>
                      )}
                    </div>

                    {/* 1. If Target Mode is Active (e.g. Assign to Ron) */}
                    {taggerTargetEntity ? (
                      <button
                        className="btn-primary"
                        style={{
                          width: '100%',
                          fontSize: '0.78rem',
                          padding: '0.4rem',
                          background: '#059669',
                          borderColor: '#10b981'
                        }}
                        onClick={() => handleAssignBox(box.id, taggerTargetEntity.name, taggerTargetEntity.entity_type)}
                        disabled={isProcessingAction}
                      >
                        <Check size={13} />
                        <span>Assign to {taggerTargetEntity.name}</span>
                      </button>
                    ) : isInlineActive ? (
                      /* 2. Inline Naming Dropdown / Input */
                      <div className="inline-tagger-box" style={{ width: '100%' }}>
                        <div style={{ position: 'relative', marginBottom: '6px' }}>
                          <input
                            type="text"
                            placeholder="Name (e.g. Ron)..."
                            className="input-styled"
                            style={{ width: '100%', fontSize: '0.75rem', padding: '4px 6px' }}
                            value={inlineTagName}
                            onChange={(e) => setInlineTagName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleAssignBox(box.id, inlineTagName, inlineTagType);
                              if (e.key === 'Escape') setActiveTagInputBoxId(null);
                            }}
                            autoFocus
                          />

                          {/* Quick suggestions from existing entities */}
                          {entities.length > 0 && (
                            <div
                              style={{
                                position: 'absolute',
                                top: '100%',
                                left: 0,
                                right: 0,
                                background: '#0f172a',
                                border: '1px solid rgba(255,255,255,0.2)',
                                borderRadius: '4px',
                                maxHeight: '120px',
                                overflowY: 'auto',
                                zIndex: 120,
                                marginTop: '2px',
                                boxShadow: '0 8px 20px rgba(0,0,0,0.6)'
                              }}
                            >
                              {entities
                                .filter((ent) =>
                                  !inlineTagName ||
                                  ent.name.toLowerCase().includes(inlineTagName.toLowerCase())
                                )
                                .slice(0, 6)
                                .map((ent) => (
                                  <div
                                    key={ent.id}
                                    className="suggestion-item"
                                    style={{
                                      padding: '5px 8px',
                                      fontSize: '0.75rem',
                                      cursor: 'pointer',
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'space-between',
                                      color: '#ffffff',
                                      borderBottom: '1px solid rgba(255,255,255,0.05)'
                                    }}
                                    onClick={() => handleAssignBox(box.id, ent.name, ent.entity_type)}
                                  >
                                    <span style={{ fontWeight: 600 }}>{ent.name}</span>
                                    <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
                                      {ent.entity_type}
                                    </span>
                                  </div>
                                ))}
                            </div>
                          )}
                        </div>

                        <div style={{ display: 'flex', gap: '4px' }}>
                          <button
                            className="btn-secondary"
                            style={{ flex: 1, padding: '3px 6px', fontSize: '0.7rem' }}
                            onClick={() => setActiveTagInputBoxId(null)}
                          >
                            Cancel
                          </button>
                          <button
                            className="btn-primary"
                            style={{ flex: 1, padding: '3px 6px', fontSize: '0.7rem' }}
                            onClick={() => handleAssignBox(box.id, inlineTagName, inlineTagType)}
                            disabled={!inlineTagName.trim() || isProcessingAction}
                          >
                            Tag
                          </button>
                        </div>
                      </div>
                    ) : (
                      /* 3. Default Button: Click to Tag */
                      <button
                        className="btn-secondary"
                        style={{
                          width: '100%',
                          fontSize: '0.75rem',
                          padding: '0.35rem 0.5rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '4px'
                        }}
                        onClick={() => {
                          setActiveTagInputBoxId(box.id);
                          setInlineTagName('');
                          setInlineTagType(isPet ? 'PET' : 'PERSON');
                        }}
                      >
                        <Tag size={12} />
                        <span>Name Face</span>
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Review & Confirmation Modal (Interactive Carousel) */}
      {isReviewModalOpen && activeReviewItem && (
        <div className="modal-overlay" onClick={() => setIsReviewModalOpen(false)}>
          <div
            className="modal-card review-modal-card"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: '620px' }}
          >
            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Sparkles size={18} color="#fbbf24" />
                <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff' }}>
                  Confirm Auto-Tag Suggestion
                </h3>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                  {reviewIndex + 1} of {pendingReviews.length}
                </span>
                <button className="btn-secondary" style={{ padding: '4px' }} onClick={() => setIsReviewModalOpen(false)}>
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Side-by-side Visual Inspection */}
            <div className="review-split-preview">
              {/* Face / Pet Crop */}
              <div className="review-crop-container">
                <img
                  src={`/api/boxes/${activeReviewItem.id}/crop`}
                  alt="Detected face crop"
                  className="review-crop-img"
                />
                <div className="review-crop-label">
                  Detected {activeReviewItem.label || 'Subject'}
                </div>
              </div>

              {/* Full Photo Context */}
              <div className="review-photo-container">
                <img
                  src={`/api/photos/${activeReviewItem.photo_id}/preview`}
                  alt={activeReviewItem.file_name}
                  className="review-photo-preview"
                />
                <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {activeReviewItem.file_name}
                </div>
              </div>
            </div>

            {/* Match Confidence & Details */}
            <div className="review-details-box glass-card" style={{ marginTop: '1rem', padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
                  Match Confidence:
                </span>
                <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#34d399' }}>
                  {reviewConfidence === null ? 'Not available' : `${reviewConfidence}% Match`}
                </span>
              </div>

              {/* Meter bar */}
              <div style={{ height: '6px', width: '100%', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden', marginBottom: '10px' }}>
                <div
                  style={{
                    height: '100%',
                    width: `${reviewConfidence ?? 0}%`,
                    background: 'linear-gradient(90deg, #10b981, #34d399)'
                  }}
                />
              </div>

              <div style={{ fontSize: '1.05rem', fontWeight: 600, color: '#ffffff', textAlign: 'center' }}>
                Is this <span style={{ color: '#38bdf8' }}>{activeReviewItem.entity_name}</span>?
              </div>
            </div>

            {/* Keyboard shortcut hint */}
            <div style={{ fontSize: '0.72rem', color: '#64748b', textAlign: 'center', margin: '0.75rem 0' }}>
              Tip: Press <kbd style={{ background: '#1e293b', padding: '2px 6px', borderRadius: '4px' }}>Enter</kbd> to confirm, <kbd style={{ background: '#1e293b', padding: '2px 6px', borderRadius: '4px' }}>Backspace</kbd> to reject, or <kbd style={{ background: '#1e293b', padding: '2px 6px', borderRadius: '4px' }}>← / →</kbd> to browse.
            </div>

            {/* Action Buttons */}
            <div style={{ display: 'flex', gap: '10px', justifyContent: 'space-between', marginTop: '0.5rem' }}>
              <button
                className="btn-secondary"
                style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                onClick={() => handleRejectSingle(activeReviewItem.id)}
                disabled={isProcessingAction}
              >
                <X size={15} />
                <span>Not {activeReviewItem.entity_name}</span>
              </button>

              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  className="btn-primary"
                  style={{ background: '#059669', borderColor: '#10b981', padding: '0.5rem 1.25rem' }}
                  onClick={() => handleConfirmSingle(activeReviewItem.id, activeReviewItem.entity_id)}
                  disabled={isProcessingAction}
                >
                  <Check size={16} />
                  <span>Confirm Tag</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Entity Modal */}
      {isAddModalOpen && (
        <div className="modal-overlay" onClick={() => setIsAddModalOpen(false)}>
          <div className="modal-card" style={{ maxWidth: '400px' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff', marginBottom: '1rem' }}>
              Add Person or Pet
            </h3>
            <form onSubmit={handleCreateEntity}>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '1rem' }}>
                <button
                  type="button"
                  className={`btn-secondary ${newEntityType === 'PERSON' ? 'active-filter-btn' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setNewEntityType('PERSON')}
                >
                  <User size={14} />
                  <span>Person</span>
                </button>
                <button
                  type="button"
                  className={`btn-secondary ${newEntityType === 'PET' ? 'active-filter-btn' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setNewEntityType('PET')}
                >
                  <Heart size={14} />
                  <span>Pet</span>
                </button>
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ fontSize: '0.8rem', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Name
                </label>
                <input
                  type="text"
                  placeholder={newEntityType === 'PERSON' ? 'e.g. Ron, Alice, Emma...' : 'e.g. Buddy, Max...'}
                  className="input-styled"
                  style={{ width: '100%' }}
                  value={newEntityName}
                  onChange={(e) => setNewEntityName(e.target.value)}
                  autoFocus
                  required
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                <button type="button" className="btn-secondary" onClick={() => setIsAddModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={!newEntityName.trim()}>
                  Create Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Entity Modal */}
      {editingEntity && (
        <div className="modal-overlay" onClick={() => setEditingEntity(null)}>
          <div className="modal-card" style={{ maxWidth: '420px' }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff', marginBottom: '1rem' }}>
              Edit Profile
            </h3>
            <form onSubmit={handleUpdateEntity}>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '1rem' }}>
                <button
                  type="button"
                  className={`btn-secondary ${editType === 'PERSON' ? 'active-filter-btn' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setEditType('PERSON')}
                >
                  <User size={14} />
                  <span>Person</span>
                </button>
                <button
                  type="button"
                  className={`btn-secondary ${editType === 'PET' ? 'active-filter-btn' : ''}`}
                  style={{ flex: 1 }}
                  onClick={() => setEditType('PET')}
                >
                  <Heart size={14} />
                  <span>Pet</span>
                </button>
              </div>

              <div style={{ marginBottom: '1.25rem' }}>
                <label style={{ fontSize: '0.8rem', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Name
                </label>
                <input
                  type="text"
                  className="input-styled"
                  style={{ width: '100%' }}
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  required
                />
              </div>

              {/* Profile Photo Controls */}
              <div style={{ padding: '0.75rem', background: 'rgba(255, 255, 255, 0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', marginBottom: '1.25rem' }}>
                <div style={{ fontSize: '0.8rem', color: '#cbd5e1', fontWeight: 600, marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Camera size={14} color="#818cf8" />
                  <span>Profile Photo</span>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                    onClick={() => {
                      const ent = editingEntity;
                      setEditingEntity(null);
                      setTaggerTargetEntity(ent);
                      setViewMode('tagger');
                    }}
                  >
                    <span>Choose / Change Photo</span>
                  </button>
                  {(editingEntity.avatar_box_id || editingEntity.representative_box_id) && (
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ fontSize: '0.75rem', padding: '4px 10px', color: '#f87171' }}
                      onClick={async () => {
                        try {
                          await setEntityAvatar(editingEntity.id, null);
                          setEditingEntity(null);
                          loadData();
                        } catch (err) {
                          alert(err.message);
                        }
                      }}
                    >
                      <span>Remove Current Photo</span>
                    </button>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ color: '#f87171', borderColor: 'rgba(239,68,68,0.3)' }}
                  onClick={() => handleDeleteEntity(editingEntity.id, editingEntity.name)}
                >
                  <Trash2 size={14} />
                  <span>Delete</span>
                </button>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button type="button" className="btn-secondary" onClick={() => setEditingEntity(null)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary" disabled={!editName.trim()}>
                    Save Changes
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
