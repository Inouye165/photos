import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText,
  Search,
  Sparkles,
  FolderSearch,
  Download,
  ExternalLink,
  Eye,
  Trash2,
  CheckCircle,
  Clock,
  HardDrive,
  Filter,
  Layers,
  ShieldCheck,
  AlertCircle,
  X,
  RefreshCw,
  SlidersHorizontal,
  FileCode,
  FileSpreadsheet,
  FileCheck2,
  BookOpen,
  Copy,
  Folder,
  FolderOpen,
  FolderCheck,
  Check,
  RotateCcw,
  Maximize2,
  FolderSync
} from 'lucide-react';
import {
  fetchDocuments,
  searchDocumentsSemantically,
  fetchDocumentStats,
  fetchScanRoots,
  startDocumentsScan,
  stopDocumentsScan,
  fetchScanStatus,
  fetchDocumentDetails,
  analyzeDocument,
  updateDocumentReview,
  fetchInterestLists,
  saveInterestList,
  deleteDocumentRecord,
  trashDocument,
  restoreDocument,
  permanentlyDeleteDocument,
  emptyDocumentsTrash,
  openDocumentsTrashFolder,
  getDocumentFileUrl,
  pickFolderWithExplorer,
  openDocumentInSystemApp,
  revealDocumentInExplorer,
  openDocumentFolder,
  revealPathInExplorer,
  clearDocumentsCatalog,
  fetchWatchedFolders
} from '../documentsApi';
import { WatchedFoldersModal } from './WatchedFoldersModal';

function getFolderPath(filePath) {
  if (!filePath) return '';
  const lastSep = Math.max(filePath.lastIndexOf('\\'), filePath.lastIndexOf('/'));
  return lastSep !== -1 ? filePath.substring(0, lastSep) : filePath;
}

function formatBytes(bytes, decimals = 1) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatDate(timestamp) {
  if (!timestamp) return 'Unknown';
  try {
    const d = new Date(timestamp * 1000);
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return 'Unknown';
  }
}

