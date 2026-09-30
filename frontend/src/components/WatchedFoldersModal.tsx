import React, { useState, useEffect, useCallback } from 'react';
import {
  FolderCheck,
  FolderOpen,
  FolderPlus,
  Trash2,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
  X,
  RefreshCw,
  HardDrive,
  Cloud,
  FolderSync
} from 'lucide-react';
import {
  fetchWatchedFolders,
  addWatchedFolder,
  removeWatchedFolder,
  syncWatchedFolder,
  syncAllWatchedFolders,
  pickFolderWithExplorer
} from '../documentsApi';
import { WatchedFolder, AllowedRoot } from '../types/documents';
import { validateFolderToWatch } from '../utils/documentPathFilter';

interface WatchedFoldersModalProps {
  isOpen: boolean;
  onClose: () => void;
  onFoldersChanged?: () => void;
}

export const WatchedFoldersModal: React.FC<WatchedFoldersModalProps> = ({
  isOpen,
  onClose,
  onFoldersChanged
}) => {
  const [folders, setFolders] = useState<WatchedFolder[]>([]);
  const [allowedRoots, setAllowedRoots] = useState<AllowedRoot[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [inputPath, setInputPath] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [isPickingExplorer, setIsPickingExplorer] = useState<boolean>(false);

  const showStatus = (text: string, type: 'success' | 'error' = 'success') => {
    setStatusMessage({ type, text });
    setTimeout(() => setStatusMessage(null), 4000);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchWatchedFolders();
      setFolders(data.watched_folders || []);
      setAllowedRoots(data.allowed_roots || []);
    } catch (err: any) {
      showStatus(err.message || 'Failed to load watched folders', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadData();
      setInputPath('');
      setValidationError(null);
      setStatusMessage(null);
    }
  }, [isOpen, loadData]);

  // Live input validation
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputPath(val);
    if (!val.trim()) {
      setValidationError(null);
      return;
    }
    const check = validateFolderToWatch(val, allowedRoots);
    if (!check.valid) {
      setValidationError(check.reason || 'Invalid path');
    } else {
      setValidationError(null);
    }
  };

  const handleBrowseExplorer = async () => {
    try {
      setIsPickingExplorer(true);
      const res = await pickFolderWithExplorer(inputPath || null);
      if (res.selected && res.folder_path) {
        setInputPath(res.folder_path);
        const check = validateFolderToWatch(res.folder_path, allowedRoots);
        if (!check.valid) {
          setValidationError(check.reason || 'Invalid path');
        } else {
          setValidationError(null);
        }
      }
    } catch (err: any) {
      showStatus(err.message || 'Explorer picker error', 'error');
    } finally {
      setIsPickingExplorer(false);
    }
  };

  const handleAddFolder = async (pathToUse?: string) => {
    const targetPath = (pathToUse || inputPath).trim();
    if (!targetPath) {
      setValidationError('Please choose or enter a folder path.');
      return;
    }

    const check = validateFolderToWatch(targetPath, allowedRoots);
    if (!check.valid) {
      setValidationError(check.reason || 'Path not allowed');
      return;
    }

    setActionLoading(true);
    try {
      const res = await addWatchedFolder(targetPath);
      showStatus(res.message || 'Folder added to watch list!', 'success');
      setInputPath('');
      setValidationError(null);
      await loadData();
      if (onFoldersChanged) onFoldersChanged();
    } catch (err: any) {
      showStatus(err.message || 'Failed to add folder', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveFolder = async (folderId: number, folderPath: string) => {
    setActionLoading(true);
    try {
      await removeWatchedFolder(folderId);
      showStatus(`Stopped watching: ${folderPath}`, 'success');
      await loadData();
      if (onFoldersChanged) onFoldersChanged();
    } catch (err: any) {
      showStatus(err.message || 'Failed to remove folder', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSyncFolder = async (folderId: number, folderPath: string) => {
    setActionLoading(true);
    try {
      const res = await syncWatchedFolder(folderId);
      showStatus(res.message || `Background sync started for: ${folderPath}`, 'success');
      if (onFoldersChanged) onFoldersChanged();
    } catch (err: any) {
      showStatus(err.message || 'Failed to sync folder', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSyncAllFolders = async () => {
    setActionLoading(true);
    try {
      const res = await syncAllWatchedFolders();
      showStatus(res.message || 'Background sync started for all watched folders', 'success');
      if (onFoldersChanged) onFoldersChanged();
    } catch (err: any) {
      showStatus(err.message || 'Failed to sync all folders', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleWatchAllBaseFolders = async () => {
    const unwatched = allowedRoots.filter(
      (r) => r.exists && !folders.some((f) => f.folder_path.toLowerCase() === r.path.toLowerCase())
    );
    if (unwatched.length === 0) {
      showStatus('All detected base folders are already being watched!', 'success');
      return;
    }

    setActionLoading(true);
    let addedCount = 0;
    try {
      for (const root of unwatched) {
        await addWatchedFolder(root.path);
        addedCount++;
      }
      showStatus(`Successfully added ${addedCount} base folder${addedCount > 1 ? 's' : ''} to watch list!`, 'success');
      await loadData();
      if (onFoldersChanged) onFoldersChanged();
    } catch (err: any) {
      showStatus(err.message || 'Failed while adding base folders', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        zIndex: 10000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px'
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '680px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 60px rgba(0, 0, 0, 0.7)',
          overflow: 'hidden'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0) 100%)'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '10px',
                background: 'rgba(56, 189, 248, 0.15)',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#38bdf8'
              }}
            >
              <FolderSync size={22} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
                Watched Document Folders
              </h2>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                Auto-indexes new and modified documents in the background. Isolated from photos.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Strict Policy Banner */}
          <div
            style={{
              background: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              borderRadius: '12px',
              padding: '14px 16px',
              display: 'flex',
              gap: '12px',
              alignItems: 'flex-start'
            }}
          >
            <ShieldCheck size={20} color="#38bdf8" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: 1.5 }}>
              <strong style={{ color: '#38bdf8', display: 'block', marginBottom: '2px' }}>
                Document Privacy & Scope Boundary
              </strong>
              Only folders inside <strong>Windows Documents</strong>, <strong>Windows Downloads</strong>, or <strong>OneDrive Documents & Downloads</strong> can be watched or scanned. System drives, Desktop, and photo folders remain completely untouched.
            </div>
          </div>

          {/* Quick-Add Allowed Roots */}
          {allowedRoots.length > 0 && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>
                  Quick Add Base Folders:
                </div>
                {allowedRoots.filter(r => r.exists && !folders.some(f => f.folder_path.toLowerCase() === r.path.toLowerCase())).length > 0 && (
                  <button
                    onClick={handleWatchAllBaseFolders}
                    disabled={actionLoading}
                    style={{
                      background: 'rgba(56, 189, 248, 0.15)',
                      border: '1px solid rgba(56, 189, 248, 0.4)',
                      color: '#38bdf8',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: actionLoading ? 'wait' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px'
                    }}
                  >
                    <FolderCheck size={13} />
                    <span>Watch All Base Folders ({allowedRoots.filter(r => r.exists && !folders.some(f => f.folder_path.toLowerCase() === r.path.toLowerCase())).length})</span>
                  </button>
                )}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '8px' }}>
                {allowedRoots.map((root) => {
                  const isAlreadyWatched = folders.some(
                    (f) => f.folder_path.toLowerCase() === root.path.toLowerCase()
                  );
                  return (
                    <div
                      key={root.key}
                      style={{
                        background: 'rgba(30, 41, 59, 0.4)',
                        border: '1px solid rgba(255, 255, 255, 0.06)',
                        borderRadius: '10px',
                        padding: '10px 12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '8px'
                      }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
                          {root.source === 'OneDrive' ? (
                            <Cloud size={14} color="#0284c7" />
                          ) : (
                            <HardDrive size={14} color="#38bdf8" />
                          )}
                          <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0' }}>{root.name}</span>
                          {!root.exists && (
                            <span style={{ fontSize: '10px', color: '#f59e0b', background: 'rgba(245, 158, 11, 0.1)', padding: '1px 5px', borderRadius: '4px' }}>
                              Not created yet
                            </span>
                          )}
                        </div>
                        <div
                          style={{
                            fontSize: '11px',
                            color: '#64748b',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}
                          title={root.path}
                        >
                          {root.path}
                        </div>
                      </div>

                      <button
                        onClick={() => handleAddFolder(root.path)}
                        disabled={actionLoading || isAlreadyWatched || !root.exists}
                        style={{
                          background: isAlreadyWatched
                            ? 'rgba(52, 211, 153, 0.12)'
                            : 'rgba(56, 189, 248, 0.15)',
                          border: `1px solid ${isAlreadyWatched ? 'rgba(52, 211, 153, 0.3)' : 'rgba(56, 189, 248, 0.4)'}`,
                          color: isAlreadyWatched ? '#34d399' : '#38bdf8',
                          padding: '6px 10px',
                          borderRadius: '6px',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: isAlreadyWatched || !root.exists ? 'default' : 'pointer',
                          whiteSpace: 'nowrap',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        {isAlreadyWatched ? (
                          <>
                            <CheckCircle2 size={13} />
                            <span>Watching</span>
                          </>
                        ) : (
                          <>
                            <FolderPlus size={13} />
                            <span>Watch</span>
                          </>
                        )}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Add Custom Subfolder Form */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
              Add a Specific Subfolder to Watch:
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={inputPath}
                onChange={handleInputChange}
                placeholder="Enter path or click Browse with Explorer..."
                style={{
                  flex: 1,
                  background: 'rgba(0, 0, 0, 0.3)',
                  border: `1px solid ${validationError ? '#f43f5e' : 'rgba(255, 255, 255, 0.15)'}`,
                  borderRadius: '8px',
                  color: '#f8fafc',
                  padding: '9px 12px',
                  fontSize: '13px',
                  outline: 'none'
                }}
              />
              <button
                type="button"
                onClick={handleBrowseExplorer}
                disabled={isPickingExplorer || actionLoading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(30, 41, 59, 0.8)',
                  border: '1px solid rgba(56, 189, 248, 0.4)',
                  color: '#38bdf8',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: isPickingExplorer ? 'wait' : 'pointer',
                  whiteSpace: 'nowrap'
                }}
                title="Select folder using native Windows Explorer dialog"
              >
                {isPickingExplorer ? <RefreshCw size={14} className="spin-animation" /> : <FolderOpen size={14} />}
                <span>Browse</span>
              </button>

              <button
                type="button"
                onClick={() => handleAddFolder()}
                disabled={actionLoading || !inputPath.trim() || !!validationError}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: !inputPath.trim() || !!validationError
                    ? 'rgba(255, 255, 255, 0.05)'
                    : 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                  border: 'none',
                  color: !inputPath.trim() || !!validationError ? '#64748b' : '#ffffff',
                  padding: '9px 16px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: !inputPath.trim() || !!validationError ? 'not-allowed' : 'pointer',
                  whiteSpace: 'nowrap'
                }}
              >
                <FolderPlus size={14} />
                <span>Add Folder</span>
              </button>
            </div>

            {/* Validation feedback */}
            {validationError && (
              <div
                style={{
                  marginTop: '6px',
                  fontSize: '12px',
                  color: '#f43f5e',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}
              >
                <AlertCircle size={14} />
                <span>{validationError}</span>
              </div>
            )}
          </div>

          {/* Status Message */}
          {statusMessage && (
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                fontSize: '12px',
                background:
                  statusMessage.type === 'success'
                    ? 'rgba(16, 185, 129, 0.12)'
                    : 'rgba(244, 63, 94, 0.12)',
                border: `1px solid ${statusMessage.type === 'success' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`,
                color: statusMessage.type === 'success' ? '#34d399' : '#f43f5e'
              }}
            >
              {statusMessage.text}
            </div>
          )}

          {/* Currently Watched Folders List */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>
                Active Watched Folders ({folders.length}):
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {folders.length > 0 && (
                  <button
                    onClick={handleSyncAllFolders}
                    disabled={actionLoading}
                    title="Scan and index existing and modified documents across all watched folders"
                    style={{
                      background: 'rgba(56, 189, 248, 0.12)',
                      border: '1px solid rgba(56, 189, 248, 0.35)',
                      color: '#38bdf8',
                      cursor: actionLoading ? 'wait' : 'pointer',
                      fontSize: '11px',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 8px',
                      borderRadius: '6px'
                    }}
                  >
                    <FolderSync size={12} />
                    <span>Sync All Now</span>
                  </button>
                )}
                <button
                  onClick={loadData}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#64748b',
                    cursor: 'pointer',
                    fontSize: '11px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <RefreshCw size={12} className={loading ? 'spin-animation' : ''} />
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            {loading && folders.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
                Loading watched folders...
              </div>
            ) : folders.length === 0 ? (
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px dashed rgba(255, 255, 255, 0.1)',
                  borderRadius: '10px',
                  padding: '24px',
                  textAlign: 'center',
                  color: '#64748b'
                }}
              >
                <FolderCheck size={32} style={{ margin: '0 auto 8px', opacity: 0.5 }} />
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#94a3b8' }}>
                  No Watched Folders Configured
                </div>
                <div style={{ fontSize: '11px', marginTop: '4px' }}>
                  Click "Watch" on any base folder above or add a custom subfolder to automatically index documents in real-time.
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {folders.map((item) => (
                  <div
                    key={item.id}
                    style={{
                      background: 'rgba(15, 23, 42, 0.7)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '12px'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: item.exists ? '#10b981' : '#f59e0b',
                          boxShadow: item.exists ? '0 0 8px #10b981' : 'none',
                          flexShrink: 0
                        }}
                        title={item.exists ? 'Live folder active' : 'Folder does not exist on disk'}
                      />
                      <div style={{ minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: '13px',
                            color: '#f8fafc',
                            fontWeight: 500,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap'
                          }}
                          title={item.folder_path}
                        >
                          {item.folder_path}
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', gap: '8px', marginTop: '2px' }}>
                          <span>Added {new Date(item.added_at * 1000).toLocaleDateString()}</span>
                          {!item.exists && (
                            <span style={{ color: '#f59e0b' }}>• Directory missing on PC</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                      <button
                        onClick={() => handleSyncFolder(item.id, item.folder_path)}
                        disabled={actionLoading}
                        title={`Scan and index existing & updated documents in:\n${item.folder_path}`}
                        style={{
                          background: 'rgba(56, 189, 248, 0.1)',
                          border: '1px solid rgba(56, 189, 248, 0.25)',
                          color: '#38bdf8',
                          padding: '5px 9px',
                          borderRadius: '6px',
                          cursor: actionLoading ? 'wait' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          fontSize: '11px',
                          fontWeight: 600
                        }}
                      >
                        <RefreshCw size={11} className={actionLoading ? 'spin-animation' : ''} />
                        <span>Sync Now</span>
                      </button>

                      <button
                        onClick={() => handleRemoveFolder(item.id, item.folder_path)}
                        disabled={actionLoading}
                        title="Stop watching this folder"
                        style={{
                          background: 'rgba(244, 63, 94, 0.1)',
                          border: '1px solid rgba(244, 63, 94, 0.25)',
                          color: '#f43f5e',
                          padding: '6px',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center'
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            justifyContent: 'flex-end',
            background: 'rgba(15, 23, 42, 0.5)'
          }}
        >
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              color: '#f8fafc',
              padding: '8px 18px',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
