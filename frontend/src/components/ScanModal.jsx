import React, { useState, useEffect, useRef } from 'react';
import { X, Folder, FolderOpen, ChevronRight, CornerLeftUp, Play, Square, AlertCircle, Trash2, CheckCircle2 } from 'lucide-react';
import { startScan, stopScan, fetchScanStatus, fetchDefaultPath, fetchBrowseFolders, clearCatalog } from '../api';

export default function ScanModal({ isOpen, onClose, onScanFinished }) {
  const [folderPath, setFolderPath] = useState('');
  const [suggestedPath, setSuggestedPath] = useState('');
  const [browserData, setBrowserData] = useState({ current_path: '', parent_path: null, subfolders: [] });
  const [scanStatus, setScanStatus] = useState(null);
  const [isStarting, setIsStarting] = useState(false);
  const [clearFirst, setClearFirst] = useState(false);
  const [error, setError] = useState(null);
  const [showBrowser, setShowBrowser] = useState(true);
  
  const wasScanningRef = useRef(false);
  const onScanFinishedRef = useRef(onScanFinished);
  onScanFinishedRef.current = onScanFinished;

  const loadDirectory = (path) => {
    fetchBrowseFolders(path)
      .then((data) => {
        setBrowserData(data);
        if (data.current_path) {
          setFolderPath(data.current_path);
        }
      })
      .catch((err) => console.error(err));
  };

  useEffect(() => {
    if (isOpen) {
      fetchDefaultPath().then((data) => {
        if (data?.suggested_path) {
          setSuggestedPath(data.suggested_path);
          if (!folderPath) {
            setFolderPath(data.suggested_path);
            loadDirectory(data.suggested_path);
          }
        }
      });
    }
  }, [isOpen]);

  // Polling loop for active scan status
  useEffect(() => {
    let interval = null;
    if (isOpen) {
      const checkStatus = () => {
        fetchScanStatus().then((status) => {
          setScanStatus(status);
          const isNowScanning = status.status === 'SCANNING' ||
                                status.status === 'DEDUPLICATING' ||
                                status.status === 'EMBEDDING';
          if (isNowScanning) {
            wasScanningRef.current = true;
          } else if (wasScanningRef.current && status.status === 'COMPLETED') {
            wasScanningRef.current = false;
            if (onScanFinishedRef.current) {
              onScanFinishedRef.current();
            }
          }
        });
      };
      checkStatus();
      interval = setInterval(checkStatus, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleClose = () => {
    onClose();
  };

  const handleStartScan = async () => {
    if (!folderPath.trim()) return;
    try {
      setIsStarting(true);
      setError(null);
      if (clearFirst) {
        await clearCatalog();
      }
      await startScan(folderPath.trim());
    } catch (err) {
      setError(err.message);
    } finally {
      setIsStarting(false);
    }
  };

  const handleStopScan = async () => {
    try {
      await stopScan();
      if (onScanFinished) onScanFinished();
    } catch (err) {
      console.error(err);
    }
  };

  const isScanning = scanStatus?.status === 'SCANNING' ||
                     scanStatus?.status === 'DEDUPLICATING' ||
                     scanStatus?.status === 'EMBEDDING';

  const percent = scanStatus?.total_found > 0
    ? Math.min(100, Math.round((scanStatus.processed_count / scanStatus.total_found) * 100))
    : 0;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-card" style={{ maxWidth: '640px' }} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Folder size={22} color="#10b981" />
            <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.35rem', color: '#ffffff' }}>
              Choose Folder to Scan
            </h2>
          </div>
          <button
            onClick={handleClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '4px'
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Directory Input */}
        <div style={{ marginBottom: '1rem' }}>
          <label style={{ display: 'block', fontSize: '0.825rem', color: '#94a3b8', marginBottom: '0.5rem', fontWeight: 500 }}>
            Target Folder Path (Will index this folder and its subfolders):
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              className="search-input"
              style={{
                background: '#161b28',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                padding: '0.65rem 0.9rem',
                fontSize: '0.9rem',
                color: '#ffffff',
                width: '100%'
              }}
              placeholder="e.g. C:\Users\inouy\photos\sample_library\vacation_2025"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              onBlur={() => folderPath && loadDirectory(folderPath)}
              disabled={isScanning}
            />
          </div>
        </div>

        {/* Interactive Subfolder Explorer */}
        {showBrowser && !isScanning && (
          <div style={{
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '10px',
            padding: '0.85rem',
            marginBottom: '1rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
              <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                📁 Select a Subfolder:
              </span>
              {browserData.parent_path && (
                <button
                  type="button"
                  onClick={() => loadDirectory(browserData.parent_path)}
                  style={{
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '6px',
                    color: '#94a3b8',
                    padding: '3px 8px',
                    fontSize: '0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    cursor: 'pointer'
                  }}
                >
                  <CornerLeftUp size={12} /> Up one folder
                </button>
              )}
            </div>

            {browserData.subfolders.length === 0 ? (
              <div style={{ fontSize: '0.8rem', color: '#64748b', padding: '0.5rem 0' }}>
                No child subfolders inside this directory. (Ready to scan this folder directly)
              </div>
            ) : (
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '6px',
                maxHeight: '140px',
                overflowY: 'auto',
                paddingRight: '4px'
              }}>
                {browserData.subfolders.map((sub) => (
                  <button
                    key={sub.path}
                    type="button"
                    onClick={() => {
                      setFolderPath(sub.path);
                      loadDirectory(sub.path);
                    }}
                    style={{
                      background: folderPath === sub.path ? 'rgba(16, 185, 129, 0.2)' : 'rgba(30, 41, 59, 0.8)',
                      border: folderPath === sub.path ? '1px solid #10b981' : '1px solid rgba(255, 255, 255, 0.08)',
                      color: folderPath === sub.path ? '#34d399' : '#e2e8f0',
                      borderRadius: '6px',
                      padding: '5px 10px',
                      fontSize: '0.8rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <FolderOpen size={13} color={folderPath === sub.path ? '#10b981' : '#60a5fa'} />
                    <span>{sub.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Clear previous test samples option */}
        {!isScanning && (
          <div style={{ marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input
              type="checkbox"
              id="clearCatalogCheck"
              checked={clearFirst}
              onChange={(e) => setClearFirst(e.target.checked)}
              style={{ cursor: 'pointer', accentColor: '#10b981', width: '15px', height: '15px' }}
            />
            <label htmlFor="clearCatalogCheck" style={{ fontSize: '0.825rem', color: '#cbd5e1', cursor: 'pointer' }}>
              Clear previous test/sample photos first (starts fresh with only this folder)
            </label>
          </div>
        )}

        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#fca5a5',
            padding: '0.75rem',
            borderRadius: '8px',
            fontSize: '0.85rem',
            marginBottom: '1rem'
          }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* Live Progress Info */}
        {scanStatus && scanStatus.status !== 'IDLE' && (
          <div style={{
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '12px',
            padding: '1.25rem',
            marginBottom: '1.5rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.85rem' }}>
              <span style={{ fontWeight: 600, color: '#f8fafc' }}>
                Status: <span style={{ color: '#10b981' }}>{scanStatus.status}</span>
              </span>
              <span style={{ color: '#94a3b8' }}>
                {scanStatus.processed_count} / {scanStatus.total_found} Files ({percent}%)
              </span>
            </div>

            {/* Progress Bar */}
            <div className="progress-bar-wrap">
              <div className="progress-bar-fill" style={{ width: `${percent}%` }} />
            </div>

            <div style={{
              fontSize: '0.78rem',
              color: '#64748b',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginBottom: '1rem'
            }}>
              Current: {scanStatus.current_file || 'Processing...'}
            </div>

            {/* Metrics Counters */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem', textAlign: 'center' }}>
              <div style={{ background: '#121722', padding: '0.6rem 0.4rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#34d399' }}>{scanStatus.photos_count}</div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Verified Photos</div>
              </div>
              <div style={{ background: '#121722', padding: '0.6rem 0.4rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f87171' }}>{scanStatus.screenshots_count + scanStatus.system_assets_count}</div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Screenshots Filtered</div>
              </div>
              <div style={{ background: '#121722', padding: '0.6rem 0.4rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fde68a' }}>{scanStatus.duplicates_count}</div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Duplicate Groups</div>
              </div>
              <div style={{ background: '#121722', padding: '0.6rem 0.4rem', borderRadius: '8px' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#c7d2fe' }}>{scanStatus.embeddings_count}</div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Vector Vectors</div>
              </div>
            </div>
          </div>
        )}

        {/* Modal Buttons */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>

          {isScanning ? (
            <button
              className="btn-primary"
              style={{ background: '#ef4444' }}
              onClick={handleStopScan}
            >
              <Square size={16} />
              <span>Stop Scan</span>
            </button>
          ) : (
            <button
              className="btn-primary"
              onClick={handleStartScan}
              disabled={isStarting || !folderPath.trim()}
            >
              <Play size={16} />
              <span>{isStarting ? 'Starting...' : 'Start Indexing'}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