function getFileTypeMeta(ext) {
  const clean = (ext || '').toLowerCase().replace('.', '');
  switch (clean) {
    case 'pdf':
      return { label: 'PDF', color: '#f43f5e', bg: 'rgba(244, 63, 94, 0.15)', icon: FileText };
    case 'docx':
    case 'doc':
      return { label: 'WORD', color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.15)', icon: BookOpen };
    case 'txt':
    case 'md':
    case 'rtf':
      return { label: 'TEXT', color: '#34d399', bg: 'rgba(52, 211, 153, 0.15)', icon: FileCode };
    case 'xlsx':
    case 'xls':
    case 'csv':
      return { label: 'SHEET', color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', icon: FileSpreadsheet };
    case 'pptx':
    case 'ppt':
      return { label: 'SLIDE', color: '#fb923c', bg: 'rgba(251, 146, 60, 0.15)', icon: Layers };
    default:
      return { label: clean.toUpperCase() || 'DOC', color: '#a78bfa', bg: 'rgba(167, 139, 250, 0.15)', icon: FileText };
  }
}

function CsvViewer({ text }) {
  if (!text) return <div style={{ color: '#94a3b8', fontStyle: 'italic', padding: '20px' }}>Empty spreadsheet file</div>;
  const lines = text.split(/\r?\n/).filter(l => l.trim().length > 0).slice(0, 150);
  const rows = lines.map(line => {
    const regex = /(?:,|\n|^)("(?:(?:"")*[^"]*)*"|[^",\n]*|(?:\n|$))/g;
    const matches = [];
    let match;
    while ((match = regex.exec(line)) !== null) {
      if (match.index === regex.lastIndex) regex.lastIndex++;
      let val = match[1] || '';
      if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1).replace(/""/g, '"');
      matches.push(val);
      if (regex.lastIndex >= line.length) break;
    }
    return matches.length > 0 ? matches : line.split(',');
  });

  const header = rows[0] || [];
  const body = rows.slice(1);

  return (
    <div style={{ overflowX: 'auto', maxHeight: '600px', background: '#090d16', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
        <thead>
          <tr style={{ background: 'rgba(56, 189, 248, 0.12)', borderBottom: '1px solid rgba(56, 189, 248, 0.25)' }}>
            <th style={{ padding: '10px 14px', color: '#64748b', width: '40px', borderRight: '1px solid rgba(255,255,255,0.06)' }}>#</th>
            {header.map((col, idx) => (
              <th key={idx} style={{ padding: '10px 14px', color: '#38bdf8', fontWeight: 700, whiteSpace: 'nowrap', borderRight: '1px solid rgba(255,255,255,0.04)' }}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rIdx) => (
            <tr key={rIdx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', background: rIdx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)' }}>
              <td style={{ padding: '8px 14px', color: '#64748b', fontSize: '11px', borderRight: '1px solid rgba(255,255,255,0.06)' }}>{rIdx + 1}</td>
              {row.map((cell, cIdx) => (
                <td key={cIdx} style={{ padding: '8px 14px', color: '#e2e8f0', whiteSpace: 'nowrap', maxWidth: '320px', overflow: 'hidden', textOverflow: 'ellipsis', borderRight: '1px solid rgba(255,255,255,0.03)' }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DocumentCard = React.memo(function DocumentCard({
  doc,
  isTrashView,
  onOpenDoc,
  onOpenInSystem,
  onRevealInExplorer,
  onRestoreDoc,
  onPermanentlyDeleteDoc,
  onTrashDoc
}) {
  const meta = getFileTypeMeta(doc.file_extension);
  const Icon = meta.icon;
  const hasSnippet = doc.match_snippet || doc.snippet;

  return (
    <div
      onClick={() => onOpenDoc(doc)}
      style={{
        background: '#1e293b',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '14px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
        position: 'relative'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.borderColor = 'rgba(56, 189, 248, 0.4)';
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(0, 0, 0, 0.3)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'none';
        e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px', marginBottom: '10px' }}>
          <span style={{
            background: meta.bg,
            color: meta.color,
            fontWeight: 800,
            fontSize: '11px',
            padding: '3px 8px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}>
            <Icon size={12} />
            {meta.label}
          </span>

          {doc.score !== undefined && (
            <span style={{
              background: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '10px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '3px'
            }}>
              <Sparkles size={11} /> {Math.round(doc.score * 100)}% match
            </span>
          )}

          {doc.duplicate_count > 0 && (
            <span style={{
              background: 'rgba(245, 158, 11, 0.2)',
              color: '#fbbf24',
              border: '1px solid rgba(245, 158, 11, 0.4)',
              fontSize: '11px',
              padding: '2px 8px',
              borderRadius: '10px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
            title={`${doc.duplicate_count + 1} identical copies found across your computer`}
            >
              <Copy size={11} /> {doc.duplicate_count + 1} copies
            </span>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              onClick={(e) => onOpenInSystem(doc.id, e)}
              title="Open in native desktop application (Word, PDF, Excel, etc.)"
              style={{
                background: 'rgba(56, 189, 248, 0.1)',
                border: '1px solid rgba(56, 189, 248, 0.25)',
                color: '#38bdf8',
                cursor: 'pointer',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '4px'
              }}
            >
              <ExternalLink size={12} /> Open
            </button>

            <button
              onClick={(e) => onRevealInExplorer(doc.id, e)}
              title={`Open containing folder in Windows Explorer:\n${doc.original_path || doc.copied_path || doc.file_name}`}
              style={{
                background: 'rgba(56, 189, 248, 0.12)',
                border: '1px solid rgba(56, 189, 248, 0.28)',
                color: '#38bdf8',
                cursor: 'pointer',
                padding: '3px 8px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                transition: 'all 0.15s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(56, 189, 248, 0.22)';
                e.currentTarget.style.borderColor = '#38bdf8';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(56, 189, 248, 0.12)';
                e.currentTarget.style.borderColor = 'rgba(56, 189, 248, 0.28)';
              }}
            >
              <FolderOpen size={12} /> Folder
            </button>

            {isTrashView ? (
              <>
                <button
                  onClick={(e) => onRestoreDoc(doc.id, e)}
                  title="Restore document back to active library"
                  style={{
                    background: 'rgba(52, 211, 153, 0.15)',
                    border: '1px solid rgba(52, 211, 153, 0.4)',
                    color: '#34d399',
                    cursor: 'pointer',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <RotateCcw size={12} /> Restore
                </button>

                <button
                  onClick={(e) => onPermanentlyDeleteDoc(doc.id, e)}
                  title="Permanently delete from holding folder (leaves PC original safe)"
                  style={{
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    color: '#f87171',
                    cursor: 'pointer',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <Trash2 size={12} /> Delete
                </button>
              </>
            ) : (
              <button
                onClick={(e) => onTrashDoc(doc.id, e)}
                title="Move copy to Documents Trash holding folder (leaves original safe)"
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '2px'
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = '#f87171'}
                onMouseLeave={(e) => e.currentTarget.style.color = '#64748b'}
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        </div>

        <h3 style={{
          margin: '0 0 6px 0',
          fontSize: '15px',
          fontWeight: 700,
          color: '#f8fafc',
          lineHeight: 1.4,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical'
        }}>
          {doc.title || doc.file_name}
        </h3>

        <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {doc.file_name}
        </div>

        {/* File & Folder Location Bar */}
        {(doc.original_path || doc.copied_path) && (
          <div
            onClick={(e) => onRevealInExplorer(doc.id, e)}
            title={`Full Location:\n${doc.original_path || doc.copied_path}\n\nClick to open containing folder in Windows Explorer`}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid rgba(56, 189, 248, 0.22)',
              padding: '6px 10px',
              borderRadius: '8px',
              marginBottom: '12px',
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#38bdf8';
              e.currentTarget.style.background = 'rgba(56, 189, 248, 0.14)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(56, 189, 248, 0.22)';
              e.currentTarget.style.background = 'rgba(15, 23, 42, 0.85)';
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
              <FolderOpen size={14} color="#38bdf8" style={{ flexShrink: 0 }} />
              <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
                <span style={{
                  fontSize: '9.5px',
                  fontWeight: 700,
                  color: '#64748b',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  lineHeight: 1.1
                }}>
                  Folder Location
                </span>
                <span style={{
                  color: '#cbd5e1',
                  fontSize: '11px',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}>
                  {getFolderPath(doc.original_path || doc.copied_path)}
                </span>
              </div>
            </div>
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10.5px',
              fontWeight: 600,
              color: '#38bdf8',
              background: 'rgba(56, 189, 248, 0.14)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              padding: '2px 8px',
              borderRadius: '5px',
              flexShrink: 0
            }}>
              Open Folder ↗
            </span>
          </div>
        )}

        {/* Text Snippet / Excerpt */}
        {hasSnippet && (
          <div style={{
            background: 'rgba(15, 23, 42, 0.6)',
            padding: '10px',
            borderRadius: '8px',
            fontSize: '12px',
            color: '#cbd5e1',
            lineHeight: 1.5,
            marginBottom: '14px',
            maxHeight: '90px',
            overflow: 'hidden',
            borderLeft: `3px solid ${meta.color}`
          }}>
            {hasSnippet}
          </div>
        )}
      </div>

      {/* Card Footer: Metadata */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '11px',
        color: '#94a3b8',
        borderTop: '1px solid rgba(255, 255, 255, 0.05)',
        paddingTop: '10px'
      }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <span>{formatBytes(doc.file_size)}</span>
          {doc.page_count > 1 && <span>• {doc.page_count} pages</span>}
          {doc.word_count > 0 && <span>• {doc.word_count.toLocaleString()} words</span>}
        </div>
        <div>
          {formatDate(doc.modified_at)}
        </div>
      </div>
    </div>
  );
});

export default function DocumentsView() {
  const [documents, setDocuments] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [isSemanticMode, setIsSemanticMode] = useState(true);
  const [selectedExtension, setSelectedExtension] = useState('ALL');
  const [sortBy, setSortBy] = useState('modified_at');
  const [sortOrder, setSortOrder] = useState('DESC');

  // Preview / Detail Modal
  const [activeDoc, setActiveDoc] = useState(null);
  const [docViewMode, setDocViewMode] = useState('visual'); // 'visual' | 'text'
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [interestLists, setInterestLists] = useState([]);
  const [newListName, setNewListName] = useState('');
  const [newListDescription, setNewListDescription] = useState('');

  // Computer Scan Modal & State
  const [isScanModalOpen, setIsScanModalOpen] = useState(false);
  const [isClearConfirmOpen, setIsClearConfirmOpen] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [scanMode, setScanMode] = useState('all_allowed_folders'); // 'all_allowed_folders' | 'single_folder'
  const [selectedRootsToScan, setSelectedRootsToScan] = useState([]);
  const [singleFolderPath, setSingleFolderPath] = useState('');
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [scanStatus, setScanStatus] = useState(null);
  const [scanRootsInfo, setScanRootsInfo] = useState(null);
  const [customRootsInput, setCustomRootsInput] = useState('');
  const [isPickingFolder, setIsPickingFolder] = useState(false);
  const [toast, setToast] = useState(null);

  // Watched Folders Modal & State
  const [isWatchedModalOpen, setIsWatchedModalOpen] = useState(false);
  const [watchedCount, setWatchedCount] = useState(0);

  // Trash Holding Area State
  const [isTrashView, setIsTrashView] = useState(false);

  const scanPollRef = useRef(null);
  const searchAbortRef = useRef(null);

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3500);
  };

  const loadWatchedCount = useCallback(() => {
    fetchWatchedFolders()
      .then(res => setWatchedCount(res.watched_folders?.length || 0))
      .catch(() => {});
  }, []);

  const loadInterestLists = useCallback(() => {
    fetchInterestLists()
      .then(res => setInterestLists(res.interest_lists || []))
      .catch(() => {});
  }, []);

  const handleSaveInterestList = async (event) => {
    event.preventDefault();
    if (!newListName.trim()) return;
    try {
      const saved = await saveInterestList(newListName.trim(), newListDescription.trim());
      setInterestLists(prev => [...prev, saved]);
      setNewListName('');
      setNewListDescription('');
      showToast(`Highlight list "${saved.name}" saved`);
    } catch (err) {
      showToast('Could not save highlight list: ' + err.message);
    }
  };

  const loadStats = useCallback(() => {
    fetchDocumentStats()
      .then(setStats)
      .catch(console.error);
  }, []);

  const wasScanningRef = useRef(false);

  const loadDocuments = useCallback(async (isBackground = false) => {
    if (searchAbortRef.current) {
      searchAbortRef.current.abort();
    }
    searchAbortRef.current = new AbortController();
    const signal = searchAbortRef.current.signal;

    // Only show full loading spinner if not a background update
    if (!isBackground) {
      setLoading(true);
    }
    try {
      if (isTrashView) {
        const ext = selectedExtension === 'ALL' ? null : selectedExtension;
        const res = await fetchDocuments({
          search: debouncedQuery.trim(),
          fileExtension: ext,
          sortBy,
          sortOrder,
          limit: 100,
          isTrashed: true,
          signal
        });
        setDocuments(res.documents || []);
        setTotalCount(res.total || 0);
      } else if (debouncedQuery.trim() && isSemanticMode) {
        // Semantic search
        const res = await searchDocumentsSemantically({ q: debouncedQuery.trim(), topK: 50, signal });
        let items = res.results || [];
        if (selectedExtension !== 'ALL') {
          items = items.filter(d => (d.file_extension || '').toLowerCase() === selectedExtension.toLowerCase());
        }
        setDocuments(items);
        setTotalCount(items.length);
      } else {
        // Standard filtered retrieval
        const ext = selectedExtension === 'ALL' ? null : selectedExtension;
        const res = await fetchDocuments({
          search: debouncedQuery.trim(),
          fileExtension: ext,
          sortBy,
          sortOrder,
          limit: 100,
          isTrashed: false,
          signal
        });
        setDocuments(res.documents || []);
        setTotalCount(res.total || 0);
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        console.error('Error loading documents:', e);
      }
    } finally {
      setLoading(false);
    }
  }, [debouncedQuery, isSemanticMode, selectedExtension, sortBy, sortOrder, isTrashView]);

  useEffect(() => {
    loadDocuments(false);
    loadStats();
    loadWatchedCount();
    loadInterestLists();
  }, [loadDocuments, loadStats, loadWatchedCount, loadInterestLists]);

  // Periodic scan status polling - purely checks scan progress, NEVER forces re-fetches while idle!
  const pollScanStatus = useCallback(async () => {
    try {
      const st = await fetchScanStatus();
      setScanStatus(st);

      // Only refresh documents if a scan was active and just transitioned to completed!
      if (wasScanningRef.current && !st.is_scanning) {
        loadStats();
        loadDocuments(true); // silent background refresh, no UI flicker
        loadWatchedCount();
      }
      wasScanningRef.current = Boolean(st?.is_scanning);

      if (st.is_scanning) {
        scanPollRef.current = setTimeout(pollScanStatus, 2000);
      }
    } catch (err) {
      console.error('Failed to poll scan status:', err);
    }
  }, [loadStats, loadDocuments, loadWatchedCount]);

  useEffect(() => {
    pollScanStatus();
    // Poll scan status every 10s when idle without refreshing documents
    const interval = setInterval(pollScanStatus, 10000);
    return () => {
      clearInterval(interval);
      if (scanPollRef.current) clearTimeout(scanPollRef.current);
    };
  }, [pollScanStatus]);

  const handleOpenScanModal = async () => {
    setIsScanModalOpen(true);
    setScanMode('all_allowed_folders');
    try {
      const roots = await fetchScanRoots();
      setScanRootsInfo(roots);
      if (roots?.roots?.length > 0) {
        setSelectedRootsToScan(roots.roots);
        if (!singleFolderPath) {
          setSingleFolderPath(roots.roots[0]);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggleScanRoot = (rootPath) => {
    setSelectedRootsToScan(prev => {
      if (prev.includes(rootPath)) {
        return prev.filter(p => p !== rootPath);
      } else {
        return [...prev, rootPath];
      }
    });
  };

  const handleSelectAllRoots = () => {
    if (scanRootsInfo?.roots) {
      setSelectedRootsToScan(scanRootsInfo.roots);
    }
  };

  const handleDeselectAllRoots = () => {
    setSelectedRootsToScan([]);
  };

  const handleBrowseFolderWithExplorer = async () => {
    try {
      setIsPickingFolder(true);
      const res = await pickFolderWithExplorer(singleFolderPath || null);
      if (res.selected && res.folder_path) {
        setSingleFolderPath(res.folder_path);
        showToast('Selected folder: ' + res.folder_path);
      }
    } catch (err) {
      console.error('Error opening Explorer folder dialog:', err);
      showToast('Could not open Explorer folder dialog: ' + err.message);
    } finally {
      setIsPickingFolder(false);
    }
  };

  const handleStartScan = async () => {
    try {
      if (scanMode === 'single_folder') {
        if (!singleFolderPath.trim()) {
          showToast('Please specify a folder path to scan.');
          return;
        }
        await startDocumentsScan({
          folderPath: singleFolderPath.trim(),
          recursive: includeSubfolders
        });
        showToast(includeSubfolders ? 'Scanning folder and subfolders...' : 'Scanning folder (subfolders excluded)...');
      } else {
        let rootsToScan = [...selectedRootsToScan];
        if (customRootsInput.trim()) {
          const extra = customRootsInput.split('\n').map(s => s.trim()).filter(Boolean);
          rootsToScan = [...rootsToScan, ...extra];
        }
        if (rootsToScan.length === 0) {
          showToast('Please select at least one folder to scan.');
          return;
        }
        await startDocumentsScan({
          customRoots: rootsToScan,
          recursive: includeSubfolders
        });
        showToast(`Scanning personal folders (${rootsToScan.length} folder${rootsToScan.length > 1 ? 's' : ''})...`);
      }
      setIsScanModalOpen(false);
      pollScanStatus();
    } catch (e) {
      showToast('Error starting scan: ' + e.message);
    }
  };

  const handleStopScan = async () => {
    try {
      await stopDocumentsScan();
      showToast('Scan stopped');
    } catch (e) {
      showToast('Error stopping scan: ' + e.message);
    }
  };

  const handleOpenDoc = async (doc) => {
    setActiveDoc(doc);
    setDocViewMode('visual');
    try {
      const full = await fetchDocumentDetails(doc.id);
      if (full) {
        setActiveDoc(full);
      }
    } catch (err) {
      console.error('Error loading full document details:', err);
    }
  };

  const getDocumentAnalysis = (doc) => {
    if (!doc?.ai_analysis_json) return null;
    try {
      return typeof doc.ai_analysis_json === 'string' ? JSON.parse(doc.ai_analysis_json) : doc.ai_analysis_json;
    } catch {
      return null;
    }
  };

  const handleAnalyzeDoc = async () => {
    if (!activeDoc) return;
    try {
      setIsAnalyzing(true);
      const analysis = await analyzeDocument(activeDoc.id);
      setActiveDoc(prev => ({ ...prev, ai_summary: analysis.summary, ai_analysis_json: JSON.stringify(analysis), ai_processed_at: Date.now() / 1000 }));
      showToast('Local AI analysis complete');
    } catch (err) {
      showToast(err.message + '. Start Ollama and run: ollama pull qwen3:8b');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleReviewDoc = async (status) => {
    if (!activeDoc) return;
    try {
      await updateDocumentReview(activeDoc.id, status);
      setActiveDoc(prev => ({ ...prev, review_status: status }));
      setDocuments(prev => prev.map(doc => doc.id === activeDoc.id ? { ...doc, review_status: status } : doc));
      showToast(`Marked document as ${status}`);
    } catch (err) {
      showToast('Could not update review status: ' + err.message);
    }
  };

  const handleOpenInSystem = async (docId, e) => {
    if (e) e.stopPropagation();
    try {
      showToast('Opening in desktop application...');
      const res = await openDocumentInSystemApp(docId);
      if (res.status === 'opened') {
        showToast('Document opened in your desktop app');
      } else {
        showToast(res.message || 'Launched file');
      }
    } catch (err) {
      showToast('Could not open in desktop app: ' + err.message);
    }
  };

  const handleRevealInExplorer = async (docId, e) => {
    if (e) e.stopPropagation();
    try {
      const res = await revealDocumentInExplorer(docId);
      if (res && res.mode === 'folder_open') {
        showToast('Opened containing folder in Windows Explorer');
      } else {
        showToast('Opened folder & highlighted file in Windows Explorer');
      }
    } catch (err) {
      showToast('Could not open folder: ' + err.message);
    }
  };

  const handleRevealPath = async (path, e) => {
    if (e) e.stopPropagation();
    try {
      await revealPathInExplorer(path);
      showToast('Opened folder in Windows Explorer');
    } catch (err) {
      showToast('Could not open folder: ' + err.message);
    }
  };

  const handleClearCatalog = async () => {
    try {
      setIsClearing(true);
      await clearDocumentsCatalog();
      setDocuments([]);
      setTotalCount(0);
      setStats(null);
      setActiveDoc(null);
      setIsClearConfirmOpen(false);
      setIsScanModalOpen(false);
      showToast('Documents catalog reset. Original PC files remain 100% safe.');
      loadStats();
      loadDocuments();
    } catch (err) {
      showToast('Failed to reset catalog: ' + err.message);
    } finally {
      setIsClearing(false);
    }
  };

  const handleTrashDoc = async (docId, e) => {
    if (e) e.stopPropagation();
    try {
      await trashDocument(docId);
      if (activeDoc && activeDoc.id === docId) {
        setActiveDoc(null);
      }
      showToast('Moved to Documents Trash holding folder (photos/documents_trash)');
      loadDocuments();
      loadStats();
    } catch (err) {
      showToast('Failed to trash document: ' + err.message);
    }
  };

  const handleRestoreDoc = async (docId, e) => {
    if (e) e.stopPropagation();
    try {
      await restoreDocument(docId);
      if (activeDoc && activeDoc.id === docId) {
        setActiveDoc(null);
      }
      showToast('Restored document back to active library');
      loadDocuments();
      loadStats();
    } catch (err) {
      showToast('Failed to restore document: ' + err.message);
    }
  };

  const handlePermanentlyDeleteDoc = async (docId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm('Permanently delete this document from the holding folder? This cannot be undone. (Your original file on your computer remains safe and untouched).')) {
      return;
    }
    try {
      await permanentlyDeleteDocument(docId);
      if (activeDoc && activeDoc.id === docId) {
        setActiveDoc(null);
      }
      showToast('Document permanently deleted from holding folder');
      loadDocuments();
      loadStats();
    } catch (err) {
      showToast('Failed to permanently delete: ' + err.message);
    }
  };

  const handleEmptyTrash = async () => {
    if (!window.confirm('Empty entire Documents Trash? All items in the holding folder will be permanently deleted. (Your original computer files remain completely safe and untouched).')) {
      return;
    }
    try {
      const res = await emptyDocumentsTrash();
      showToast(`Emptied Documents Trash (${res.purged_count} files removed)`);
      loadDocuments();
      loadStats();
    } catch (err) {
      showToast('Failed to empty trash: ' + err.message);
    }
  };

  const handleOpenTrashFolder = async () => {
    try {
      await openDocumentsTrashFolder();
      showToast('Opened Documents Trash holding folder in Windows Explorer');
    } catch (err) {
      showToast('Could not open trash folder: ' + err.message);
    }
  };

  return (
    <div style={{ padding: '24px 32px', maxWidth: '1600px', margin: '0 auto', color: '#e2e8f0' }}>
      {/* Toast Notification */}
      {toast && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          background: 'rgba(15, 23, 42, 0.95)',
          border: '1px solid rgba(56, 189, 248, 0.5)',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
          color: '#38bdf8',
          padding: '12px 20px',
          borderRadius: '12px',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontWeight: 600,
          backdropFilter: 'blur(10px)'
        }}>
          <CheckCircle size={16} />
          <span>{toast}</span>
        </div>
      )}

      {/* Top Banner & Header */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '16px',
        marginBottom: '24px',
        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8))',
        padding: '24px',
        borderRadius: '16px',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        backdropFilter: 'blur(16px)',
        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <span style={{
              background: 'linear-gradient(135deg, #0284c7, #38bdf8)',
              color: '#ffffff',
              padding: '6px',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <FileText size={22} />
            </span>
            <h1 style={{ margin: 0, fontSize: '26px', fontWeight: 800, letterSpacing: '-0.02em', color: '#f8fafc' }}>
              Personal Document Studio
            </h1>
            <span style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              padding: '2px 10px',
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}>
              <ShieldCheck size={13} /> Original Safe Copy Pipeline
            </span>
          </div>
          <p style={{ margin: 0, color: '#94a3b8', fontSize: '14px', maxWidth: '750px', lineHeight: 1.5 }}>
            Automated discovery of personal documents across your computer. Copies are safely cataloged and indexed with dense neural vectors for deep semantic retrieval, leaving your originals completely untouched.
          </p>
          <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ color: '#94a3b8', fontSize: '11px', fontWeight: 700 }}>Highlight lists:</span>
            {interestLists.map(list => (
              <span key={list.id || list.name} title={list.description} style={{ color: '#bae6fd', background: 'rgba(14,116,144,0.2)', border: '1px solid rgba(56,189,248,0.25)', borderRadius: '999px', padding: '4px 9px', fontSize: '11px' }}>{list.name}</span>
            ))}
            <form onSubmit={handleSaveInterestList} style={{ display: 'flex', gap: '5px', flexWrap: 'wrap' }}>
              <input value={newListName} onChange={event => setNewListName(event.target.value)} placeholder="New list" aria-label="New highlight list name" style={{ width: '110px', background: 'rgba(15,23,42,0.7)', border: '1px solid rgba(148,163,184,0.25)', borderRadius: '6px', color: '#e2e8f0', padding: '4px 7px', fontSize: '11px' }} />
              <input value={newListDescription} onChange={event => setNewListDescription(event.target.value)} placeholder="What to spot" aria-label="Highlight list description" style={{ width: '140px', background: 'rgba(15,23,42,0.7)', border: '1px solid rgba(148,163,184,0.25)', borderRadius: '6px', color: '#e2e8f0', padding: '4px 7px', fontSize: '11px' }} />
              <button type="submit" disabled={!newListName.trim()} style={{ border: '1px solid rgba(52,211,153,0.35)', borderRadius: '6px', padding: '4px 8px', cursor: newListName.trim() ? 'pointer' : 'not-allowed', color: '#6ee7b7', background: 'rgba(16,185,129,0.12)', fontSize: '11px', fontWeight: 700 }}>Add</button>
            </form>
          </div>
        </div>

        {/* Scan Actions & Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {scanStatus?.is_scanning ? (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              background: 'rgba(56, 189, 248, 0.1)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              padding: '8px 16px',
              borderRadius: '12px'
            }}>
              <RefreshCw size={16} className="spin-animation" style={{ color: '#38bdf8' }} />
              <div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>
                  Scanning Computer ({scanStatus.found_docs} found, {scanStatus.copied_docs} copied)
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', maxWidth: '240px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {scanStatus.current_file}
                </div>
              </div>
              <button
                onClick={handleStopScan}
                style={{
                  background: 'rgba(239, 68, 68, 0.2)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  color: '#f87171',
                  borderRadius: '8px',
                  padding: '4px 10px',
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Stop
              </button>
            </div>
          ) : (
            <button
              onClick={handleOpenScanModal}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                background: 'linear-gradient(135deg, #0284c7, #2563eb)',
                color: '#ffffff',
                border: 'none',
                padding: '10px 18px',
                borderRadius: '12px',
                fontWeight: 700,
                fontSize: '14px',
                cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
                transition: 'all 0.2s'
              }}
            >
              <FolderSearch size={17} />
              <span>Scan Folders</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsWatchedModalOpen(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'rgba(56, 189, 248, 0.12)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              padding: '10px 18px',
              borderRadius: '12px',
              fontWeight: 700,
              fontSize: '14px',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
            title="Configure real-time watched folders (restricted to Documents & Downloads in Windows/OneDrive)"
          >
            <FolderSync size={17} />
            <span>Watched Folders ({watchedCount})</span>
          </button>

          <button
            type="button"
            onClick={() => setIsTrashView(prev => !prev)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: isTrashView ? 'rgba(239, 68, 68, 0.25)' : 'rgba(239, 68, 68, 0.12)',
              color: isTrashView ? '#fca5a5' : '#f87171',
              border: `1px solid ${isTrashView ? 'rgba(239, 68, 68, 0.6)' : 'rgba(239, 68, 68, 0.3)'}`,
              padding: '10px 18px',
              borderRadius: '12px',
              fontWeight: 700,
              fontSize: '14px',
              cursor: 'pointer',
              transition: 'all 0.2s',
              boxShadow: isTrashView ? '0 0 16px rgba(239, 68, 68, 0.35)' : 'none'
            }}
            title="Documents Trash holding folder (photos/documents_trash, git-ignored)"
          >
            <Trash2 size={17} />
            <span>Trash ({stats?.trashed_count || 0})</span>
          </button>

          <button
            onClick={() => { loadStats(); loadDocuments(); }}
            title="Refresh Library"
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              color: '#cbd5e1',
              padding: '10px',
              borderRadius: '12px',
              cursor: 'pointer'
            }}
          >
            <RefreshCw size={17} />
          </button>

          {totalCount > 0 && (
            <button
              onClick={() => setIsClearConfirmOpen(true)}
              title="Reset Catalog: safely clears index & copies without touching PC original files"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#f87171',
                padding: '10px 14px',
                borderRadius: '12px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s'
              }}
            >
              <RotateCcw size={15} />
              <span>Reset Catalog</span>
            </button>
          )}
        </div>
      </div>

      {/* Trash Holding Area Banner */}
      {isTrashView && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(185, 28, 28, 0.18))',
          border: '1px solid rgba(239, 68, 68, 0.4)',
          borderRadius: '16px',
          padding: '18px 24px',
          marginBottom: '24px',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '16px',
          boxShadow: '0 8px 30px rgba(239, 68, 68, 0.1)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{
              background: 'rgba(239, 68, 68, 0.25)',
              color: '#f87171',
              padding: '10px',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Trash2 size={24} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#fca5a5' }}>
                  Documents Trash Holding Folder
                </h3>
                <span style={{
                  background: 'rgba(239, 68, 68, 0.25)',
                  color: '#fca5a5',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  fontSize: '11px',
                  fontWeight: 700
                }}>
                  Git-Ignored • Workspace Holding Area
                </span>
              </div>
              <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: '#cbd5e1' }}>
                Trashed copies are moved to <code style={{ color: '#fca5a5', background: 'rgba(0,0,0,0.35)', padding: '2px 6px', borderRadius: '4px', fontFamily: 'monospace' }}>photos/documents_trash/</code>. Original files on your computer remain completely safe.
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={handleOpenTrashFolder}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'rgba(255, 255, 255, 0.08)',
                border: '1px solid rgba(255, 255, 255, 0.18)',
                color: '#f8fafc',
                padding: '9px 15px',
                borderRadius: '10px',
                fontSize: '13px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s'
              }}
              title="Open documents_trash in Windows File Explorer"
            >
              <FolderOpen size={15} />
              <span>Open Holding Folder</span>
            </button>

            {documents.length > 0 && (
              <button
                onClick={handleEmptyTrash}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(239, 68, 68, 0.25)',
                  border: '1px solid rgba(239, 68, 68, 0.5)',
                  color: '#fca5a5',
                  padding: '9px 15px',
                  borderRadius: '10px',
                  fontSize: '13px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  transition: 'all 0.15s'
                }}
                title="Empty holding folder and delete records"
              >
                <Trash2 size={15} />
                <span>Empty Trash</span>
              </button>
            )}

            <button
              onClick={() => setIsTrashView(false)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: 'rgba(56, 189, 248, 0.15)',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                color: '#38bdf8',
                padding: '9px 15px',
                borderRadius: '10px',
                fontSize: '13px',
                fontWeight: 700,
                cursor: 'pointer',
                transition: 'all 0.15s'
              }}
            >
              <span>Back to Active Documents</span>
            </button>
          </div>
        </div>
      )}

      {/* Semantic Search Bar */}
      <div style={{
        position: 'relative',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }}>
        <div style={{
          position: 'relative',
          flex: 1,
          display: 'flex',
          alignItems: 'center'
        }}>
          <span style={{ position: 'absolute', left: '16px', color: '#64748b' }}>
            {isSemanticMode ? <Sparkles size={20} color="#38bdf8" /> : <Search size={20} />}
          </span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={
              isSemanticMode
                ? "Search meanings, concepts, or questions (e.g. 'tax return 2024', 'rental lease agreement', 'meeting notes')..."
                : "Search documents by exact keywords or file names..."
            }
            style={{
              width: '100%',
              padding: '14px 44px 14px 48px',
              background: 'rgba(15, 23, 42, 0.8)',
              border: `1px solid ${isSemanticMode ? 'rgba(56, 189, 248, 0.4)' : 'rgba(255, 255, 255, 0.1)'}`,
              borderRadius: '14px',
              color: '#f8fafc',
              fontSize: '15px',
              outline: 'none',
              boxShadow: isSemanticMode ? '0 0 20px rgba(56, 189, 248, 0.15)' : 'none',
              transition: 'all 0.2s'
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute',
                right: '16px',
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer'
              }}
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Semantic Toggle */}
        <button
          onClick={() => setIsSemanticMode(!isSemanticMode)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            background: isSemanticMode ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.05)',
            border: `1px solid ${isSemanticMode ? 'rgba(56, 189, 248, 0.4)' : 'rgba(255, 255, 255, 0.1)'}`,
            color: isSemanticMode ? '#38bdf8' : '#94a3b8',
            padding: '12px 16px',
            borderRadius: '12px',
            fontWeight: 600,
            fontSize: '13px',
            cursor: 'pointer',
            whiteSpace: 'nowrap'
          }}
          title={isSemanticMode ? "Semantic Vector Mode is ON" : "Keyword Mode is ON"}
        >
          <Sparkles size={16} />
          <span>{isSemanticMode ? "AI Semantic Search" : "Keyword Search"}</span>
        </button>
      </div>

      {/* Filter Chips & Stats Bar */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '12px',
        marginBottom: '24px',
        fontSize: '13px'
      }}>
        {/* Type Filter Chips */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          <span style={{ color: '#64748b', fontWeight: 600, marginRight: '4px' }}>Types:</span>
          {[
            { key: 'ALL', label: 'All Documents', count: stats?.total_documents },
            { key: '.pdf', label: 'PDFs', count: stats?.type_counts?.['.pdf'] },
            { key: '.docx', label: 'Word (.docx)', count: stats?.type_counts?.['.docx'] },
            { key: '.txt', label: 'Plain Text', count: stats?.type_counts?.['.txt'] },
            { key: '.md', label: 'Markdown', count: stats?.type_counts?.['.md'] },
            { key: '.csv', label: 'Spreadsheet (.csv)', count: stats?.type_counts?.['.csv'] },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setSelectedExtension(f.key)}
              style={{
                background: selectedExtension === f.key ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${selectedExtension === f.key ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255, 255, 255, 0.08)'}`,
                color: selectedExtension === f.key ? '#38bdf8' : '#cbd5e1',
                padding: '6px 12px',
                borderRadius: '20px',
                fontWeight: selectedExtension === f.key ? 700 : 500,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                transition: 'all 0.15s'
              }}
            >
              <span>{f.label}</span>
              {f.count !== undefined && f.count > 0 && (
                <span style={{
                  background: 'rgba(255, 255, 255, 0.1)',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  fontSize: '11px',
                  color: '#94a3b8'
                }}>
                  {f.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Sort and Counters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', color: '#94a3b8' }}>
          <div>
            Showing <strong style={{ color: '#f8fafc' }}>{totalCount}</strong> documents
            {stats?.total_bytes ? ` (${formatBytes(stats.total_bytes)})` : ''}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <SlidersHorizontal size={14} />
            <select
              value={`${sortBy}_${sortOrder}`}
              onChange={(e) => {
                const [sb, so] = e.target.value.split('_');
                setSortBy(sb);
                setSortOrder(so);
              }}
              style={{
                background: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                color: '#cbd5e1',
                padding: '5px 10px',
                borderRadius: '8px',
                fontSize: '12px',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="modified_at_DESC">Newest Modified</option>
              <option value="modified_at_ASC">Oldest Modified</option>
              <option value="file_size_DESC">Largest Size</option>
              <option value="file_name_ASC">Name (A-Z)</option>
              <option value="word_count_DESC">Most Words</option>
            </select>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && documents.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#94a3b8' }}>
          <RefreshCw size={32} className="spin-animation" style={{ margin: '0 auto 12px auto', display: 'block', color: '#38bdf8' }} />
          <div>Searching and organizing documents...</div>
        </div>
      )}

      {/* Empty State */}
      {!loading && documents.length === 0 && (
        <div style={{
          textAlign: 'center',
          padding: '80px 20px',
          background: 'rgba(15, 23, 42, 0.5)',
          borderRadius: '16px',
          border: '1px dashed rgba(255, 255, 255, 0.1)'
        }}>
          {isTrashView ? (
            <>
              <Trash2 size={48} style={{ color: '#64748b', margin: '0 auto 16px auto' }} />
              <h3 style={{ margin: '0 0 8px 0', color: '#f8fafc', fontSize: '18px' }}>
                Documents Trash is Empty
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '14px', maxWidth: '500px', margin: '0 auto 20px auto', lineHeight: 1.5 }}>
                No documents are currently in the trash holding folder. When you trash a document, its copy is moved to photos/documents_trash/ while keeping your PC original safe.
              </p>
              <button
                onClick={() => setIsTrashView(false)}
                style={{
                  background: 'rgba(56, 189, 248, 0.15)',
                  border: '1px solid rgba(56, 189, 248, 0.4)',
                  color: '#38bdf8',
                  padding: '10px 20px',
                  borderRadius: '12px',
                  fontWeight: 700,
                  fontSize: '14px',
                  cursor: 'pointer'
                }}
              >
                Return to Active Documents
              </button>
            </>
          ) : (
            <>
              <FileText size={48} style={{ color: '#64748b', margin: '0 auto 16px auto' }} />
              <h3 style={{ margin: '0 0 8px 0', color: '#f8fafc', fontSize: '18px' }}>
                {searchQuery ? "No matching documents found" : "No Personal Documents Cataloged Yet"}
              </h3>
              <p style={{ color: '#94a3b8', fontSize: '14px', maxWidth: '500px', margin: '0 auto 20px auto', lineHeight: 1.5 }}>
                {searchQuery
                  ? "Try adjusting your semantic query or selecting 'All Documents'."
                  : "Click 'Scan Computer for Documents' to automatically discover PDFs, Word documents, text notes, and spreadsheets across your personal folders."}
              </p>
              {!searchQuery && (
                <button
                  onClick={handleOpenScanModal}
                  style={{
                    background: 'linear-gradient(135deg, #0284c7, #2563eb)',
                    color: '#ffffff',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '12px',
                    fontWeight: 700,
                    fontSize: '14px',
                    cursor: 'pointer'
                  }}
                >
                  Start Personal Documents Scan
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Documents Grid */}
      {documents.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: '16px',
          opacity: loading ? 0.75 : 1,
          transition: 'opacity 0.15s ease'
        }}>
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              doc={doc}
              isTrashView={isTrashView}
              onOpenDoc={handleOpenDoc}
              onOpenInSystem={handleOpenInSystem}
              onRevealInExplorer={handleRevealInExplorer}
              onRestoreDoc={handleRestoreDoc}
              onPermanentlyDeleteDoc={handlePermanentlyDeleteDoc}
              onTrashDoc={handleTrashDoc}
            />
          ))}
        </div>
      )}

      {/* Document Detail / Reader Modal */}
      {activeDoc && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 10000,
          backdropFilter: 'blur(8px)',
          padding: '24px'
        }}
        onClick={() => setActiveDoc(null)}
        >
          <div
            style={{
              background: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '16px',
              maxWidth: '1350px',
              width: '95vw',
              height: '92vh',
              maxHeight: '94vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.7)',
              overflow: 'hidden'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{
              padding: '16px 24px',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '12px',
              background: 'rgba(15, 23, 42, 0.98)'
            }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <span style={{
                    ...getFileTypeMeta(activeDoc.file_extension),
                    padding: '2px 8px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 700
                  }}>
                    {getFileTypeMeta(activeDoc.file_extension).label}
                  </span>
                  <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700, color: '#f8fafc', maxWidth: '480px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {activeDoc.title || activeDoc.file_name}
                  </h2>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  {activeDoc.file_name} • {formatBytes(activeDoc.file_size)} • Modified {formatDate(activeDoc.modified_at)}
                </div>
              </div>

              {/* Center View Mode Switcher */}
              <div style={{
                display: 'flex',
                background: 'rgba(255, 255, 255, 0.05)',
                padding: '3px',
                borderRadius: '10px',
                border: '1px solid rgba(255, 255, 255, 0.08)'
              }}>
                <button
                  type="button"
                  onClick={() => setDocViewMode('visual')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: docViewMode === 'visual' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                    border: docViewMode === 'visual' ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid transparent',
                    color: docViewMode === 'visual' ? '#38bdf8' : '#94a3b8',
                    padding: '6px 14px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: docViewMode === 'visual' ? 700 : 500,
                    cursor: 'pointer'
                  }}
                >
                  <Eye size={14} />
                  <span>Document View</span>
                </button>
                <button
                  type="button"
                  onClick={() => setDocViewMode('text')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: docViewMode === 'text' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                    border: docViewMode === 'text' ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid transparent',
                    color: docViewMode === 'text' ? '#38bdf8' : '#94a3b8',
                    padding: '6px 14px',
                    borderRadius: '8px',
                    fontSize: '12px',
                    fontWeight: docViewMode === 'text' ? 700 : 500,
                    cursor: 'pointer'
                  }}
                >
                  <FileText size={14} />
                  <span>Extracted Text</span>
                </button>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={() => handleOpenInSystem(activeDoc.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: 'linear-gradient(135deg, #0284c7, #2563eb)',
                    color: '#ffffff',
                    border: 'none',
                    padding: '8px 14px',
                    borderRadius: '10px',
                    fontSize: '12px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)'
                  }}
                  title="Open file in native desktop application (Word, Acrobat, Excel, etc.)"
                >
                  <ExternalLink size={14} />
                  <span>
                    {activeDoc.file_extension?.toLowerCase() === '.docx' || activeDoc.file_extension?.toLowerCase() === '.doc'
                      ? 'Open in Word'
                      : activeDoc.file_extension?.toLowerCase() === '.pdf'
                      ? 'Open in Acrobat / App'
                      : activeDoc.file_extension?.toLowerCase() === '.xlsx' || activeDoc.file_extension?.toLowerCase() === '.csv'
                      ? 'Open in Excel'
                      : 'Open in Desktop App'}
                  </span>
                </button>

                <button
                  onClick={() => handleRevealInExplorer(activeDoc.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: 'rgba(56, 189, 248, 0.12)',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                    color: '#38bdf8',
                    padding: '8px 12px',
                    borderRadius: '10px',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                  title="Open containing folder in Windows File Explorer"
                >
                  <FolderOpen size={14} />
                  <span>Open Folder</span>
                </button>

                <a
                  href={getDocumentFileUrl(activeDoc.id)}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    background: 'rgba(56, 189, 248, 0.12)',
                    color: '#38bdf8',
                    border: '1px solid rgba(56, 189, 248, 0.25)',
                    padding: '8px 12px',
                    borderRadius: '10px',
                    fontSize: '12px',
                    fontWeight: 600,
                    textDecoration: 'none'
                  }}
                  title="Open file in new browser tab or download"
                >
                  <Maximize2 size={14} />
                  <span>Browser Tab</span>
                </a>

                {activeDoc.is_trashed || isTrashView ? (
                  <button
                    onClick={() => handleRestoreDoc(activeDoc.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: 'rgba(52, 211, 153, 0.15)',
                      border: '1px solid rgba(52, 211, 153, 0.4)',
                      color: '#34d399',
                      padding: '8px 12px',
                      borderRadius: '10px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                    title="Restore document to active library"
                  >
                    <RotateCcw size={14} />
                    <span>Restore</span>
                  </button>
                ) : (
                  <button
                    onClick={() => handleTrashDoc(activeDoc.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      background: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid rgba(239, 68, 68, 0.35)',
                      color: '#f87171',
                      padding: '8px 12px',
                      borderRadius: '10px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                    title="Move copy to Documents Trash holding folder"
                  >
                    <Trash2 size={14} />
                    <span>Trash</span>
                  </button>
                )}

                <button
                  onClick={() => setActiveDoc(null)}
                  style={{
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: 'none',
                    color: '#94a3b8',
                    borderRadius: '10px',
                    padding: '8px',
                    cursor: 'pointer'
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Path Protection Notice & Duplicate Copies Breakdown */}
            {activeDoc.locations && activeDoc.locations.length > 1 ? (
              <div style={{
                background: 'rgba(245, 158, 11, 0.08)',
                borderBottom: '1px solid rgba(245, 158, 11, 0.25)',
                padding: '10px 24px',
                fontSize: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#fbbf24', fontWeight: 700 }}>
                    <Copy size={15} />
                    <span>Exact Duplicate Document: Found at {activeDoc.locations.length} Locations on Your PC</span>
                  </div>
                  <span style={{ color: '#94a3b8', fontSize: '11px' }}>
                    SHA-256: {activeDoc.sha256?.substring(0, 10)}... (Single copy kept in library)
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', maxHeight: '90px', overflowY: 'auto' }}>
                  {activeDoc.locations.map((loc, idx) => (
                    <div
                      key={loc.id || idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'rgba(0, 0, 0, 0.35)',
                        padding: '6px 12px',
                        borderRadius: '6px',
                        fontSize: '11px',
                        border: '1px solid rgba(255, 255, 255, 0.06)'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                        <span style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: idx === 0 ? 'rgba(56, 189, 248, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                          color: idx === 0 ? '#38bdf8' : '#fbbf24'
                        }}>
                          {idx === 0 ? 'Original Discovered' : `Duplicate #${idx}`}
                        </span>
                        <span style={{ color: '#f1f5f9', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {loc.original_path}
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
                        <span style={{ color: '#94a3b8', fontSize: '11px' }}>
                          {formatBytes(loc.file_size)} • {formatDate(loc.modified_at)}
                        </span>
                        <button
                          onClick={(e) => handleRevealPath(loc.original_path, e)}
                          title="Open this copy's folder in Windows Explorer"
                          style={{
                            background: 'rgba(56, 189, 248, 0.12)',
                            border: '1px solid rgba(56, 189, 248, 0.25)',
                            borderRadius: '6px',
                            color: '#38bdf8',
                            cursor: 'pointer',
                            padding: '2px 6px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px',
                            fontWeight: 600
                          }}
                        >
                          <FolderOpen size={11} /> Folder
                        </button>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(loc.original_path);
                            showToast('Copied path to clipboard!');
                          }}
                          title="Copy file path"
                          style={{
                            background: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            borderRadius: '6px',
                            color: '#cbd5e1',
                            cursor: 'pointer',
                            padding: '2px 6px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            fontSize: '11px'
                          }}
                        >
                          <Copy size={11} /> Copy
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{
                background: 'rgba(16, 185, 129, 0.08)',
                borderBottom: '1px solid rgba(16, 185, 129, 0.2)',
                padding: '8px 24px',
                fontSize: '11px',
                color: '#34d399',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <ShieldCheck size={14} flexShrink={0} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    Original PC Path (Untouched): <strong>{activeDoc.original_path}</strong>
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    onClick={() => handleRevealInExplorer(activeDoc.id)}
                    title="Open containing folder in Windows Explorer"
                    style={{
                      background: 'rgba(56, 189, 248, 0.15)',
                      border: '1px solid rgba(56, 189, 248, 0.35)',
                      color: '#38bdf8',
                      cursor: 'pointer',
                      padding: '3px 8px',
                      borderRadius: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px',
                      fontWeight: 600
                    }}
                  >
                    <FolderOpen size={12} /> Open Folder
                  </button>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(activeDoc.original_path);
                      showToast('Copied original path to clipboard!');
                    }}
                    title="Copy original path"
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: '#34d399',
                      cursor: 'pointer',
                      padding: '2px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '11px'
                    }}
                  >
                    <Copy size={11} /> Copy Path
                  </button>
                </div>
              </div>
            )}

            {/* Document Body Area */}
            {(() => {
              const analysis = getDocumentAnalysis(activeDoc);
              return (
                <div style={{ padding: '14px 24px', borderBottom: '1px solid rgba(255,255,255,0.08)', background: 'rgba(2, 132, 199, 0.06)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Sparkles size={16} color="#38bdf8" />
                      <strong style={{ color: '#e0f2fe', fontSize: '13px' }}>Local AI Review</strong>
                      {activeDoc.review_status && activeDoc.review_status !== 'unreviewed' && (
                        <span style={{ color: '#34d399', fontSize: '11px' }}>Human decision: {activeDoc.review_status}</span>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      {['keep', 'review', 'remove'].map(status => (
                        <button key={status} onClick={() => handleReviewDoc(status)} style={{ border: '1px solid rgba(255,255,255,0.14)', borderRadius: '7px', padding: '5px 9px', cursor: 'pointer', color: status === 'remove' ? '#fda4af' : '#cbd5e1', background: activeDoc.review_status === status ? 'rgba(56,189,248,0.2)' : 'rgba(255,255,255,0.05)', fontSize: '11px', fontWeight: 700 }}>
                          {status === 'keep' ? 'Keep' : status === 'review' ? 'Review' : 'Mark Remove'}
                        </button>
                      ))}
                      <button onClick={handleAnalyzeDoc} disabled={isAnalyzing} style={{ border: '1px solid rgba(56,189,248,0.35)', borderRadius: '7px', padding: '5px 10px', cursor: isAnalyzing ? 'wait' : 'pointer', color: '#38bdf8', background: 'rgba(56,189,248,0.12)', fontSize: '11px', fontWeight: 700 }}>
                        {isAnalyzing ? 'Analyzing...' : analysis ? 'Analyze Again' : 'Analyze Locally'}
                      </button>
                    </div>
                  </div>
                  {analysis ? (
                    <div style={{ marginTop: '10px', display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) minmax(260px, 1.4fr)', gap: '12px' }}>
                      <div style={{ color: '#cbd5e1', fontSize: '12px', lineHeight: 1.5 }}>
                        <div style={{ color: '#94a3b8', fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', marginBottom: '3px' }}>Summary</div>
                        {analysis.summary || 'No summary returned.'}
                        {analysis.suggested_status && <div style={{ marginTop: '6px', color: '#fbbf24' }}>Suggested: {analysis.suggested_status}</div>}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        {(analysis.highlights || []).slice(0, 3).map((item, index) => (
                          <div key={`${item.category}-${index}`} style={{ background: 'rgba(250,204,21,0.1)', borderLeft: '3px solid #facc15', padding: '6px 9px', color: '#fef3c7', fontSize: '11px' }}>
                            <strong>{item.category || 'Important'}:</strong> “{item.quote}” <span style={{ color: '#cbd5e1' }}>{item.reason}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div style={{ marginTop: '6px', color: '#94a3b8', fontSize: '11px' }}>No local analysis yet. Your original file will remain untouched.</div>
                  )}
                </div>
              );
            })()}

            {docViewMode === 'visual' ? (
              activeDoc.file_extension?.toLowerCase() === '.pdf' ? (
                /* Native PDF Viewer inside iframe */
                <div style={{ flex: 1, width: '100%', height: '100%', minHeight: 0, position: 'relative', background: '#334155' }}>
                  <iframe
                    src={getDocumentFileUrl(activeDoc.id)}
                    title={activeDoc.file_name}
                    style={{ width: '100%', height: '100%', border: 'none' }}
                  />
                </div>
              ) : activeDoc.file_extension?.toLowerCase() === '.docx' || activeDoc.file_extension?.toLowerCase() === '.doc' ? (
                /* Word Document Visual View */
                <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: '#090d16' }}>
                  <div style={{ maxWidth: '900px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{
                      background: 'linear-gradient(135deg, rgba(2, 132, 199, 0.15), rgba(30, 41, 59, 0.6))',
                      border: '1px solid rgba(56, 189, 248, 0.3)',
                      borderRadius: '14px',
                      padding: '20px 24px',
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '16px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                        <div style={{
                          background: '#0284c7',
                          color: '#fff',
                          padding: '14px',
                          borderRadius: '12px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          boxShadow: '0 6px 20px rgba(2, 132, 199, 0.4)'
                        }}>
                          <BookOpen size={28} />
                        </div>
                        <div>
                          <div style={{ fontSize: '17px', fontWeight: 800, color: '#f8fafc' }}>
                            Microsoft Word Document
                          </div>
                          <div style={{ fontSize: '13px', color: '#94a3b8', marginTop: '2px' }}>
                            Open in Microsoft Word for 100% full original layout, tables, formatting, and images.
                          </div>
                        </div>
                      </div>

                      <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                          onClick={() => handleOpenInSystem(activeDoc.id)}
                          style={{
                            background: 'linear-gradient(135deg, #0284c7, #2563eb)',
                            color: '#ffffff',
                            border: 'none',
                            padding: '10px 20px',
                            borderRadius: '10px',
                            fontWeight: 700,
                            fontSize: '13px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)'
                          }}
                        >
                          <BookOpen size={16} /> Open in Word
                        </button>
                        <button
                          onClick={() => handleRevealInExplorer(activeDoc.id)}
                          style={{
                            background: 'rgba(255, 255, 255, 0.06)',
                            color: '#cbd5e1',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            padding: '10px 14px',
                            borderRadius: '10px',
                            fontWeight: 600,
                            fontSize: '13px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                          }}
                        >
                          <FolderOpen size={16} /> Open Folder
                        </button>
                      </div>
                    </div>

                    {/* Paper Document Preview */}
                    <div style={{
                      background: '#1e293b',
                      borderRadius: '12px',
                      padding: '32px 40px',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      boxShadow: '0 8px 30px rgba(0, 0, 0, 0.3)',
                      color: '#f1f5f9',
                      lineHeight: 1.8,
                      fontSize: '14.5px',
                      whiteSpace: 'pre-wrap',
                      fontFamily: 'Inter, system-ui, -apple-system, sans-serif'
                    }}>
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                        paddingBottom: '12px',
                        marginBottom: '20px'
                      }}>
                        <span style={{ fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#38bdf8', fontWeight: 800 }}>
                          Document Text Preview ({activeDoc.word_count || 0} words)
                        </span>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(activeDoc.extracted_text || '');
                            showToast('Document text copied to clipboard!');
                          }}
                          style={{
                            background: 'rgba(255, 255, 255, 0.05)',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            color: '#cbd5e1',
                            borderRadius: '6px',
                            padding: '4px 8px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                        >
                          <Copy size={12} /> Copy Text
                        </button>
                      </div>
                      {activeDoc.extracted_text || (
                        <div style={{ color: '#64748b', fontStyle: 'italic', textAlign: 'center', padding: '40px 0' }}>
                          No text extracted. Click "Open in Word" above to view in Microsoft Word.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : activeDoc.file_extension?.toLowerCase() === '.csv' ? (
                /* CSV Spreadsheet Table View */
                <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: '#090d16' }}>
                  <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                        Spreadsheet Grid Preview
                      </div>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          onClick={() => handleOpenInSystem(activeDoc.id)}
                          style={{
                            background: 'linear-gradient(135deg, #059669, #10b981)',
                            color: '#fff',
                            border: 'none',
                            padding: '8px 16px',
                            borderRadius: '8px',
                            fontSize: '12px',
                            fontWeight: 700,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                          }}
                        >
                          <FileSpreadsheet size={15} /> Open in Excel
                        </button>
                        <button
                          onClick={() => handleRevealInExplorer(activeDoc.id)}
                          style={{
                            background: 'rgba(255, 255, 255, 0.06)',
                            color: '#cbd5e1',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            padding: '8px 14px',
                            borderRadius: '8px',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                          }}
                        >
                          <FolderOpen size={14} /> Open Folder
                        </button>
                      </div>
                    </div>
                    <CsvViewer text={activeDoc.extracted_text} />
                  </div>
                </div>
              ) : (
                /* Text / Markdown / Other Documents */
                <div style={{ flex: 1, overflowY: 'auto', padding: '24px', background: '#090d16' }}>
                  <div style={{
                    maxWidth: '900px',
                    margin: '0 auto',
                    background: '#1e293b',
                    borderRadius: '12px',
                    padding: '32px 40px',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    boxShadow: '0 8px 30px rgba(0, 0, 0, 0.3)',
                    color: '#f1f5f9',
                    lineHeight: 1.8,
                    fontSize: '14px',
                    whiteSpace: 'pre-wrap',
                    fontFamily: activeDoc.file_extension?.toLowerCase() === '.md' ? 'monospace, monospace' : 'inherit'
                  }}>
                    {activeDoc.extracted_text || (
                      <div style={{ color: '#64748b', fontStyle: 'italic', textAlign: 'center', padding: '40px 0' }}>
                        No text content extracted. Click "Open in Desktop App" above to view.
                      </div>
                    )}
                  </div>
                </div>
              )
            ) : (
              /* Extracted Text Mode */
              <div style={{
                padding: '24px',
                overflowY: 'auto',
                flex: 1,
                fontFamily: 'system-ui, -apple-system, sans-serif',
                fontSize: '14px',
                lineHeight: 1.7,
                color: '#cbd5e1',
                whiteSpace: 'pre-wrap',
                background: 'rgba(15, 23, 42, 0.95)'
              }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                  paddingBottom: '10px',
                  marginBottom: '16px'
                }}>
                  <span style={{ fontSize: '12px', color: '#94a3b8' }}>
                    Raw Extracted Text ({activeDoc.word_count || 0} words)
                  </span>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(activeDoc.extracted_text || '');
                      showToast('Copied text to clipboard!');
                    }}
                    style={{
                      background: 'rgba(255, 255, 255, 0.05)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      color: '#cbd5e1',
                      borderRadius: '6px',
                      padding: '4px 10px',
                      fontSize: '12px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                  >
                    <Copy size={13} /> Copy Text
                  </button>
                </div>
                {activeDoc.extracted_text ? (
                  activeDoc.extracted_text
                ) : (
                  <div style={{ color: '#64748b', fontStyle: 'italic', textAlign: 'center', padding: '40px 0' }}>
                    No text extracted. Click "Open in Desktop App" above to view directly.
                  </div>
                )}
              </div>
            )}

            {/* Modal Footer */}
            <div style={{
              padding: '12px 24px',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: '12px',
              color: '#64748b',
              background: 'rgba(15, 23, 42, 0.98)'
            }}>
              <span>
                Word count: <strong>{activeDoc.word_count || 0}</strong> • Pages: <strong>{activeDoc.page_count || 1}</strong> • SHA: {activeDoc.sha256?.substring(0, 12)}
              </span>
              <button
                onClick={(e) => handleDeleteDoc(activeDoc.id, e)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#ef4444',
                  cursor: 'pointer',
                  fontSize: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                <Trash2 size={14} /> Remove Catalog Entry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Computer Scan Modal */}
      {isScanModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 10000,
          backdropFilter: 'blur(8px)',
          padding: '24px'
        }}
        onClick={() => setIsScanModalOpen(false)}
        >
          <div
            style={{
              background: '#0f172a',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '16px',
              maxWidth: '650px',
              width: '100%',
              padding: '24px',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.6)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <FolderSearch size={22} color="#38bdf8" />
                <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>
                  Scan Computer for Documents
                </h2>
              </div>
              <button
                onClick={() => setIsScanModalOpen(false)}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Mode Tabs */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '18px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '12px' }}>
              <button
                type="button"
                onClick={() => setScanMode('all_allowed_folders')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: scanMode === 'all_allowed_folders' ? 'rgba(56, 189, 248, 0.18)' : 'rgba(255, 255, 255, 0.04)',
                  border: `1px solid ${scanMode === 'all_allowed_folders' ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255, 255, 255, 0.08)'}`,
                  color: scanMode === 'all_allowed_folders' ? '#38bdf8' : '#94a3b8',
                  padding: '8px 16px',
                  borderRadius: '10px',
                  fontWeight: scanMode === 'all_allowed_folders' ? 700 : 500,
                  fontSize: '13px',
                  cursor: 'pointer'
                }}
              >
                <FolderSearch size={15} />
                <span>All Document Folders (Recommended)</span>
              </button>

              <button
                type="button"
                onClick={() => setScanMode('single_folder')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: scanMode === 'single_folder' ? 'rgba(56, 189, 248, 0.18)' : 'rgba(255, 255, 255, 0.04)',
                  border: `1px solid ${scanMode === 'single_folder' ? 'rgba(56, 189, 248, 0.5)' : 'rgba(255, 255, 255, 0.08)'}`,
                  color: scanMode === 'single_folder' ? '#38bdf8' : '#94a3b8',
                  padding: '8px 16px',
                  borderRadius: '10px',
                  fontWeight: scanMode === 'single_folder' ? 700 : 500,
                  fontSize: '13px',
                  cursor: 'pointer'
                }}
              >
                <Folder size={15} />
                <span>Specific Folder</span>
              </button>
            </div>

            <div style={{
              background: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              padding: '12px 16px',
              borderRadius: '10px',
              color: '#38bdf8',
              fontSize: '12px',
              marginBottom: '18px',
              display: 'flex',
              gap: '10px',
              alignItems: 'flex-start'
            }}>
              <ShieldCheck size={18} flexShrink={0} style={{ marginTop: '2px' }} />
              <div style={{ color: '#cbd5e1' }}>
                <strong style={{ color: '#38bdf8' }}>Strict Document Boundary:</strong> Scans solely within <strong>Documents</strong> and <strong>Downloads</strong> (in Windows and OneDrive). System drives, Desktop, and photo library remain completely untouched.
              </div>
            </div>

            {/* ALL ALLOWED FOLDERS MODE */}
            {scanMode === 'all_allowed_folders' ? (
              <div>
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc' }}>
                      Select Document Folders to Scan:
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        onClick={handleSelectAllRoots}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#38bdf8',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          textDecoration: 'underline'
                        }}
                      >
                        Select All
                      </button>
                      <span style={{ color: '#475569' }}>|</span>
                      <button
                        type="button"
                        onClick={handleDeselectAllRoots}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#94a3b8',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          textDecoration: 'underline'
                        }}
                      >
                        Deselect All
                      </button>
                    </div>
                  </div>

                  <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                    maxHeight: '190px',
                    overflowY: 'auto'
                  }}>
                    {scanRootsInfo?.roots && scanRootsInfo.roots.length > 0 ? (
                      scanRootsInfo.roots.map((rootPath, idx) => {
                        const isChecked = selectedRootsToScan.includes(rootPath);
                        const isOneDrive = rootPath.toLowerCase().includes('onedrive');
                        const isDownloads = rootPath.toLowerCase().includes('downloads');
                        const label = isOneDrive
                          ? (isDownloads ? 'OneDrive Downloads' : 'OneDrive Documents')
                          : (isDownloads ? 'Windows Downloads' : 'Windows Documents');

                        return (
                          <label
                            key={idx}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '10px',
                              background: isChecked ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                              border: `1px solid ${isChecked ? 'rgba(56, 189, 248, 0.35)' : 'rgba(255, 255, 255, 0.06)'}`,
                              borderRadius: '8px',
                              padding: '10px 12px',
                              cursor: 'pointer',
                              transition: 'all 0.15s'
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => handleToggleScanRoot(rootPath)}
                              style={{ width: '16px', height: '16px', accentColor: '#38bdf8', cursor: 'pointer' }}
                            />
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <Folder size={14} color="#38bdf8" />
                                <span style={{ fontSize: '12.5px', fontWeight: 600, color: '#f8fafc' }}>
                                  {label}
                                </span>
                              </div>
                              <div style={{
                                fontSize: '11px',
                                color: '#94a3b8',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                                marginTop: '2px',
                                fontFamily: 'monospace'
                              }}>
                                {rootPath}
                              </div>
                            </div>
                          </label>
                        );
                      })
                    ) : (
                      <div style={{ fontSize: '12px', color: '#94a3b8', padding: '12px', textAlign: 'center' }}>
                        Loading detected document folders...
                      </div>
                    )}
                  </div>
                </div>

                {/* Subfolders Toggle Checkbox */}
                <div style={{ marginBottom: '16px' }}>
                  <label style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    cursor: 'pointer',
                    background: 'rgba(255, 255, 255, 0.03)',
                    padding: '12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(255, 255, 255, 0.08)'
                  }}>
                    <input
                      type="checkbox"
                      checked={includeSubfolders}
                      onChange={(e) => setIncludeSubfolders(e.target.checked)}
                      style={{ marginTop: '3px', cursor: 'pointer', width: '16px', height: '16px', accentColor: '#38bdf8' }}
                    />
                    <div>
                      <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '13px' }}>
                        Include subfolders (recursive scan)
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '11px', marginTop: '2px', lineHeight: 1.4 }}>
                        Recursively scans all subdirectories inside the selected personal folders.
                      </div>
                    </div>
                  </label>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                    Extra Allowed Folders (Optional):
                  </div>
                  <textarea
                    value={customRootsInput}
                    onChange={(e) => setCustomRootsInput(e.target.value)}
                    placeholder="Enter one directory path per line if you wish to scan specific subfolders..."
                    rows={2}
                    style={{
                      width: '100%',
                      background: 'rgba(0, 0, 0, 0.3)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      padding: '8px 10px',
                      fontSize: '12px',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
              </div>
            ) : (
              /* SINGLE FOLDER MODE */
              <div>
                <div style={{ marginBottom: '14px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 700, color: '#cbd5e1', marginBottom: '6px' }}>
                    Folder Path to Scan:
                  </label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input
                      type="text"
                      value={singleFolderPath}
                      onChange={(e) => setSingleFolderPath(e.target.value)}
                      placeholder="Enter path or click Browse with Explorer..."
                      style={{
                        flex: 1,
                        background: 'rgba(0, 0, 0, 0.3)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        borderRadius: '8px',
                        color: '#f8fafc',
                        padding: '10px 12px',
                        fontSize: '13px',
                        outline: 'none',
                        boxSizing: 'border-box'
                      }}
                    />
                    <button
                      type="button"
                      onClick={handleBrowseFolderWithExplorer}
                      disabled={isPickingFolder}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        background: 'linear-gradient(135deg, rgba(2, 132, 199, 0.25), rgba(37, 99, 235, 0.35))',
                        border: '1px solid rgba(56, 189, 248, 0.5)',
                        color: '#38bdf8',
                        padding: '10px 16px',
                        borderRadius: '8px',
                        fontSize: '13px',
                        fontWeight: 700,
                        cursor: isPickingFolder ? 'wait' : 'pointer',
                        whiteSpace: 'nowrap',
                        transition: 'all 0.15s'
                      }}
                      title="Open native Windows Explorer to choose a folder"
                    >
                      {isPickingFolder ? (
                        <RefreshCw size={15} className="spin-animation" />
                      ) : (
                        <FolderOpen size={16} />
                      )}
                      <span>{isPickingFolder ? 'Opening Explorer...' : 'Browse with Explorer'}</span>
                    </button>
                  </div>
                </div>

                {/* Quick-pick shortcuts */}
                {scanRootsInfo?.roots && scanRootsInfo.roots.length > 0 && (
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
                      Quick Pick Windows Folders:
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {scanRootsInfo.roots.map((r, i) => {
                        const parts = r.split(/[\\/]/);
                        const label = parts[parts.length - 1] || r;
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => setSingleFolderPath(r)}
                            style={{
                              background: singleFolderPath === r ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                              border: `1px solid ${singleFolderPath === r ? '#38bdf8' : 'rgba(255, 255, 255, 0.1)'}`,
                              color: singleFolderPath === r ? '#38bdf8' : '#cbd5e1',
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              cursor: 'pointer'
                            }}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Subfolders Toggle Checkbox */}
                <div style={{ marginBottom: '20px' }}>
                  <label style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    cursor: 'pointer',
                    background: 'rgba(255, 255, 255, 0.03)',
                    padding: '12px',
                    borderRadius: '10px',
                    border: '1px solid rgba(255, 255, 255, 0.08)'
                  }}>
                    <input
                      type="checkbox"
                      checked={includeSubfolders}
                      onChange={(e) => setIncludeSubfolders(e.target.checked)}
                      style={{ marginTop: '3px', cursor: 'pointer', width: '16px', height: '16px', accentColor: '#38bdf8' }}
                    />
                    <div>
                      <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: '13px' }}>
                        Include subfolders (recursive scan)
                      </div>
                      <div style={{ color: '#94a3b8', fontSize: '11px', marginTop: '2px', lineHeight: 1.4 }}>
                        {includeSubfolders
                          ? "Will scan this folder and all subdirectories inside it for personal documents."
                          : "Only scans documents directly inside this folder. Subdirectories will be skipped."}
                      </div>
                    </div>
                  </label>
                </div>
              </div>
            )}

            {/* Reset / Clear Catalog Helper in Scan Modal */}
            <div style={{
              marginTop: '16px',
              paddingTop: '16px',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: '12px'
            }}>
              <div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#f87171' }}>
                  Reset or clean up catalog?
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  Safely purge the catalog database & library copies. Original files on your computer remain 100% untouched.
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsScanModalOpen(false);
                  setIsClearConfirmOpen(true);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(239, 68, 68, 0.12)',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  color: '#f87171',
                  padding: '7px 12px',
                  borderRadius: '8px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap'
                }}
              >
                <RotateCcw size={13} />
                <span>Reset Catalog</span>
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '16px' }}>
              <button
                type="button"
                onClick={() => setIsScanModalOpen(false)}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#cbd5e1',
                  padding: '10px 18px',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() => {
                  handleStartScan();
                }}
                disabled={scanMode === 'all_allowed_folders' && selectedRootsToScan.length === 0}
                style={{
                  background: 'linear-gradient(135deg, #0284c7, #2563eb)',
                  color: '#ffffff',
                  border: 'none',
                  padding: '10px 22px',
                  borderRadius: '10px',
                  cursor: (scanMode === 'all_allowed_folders' && selectedRootsToScan.length === 0) ? 'not-allowed' : 'pointer',
                  fontWeight: 700,
                  boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  opacity: (scanMode === 'all_allowed_folders' && selectedRootsToScan.length === 0) ? 0.5 : 1
                }}
              >
                <FolderSearch size={16} />
                <span>
                  {scanMode === 'all_allowed_folders'
                    ? `Start Scan (${selectedRootsToScan.length} Folder${selectedRootsToScan.length === 1 ? '' : 's'})`
                    : 'Scan Selected Folder'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clear / Reset Catalog Confirmation Modal */}
      {isClearConfirmOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.85)',
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          zIndex: 11000,
          backdropFilter: 'blur(8px)',
          padding: '24px'
        }}
        onClick={() => !isClearing && setIsClearConfirmOpen(false)}
        >
          <div
            style={{
              background: '#0f172a',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: '16px',
              maxWidth: '520px',
              width: '100%',
              padding: '24px',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.7)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <div style={{
                background: 'rgba(239, 68, 68, 0.15)',
                color: '#f87171',
                padding: '10px',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <RotateCcw size={22} />
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#f8fafc' }}>
                  Reset Documents Catalog?
                </h2>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  Accidentally scanned more areas? Cleanly reset the catalog here.
                </div>
              </div>
            </div>

            <div style={{
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              padding: '12px 14px',
              borderRadius: '10px',
              color: '#34d399',
              fontSize: '12px',
              lineHeight: 1.5,
              marginBottom: '16px',
              display: 'flex',
              gap: '10px'
            }}>
              <ShieldCheck size={18} flexShrink={0} style={{ marginTop: '2px' }} />
              <div>
                <strong>Your PC original files are 100% safe:</strong> None of your original files on your computer will ever be touched, modified, or deleted. This only clears the document index database and the copies stored in the documents library.
              </div>
            </div>

            <p style={{ color: '#cbd5e1', fontSize: '13px', lineHeight: 1.5, margin: '0 0 20px 0' }}>
              This will remove all {totalCount} indexed entries and copies from this Documents view so you can rescan only the exact folder you want.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                disabled={isClearing}
                onClick={() => setIsClearConfirmOpen(false)}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  color: '#cbd5e1',
                  padding: '10px 18px',
                  borderRadius: '10px',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isClearing}
                onClick={handleClearCatalog}
                style={{
                  background: 'linear-gradient(135deg, #dc2626, #b91c1c)',
                  color: '#ffffff',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '10px',
                  cursor: isClearing ? 'wait' : 'pointer',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  boxShadow: '0 4px 14px rgba(220, 38, 38, 0.4)'
                }}
              >
                {isClearing ? <RefreshCw size={15} className="spin-animation" /> : <RotateCcw size={15} />}
                <span>{isClearing ? 'Resetting Catalog...' : 'Confirm Reset Catalog'}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Watched Folders Management Modal */}
      <WatchedFoldersModal
        isOpen={isWatchedModalOpen}
        onClose={() => setIsWatchedModalOpen(false)}
        onFoldersChanged={() => {
          loadWatchedCount();
          loadStats();
          loadDocuments();
          pollScanStatus();
        }}
      />
    </div>
  );
}
