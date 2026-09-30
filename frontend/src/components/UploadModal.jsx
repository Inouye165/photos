import React, { useState, useRef } from 'react';
import { X, UploadCloud, Image as ImageIcon, CheckCircle2, AlertCircle, FileText, Trash2, Smartphone } from 'lucide-react';
import { uploadPhotos } from '../api';

const MAX_UPLOAD_FILES = 50;
const MAX_UPLOAD_FILE_BYTES = 1024 * 1024 * 1024;
const MAX_UPLOAD_BATCH_BYTES = 2 * 1024 * 1024 * 1024;
const SUPPORTED_UPLOAD_EXTENSION = /\.(jpg|jpeg|png|heic|heif|webp|tiff|tif|cr2|nef|arw|dng|rw2|orf|pef|mp4|mov|m4v|avi|mkv|wmv)$/i;

export default function UploadModal({ isOpen, onClose, onUploadComplete }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleFiles = (files) => {
    const candidates = Array.from(files);
    const valid = candidates.filter((file) => SUPPORTED_UPLOAD_EXTENSION.test(file.name));
    if (valid.length === 0) {
      setErrorMessage('Please select supported photo or video files.');
      return;
    }
    const currentBytes = selectedFiles.reduce((total, file) => total + file.size, 0);
    let nextBytes = currentBytes;
    let rejectedCount = candidates.length - valid.length;
    const accepted = [];
    for (const file of valid) {
      if (file.size > MAX_UPLOAD_FILE_BYTES || selectedFiles.length + accepted.length >= MAX_UPLOAD_FILES || nextBytes + file.size > MAX_UPLOAD_BATCH_BYTES) {
        rejectedCount += 1;
        continue;
      }
      accepted.push(file);
      nextBytes += file.size;
    }
    setErrorMessage(rejectedCount ? `${rejectedCount} file${rejectedCount === 1 ? ' was' : 's were'} skipped (unsupported type, size, or batch limit).` : null);
    setUploadResult(null);
    setSelectedFiles((prev) => [...prev, ...accepted]);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer?.files?.length) {
      handleFiles(e.dataTransfer.files);
    }
  };

  const removeFile = (index) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const clearAll = () => {
    setSelectedFiles([]);
    setUploadResult(null);
    setErrorMessage(null);
    setUploadProgress(0);
  };

  const handleStartUpload = async () => {
    if (selectedFiles.length === 0 || isUploading) return;

    setIsUploading(true);
    setUploadProgress(0);
    setErrorMessage(null);

    try {
      const res = await uploadPhotos(selectedFiles, (percent) => {
        setUploadProgress(percent);
      });

      setUploadResult(res);
      if (onUploadComplete) {
        onUploadComplete(res);
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to upload photos.');
    } finally {
      setIsUploading(false);
    }
  };

  const retryFailedUploads = () => {
    const failedIndexes = new Set(
      (uploadResult?.results || [])
        .filter((result) => result.status === 'failed')
        .map((result) => result.file_index)
    );
    setSelectedFiles((current) => current.filter((_, index) => failedIndexes.has(index)));
    setUploadResult(null);
    setUploadProgress(0);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '0 B';
    const mb = bytes / (1024 * 1024);
    if (mb >= 1) return `${mb.toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card"
        style={{ maxWidth: '580px', width: '92%' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              background: 'rgba(16, 185, 129, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <UploadCloud size={20} color="#10b981" />
            </div>
            <div>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', color: '#ffffff', margin: 0 }}>
                Upload to Library
              </h2>
              <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: 0 }}>
                Upload photos from your computer or phone over Wi-Fi
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '6px' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Drag and Drop Zone */}
        {!isUploading && !uploadResult && (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${isDragging ? '#10b981' : 'rgba(255, 255, 255, 0.15)'}`,
              borderRadius: '14px',
              padding: '2rem 1.5rem',
              textAlign: 'center',
              background: isDragging ? 'rgba(16, 185, 129, 0.06)' : 'rgba(15, 23, 42, 0.4)',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              marginBottom: '1rem'
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*,video/*,.heic,.heif,.cr2,.nef,.arw,.dng"
              style={{ display: 'none' }}
              onChange={(e) => {
                if (e.target.files) handleFiles(e.target.files);
              }}
            />
            <UploadCloud size={36} color={isDragging ? '#10b981' : '#64748b'} style={{ marginBottom: '10px' }} />
            <div style={{ color: '#f8fafc', fontWeight: 600, fontSize: '0.95rem', marginBottom: '4px' }}>
              Choose photos or drag them here
            </div>
            <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>
              Supports JPG, PNG, HEIC, WebP & Camera RAW. Automatically indexed into library.
            </div>
          </div>
        )}

        {/* Selected Files List */}
        {selectedFiles.length > 0 && !isUploading && !uploadResult && (
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.82rem', color: '#94a3b8', fontWeight: 600 }}>
                {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} ready to upload
              </span>
              <button
                onClick={clearAll}
                style={{ background: 'transparent', border: 'none', color: '#ef4444', fontSize: '0.78rem', cursor: 'pointer', padding: 0 }}
              >
                Clear all
              </button>
            </div>
            <div style={{
              maxHeight: '160px',
              overflowY: 'auto',
              background: '#131926',
              borderRadius: '10px',
              padding: '8px',
              border: '1px solid rgba(255, 255, 255, 0.08)'
            }}>
              {selectedFiles.slice(0, 10).map((file, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 8px',
                    borderRadius: '6px',
                    background: 'rgba(255, 255, 255, 0.02)',
                    marginBottom: '4px',
                    fontSize: '0.82rem'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                    <ImageIcon size={14} color="#10b981" />
                    <span style={{ color: '#e2e8f0', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                      {file.name}
                    </span>
                    <span style={{ color: '#64748b', fontSize: '0.75rem' }}>
                      ({formatFileSize(file.size)})
                    </span>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); removeFile(idx); }}
                    style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '2px' }}
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
              {selectedFiles.length > 10 && (
                <div style={{ textAlign: 'center', padding: '4px', fontSize: '0.78rem', color: '#64748b' }}>
                  +{selectedFiles.length - 10} more files
                </div>
              )}
            </div>
          </div>
        )}

        {/* Upload Progress Bar */}
        {isUploading && (
          <div style={{ padding: '1.5rem 0', textAlign: 'center' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: '#f8fafc', marginBottom: '8px' }}>
              <span>Uploading & indexing...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div style={{
              height: '8px',
              background: 'rgba(255, 255, 255, 0.1)',
              borderRadius: '4px',
              overflow: 'hidden',
              marginBottom: '10px'
            }}>
              <div style={{
                height: '100%',
                width: `${uploadProgress}%`,
                background: 'linear-gradient(90deg, #10b981, #06b6d4)',
                borderRadius: '4px',
                transition: 'width 0.2s ease'
              }} />
            </div>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
              Extracting EXIF metadata, classifying photo, and generating thumbnail...
            </span>
          </div>
        )}

        {/* Success Result */}
        {uploadResult && (
          <div style={{
            padding: '1.5rem',
            textAlign: 'center',
            background: 'rgba(16, 185, 129, 0.08)',
            border: '1px solid rgba(16, 185, 129, 0.25)',
            borderRadius: '12px',
            marginBottom: '1rem'
          }}>
            <CheckCircle2 size={40} color="#10b981" style={{ marginBottom: '10px' }} />
            <h3 style={{ color: '#ffffff', fontSize: '1.1rem', margin: '0 0 6px 0' }}>
              {uploadResult.failed ? `Uploaded ${uploadResult.count}; ${uploadResult.failed} need attention` : 'Upload Complete!'}
            </h3>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', margin: 0 }}>
              {uploadResult.message || `Added ${uploadResult.count} photos to your library.`}
            </p>
            {uploadResult.results?.some((item) => item.status === 'failed') && (
              <div style={{ maxHeight: '150px', overflowY: 'auto', marginTop: '1rem', textAlign: 'left' }}>
                {uploadResult.results.filter((item) => item.status === 'failed').map((item, index) => (
                  <div key={`${item.filename}-${index}`} style={{ color: '#fca5a5', fontSize: '0.8rem', marginTop: '0.35rem' }}>
                    {item.filename || 'Unnamed file'}: {item.error}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error Alert */}
        {errorMessage && (
          <div style={{
            padding: '0.75rem 1rem',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '1rem'
          }}>
            <AlertCircle size={16} color="#ef4444" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Modal Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '1rem' }}>
          {uploadResult ? (
            <>
              {uploadResult.failed > 0 && (
                <button className="btn-secondary" onClick={retryFailedUploads}>
                  Retry Failed ({uploadResult.failed})
                </button>
              )}
              <button
                className="btn-primary"
                onClick={() => {
                  setSelectedFiles([]);
                  setUploadResult(null);
                  onClose();
                }}
              >
                Done
              </button>
            </>
          ) : (
            <>
              <button
                className="btn-secondary"
                onClick={onClose}
                disabled={isUploading}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleStartUpload}
                disabled={selectedFiles.length === 0 || isUploading}
                style={{ opacity: selectedFiles.length === 0 ? 0.5 : 1 }}
              >
                {isUploading ? 'Uploading...' : `Upload ${selectedFiles.length > 0 ? selectedFiles.length : ''} Photos`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
