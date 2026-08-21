import React from 'react';
import { Camera, Copy, ShieldAlert, FolderSearch, Sparkles, RefreshCw, Smartphone } from 'lucide-react';

export default function Header({
  activeTab,
  setActiveTab,
  stats,
  onOpenScanModal,
  onOpenMobileModal,
  onRefresh
}) {
  return (
    <header className="glass-header">
      {/* Brand */}
      <div className="brand-section" onClick={() => setActiveTab('photos')}>
        <div className="brand-icon">
          <Camera size={20} color="#ffffff" />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="brand-title">LuminaPhoto</span>
            <span className="brand-badge">In-Place Pointer</span>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <nav className="nav-tabs">
        <button
          className={`nav-tab-btn tab-photos ${activeTab === 'photos' ? 'active' : ''}`}
          onClick={() => setActiveTab('photos')}
        >
          <Sparkles size={16} />
          <span>Photos</span>
          {stats?.total_photos !== undefined && (
            <span className="nav-badge">{stats.total_photos.toLocaleString()}</span>
          )}
        </button>

        <button
          className={`nav-tab-btn tab-dups ${activeTab === 'duplicates' ? 'active' : ''}`}
          onClick={() => setActiveTab('duplicates')}
        >
          <Copy size={16} />
          <span>Duplicates</span>
          {stats?.total_duplicates > 0 && (
            <span className="nav-badge" style={{ background: 'rgba(245, 158, 11, 0.3)', color: '#fde68a' }}>
              {stats.total_duplicates}
            </span>
          )}
        </button>

        <button
          className={`nav-tab-btn tab-filtered ${activeTab === 'filtered' ? 'active' : ''}`}
          onClick={() => setActiveTab('filtered')}
        >
          <ShieldAlert size={16} />
          <span>Filtered Assets</span>
          {stats?.total_screenshots > 0 && (
            <span className="nav-badge">{stats.total_screenshots}</span>
          )}
        </button>
      </nav>

      {/* Header Actions */}
      <div className="header-actions">
        <button
          className="btn-secondary"
          onClick={onOpenMobileModal}
          title="Connect Phone / Wi-Fi"
          style={{ borderColor: 'rgba(16, 185, 129, 0.3)', color: '#34d399' }}
        >
          <Smartphone size={15} />
          <span className="hide-on-mobile">Phone / Wi-Fi</span>
        </button>

        <button className="btn-secondary" onClick={onRefresh} title="Refresh Library">
          <RefreshCw size={15} />
        </button>

        <button className="btn-primary" onClick={onOpenScanModal}>
          <FolderSearch size={16} />
          <span className="hide-on-mobile">Scan Folder</span>
        </button>
      </div>
    </header>
  );
}
