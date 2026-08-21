import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import SemanticSearch from './components/SemanticSearch';
import PhotoGrid from './components/PhotoGrid';
import Lightbox from './components/Lightbox';
import DuplicatesView from './components/DuplicatesView';
import FilteredView from './components/FilteredView';
import ScanModal from './components/ScanModal';
import MobileConnectModal from './components/MobileConnectModal';
import { fetchPhotos, fetchStats } from './api';
import { Filter, SlidersHorizontal, MapPin, Eye, EyeOff, Sparkles, Copy, ShieldAlert, Smartphone } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('photos'); // 'photos', 'duplicates', 'filtered'
  const [photos, setPhotos] = useState([]);
  const [totalPhotos, setTotalPhotos] = useState(0);
  const [stats, setStats] = useState(null);
  
  // Search & Filter state
  const [query, setQuery] = useState('');
  const [cameraMake, setCameraMake] = useState('');
  const [hasGps, setHasGps] = useState(null);
  const [includeDuplicates, setIncludeDuplicates] = useState(true);
  const [sortBy, setSortBy] = useState('date_taken');
  const [sortOrder, setSortOrder] = useState('DESC');
  const [isLoading, setIsLoading] = useState(false);

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

  const loadPhotos = useCallback((searchQuery = query) => {
    setIsLoading(true);
    fetchPhotos({
      query: searchQuery,
      includeDuplicates,
      cameraMake: cameraMake || null,
      hasGps: hasGps,
      sortBy,
      sortOrder,
      limit: 100,
      offset: 0
    })
      .then((data) => {
        setPhotos(data.photos || []);
        setTotalPhotos(data.total || 0);
        setIsLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setIsLoading(false);
      });
  }, [query, includeDuplicates, cameraMake, hasGps, sortBy, sortOrder]);

  useEffect(() => {
    loadStats();
    loadPhotos();
  }, [loadStats, loadPhotos]);

  const handleSearch = (searchQuery) => {
    setQuery(searchQuery);
    loadPhotos(searchQuery);
  };

  const handleRefreshLibrary = useCallback(() => {
    loadStats();
    loadPhotos();
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
              onSelectPhoto={(photo) => setSelectedPhoto(photo)}
              query={query}
              isLoading={isLoading}
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
