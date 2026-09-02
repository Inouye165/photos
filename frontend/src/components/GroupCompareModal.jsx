import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  X,
  Trash2,
  Check,
  Star,
  ChevronLeft,
  ChevronRight,
  EyeOff,
  RotateCcw,
  Sparkles,
  ZoomIn,
  ZoomOut,
  Folder,
  Layers,
  Columns2,
  Grid2X2,
  LayoutGrid,
  Maximize2,
  Crosshair,
  Undo2,
  ShieldCheck
} from 'lucide-react';
import { batchTagTrash } from '../api';

export default function GroupCompareModal({
  group,
  groupIndex,
  onClose,
  onApplied
}) {
  // Combine primary and duplicates into a single flat list
  const initialPhotos = useMemo(() => {
    if (!group) return [];
    const list = [];
    if (group.primary) {
      list.push({ ...group.primary, isPrimaryOriginal: true });
    }
    if (group.duplicates && group.duplicates.length > 0) {
      group.duplicates.forEach((d) => {
        list.push({ ...d, isPrimaryOriginal: false });
      });
    }
    return list;
  }, [group]);

  // BEST PRACTICE: Default to EMPTY set (Keep All).
  // Users intentionally select which photos to move to trash.
  const [markedTrashIds, setMarkedTrashIds] = useState(() => new Set());

  // Set of photo IDs temporarily hidden/eliminated from the active shootout comparison
  const [hiddenPhotoIds, setHiddenPhotoIds] = useState(new Set());

  // Layout mode: '6' (default), '4', '2', or 'auto'
  const [layoutMode, setLayoutMode] = useState('6');

  // Carousel offset
  const [carouselIndex, setCarouselIndex] = useState(0);

  // Full-size inspect photo
  const [inspectPhoto, setInspectPhoto] = useState(null);

  // Synchronized Zoom & Pan state
  // Default to upper-third (y: 22%) where faces are located in standing & group portrait photos
  const [zoomLevel, setZoomLevel] = useState(1);
  const [zoomFocus, setZoomFocus] = useState({ x: 50, y: 22 }); // percentage
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 }); // pixels
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0, initPanX: 0, initPanY: 0, moved: false });

  const [isApplying, setIsApplying] = useState(false);
  const stageRef = useRef(null);

  // Active candidates (not hidden)
  const activeCandidates = useMemo(() => {
    return initialPhotos.filter((p) => !hiddenPhotoIds.has(p.id));
  }, [initialPhotos, hiddenPhotoIds]);

  const totalCandidates = initialPhotos.length;

  // Determine number of visible images according to layoutMode
  const visibleLimit = useMemo(() => {
    if (layoutMode === '2') return 2;
    if (layoutMode === '4') return 4;
    if (layoutMode === '6') return 6;
    return Math.min(6, Math.max(1, activeCandidates.length));
  }, [layoutMode, activeCandidates.length]);

  // Visible photos slice
  const visiblePhotos = useMemo(() => {
    if (activeCandidates.length === 0) return [];
    const maxStart = Math.max(0, activeCandidates.length - visibleLimit);
    const start = Math.min(carouselIndex, maxStart);
    return activeCandidates.slice(start, start + visibleLimit);
  }, [activeCandidates, carouselIndex, visibleLimit]);

  // Max carousel offset
  const maxCarouselOffset = useMemo(() => {
    return Math.max(0, activeCandidates.length - visibleLimit);
  }, [activeCandidates.length, visibleLimit]);

  // Clamp carousel index when list size changes
  useEffect(() => {
    if (carouselIndex > maxCarouselOffset) {
      setCarouselIndex(maxCarouselOffset);
    }
  }, [carouselIndex, maxCarouselOffset]);

  // Wheel handling:
  // - If zoomed in (> 1x): wheel zooms in/out smoothly (1x to 8x)
  // - If at 1x: wheel slides the carousel across duplicate candidates
  useEffect(() => {
    const container = stageRef.current;
    if (!container) return;

    let wheelAccumulator = 0;
    const carouselThreshold = 45;

    const handleWheel = (e) => {
      e.preventDefault();

      if (zoomLevel > 1 || e.ctrlKey || e.metaKey) {
        // Exponential zoom: smooth and natural from 1x all the way to 30x
        const factor = e.deltaY < 0 ? 1.25 : 0.8;
        setZoomLevel((prev) => {
          const next = Math.min(30, Math.max(1, Math.round(prev * factor * 10) / 10));
          if (next <= 1.1) {
            setPanOffset({ x: 0, y: 0 });
            return 1;
          }
          return next;
        });
        return;
      }

      if (maxCarouselOffset > 0) {
        wheelAccumulator += e.deltaY || e.deltaX;
        if (wheelAccumulator > carouselThreshold) {
          setCarouselIndex((prev) => Math.min(prev + 1, maxCarouselOffset));
          wheelAccumulator = 0;
        } else if (wheelAccumulator < -carouselThreshold) {
          setCarouselIndex((prev) => Math.max(prev - 1, 0));
          wheelAccumulator = 0;
        }
      }
    };

    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      container.removeEventListener('wheel', handleWheel);
    };
  }, [zoomLevel, maxCarouselOffset]);

  // Focus coordinates on true photo pixels
  const getCoordinatesFromEvent = (e) => {
    const imgEl = e.currentTarget.querySelector('img');
    if (!imgEl) return { x: 50, y: 50 };
    const rect = imgEl.getBoundingClientRect();
    if (
      e.clientX >= rect.left && e.clientX <= rect.right &&
      e.clientY >= rect.top && e.clientY <= rect.bottom
    ) {
      const xPercent = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
      const yPercent = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
      return { x: xPercent, y: yPercent };
    }
    return { x: 50, y: 50 };
  };

  // Click on image viewport:
  // - If at 1x: zooms straight into that clicked spot across ALL images at 16x (face fills the picture!)
  // - If > 1x: clicking another spot re-centers zoom on that new spot!
  const handleImageClick = (e) => {
    if (dragStartRef.current.moved) return;

    const coords = getCoordinatesFromEvent(e);
    if (zoomLevel === 1) {
      setZoomFocus(coords);
      setPanOffset({ x: 0, y: 0 });
      setZoomLevel(16); // 16x magnification: face fills the frame!
    } else {
      setZoomFocus(coords);
      setPanOffset({ x: 0, y: 0 });
    }
  };

  // Double click resets zoom back to Fit (1x)
  const handleImageDoubleClick = (e) => {
    e.stopPropagation();
    setZoomLevel(1);
    setZoomFocus({ x: 50, y: 22 });
    setPanOffset({ x: 0, y: 0 });
  };

  // Mouse Drag to Pan all images simultaneously
  const handleMouseDown = (e) => {
    if (zoomLevel <= 1) return;
    setIsDragging(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      initPanX: panOffset.x,
      initPanY: panOffset.y,
      moved: false
    };
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - dragStartRef.current.x;
      const dy = e.clientY - dragStartRef.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        dragStartRef.current.moved = true;
      }
      setPanOffset({
        x: dragStartRef.current.initPanX + dx,
        y: dragStartRef.current.initPanY + dy
      });
    };

    const handleMouseUp = () => {
      if (isDragging) setIsDragging(false);
    };

    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (inspectPhoto) {
          setInspectPhoto(null);
        } else if (zoomLevel > 1) {
          setZoomLevel(1);
          setPanOffset({ x: 0, y: 0 });
        } else {
          onClose();
        }
      } else if (e.key === 'ArrowRight') {
        setCarouselIndex((prev) => Math.min(prev + 1, maxCarouselOffset));
      } else if (e.key === 'ArrowLeft') {
        setCarouselIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === '+' || e.key === '=') {
        setZoomLevel((prev) => Math.min(35, Math.round(prev * 1.25 * 10) / 10));
      } else if (e.key === '-') {
        setZoomLevel((prev) => Math.max(1, Math.round(prev / 1.25 * 10) / 10));
      } else if (e.key === '0') {
        setZoomLevel(1);
        setZoomFocus({ x: 50, y: 28 });
        setPanOffset({ x: 0, y: 0 });
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, maxCarouselOffset, inspectPhoto, zoomLevel]);

  // Toggle single photo trash/keep status
  const toggleTrash = (photoId) => {
    setMarkedTrashIds((prev) => {
      const next = new Set(prev);
      if (next.has(photoId)) {
        next.delete(photoId);
      } else {
        next.add(photoId);
      }
      return next;
    });
  };

  // Mark all other photos for trash, keeping only this one
  const handleKeepOnlyThis = (photoId) => {
    const newTrash = new Set();
    initialPhotos.forEach((p) => {
      if (p.id !== photoId) {
        newTrash.add(p.id);
      }
    });
    setMarkedTrashIds(newTrash);
  };

  // Eliminate/hide from shootout view
  const handleEliminateFromShootout = (photoId) => {
    setHiddenPhotoIds((prev) => new Set([...prev, photoId]));
  };

  // Restore hidden photo
  const handleRestoreToShootout = (photoId) => {
    setHiddenPhotoIds((prev) => {
      const next = new Set(prev);
      next.delete(photoId);
      return next;
    });
  };

  // Restore all hidden photos
  const handleRestoreAllToShootout = () => {
    setHiddenPhotoIds(new Set());
  };

  // Clear all selections (revert to Keep All)
  const handleResetSelections = () => {
    setMarkedTrashIds(new Set());
    setHiddenPhotoIds(new Set());
    setCarouselIndex(0);
    setZoomLevel(1);
    setPanOffset({ x: 0, y: 0 });
  };

  // Format file size helper
  const formatSize = (bytes) => {
    if (!bytes) return '0 B';
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(2)} MB` : `${Math.round(bytes / 1024)} KB`;
  };

  // Apply batch trash changes
  const handleApply = async () => {
    const trashList = Array.from(markedTrashIds);
    if (trashList.length === 0) {
      // Clean exit with no changes
      onClose();
      return;
    }

    if (trashList.length === initialPhotos.length) {
      const proceed = window.confirm(
        'Warning: You have marked ALL photos in this group for deletion. Are you sure you want to delete all copies?'
      );
      if (!proceed) return;
    }

    setIsApplying(true);
    try {
      await batchTagTrash(trashList, true);
      onApplied();
      onClose();
    } catch (err) {
      alert('Failed to trash selected photos: ' + err.message);
    } finally {
      setIsApplying(false);
    }
  };

  const trashCount = markedTrashIds.size;
  const keepCount = initialPhotos.length - trashCount;

  // Dynamic grid class based on actual displayed count
  const count = visiblePhotos.length;
  let gridLayoutClass = 'grid-6';
  if (count === 1) gridLayoutClass = 'grid-1';
  else if (count === 2) gridLayoutClass = 'grid-2';
  else if (count === 3) gridLayoutClass = 'grid-3';
  else if (count === 4) gridLayoutClass = 'grid-4';
  else if (count === 5) gridLayoutClass = 'grid-5';
  else if (count >= 6) gridLayoutClass = 'grid-6';

  return (
    <div className="compare-modal-backdrop">
      <div className="compare-modal-container">
        {/* Header Bar */}
        <header className="compare-modal-header">
          <div className="compare-header-left">
            <div className="compare-title-row">
              <span className="compare-badge">
                {group.match_type === 'EXACT_HASH' ? 'Exact SHA-256 Match' : 'Perceptual Visual Match'}
              </span>
              <h2 className="compare-title">
                Group #{groupIndex + 1} Comparison Studio
              </h2>
              <span className="compare-total-count">
                ({totalCandidates} copies)
              </span>
            </div>

            {/* Clear, reassuring status summary */}
            <div className="compare-meta-status">
              <span className="status-chip keep">
                <ShieldCheck size={13} /> {keepCount} Keeping
              </span>
              {trashCount > 0 && (
                <span className="status-chip trash">
                  <Trash2 size={13} /> {trashCount} Selected for Trash
                </span>
              )}
              {hiddenPhotoIds.size > 0 && (
                <span className="status-chip hidden">
                  <EyeOff size={13} /> {hiddenPhotoIds.size} Hidden
                </span>
              )}
            </div>
          </div>

          {/* Layout Mode Switcher */}
          <div className="compare-header-center">
            <div className="layout-mode-picker" title="Choose comparison view">
              <button
                type="button"
                className={`layout-btn ${layoutMode === '6' ? 'active' : ''}`}
                onClick={() => { setLayoutMode('6'); setCarouselIndex(0); }}
                title="6 Images on Screen"
              >
                <LayoutGrid size={15} />
                <span>6 Grid</span>
              </button>

              <button
                type="button"
                className={`layout-btn ${layoutMode === '4' ? 'active' : ''}`}
                onClick={() => { setLayoutMode('4'); setCarouselIndex(0); }}
                title="4 Images on Screen"
              >
                <Grid2X2 size={15} />
                <span>4 Quad</span>
              </button>

              <button
                type="button"
                className={`layout-btn ${layoutMode === '2' ? 'active' : ''}`}
                onClick={() => { setLayoutMode('2'); setCarouselIndex(0); }}
                title="2 Images Large Side-by-Side"
              >
                <Columns2 size={15} />
                <span>2 Side-by-Side</span>
              </button>

              <button
                type="button"
                className={`layout-btn ${layoutMode === 'auto' ? 'active' : ''}`}
                onClick={() => setLayoutMode('auto')}
                title="Auto Dynamic Scale (Expands remaining photos as you eliminate)"
              >
                <Maximize2 size={14} />
                <span>Auto-Scale</span>
              </button>
            </div>
          </div>

          <div className="compare-header-actions">
            {hiddenPhotoIds.size > 0 && (
              <button
                type="button"
                className="btn-secondary compare-head-btn"
                onClick={handleRestoreAllToShootout}
                title="Restore all hidden photos back into the comparison"
              >
                <RotateCcw size={14} />
                <span>Show All ({totalCandidates})</span>
              </button>
            )}

            <button
              type="button"
              className="compare-close-btn"
              onClick={onClose}
              title="Close Comparison (Esc)"
            >
              <X size={20} />
            </button>
          </div>
        </header>

        {/* Carousel & Synchronized Face Zoom Controls */}
        <div className="compare-carousel-bar">
          {/* Left: Carousel navigation */}
          <div className="carousel-nav-wrap">
            <button
              type="button"
              className="carousel-arrow-btn"
              disabled={carouselIndex === 0}
              onClick={() => setCarouselIndex((p) => Math.max(p - 1, 0))}
              title="Previous photos"
            >
              <ChevronLeft size={18} />
            </button>
            
            <div className="carousel-info-text">
              <Layers size={14} style={{ color: '#38bdf8' }} />
              <span>
                Showing <strong>{carouselIndex + 1} – {Math.min(carouselIndex + visibleLimit, activeCandidates.length)}</strong> of <strong>{activeCandidates.length}</strong>
              </span>
              <span className="carousel-hint-badge">
                {zoomLevel > 1 ? 'Wheel: Zoom in/out' : 'Wheel: Scroll photos'}
              </span>
            </div>

            <button
              type="button"
              className="carousel-arrow-btn"
              disabled={carouselIndex >= maxCarouselOffset}
              onClick={() => setCarouselIndex((p) => Math.min(p + 1, maxCarouselOffset))}
              title="Next photos"
            >
              <ChevronRight size={18} />
            </button>
          </div>

          {/* Right: Synchronized Face Zoom Toolbar */}
          <div className="sync-zoom-toolbar">
            <div className="sync-lock-indicator" title="All photos zoom and pan synchronously to the exact same position">
              <Crosshair size={13} style={{ color: '#10b981' }} />
              <span>Sync Zoom: <strong>{zoomLevel === 1 ? 'Fit' : `${zoomLevel.toFixed(1)}×`}</strong></span>
            </div>

            <button
              type="button"
              className="zoom-tool-btn"
              disabled={zoomLevel <= 1}
              onClick={() => {
                const next = Math.max(1, Math.round(zoomLevel / 1.3 * 10) / 10);
                setZoomLevel(next <= 1.1 ? 1 : next);
                if (next <= 1.1) setPanOffset({ x: 0, y: 0 });
              }}
              title="Zoom Out (-)"
            >
              <ZoomOut size={15} />
            </button>

            <button
              type="button"
              className={`zoom-preset-btn ${zoomLevel === 1 ? 'active' : ''}`}
              onClick={() => { setZoomLevel(1); setPanOffset({ x: 0, y: 0 }); }}
            >
              Fit
            </button>

            <button
              type="button"
              className={`zoom-preset-btn ${zoomLevel === 4 ? 'active' : ''}`}
              onClick={() => { setZoomLevel(4); setPanOffset({ x: 0, y: 0 }); }}
            >
              4×
            </button>

            <button
              type="button"
              className={`zoom-preset-btn ${zoomLevel === 10 ? 'active' : ''}`}
              onClick={() => { setZoomLevel(10); setPanOffset({ x: 0, y: 0 }); }}
            >
              10×
            </button>

            <button
              type="button"
              className={`zoom-preset-btn ${zoomLevel === 16 ? 'active' : ''}`}
              onClick={() => { setZoomLevel(16); setPanOffset({ x: 0, y: 0 }); }}
              title="Face Fills the Frame"
            >
              16× (Face)
            </button>

            <button
              type="button"
              className={`zoom-preset-btn ${zoomLevel === 25 ? 'active' : ''}`}
              onClick={() => { setZoomLevel(25); setPanOffset({ x: 0, y: 0 }); }}
              title="Maximum Detail for Eyes, Smile & Focus"
            >
              25× (Eyes & Focus)
            </button>

            <button
              type="button"
              className="zoom-tool-btn"
              disabled={zoomLevel >= 30}
              onClick={() => setZoomLevel((z) => Math.min(30, Math.round(z * 1.3 * 10) / 10))}
              title="Zoom In (+)"
            >
              <ZoomIn size={15} />
            </button>

            <span className="sync-hint-text">
              Click face to zoom • Drag to pan • Scroll wheel zooms up to 30×
            </span>
          </div>
        </div>

        {/* Shootout Stage / Grid Area */}
        <div className="compare-stage" ref={stageRef}>
          {visiblePhotos.length === 0 ? (
            <div className="compare-empty-state">
              <EyeOff size={40} color="#94a3b8" />
              <h3>All candidate photos are currently hidden from view</h3>
              <p>Click below to restore all candidates and continue comparison.</p>
              <button
                type="button"
                className="btn-primary"
                style={{ marginTop: '1rem' }}
                onClick={handleRestoreAllToShootout}
              >
                <RotateCcw size={16} />
                <span>Restore All Candidates</span>
              </button>
            </div>
          ) : (
            <div className={`compare-grid ${gridLayoutClass}`}>
              {visiblePhotos.map((photo) => {
                const isTrash = markedTrashIds.has(photo.id);
                const isPrimary = photo.isPrimaryOriginal;

                return (
                  <div
                    key={photo.id}
                    className={`compare-card ${isTrash ? 'is-staged-trash' : 'is-default-candidate'}`}
                  >
                    {/* Top Overlay Badges */}
                    <div className="card-top-badges">
                      <div className="top-badge-group">
                        {/* Only show badge if intentionally marked for trash */}
                        {isTrash && (
                          <div className="trash-staged-badge" title="Marked to be moved to trash">
                            <Trash2 size={12} />
                            <span>Marked for Trash</span>
                          </div>
                        )}

                        {isPrimary && (
                          <span className="primary-original-pill">
                            <Star size={11} fill="#ffffff" />
                            Primary Original
                          </span>
                        )}
                      </div>

                      {/* Shootout knockout button (hides from grid to scale remaining) */}
                      <button
                        type="button"
                        className="btn-knockout"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEliminateFromShootout(photo.id);
                        }}
                        title="Hide from view so remaining photos expand (does not delete)"
                      >
                        <EyeOff size={14} />
                      </button>
                    </div>

                    {/* Image Viewport with Synchronized Pixel-Accurate Zoom & Pan */}
                    <div
                      className={`card-image-viewport ${zoomLevel > 1 ? (isDragging ? 'is-dragging' : 'can-pan') : 'can-zoom'}`}
                      onClick={handleImageClick}
                      onDoubleClick={handleImageDoubleClick}
                      onMouseDown={handleMouseDown}
                      title={
                        zoomLevel > 1
                          ? 'Click to re-center zoom • Drag to pan all photos • Double-click resets'
                          : 'Click anywhere on face to zoom all photos directly into that spot'
                      }
                    >
                      <img
                        src={`/api/photos/${photo.id}/full`}
                        alt={photo.file_name}
                        className="card-img"
                        style={{
                          transformOrigin: '50% 50%',
                          transform: zoomLevel > 1
                            ? `scale(${zoomLevel}) translate(calc(${50 - zoomFocus.x}% + ${panOffset.x / zoomLevel}px), calc(${50 - zoomFocus.y}% + ${panOffset.y / zoomLevel}px))`
                            : 'scale(1) translate(0px, 0px)',
                          transition: isDragging ? 'none' : 'transform 0.15s cubic-bezier(0.16, 1, 0.3, 1)'
                        }}
                        onError={(e) => {
                          e.currentTarget.src = `/api/photos/${photo.id}/preview`;
                        }}
                        draggable={false}
                      />

                      {/* Full-res Zoom Modal */}
                      <button
                        type="button"
                        className="btn-inspect-zoom"
                        onClick={(e) => {
                          e.stopPropagation();
                          setInspectPhoto(photo);
                        }}
                        title="View Full Resolution Modal"
                      >
                        <Maximize2 size={15} />
                      </button>
                    </div>

                    {/* Card Footer & Controls */}
                    <div className="card-footer">
                      <div className="card-details">
                        <div className="card-filename" title={photo.file_name}>
                          {photo.file_name}
                        </div>
                        <div className="card-specs">
                          <span className="spec-dim">
                            {photo.width && photo.height ? `${photo.width}×${photo.height}` : '—'}
                          </span>
                          <span className="spec-separator">•</span>
                          <span className="spec-size">{formatSize(photo.file_size)}</span>
                        </div>
                        <div className="card-path" title={photo.file_path}>
                          <Folder size={11} style={{ flexShrink: 0, opacity: 0.7 }} />
                          <span className="path-text">{photo.file_path}</span>
                        </div>
                      </div>

                      {/* Action buttons: Clear, reassuring UX */}
                      <div className="card-action-bar">
                        {isTrash ? (
                          <button
                            type="button"
                            className="btn-restore-candidate"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleTrash(photo.id);
                            }}
                            title="Undo: Keep this photo in library"
                          >
                            <Undo2 size={13} />
                            <span>Keep Photo</span>
                          </button>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="btn-mark-for-trash"
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleTrash(photo.id);
                              }}
                              title="Mark this copy to be moved to trash"
                            >
                              <Trash2 size={13} />
                              <span>Select to Trash</span>
                            </button>

                            <button
                              type="button"
                              className="btn-card-solo"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleKeepOnlyThis(photo.id);
                              }}
                              title="Keep only this winner and select all other copies for trash"
                            >
                              <Sparkles size={13} />
                              <span>Keep Winner</span>
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Hidden Photos Drawer */}
        {hiddenPhotoIds.size > 0 && (
          <div className="compare-hidden-drawer">
            <div className="hidden-drawer-header">
              <span className="hidden-drawer-title">
                Hidden from view ({hiddenPhotoIds.size}) — click to bring back:
              </span>
            </div>
            <div className="hidden-drawer-strip">
              {initialPhotos
                .filter((p) => hiddenPhotoIds.has(p.id))
                .map((p) => {
                  const isTrash = markedTrashIds.has(p.id);
                  return (
                    <div
                      key={p.id}
                      className={`hidden-thumb-chip ${isTrash ? 'is-trash' : 'is-keep'}`}
                      onClick={() => handleRestoreToShootout(p.id)}
                      title={`Click to restore ${p.file_name} back into comparison`}
                    >
                      <img
                        src={`/api/photos/${p.id}/thumbnail`}
                        alt={p.file_name}
                        className="hidden-thumb-img"
                      />
                      <span className="hidden-thumb-name">{p.file_name}</span>
                      <span className="hidden-thumb-status">
                        {isTrash ? 'TRASH' : 'KEEP'}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* Footer Actions: Senior UI/UX Pattern */}
        <footer className="compare-modal-footer">
          <div className="footer-left">
            {trashCount > 0 && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleResetSelections}
                disabled={isApplying}
                title="Reset all selections and keep all photos"
              >
                <RotateCcw size={14} />
                <span>Reset to Keep All</span>
              </button>
            )}
          </div>

          <div className="footer-right">
            <button
              type="button"
              className="btn-secondary"
              onClick={onClose}
              disabled={isApplying}
            >
              Cancel
            </button>

            {/* Primary Action Button: Clear intent based on selection */}
            {trashCount === 0 ? (
              <button
                type="button"
                className="btn-primary compare-done-btn"
                onClick={onClose}
                disabled={isApplying}
              >
                <Check size={15} />
                <span>Keep All & Done</span>
              </button>
            ) : (
              <button
                type="button"
                className="btn-primary compare-apply-btn"
                onClick={handleApply}
                disabled={isApplying}
              >
                <Trash2 size={15} />
                <span>
                  {isApplying
                    ? 'Moving to Trash...'
                    : `Move ${trashCount} Selected to Trash`}
                </span>
              </button>
            )}
          </div>
        </footer>

        {/* Full Image Pristine Inspector Modal */}
        {inspectPhoto && (
          <div
            className="inspect-modal-overlay"
            onClick={() => setInspectPhoto(null)}
          >
            <div
              className="inspect-content-box"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="inspect-header">
                <div>
                  <h4>{inspectPhoto.file_name}</h4>
                  <p>
                    {inspectPhoto.width}×{inspectPhoto.height} px • {formatSize(inspectPhoto.file_size)}
                  </p>
                </div>
                <button
                  type="button"
                  className="compare-close-btn"
                  onClick={() => setInspectPhoto(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="inspect-image-wrap">
                <img
                  src={`/api/photos/${inspectPhoto.id}/preview`}
                  alt={inspectPhoto.file_name}
                  className="inspect-full-img"
                  onError={(e) => {
                    e.currentTarget.src = `/api/photos/${inspectPhoto.id}/original`;
                  }}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
