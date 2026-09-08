import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Camera, Calendar, Copy, Sparkles, Image as ImageIcon, MapPin, ArrowUp, Loader2, Trash2, RotateCcw, CloudCheck, CloudUpload } from 'lucide-react';

// Memoized individual PhotoCard component to eliminate full grid re-renders
const PhotoCard = React.memo(function PhotoCard({
  photo,
  isSelected,
  isSelectMode,
  onSelectPhoto,
  onToggleSelectPhoto,
  onStartTrashSelect,
  onToggleTrash,
  formatDate
}) {
  const thumbUrl = `/api/photos/${photo.id}/thumbnail`;
  const hasDups = photo.duplicate_count > 0;
  const hasGps = photo.latitude !== null && photo.longitude !== null;
  const isTrashed = Boolean(photo.is_trashed);
  const isBackedUp = photo.gdrive_backup_status === 'backed_up';
  const isUploading = photo.gdrive_backup_status === 'uploading';
  const simScore = photo.similarity_score !== undefined
    ? Math.round(photo.similarity_score * 100)
    : null;

  const handleCardClick = () => {
    if (isSelectMode) {
      if (onToggleSelectPhoto) onToggleSelectPhoto(photo);
    } else {
      if (onSelectPhoto) onSelectPhoto(photo);
    }
  };

  return (
    <div
      className={`photo-card ${isTrashed ? 'trashed-card' : ''} ${isSelectMode ? 'in-select-mode' : ''} ${isSelected ? 'is-selected-card' : ''}`}
      onClick={handleCardClick}
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

        {/* Select Mode Checkbox Indicator */}
        {isSelectMode ? (
          <div className={`select-mode-checkbox ${isSelected ? 'checked' : ''}`}>
            {isSelected ? <Trash2 size={13} /> : <div className="checkbox-ring" />}
          </div>
        ) : (
          /* Quick Tag for Trash button - triggers Select Mode */
          <button
            className={`quick-trash-btn ${isTrashed ? 'is-active' : ''}`}
            title={isTrashed ? 'Tagged for trash (Click to restore)' : 'Mark for trash (enters multi-select mode)'}
            onClick={(e) => {
              e.stopPropagation();
              if (onStartTrashSelect) {
                onStartTrashSelect(photo);
              } else if (onToggleTrash) {
                onToggleTrash(photo, !isTrashed);
              }
            }}
          >
            {isTrashed ? <RotateCcw size={13} /> : <Trash2 size={13} />}
          </button>
        )}
        
        {/* Badges */}
        <div className="photo-badge-top-left">
          {isTrashed && (
            <span className="badge-trash" title="Tagged for deferred trash deletion">
              <Trash2 size={10} />
              <span>Trash</span>
            </span>
          )}
          {isBackedUp && (
            <span
              className="badge-gdrive"
              title="Backed up to Google Drive"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                padding: '2px 5px',
                borderRadius: '4px',
                fontSize: '10px',
                fontWeight: 600,
                background: 'rgba(16, 185, 129, 0.3)',
                color: '#6ee7b7',
                backdropFilter: 'blur(4px)',
                border: '1px solid rgba(16, 185, 129, 0.4)'
              }}
            >
              <CloudCheck size={10} />
              <span>Drive</span>
            </span>
          )}
          {isUploading && (
            <span
              className="badge-gdrive-sync"
              title="Syncing to Google Drive..."
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                padding: '2px 5px',
                borderRadius: '4px',
                background: 'rgba(6, 182, 212, 0.3)',
                color: '#67e8f9',
                backdropFilter: 'blur(4px)',
                border: '1px solid rgba(6, 182, 212, 0.4)'
              }}
            >
              <CloudUpload size={10} className="animate-pulse" />
            </span>
          )}
          {simScore !== null && (
            <span className="badge-sim">
              <Sparkles size={10} />
              <span>{simScore}% Match</span>
            </span>
          )}
          {hasDups && (
            <span className="badge-dup">
              <Copy size={10} />
              <span>{photo.duplicate_count + 1} Duplicates</span>
            </span>
          )}
          {hasGps && (
            <span className="badge-gps" title="Geotagged with GPS coordinates">
              <MapPin size={10} />
            </span>
          )}
        </div>
      </div>

      <div className="photo-card-info">
        <div className="photo-card-name" title={photo.file_name}>
          {photo.file_name}
        </div>
        <div className="photo-card-meta">
          <span className="photo-card-camera">
            {photo.camera_model || photo.camera_make || (photo.width ? `${photo.width}×${photo.height}` : 'Photo')}
          </span>
          <span>{formatDate(photo.date_taken || (photo.file_modified_at ? new Date(photo.file_modified_at * 1000).toISOString() : ''))}</span>
        </div>
      </div>
    </div>
  );
});

