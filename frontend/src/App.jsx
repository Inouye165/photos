import React, { useState, useEffect, useCallback, useRef } from 'react';
import Header from './components/Header';
import SemanticSearch from './components/SemanticSearch';
import PhotoGrid from './components/PhotoGrid';
import Lightbox from './components/Lightbox';
import DuplicatesView from './components/DuplicatesView';
import FilteredView from './components/FilteredView';
import ScanModal from './components/ScanModal';
import MobileConnectModal from './components/MobileConnectModal';
import TimelineScrubber from './components/TimelineScrubber';
import { fetchPhotos, fetchStats } from './api';
import { Filter, SlidersHorizontal, MapPin, Eye, EyeOff, Sparkles, Copy, ShieldAlert, Smartphone, Calendar } from 'lucide-react';

const PAGE_SIZE = 80;

export default function App() {
  const [activeTab, setActiveTab] = useState('photos'); // 'photos', 'duplicates', 'filtered'
  const [photos, setPhotos] = useState([]);
  const [totalPhotos, setTotalPhotos] = useState(0);
  const [stats, setStats] = useState(null);
  
  // Search & Filter state
  const [query, setQuery] = useState('');
  const [selectedYear, setSelectedYear] = useState(null);
  const [cameraMake, setCameraMake] = useState('');
  const [hasGps, setHasGps] = useState(null);
  const [includeDuplicates, setIncludeDuplicates] = useState(true);
  const [sortBy, setSortBy] = useState('date_taken');
  const [sortOrder, setSortOrder] = useState('DESC');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);

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

  const loadPhotos = useCallback((options = {}) => {
    const isLoadMore = options.isLoadMore || false;
    const searchQuery = options.searchQuery !== undefined ? options.searchQuery : query;
    const yearFilter = options.year !== undefined ? options.year : selectedYear;

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
        offset: photos.length
      })
        .then((data) => {
          const newItems = data.photos || [];
          setPhotos((prev) => [...prev, ...newItems]);
          setTotalPhotos(data.total || 0);
          setHasMore(photos.length + newItems.length < (data.total || 0));
          setIsLoadingMore(false);
        })
        .catch((err) => {
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
        offset: 0
      })
        .then((data) => {
          const items = data.photos || [];
          setPhotos(items);
          setTotalPhotos(data.total || 0);
          setHasMore(items.length < (data.total || 0));
          setIsLoading(false);
        })
        .catch((err) => {
          console.error('Error loading photos:', err);
          setIsLoading(false);
        });
    }
  }, [query, selectedYear, includeDuplicates, cameraMake, hasGps, sortBy, sortOrder, photos.length]);

  // Initial load or filter changes
  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadPhotos({ isLoadMore: false });
  }, [query, selectedYear, includeDuplicates, cameraMake, hasGps, sortBy, sortOrder]);

  const handleSearch = (searchQuery) => {
    setQuery(searchQuery);
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

  return (
    <div className="app-container">
      {/* Ambient background glows */}
      <div className="ambient-bg">
        <div className="ambient-orb-1" />
        <div className="ambient-orb-2" />
      </div>

      {/* Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
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

              {/* Sort Order */}
              <div className="filter-group">
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
          className="mobile-nav-item"
          onClick={() => setIsMobileModalOpen(true)}
        >
          <Smartphone size={20} />
          <span>Wi-Fi IP</span>
        </button>
      </div>

      {/* Lightbox / EXIF Inspector Modal */}
      {selectedPhoto && (
        <Lightbox
          photo={selectedPhoto}
          onClose={() => setSelectedPhoto(null)}
          onReclassifySuccess={handleRefreshLibrary}
          onPhotoDeleted={handleRefreshLibrary}
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
