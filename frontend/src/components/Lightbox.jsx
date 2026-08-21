import React, { useState, useEffect } from 'react';
import {
  X,
  Camera,
  MapPin,
  Calendar,
  FileText,
  Copy,
  Download,
  Info,
  ExternalLink,
  ShieldCheck,
  Tag,
  Trash2,
  AlertTriangle
} from 'lucide-react';
import { fetchPhotoDetails, reclassifyPhoto, deletePhoto } from '../api';

export default function Lightbox({ photo, onClose, onReclassifySuccess, onPhotoDeleted }) {
  const [details, setDetails] = useState(photo);
  const [loading, setLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  useEffect(() => {
    if (!photo?.id) return;
    setLoading(true);
    fetchPhotoDetails(photo.id)
      .then((data) => {
        setDetails(data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [photo?.id]);

  if (!photo) return null;

  const previewUrl = `/api/photos/${photo.id}/preview`;
  const originalUrl = `/api/photos/${photo.id}/original`;

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown';
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(2)} MB (${bytes.toLocaleString()} bytes)` : `${(bytes / 1024).toFixed(1)} KB`;
  };

  const handleReclassify = async (newClass) => {
    try {
      setIsUpdating(true);
      await reclassifyPhoto(photo.id, newClass);
      setDetails((prev) => ({ ...prev, classification: newClass }));
      if (onReclassifySuccess) onReclassifySuccess();
    } catch (e) {
      alert('Failed to reclassify: ' + e.message);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    try {
      setIsDeleting(true);
      await deletePhoto(photo.id);
      setShowDeleteConfirm(false);
      if (onPhotoDeleted) onPhotoDeleted();
      onClose();
    } catch (err) {
      alert('Error deleting photo: ' + err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  const hasGps = details.latitude !== null && details.longitude !== null;
  const mapsUrl = hasGps
    ? `https://www.google.com/maps?q=${details.latitude},${details.longitude}`
    : null;

  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <div className="lightbox-main" onClick={(e) => e.stopPropagation()}>
        {/* Top bar */}
        <div className="lightbox-top-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', overflow: 'hidden' }}>
            <span style={{ fontWeight: 600, fontSize: '1.1rem', color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {details.file_name}
            </span>
            <span style={{
              fontSize: '0.75rem',
              padding: '2px 8px',
              borderRadius: '9999px',
              background: details.classification === 'VERIFIED_PHOTO' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(99, 102, 241, 0.2)',
              color: details.classification === 'VERIFIED_PHOTO' ? '#6ee7b7' : '#c7d2fe',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              flexShrink: 0
            }}>
              {details.classification?.replace('_', ' ')}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              className="btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.4rem 0.75rem', color: '#fca5a5', borderColor: 'rgba(239, 68, 68, 0.3)' }}
              onClick={() => setShowDeleteConfirm(true)}
              title="Move file to Recycle Bin"
            >
              <Trash2 size={14} />
              <span className="hide-on-mobile">Delete</span>
            </button>

            <a
              href={originalUrl}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary"
              style={{ textDecoration: 'none', fontSize: '0.8rem', padding: '0.4rem 0.85rem' }}
            >
              <Download size={14} />
              <span className="hide-on-mobile">Original File</span>
            </a>

            <button
              onClick={onClose}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: 'none',
                color: '#ffffff',
                width: '36px',
                height: '36px',
                borderRadius: '50%',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Center Preview Image */}
        <div className="lightbox-preview-area">
          <img
            src={previewUrl}
            alt={details.file_name}
            className="lightbox-image"
          />
        </div>
      </div>

      {/* Side EXIF Drawer */}
      <div className="lightbox-side-drawer" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
          <Camera size={18} color="#10b981" />
          <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.1rem', color: '#ffffff' }}>
            EXIF & File Pointer
          </h3>
        </div>

        {/* Classification & Reason */}
        <div className="exif-block">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: '#a7f3d0', fontSize: '0.85rem', fontWeight: 600 }}>
            <ShieldCheck size={16} />
            <span>Verification Status</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#cbd5e1', lineHeight: '1.4' }}>
            {details.classification_reason || 'Verified Camera Photo'}
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem' }}>
            <select
              className="select-styled"
              style={{ width: '100%', fontSize: '0.75rem' }}
              value={details.classification}
              onChange={(e) => handleReclassify(e.target.value)}
              disabled={isUpdating}
            >
              <option value="VERIFIED_PHOTO">Verified Camera Photo</option>
              <option value="LIKELY_PHOTO">Likely Photo</option>
              <option value="SCREENSHOT">Screenshot / Screen Grab</option>
              <option value="SYSTEM_ASSET">System / UI Asset</option>
            </select>
          </div>
        </div>

        {/* Camera Hardware */}
        <div className="exif-block">
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Camera & Optics
          </div>
          <div className="exif-row">
            <span className="exif-label">Camera Make</span>
            <span className="exif-value">{details.camera_make || 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Camera Model</span>
            <span className="exif-value">{details.camera_model || 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Lens Model</span>
            <span className="exif-value">{details.lens_model || 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Focal Length</span>
            <span className="exif-value">{details.focal_length ? `${details.focal_length} mm` : 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Aperture</span>
            <span className="exif-value">{details.f_number ? `f/${details.f_number}` : 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Exposure</span>
            <span className="exif-value">{details.exposure_time ? `${details.exposure_time} s` : 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">ISO</span>
            <span className="exif-value">{details.iso || 'N/A'}</span>
          </div>
          {details.software && (
            <div className="exif-row">
              <span className="exif-label">Software</span>
              <span className="exif-value">{details.software}</span>
            </div>
          )}
        </div>

        {/* Date & Location */}
        <div className="exif-block">
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Time & Geotag
          </div>
          <div className="exif-row">
            <span className="exif-label">Date Taken</span>
            <span className="exif-value">{details.date_taken || 'N/A'}</span>
          </div>
          {hasGps && (
            <>
              <div className="exif-row">
                <span className="exif-label">GPS Coordinates</span>
                <span className="exif-value">{details.latitude?.toFixed(4)}, {details.longitude?.toFixed(4)}</span>
              </div>
              <div style={{ marginTop: '0.5rem', textAlign: 'right' }}>
                <a
                  href={mapsUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#38bdf8', fontSize: '0.78rem', display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                >
                  <MapPin size={12} />
                  <span>View in Google Maps</span>
                  <ExternalLink size={11} />
                </a>
              </div>
            </>
          )}
        </div>

        {/* In-Place Pointer & Hashes */}
        <div className="exif-block">
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            In-Place Pointer & Hashes
          </div>
          <div className="exif-row">
            <span className="exif-label">Dimensions</span>
            <span className="exif-value">{details.width} × {details.height} px</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">File Size</span>
            <span className="exif-value">{formatFileSize(details.file_size)}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Format</span>
            <span className="exif-value">{details.file_extension?.toUpperCase()}</span>
          </div>
          <div className="exif-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
            <span className="exif-label">Original File Path Pointer</span>
            <span className="exif-value" style={{ maxWidth: '100%', textAlign: 'left', fontSize: '0.7rem', color: '#94a3b8', wordBreak: 'break-all', whiteSpace: 'normal' }}>
              {details.file_path}
            </span>
          </div>
          <div className="exif-row">
            <span className="exif-label">pHash</span>
            <span className="exif-value">{details.phash || 'N/A'}</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">SHA-256</span>
            <span className="exif-value" style={{ fontSize: '0.65rem' }}>{details.sha256 ? `${details.sha256.slice(0, 16)}...` : 'N/A'}</span>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="modal-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="modal-card" style={{ maxWidth: '440px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f87171', marginBottom: '1rem' }}>
              <AlertTriangle size={22} />
              <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', color: '#ffffff' }}>
                Delete Photo File?
              </h3>
            </div>
            <p style={{ fontSize: '0.875rem', color: '#cbd5e1', marginBottom: '1rem', lineHeight: '1.4' }}>
              Are you sure you want to delete this photo? It will be moved to the <strong>Windows Recycle Bin</strong>:
            </p>
            <div style={{
              background: '#161b28',
              padding: '0.75rem',
              borderRadius: '8px',
              fontSize: '0.78rem',
              color: '#94a3b8',
              wordBreak: 'break-all',
              marginBottom: '1.25rem'
            }}>
              {details.file_path}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button className="btn-secondary" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{ background: '#ef4444' }}
                onClick={handleDelete}
                disabled={isDeleting}
              >
                <Trash2 size={15} />
                <span>{isDeleting ? 'Deleting...' : 'Move to Recycle Bin'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