export default function PhotoGrid({
  photos = [],
  totalPhotos = 0,
  onSelectPhoto,
  onToggleTrash,
  query,
  isLoading = false,
  isLoadingMore = false,
  hasMore = false,
  onLoadMore,
  groupByDate = true,
  isSelectMode = false,
  selectedIds = new Set(),
  onToggleSelectPhoto,
  onStartTrashSelect
}) {
  const sentinelRef = useRef(null);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Monitor scroll for Back-to-Top button
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 600);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // IntersectionObserver for continuous Infinite Scrolling
  useEffect(() => {
    if (!hasMore || isLoadingMore || isLoading || !onLoadMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first.isIntersecting) {
          onLoadMore();
        }
      },
      { rootMargin: '400px' }
    );

    const currentSentinel = sentinelRef.current;
    if (currentSentinel) {
      observer.observe(currentSentinel);
    }

    return () => {
      if (currentSentinel) {
        observer.unobserve(currentSentinel);
      }
    };
  }, [hasMore, isLoadingMore, isLoading, onLoadMore]);

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const getEffectiveDate = (photo) => {
    if (!photo) return null;
    if (photo.date_taken) return photo.date_taken;
    if (photo.file_modified_at) {
      try {
        return new Date(photo.file_modified_at * 1000).toISOString();
      } catch {
        return null;
      }
    }
    return null;
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  const formatMonthYear = (photo) => {
    const effective = getEffectiveDate(photo);
    if (!effective) return 'Undated Photos';
    try {
      const d = new Date(effective);
      if (isNaN(d.getTime())) return 'Undated Photos';
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'long' });
    } catch {
      return 'Undated Photos';
    }
  };

  // Group photos into Month-Year sections if query is not active
  const groupedSections = useMemo(() => {
    if (query || !groupByDate || photos.length === 0) {
      return [{ title: null, items: photos }];
    }

    const sections = [];
    let currentTitle = null;
    let currentItems = [];

    for (const photo of photos) {
      const title = formatMonthYear(photo);
      if (title !== currentTitle) {
        if (currentItems.length > 0) {
          sections.push({ title: currentTitle, items: currentItems });
        }
        currentTitle = title;
        currentItems = [photo];
      } else {
        currentItems.push(photo);
      }
    }

    if (currentItems.length > 0) {
      sections.push({ title: currentTitle, items: currentItems });
    }

    return sections;
  }, [photos, query, groupByDate]);

  if (isLoading && photos.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '5rem 0', color: '#94a3b8' }}>
        <div style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>
          <Sparkles size={32} color="#10b981" />
        </div>
        <p style={{ marginTop: '1rem', fontSize: '0.95rem' }}>Loading photo library...</p>
      </div>
    );
  }

  if (!photos || photos.length === 0) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '5rem 2rem',
        background: 'rgba(255, 255, 255, 0.02)',
        borderRadius: '16px',
        border: '1px dashed rgba(255, 255, 255, 0.1)',
        maxWidth: '600px',
        margin: '2rem auto'
      }}>
        <ImageIcon size={48} color="#475569" style={{ marginBottom: '1rem' }} />
        <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>
          {query ? `No matching photos for "${query}"` : 'No photos found in this filter'}
        </h3>
        <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
          {query
            ? 'Try another search prompt or adjust your filters.'
            : 'Try selecting "All Years" or clearing filters to view all photos.'}
        </p>
      </div>
    );
  }

  return (
    <div className="photo-grid-container">
      {/* Progress pill */}
      <div className="photo-progress-bar">
        <span>
          Showing <strong>{photos.length.toLocaleString()}</strong> of{' '}
          <strong>{totalPhotos.toLocaleString()}</strong> photos
        </span>
      </div>

      {groupedSections.map((section, sIdx) => (
        <div key={sIdx} className="photo-grid-section">
          {section.title && (
            <div className="section-date-header">
              <Calendar size={15} color="#10b981" />
              <span>{section.title}</span>
              <span className="section-count">{section.items.length} {section.items.length === 1 ? 'photo' : 'photos'}</span>
            </div>
          )}

          <div className="photo-grid">
            {section.items.map((photo) => (
              <PhotoCard
                key={photo.id}
                photo={photo}
                isSelected={Boolean(selectedIds && selectedIds.has(photo.id))}
                isSelectMode={isSelectMode}
                onSelectPhoto={onSelectPhoto}
                onToggleSelectPhoto={onToggleSelectPhoto}
                onStartTrashSelect={onStartTrashSelect}
                onToggleTrash={onToggleTrash}
                formatDate={formatDate}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Infinite Scroll Sentinel */}
      <div ref={sentinelRef} className="infinite-scroll-sentinel">
        {isLoadingMore && (
          <div className="infinite-loader">
            <Loader2 size={24} className="spin-icon" color="#10b981" />
            <span>Loading more photos...</span>
          </div>
        )}
        {!hasMore && photos.length > 0 && (
          <div className="end-of-library">
            <span>You've reached the end of the collection ({photos.length.toLocaleString()} photos)</span>
          </div>
        )}
      </div>

      {/* Floating Scroll To Top Button */}
      {showScrollTop && (
        <button
          className="scroll-top-btn"
          onClick={scrollToTop}
          title="Back to Top"
        >
          <ArrowUp size={20} />
        </button>
      )}
    </div>
  );
}
