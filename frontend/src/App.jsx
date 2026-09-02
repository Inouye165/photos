import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import Header from './components/Header';
import SemanticSearch from './components/SemanticSearch';
import PhotoGrid from './components/PhotoGrid';
import Lightbox from './components/Lightbox';
import DuplicatesView from './components/DuplicatesView';
import FilteredView from './components/FilteredView';
import TrashView from './components/TrashView';
import ScanModal from './components/ScanModal';
import MobileConnectModal from './components/MobileConnectModal';
import TimelineScrubber from './components/TimelineScrubber';
import TrashSelectionBar from './components/TrashSelectionBar';
import ConfirmTrashModal from './components/ConfirmTrashModal';
import { fetchPhotos, fetchStats, tagPhotoTrash, batchTagTrash } from './api';
import { Filter, SlidersHorizontal, MapPin, Eye, EyeOff, Sparkles, Copy, ShieldAlert, Smartphone, Calendar, Trash2, CheckSquare, CheckCircle2 } from 'lucide-react';

const PAGE_SIZE = 80;

export default function App() {
  const [activeTab, setActiveTab] = useState('photos'); // 'photos', 'duplicates', 'filtered', 'trash'
  const [photos, setPhotos] = useState([]);
  const [totalPhotos, setTotalPhotos] = useState(0);
  const [stats, setStats] = useState(null);
  
  // Search & Filter state
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [parsedQuery, setParsedQuery] = useState(null);
  const [selectedYear, setSelectedYear] = useState(null);
  const [cameraMake, setCameraMake] = useState('');
  const [hasGps, setHasGps] = useState(null);
  const [includeDuplicates, setIncludeDuplicates] = useState(true);
  const [includeTrashed, setIncludeTrashed] = useState(false);
  const [sortBy, setSortBy] = useState('date_taken');
  const [sortOrder, setSortOrder] = useState('DESC');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  // Abort controller ref for canceling in-flight search requests
  const searchAbortRef = useRef(null);

  // Debounce search query updates by 300ms to eliminate typing CPU spikes
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  // Multi-select / Select Mode for Trashing
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [isTrashBatchLoading, setIsTrashBatchLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // Selected photo for Lightbox
  const [selectedPhoto, setSelectedPhoto] = useState(null);

  // Modals state
  const [isScanModalOpen, setIsScanModalOpen] = useState(false);
  const [isMobileModalOpen, setIsMobileModalOpen] = useState(false);

  const loadStats = useCallback(() => {
    fetchStats()
      .then((data) => setStats(data))
      .catch(console.error);
  }, []);

  // Keyboard shortcut listener (Escape to cancel selection)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (isConfirmModalOpen) {
          setIsConfirmModalOpen(false);
        } else if (isSelectMode) {
          setIsSelectMode(false);
          setSelectedIds(new Set());
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isConfirmModalOpen, isSelectMode]);

  // Selected photos list and total byte size calculation for modal
  const selectedPhotosList = useMemo(() => {
    if (selectedIds.size === 0) return [];
    const idMap = new Map(photos.map((p) => [p.id, p]));
    return Array.from(selectedIds)
      .map((id) => idMap.get(id))
      .filter(Boolean);
  }, [photos, selectedIds]);

  const totalSelectedBytes = useMemo(() => {
    return selectedPhotosList.reduce((acc, p) => acc + (p.file_size || 0), 0);
  }, [selectedPhotosList]);

  const loadPhotos = useCallback((options = {}) => {
    const isLoadMore = options.isLoadMore || false;
    const searchQuery = options.searchQuery !== undefined ? options.searchQuery : debouncedQuery;
    const yearFilter = options.year !== undefined ? options.year : selectedYear;

    if (!isLoadMore) {
      if (searchAbortRef.current) {
        searchAbortRef.current.abort();
      }
      searchAbortRef.current = new AbortController();
    }
    const signal = !isLoadMore ? searchAbortRef.current?.signal : null;

    if (isLoadMore) {
      setIsLoadingMore(true);
      fetchPhotos({
        query: searchQuery,
        year: yearFilter,
        includeDuplicates,
        cameraMake: cameraMake || null,
        hasGps: hasGps,
        sortBy,
        sortOrder,
        limit: PAGE_SIZE,
        offset: photos.length,
        knownTotal: totalPhotos,
        signal
      })
        .then((data) => {
          const newItems = data.photos || [];
          setPhotos((prev) => [...prev, ...newItems]);
          setTotalPhotos(data.total || 0);
          setHasMore(photos.length + newItems.length < (data.total || 0));
          setIsLoadingMore(false);
        })
        .catch((err) => {
          if (err?.name === 'AbortError') return;
          console.error('Error loading more photos:', err);
          setIsLoadingMore(false);
        });
    } else {
      setIsLoading(true);
      fetchPhotos({
        query: searchQuery,
        year: yearFilter,
        includeDuplicates,
        cameraMake: cameraMake || null,
        hasGps: hasGps,
        sortBy,
        sortOrder,
        limit: PAGE_SIZE,
        offset: 0,
        signal
      })
        .then((data) => {
          const items = data.photos || [];
          setPhotos(items);
          setTotalPhotos(data.total || 0);
          setHasMore(items.length < (data.total || 0));
          setParsedQuery(data.parsed_query || null);
          setIsLoading(false);
        })
        .catch((err) => {
          if (err?.name === 'AbortError') return;
          console.error('Error loading photos:', err);
          setIsLoading(false);
        });
    }
  }, [debouncedQuery, selectedYear, includeDuplicates, cameraMake, hasGps, sortBy, sortOrder, photos.length, totalPhotos]);

  // Initial load or filter changes
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadPhotos({ isLoadMore: false });
  }, [debouncedQuery, selectedYear, includeDuplicates, cameraMake, hasGps, sortBy, sortOrder]);

  const handleSearch = (searchQuery) => {
    setQuery(searchQuery);
    setDebouncedQuery(searchQuery);
    if (!searchQuery) {
      setParsedQuery(null);
    }
  };

  const handleSelectYear = (year) => {
    setSelectedYear(year);
  };

  const handleLoadMore = () => {
    if (!isLoadingMore && hasMore && !isLoading) {
      loadPhotos({ isLoadMore: true });
    }
  };

  const handleRefreshLibrary = useCallback(() => {
    loadStats();
    loadPhotos({ isLoadMore: false });
  }, [loadStats, loadPhotos]);

  // Quick scroll-time tagging for trash / entering Select Mode
  const handleToggleTrashPhoto = async (photo, nextTrashed) => {
    // Optimistic UI state update so scrolling is silky smooth
    setPhotos((prev) =>
      prev.map((p) => (p.id === photo.id ? { ...p, is_trashed: nextTrashed ? 1 : 0 } : p))
    );
    try {
      await tagPhotoTrash(photo.id, nextTrashed);
      loadStats();
    } catch (err) {
      console.error('Failed to update trash status:', err);
      loadPhotos({ isLoadMore: false });
    }
  };

  // Called when user clicks the quick trash button on a photo card
  const handleStartTrashSelect = (photo) => {
    if (photo.is_trashed) {
      // If already tagged for trash, restore it directly
      handleToggleTrashPhoto(photo, false);
    } else {
      // Enter Select Mode and immediately select this photo
      setIsSelectMode(true);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.add(photo.id);
        return next;
      });
    }
  };

  // Toggle selection for a photo while in Select Mode
  const handleToggleSelectPhoto = (photo) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(photo.id)) {
        next.delete(photo.id);
      } else {
        next.add(photo.id);
      }
      return next;
    });
  };

  // Select all visible photos
  const handleSelectAllVisible = () => {
    setSelectedIds(new Set(photos.map((p) => p.id)));
  };

  // Deselect all
  const handleDeselectAll = () => {
    setSelectedIds(new Set());
  };

  // Exit Select Mode
  const handleExitSelectMode = () => {
    setIsSelectMode(false);
    setSelectedIds(new Set());
  };

  // Confirm and execute batch moving selected photos to trash
  const handleConfirmBatchTrash = async () => {
    if (selectedIds.size === 0) return;
    const idsToTrash = Array.from(selectedIds);
    setIsTrashBatchLoading(true);
    try {
      await batchTagTrash(idsToTrash, true);

      // Optimistic UI update
      setPhotos((prev) =>
        prev.map((p) => (selectedIds.has(p.id) ? { ...p, is_trashed: 1 } : p))
      );

      const count = idsToTrash.length;
      setIsConfirmModalOpen(false);
      setIsSelectMode(false);
      setSelectedIds(new Set());
      loadStats();

      setToastMessage(`Moved ${count} photo${count === 1 ? '' : 's'} to trash`);
      setTimeout(() => setToastMessage(null), 4000);
    } catch (err) {
      console.error('Failed to batch trash photos:', err);
      alert('Failed to move selected photos to trash: ' + err.message);
    } finally {
      setIsTrashBatchLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Ambient background glows */}
      <div className="ambient-bg">
        <div className="ambient-orb-1" />
        <div className="ambient-orb-2" />
      </div>

      {/* Toast notification banner */}
      {toastMessage && (
        <div className="toast-notification">
          <CheckCircle2 size={16} color="#10b981" />
          <span>{toastMessage}</span>
          <button
            className="toast-btn-action"
            onClick={() => {
              setActiveTab('trash');
              setToastMessage(null);
            }}
          >
            View Trash
          </button>
        </div>
      )}

      {/* Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={(tab) => {
          if (isSelectMode) handleExitSelectMode();
          setActiveTab(tab);
        }}
        stats={stats}
        onOpenScanModal={() => setIsScanModalOpen(true)}
        onOpenMobileModal={() => setIsMobileModalOpen(true)}
        onRefresh={handleRefreshLibrary}
      />

      {/* Main Container */}
      <main className="main-content">
        {activeTab === 'photos' && (
          <>
            {/* Semantic Vector Search Hero */}
            <SemanticSearch
              query={query}
              setQuery={setQuery}
              onSearch={handleSearch}
              isLoading={isLoading}
              parsedQuery={parsedQuery}
            />

            {/* Timeline Scrubber */}
            <TimelineScrubber
              timelineYears={stats?.timeline_years || []}
              selectedYear={selectedYear}
              onSelectYear={handleSelectYear}
              totalPhotos={stats?.total_photos || totalPhotos}
            />

            {/* Filter and sorting controls */}
            <div className="controls-bar">
              <div className="filter-group">
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#94a3b8', fontSize: '0.825rem' }}>
                  <SlidersHorizontal size={15} />
                  <span>Filters:</span>
                </div>

                {/* Camera filter */}
                {stats?.top_cameras?.length > 0 && (
                  <select
                    className="select-styled"
                    value={cameraMake}
                    onChange={(e) => setCameraMake(e.target.value)}
                  >
                    <option value="">All Cameras</option>
                    {stats.top_cameras.map((c, i) => (
                      <option key={i} value={c.camera_make}>
                        {c.camera_make} {c.camera_model} ({c.count})
                      </option>
                    ))}
                  </select>
                )}

                {/* GPS Filter */}
                <select
                  className="select-styled"
                  value={hasGps === null ? '' : hasGps.toString()}
                  onChange={(e) => {
                    const val = e.target.value;
                    setHasGps(val === '' ? null : val === 'true');
                  }}
                >
                  <option value="">All Locations</option>
                  <option value="true">Geotagged (Has GPS)</option>
                  <option value="false">No GPS Data</option>
                </select>

                {/* Duplicates Toggle */}
                <label className="toggle-switch-label">
                  <input
                    type="checkbox"
                    checked={includeDuplicates}
                    onChange={(e) => setIncludeDuplicates(e.target.checked)}
                    style={{ accentColor: '#10b981', cursor: 'pointer' }}
                  />
                  <span>Show Duplicates</span>
                </label>
              </div>

              {/* Sort Order & Multi-Select Toggle */}
              <div className="filter-group">
                {/* Manual Select Mode Toggle */}
                <button
                  type="button"
                  className={`btn-select-mode-toggle ${isSelectMode ? 'active' : ''}`}
                  onClick={() => {
                    if (isSelectMode) {
                      handleExitSelectMode();
                    } else {
                      setIsSelectMode(true);
                    }
                  }}
                  title={isSelectMode ? 'Exit Select Mode (Esc)' : 'Enter multi-select mode to mark multiple photos for deletion/trash'}
                >
                  <CheckSquare size={14} />
                  <span>{isSelectMode ? 'Exit Select' : 'Select Mode'}</span>
                </button>

                <span style={{ fontSize: '0.825rem', color: '#94a3b8' }}>Sort:</span>
                <select
                  className="select-styled"
                  value={`${sortBy}_${sortOrder}`}
                  onChange={(e) => {
                    const [f, o] = e.target.value.split('_');
                    setSortBy(f);
                    setSortOrder(o);
                  }}
                >
                  <option value="date_taken_DESC">Newest Date Taken</option>
                  <option value="date_taken_ASC">Oldest Date Taken</option>
                  <option value="file_size_DESC">Largest File Size</option>
                  <option value="file_name_ASC">File Name (A-Z)</option>
                </select>
              </div>
            </div>

            {/* Photo Grid */}
            <PhotoGrid
              photos={photos}
              totalPhotos={totalPhotos}
              onSelectPhoto={(photo) => setSelectedPhoto(photo)}
              onToggleTrash={handleToggleTrashPhoto}
              onStartTrashSelect={handleStartTrashSelect}
              isSelectMode={isSelectMode}
              selectedIds={selectedIds}
              onToggleSelectPhoto={handleToggleSelectPhoto}
              query={query}
              isLoading={isLoading}
              isLoadingMore={isLoadingMore}
              hasMore={hasMore}
              onLoadMore={handleLoadMore}
            />
          </>
        )}

        {activeTab === 'duplicates' && (
          <DuplicatesView
            onSelectPhoto={(photo) => setSelectedPhoto(photo)}
            onLibraryUpdated={handleRefreshLibrary}
          />
        )}

        {activeTab === 'filtered' && (
          <FilteredView
            onSelectPhoto={(photo) => setSelectedPhoto(photo)}
            onRefreshStats={handleRefreshLibrary}
          />
        )}

        {activeTab === 'trash' && (
          <TrashView
            onSelectPhoto={(photo) => setSelectedPhoto(photo)}
            onLibraryUpdated={handleRefreshLibrary}
          />
        )}
      </main>

      {/* Mobile Bottom Navigation Bar (Visible only on small mobile screens) */}
      <div className="mobile-bottom-nav">
        <button
          className={`mobile-nav-item ${activeTab === 'photos' ? 'active' : ''}`}
          onClick={() => setActiveTab('photos')}
        >
          <Sparkles size={20} />
          <span>Photos</span>
        </button>

        <button
          className={`mobile-nav-item ${activeTab === 'duplicates' ? 'active' : ''}`}
          onClick={() => setActiveTab('duplicates')}
        >
          <Copy size={20} />
          <span>Duplicates</span>
        </button>

        <button
          className={`mobile-nav-item ${activeTab === 'filtered' ? 'active' : ''}`}
          onClick={() => setActiveTab('filtered')}
        >
          <ShieldAlert size={20} />
          <span>Filtered</span>
        </button>

        <button
          className={`mobile-nav-item ${activeTab === 'trash' ? 'active' : ''}`}
          onClick={() => setActiveTab('trash')}
        >
          <Trash2 size={20} />
          <span>Trash</span>
        </button>

        <button
          className="mobile-nav-item"
          onClick={() => setIsMobileModalOpen(true)}
        >
          <Smartphone size={20} />
          <span>Wi-Fi IP</span>
        </button>
      </div>

      {/* Floating Batch Selection Bar */}
      {isSelectMode && activeTab === 'photos' && (
        <TrashSelectionBar
          selectedCount={selectedIds.size}
          totalVisible={photos.length}
          onSelectAll={handleSelectAllVisible}
          onDeselectAll={handleDeselectAll}
          onOpenConfirm={() => setIsConfirmModalOpen(true)}
          onCancel={handleExitSelectMode}
          totalBytes={totalSelectedBytes}
        />
      )}

      {/* Confirmation Modal for moving selected photos to trash */}
      <ConfirmTrashModal
        isOpen={isConfirmModalOpen}
        onClose={() => setIsConfirmModalOpen(false)}
        onConfirm={handleConfirmBatchTrash}
        selectedPhotos={selectedPhotosList}
        isLoading={isTrashBatchLoading}
      />

      {/* Lightbox / EXIF Inspector Modal */}
      {selectedPhoto && (
        <Lightbox
          photo={selectedPhoto}
          onClose={() => setSelectedPhoto(null)}
          onReclassifySuccess={handleRefreshLibrary}
          onPhotoDeleted={handleRefreshLibrary}
          onTrashStatusChanged={handleRefreshLibrary}
        />
      )}

      {/* Folder Scan Modal */}
      <ScanModal
        isOpen={isScanModalOpen}
        onClose={() => setIsScanModalOpen(false)}
        onScanFinished={handleRefreshLibrary}
      />

      {/* Mobile / Wi-Fi QR Code Modal */}
      <MobileConnectModal
        isOpen={isMobileModalOpen}
        onClose={() => setIsMobileModalOpen(false)}
      />
    </div>
  );
}

