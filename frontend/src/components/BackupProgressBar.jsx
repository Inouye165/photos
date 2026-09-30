import React, { useState, useEffect, useRef } from 'react';
import {
  Cloud,
  CloudCheck,
  CloudUpload,
  CloudOff,
  Pause,
  Play,
  Settings,
  X,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Clock,
  RotateCcw,
  RefreshCw,
  FileCode
} from 'lucide-react';
import {
  fetchBackupStatus,
  fetchBackupAuthUrl,
  exchangeBackupCode,
  startBackupAuth,
  disconnectBackup,
  pauseBackup,
  resumeBackup,
  updateBackupSettings,
  retryFailedBackups
} from '../api';

export default function BackupProgressBar() {
  const [state, setState] = useState(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isCheckingConfig, setIsCheckingConfig] = useState(false);
  const [actionError, setActionError] = useState('');
  const [isRetrying, setIsRetrying] = useState(false);
  const [directAuthUrl, setDirectAuthUrl] = useState('');
  const [manualCode, setManualCode] = useState('');
  const [isExchangingCode, setIsExchangingCode] = useState(false);
  const [successBanner, setSuccessBanner] = useState('');
  const [copiedLink, setCopiedLink] = useState(false);
  const [editLimit, setEditLimit] = useState(25);
  const [editDelay, setEditDelay] = useState(30);
  const popoverRef = useRef(null);
  const hasInitializedInputs = useRef(false);

  const loadStatus = async () => {
    try {
      const data = await fetchBackupStatus();
      setState(data);
      if (data && !hasInitializedInputs.current) {
        setEditLimit(data.hourly_limit || 25);
        setEditDelay(data.delay_seconds || 30);
        hasInitializedInputs.current = true;
      }
      return data;
    } catch (err) {
      console.warn('Could not fetch backup status:', err);
      return null;
    }
  };

  useEffect(() => {
    // Check if redirected from successful Google OAuth
    const params = new URLSearchParams(window.location.search);
    if (params.get('backup_connected') === 'true') {
      setSuccessBanner('✓ Google Drive linked! Background backup has started.');
      window.history.replaceState({}, '', window.location.pathname);
      setIsOpen(true);
      loadStatus();
    }
  }, []);

  // Live polling: refresh status every 2.5s when popover open, every 8s in background
  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, isOpen ? 2500 : 8000);
    return () => clearInterval(interval);
  }, [isOpen]);

  // Close popover on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  if (!state) return null;

  const {
    stats,
    status,
    current_file,
    uploads_this_hour,
    hourly_limit,
    is_paused,
    is_authenticated,
    is_configured = true
  } = state;
  const total = stats?.total_photos || 0;
  const backedUp = stats?.backed_up_count || 0;
  const pct = total > 0 ? Math.min(100, Math.round((backedUp / total) * 100)) : 0;

  const handleCheckConfig = async () => {
    setIsCheckingConfig(true);
    setActionError('');
    try {
      const data = await loadStatus();
      if (data && data.is_configured) {
        setSuccessBanner('✓ credentials.json detected! Click "Authorize Google Drive" below.');
      } else {
        setActionError('credentials.json was not found in backend/. Please make sure the file is saved as photos/backend/credentials.json and check again.');
      }
    } catch (err) {
      setActionError('Error checking configuration: ' + err.message);
    } finally {
      setIsCheckingConfig(false);
    }
  };

  const handleConnect = async () => {
    setIsConnecting(true);
    setActionError('');
    try {
      const data = await fetchBackupAuthUrl();
      if (data && data.auth_url) {
        setDirectAuthUrl(data.auth_url);
        // Direct browser navigation to Google authorization page
        window.location.href = data.auth_url;
      }
    } catch (e) {
      // If error is about missing credentials, display clearly
      if (e.message && e.message.includes('credentials.json')) {
        setActionError(e.message);
        loadStatus();
      } else {
        // Fallback: trigger background server launcher
        try {
          await startBackupAuth();
          setTimeout(loadStatus, 2000);
          setTimeout(loadStatus, 5000);
        } catch (e2) {
          setActionError(e2.message || e.message || 'Could not start Google authorization.');
        }
      }
    } finally {
      setIsConnecting(false);
    }
  };

  const handleManualCodeSubmit = async (e) => {
    e.preventDefault();
    if (!manualCode.trim()) return;
    setIsExchangingCode(true);
    setActionError('');
    try {
      await exchangeBackupCode(manualCode.trim());
      setSuccessBanner('✓ Google Drive linked successfully!');
      setManualCode('');
      await loadStatus();
    } catch (err) {
      setActionError('Failed to authorize with code: ' + err.message);
    } finally {
      setIsExchangingCode(false);
    }
  };

  const handleCopyLink = async () => {
    try {
      let url = directAuthUrl;
      if (!url) {
        const data = await fetchBackupAuthUrl();
        url = data.auth_url;
        setDirectAuthUrl(url);
      }
      await navigator.clipboard.writeText(url);
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 3000);
    } catch (err) {
      alert('Please copy manually: ' + directAuthUrl);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Disconnect your Google Drive account? No files will be deleted from your Drive.')) return;
    setIsUpdating(true);
    try {
      await disconnectBackup();
      await loadStatus();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleTogglePause = async () => {
    setIsUpdating(true);
    try {
      if (is_paused) {
        await resumeBackup();
      } else {
        await pauseBackup();
      }
      await loadStatus();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setIsUpdating(true);
    try {
      const updated = await updateBackupSettings({
        hourly_limit: parseInt(editLimit, 10),
        delay_seconds: parseFloat(editDelay)
      });
      if (updated) {
        setEditLimit(updated.hourly_limit);
        setEditDelay(updated.delay_seconds);
        hasInitializedInputs.current = true;
      }
      await loadStatus();
    } finally {
      setIsUpdating(false);
    }
  };

  const handleRetryFailed = async () => {
    setIsRetrying(true);
    try {
      await retryFailedBackups();
      await loadStatus();
    } catch (err) {
      alert('Failed to retry: ' + err.message);
    } finally {
      setIsRetrying(false);
    }
  };

  // Status icon & label
  let statusIcon = <Cloud size={14} className="text-slate-400" />;
  let statusText = 'Not Connected';

  if (!is_configured) {
    statusIcon = <AlertCircle size={14} style={{ color: '#f59e0b' }} />;
    statusText = 'Setup Drive';
  } else if (!is_authenticated) {
    statusIcon = <CloudOff size={14} style={{ color: '#94a3b8' }} />;
    statusText = 'Connect Drive';
  } else if (is_paused) {
    statusIcon = <Pause size={14} style={{ color: '#f59e0b' }} />;
    statusText = 'Backup Paused';
  } else if (stats?.failed_count > 0 || status === 'error') {
    statusIcon = <AlertCircle size={14} style={{ color: '#f87171' }} />;
    statusText = stats?.failed_count > 0 ? `${stats.failed_count} Failed` : 'Backup Issue';
  } else if (status === 'uploading') {
    statusIcon = <CloudUpload size={14} style={{ color: '#06b6d4' }} className="animate-pulse" />;
    statusText = `Syncing (${uploads_this_hour}/${hourly_limit}/hr)`;
  } else if (status === 'throttled') {
    statusIcon = <Clock size={14} style={{ color: '#a855f7' }} />;
    statusText = `Hourly Cap (${uploads_this_hour}/${hourly_limit})`;
  } else if (backedUp >= total && total > 0) {
    statusIcon = <CloudCheck size={14} style={{ color: '#10b981' }} />;
    statusText = 'Backed Up';
  } else if (stats?.pending_count > 0) {
    statusIcon = <Cloud size={14} style={{ color: '#38bdf8' }} />;
    statusText = `Pacing (${backedUp.toLocaleString()} / ${total.toLocaleString()})`;
  } else {
    statusIcon = <Cloud size={14} style={{ color: '#38bdf8' }} />;
    statusText = `${backedUp.toLocaleString()} / ${total.toLocaleString()}`;
  }

  return (
    <div className="backup-widget-container" ref={popoverRef} style={{ position: 'relative' }}>
      {/* Compact Header Pill */}
      <button
        type="button"
        className={`backup-pill ${status === 'uploading' ? 'syncing' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title="Google Drive Conservative Backup"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '5px 12px',
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '20px',
          color: '#e2e8f0',
          fontSize: '12px',
          fontWeight: 500,
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          backdropFilter: 'blur(8px)',
          minWidth: '135px'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center' }}>
          {statusIcon}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', textAlign: 'left', flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {statusText}
            </span>
            {is_authenticated && total > 0 && (
              <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 600 }}>{pct}%</span>
            )}
          </div>

          {/* Slender Progress Bar */}
          {is_authenticated && total > 0 && (
            <div
              style={{
                width: '100%',
                height: '3px',
                background: 'rgba(255, 255, 255, 0.1)',
                borderRadius: '2px',
                marginTop: '3px',
                overflow: 'hidden'
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: is_paused
                    ? '#f59e0b'
                    : 'linear-gradient(90deg, #06b6d4, #10b981)',
                  borderRadius: '2px',
                  transition: 'width 0.4s ease'
                }}
              />
            </div>
          )}
        </div>
      </button>

      {/* Detail Popover Panel */}
      {isOpen && (
        <div
          className="backup-popover glass-panel"
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: '350px',
            padding: '16px',
            background: 'rgba(15, 23, 42, 0.96)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '12px',
            boxShadow: '0 16px 36px rgba(0,0,0,0.6)',
            backdropFilter: 'blur(16px)',
            zIndex: 1000,
            color: '#e2e8f0',
            fontSize: '13px'
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Cloud size={16} color="#38bdf8" />
              <strong style={{ fontSize: '13px', color: '#f8fafc' }}>Google Drive Backup</strong>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
            >
              <X size={15} />
            </button>
          </div>

          {/* Success Banner if redirected from auth or verified */}
          {successBanner && (
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.2)',
                border: '1px solid rgba(16, 185, 129, 0.4)',
                borderRadius: '8px',
                padding: '10px',
                marginBottom: '12px',
                color: '#6ee7b7',
                fontSize: '12px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              <CheckCircle2 size={15} color="#34d399" />
              <span>{successBanner}</span>
            </div>
          )}

          {!is_configured ? (
            /* Setup Instructions Panel */
            <div>
              <div
                style={{
                  background: 'rgba(245, 158, 11, 0.12)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                  borderRadius: '10px',
                  padding: '12px',
                  marginBottom: '12px',
                  fontSize: '12px',
                  lineHeight: 1.5,
                  color: '#fef3c7'
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: '6px', color: '#fbbf24', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <AlertCircle size={15} />
                  <span>Google Drive Setup Required</span>
                </div>
                <p style={{ margin: '0 0 10px 0', color: '#cbd5e1', fontSize: '11.5px', lineHeight: 1.4 }}>
                  To protect your privacy and backup directly to your personal Google storage, LuminaPhoto uses your own Google Cloud OAuth credentials:
                </p>

                <ol style={{ margin: '0 0 10px 0', paddingLeft: '18px', color: '#cbd5e1', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <li>
                    Open <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer" style={{ color: '#38bdf8', textDecoration: 'underline' }}>Google Cloud Console</a> & create a project.
                  </li>
                  <li>
                    Enable the <strong>Google Drive API</strong>.
                  </li>
                  <li>
                    In <strong>OAuth consent screen</strong>, choose <em>External</em> and add your email to <em>Test users</em>.
                  </li>
                  <li>
                    In <strong>Credentials</strong>, click <em>Create Credentials</em> &rarr; <em>OAuth client ID</em> (Type: <strong>Desktop app</strong>).
                  </li>
                  <li>
                    Download client JSON, rename to <strong>credentials.json</strong>, and place it at:
                  </li>
                </ol>

                <div
                  style={{
                    padding: '6px 8px',
                    background: 'rgba(0, 0, 0, 0.45)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '6px',
                    fontFamily: 'monospace',
                    fontSize: '10.5px',
                    color: '#67e8f9',
                    wordBreak: 'break-all',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                >
                  <FileCode size={13} style={{ flexShrink: 0, color: '#38bdf8' }} />
                  <span>photos/backend/credentials.json</span>
                </div>
              </div>

              {actionError && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.35)',
                    borderRadius: '8px',
                    padding: '8px 10px',
                    marginBottom: '12px',
                    color: '#fca5a5',
                    fontSize: '11.5px',
                    lineHeight: 1.4,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '6px'
                  }}
                >
                  <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <span>{actionError}</span>
                </div>
              )}

              <button
                type="button"
                onClick={handleCheckConfig}
                disabled={isCheckingConfig}
                className="btn-primary"
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  padding: '9px 14px',
                  borderRadius: '8px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: isCheckingConfig ? 'wait' : 'pointer'
                }}
              >
                <RefreshCw size={14} className={isCheckingConfig ? 'animate-spin' : ''} />
                <span>{isCheckingConfig ? 'Verifying credentials.json...' : 'Check Configuration'}</span>
              </button>
            </div>
          ) : !is_authenticated ? (
            /* Robust Connect Prompt */
            <div style={{ textAlign: 'center', padding: '6px 0' }}>
              <p style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '14px', lineHeight: 1.5 }}>
                Click below to sign in to Google. Your photos will back up in the background organized by Year and Month.
              </p>

              {actionError && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.35)',
                    borderRadius: '8px',
                    padding: '8px 10px',
                    marginBottom: '12px',
                    color: '#fca5a5',
                    fontSize: '11.5px',
                    textAlign: 'left',
                    lineHeight: 1.4,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '6px'
                  }}
                >
                  <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '2px' }} />
                  <span>{actionError}</span>
                </div>
              )}

              <button
                onClick={handleConnect}
                disabled={isConnecting}
                className="btn-primary"
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                <ExternalLink size={15} />
                <span>{isConnecting ? 'Opening Google Sign-In...' : 'Authorize Google Drive'}</span>
              </button>

              {/* Direct fallback link & copy button */}
              <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <button
                  type="button"
                  onClick={handleCopyLink}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#38bdf8',
                    fontSize: '11px',
                    cursor: 'pointer',
                    textDecoration: 'underline'
                  }}
                >
                  {copiedLink ? '✓ Authorization link copied to clipboard!' : 'Copy sign-in link to clipboard'}
                </button>
              </div>

              {/* Optional code paste fallback */}
              <form onSubmit={handleManualCodeSubmit} style={{ marginTop: '10px' }}>
                <details style={{ fontSize: '11px', color: '#64748b' }}>
                  <summary style={{ cursor: 'pointer', marginBottom: '6px' }}>Have an authorization code?</summary>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                    <input
                      type="text"
                      placeholder="Paste code from Google"
                      value={manualCode}
                      onChange={(e) => setManualCode(e.target.value)}
                      style={{
                        flex: 1,
                        padding: '4px 8px',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '4px',
                        color: '#f8fafc',
                        fontSize: '11px'
                      }}
                    />
                    <button
                      type="submit"
                      disabled={isExchangingCode}
                      style={{
                        padding: '4px 8px',
                        background: 'rgba(16, 185, 129, 0.2)',
                        border: '1px solid rgba(16, 185, 129, 0.4)',
                        borderRadius: '4px',
                        color: '#34d399',
                        fontSize: '11px',
                        cursor: 'pointer'
                      }}
                    >
                      {isExchangingCode ? '...' : 'Submit'}
                    </button>
                  </div>
                </details>
              </form>
            </div>
          ) : (
            /* Active Sync Status */
            <div>
              {/* Error / Failure Banner if any */}
              {(stats?.failed_count > 0 || status === 'error') && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: '8px',
                    padding: '10px',
                    marginBottom: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fca5a5', fontWeight: 600, fontSize: '12px' }}>
                    <AlertCircle size={14} color="#f87171" />
                    <span>
                      {stats?.failed_count > 0
                        ? `${stats.failed_count} photo(s) failed to back up`
                        : 'Backup encountered an error'}
                    </span>
                  </div>
                  {state.status_message && (
                    <div style={{ fontSize: '11px', color: '#fecaca', lineHeight: 1.4 }}>
                      {state.status_message}
                    </div>
                  )}
                  {stats?.failed_count > 0 && (
                    <button
                      type="button"
                      onClick={handleRetryFailed}
                      disabled={isRetrying}
                      style={{
                        marginTop: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '6px 10px',
                        background: 'rgba(239, 68, 68, 0.3)',
                        border: '1px solid rgba(239, 68, 68, 0.5)',
                        borderRadius: '6px',
                        color: '#ffffff',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      <RotateCcw size={12} />
                      <span>{isRetrying ? 'Retrying...' : 'Retry Failed Photos'}</span>
                    </button>
                  )}
                </div>
              )}

              {/* Stats Box */}
              <div
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: '8px',
                  padding: '10px',
                  marginBottom: '12px'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ color: '#94a3b8' }}>Status</span>
                  <span style={{ fontWeight: 600, color: is_paused ? '#f59e0b' : status === 'uploading' ? '#06b6d4' : status === 'throttled' ? '#a855f7' : (stats?.pending_count > 0 ? '#38bdf8' : '#10b981') }}>
                    {is_paused
                      ? 'Paused'
                      : status === 'uploading'
                      ? 'Uploading photo...'
                      : status === 'throttled'
                      ? 'Throttled (Hourly Cap Reached)'
                      : stats?.pending_count > 0
                      ? `Pacing (${state.delay_seconds || 30}s spacing delay)`
                      : 'All Photos Backed Up'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ color: '#94a3b8' }}>Backed Up</span>
                  <span style={{ fontWeight: 600, color: '#10b981' }}>
                    {backedUp.toLocaleString()} / {total.toLocaleString()} ({pct}%)
                  </span>
                </div>
                {stats?.pending_count > 0 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ color: '#94a3b8' }}>Remaining</span>
                    <span style={{ fontWeight: 500, color: '#cbd5e1' }}>
                      {stats.pending_count.toLocaleString()} photos
                    </span>
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ color: '#94a3b8' }}>This Hour</span>
                  <span style={{ fontWeight: 500, color: '#f8fafc' }}>
                    {uploads_this_hour} / {hourly_limit} max
                  </span>
                </div>
                {current_file ? (
                  <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>Current upload:</span>
                    <div style={{ fontSize: '12px', color: '#38bdf8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {current_file}
                    </div>
                  </div>
                ) : state.status_message ? (
                  <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>Last completed:</span>
                    <div style={{ fontSize: '12px', color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {state.status_message}
                    </div>
                  </div>
                ) : null}
              </div>

              {/* Action Controls */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                <button
                  type="button"
                  onClick={handleTogglePause}
                  disabled={isUpdating}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '7px 10px',
                    background: is_paused ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    border: `1px solid ${is_paused ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                    borderRadius: '6px',
                    color: is_paused ? '#34d399' : '#fbbf24',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                >
                  {is_paused ? <Play size={13} /> : <Pause size={13} />}
                  <span>{is_paused ? 'Resume' : 'Pause'}</span>
                </button>

                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={isUpdating}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '7px 10px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.25)',
                    borderRadius: '6px',
                    color: '#f87171',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                  title="Disconnect Google Drive"
                >
                  <CloudOff size={13} />
                  <span>Disconnect</span>
                </button>
              </div>

              {/* Conservative Rate Settings */}
              <form onSubmit={handleSaveSettings} style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '10px' }}>
                <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Throttling Safeguards
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '2px' }}>Max / Hour</label>
                    <input
                      type="number"
                      min="5"
                      max="2000"
                      value={editLimit}
                      onChange={(e) => setEditLimit(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '4px 8px',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '4px',
                        color: '#f8fafc',
                        fontSize: '12px'
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '2px' }}>Delay (sec)</label>
                    <input
                      type="number"
                      min="1"
                      max="300"
                      value={editDelay}
                      onChange={(e) => setEditDelay(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '4px 8px',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '4px',
                        color: '#f8fafc',
                        fontSize: '12px'
                      }}
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={isUpdating}
                  style={{
                    width: '100%',
                    padding: '5px',
                    background: 'rgba(255,255,255,0.06)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    borderRadius: '4px',
                    color: '#94a3b8',
                    fontSize: '11px',
                    cursor: 'pointer'
                  }}
                >
                  Apply Rate Limits
                </button>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
