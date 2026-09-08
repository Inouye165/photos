import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  AlertTriangle,
  RotateCcw,
  User,
  Heart,
  Sparkles,
  Plus,
  Cloud,
  CloudCheck,
  CloudUpload
} from 'lucide-react';
import { fetchPhotoDetails, reclassifyPhoto, deletePhoto, tagPhotoTrash } from '../api';
import BoundingBoxOverlay from './BoundingBoxOverlay';

export default function Lightbox({ photo, onClose, onReclassifySuccess, onPhotoDeleted, onTrashStatusChanged }) {
  const [details, setDetails] = useState(photo);
  const [loading, setLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showBoxes, setShowBoxes] = useState(true);
  const [photoBoxes, setPhotoBoxes] = useState([]);
  const [isDrawMode, setIsDrawMode] = useState(false);
  const [selectedBoxId, setSelectedBoxId] = useState(null);

  const handleBoxesUpdated = useCallback((boxes) => {
    if (Array.isArray(boxes)) {
      setPhotoBoxes(boxes);
    }
  }, []);

  const imageRef = useRef(null);
  const previewContainerRef = useRef(null);

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

  const isTrashed = Boolean(details.is_trashed);
  const previewUrl = `/api/photos/${photo.id}/preview`;
  const originalUrl = `/api/photos/${photo.id}/original`;

  const formatFileSize = (bytes) => {
    if (!bytes) return 'Unknown';
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(2)} MB (${bytes.toLocaleString()} bytes)` : `${(bytes / 1024).toFixed(1)} KB`;
  };

  const handleToggleTrash = async () => {
    try {
      setIsUpdating(true);
      const nextTrashed = !isTrashed;
      await tagPhotoTrash(photo.id, nextTrashed);
      setDetails((prev) => ({ ...prev, is_trashed: nextTrashed ? 1 : 0 }));
      if (onTrashStatusChanged) onTrashStatusChanged();
    } catch (e) {
      alert('Failed to update trash status: ' + e.message);
    } finally {
      setIsUpdating(false);
    }
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

  const hasGps = details.latitude != null && details.longitude != null && !isNaN(Number(details.latitude)) && !isNaN(Number(details.longitude));
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
            {isTrashed && (
              <span style={{
                fontSize: '0.75rem',
                padding: '2px 8px',
                borderRadius: '9999px',
                background: 'rgba(239, 68, 68, 0.25)',
                color: '#fca5a5',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                flexShrink: 0,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px'
              }}>
                <Trash2 size={11} />
                <span>Tagged for Trash</span>
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {/* Tag / Restore Trash button */}
            <button
              className="btn-secondary"
              style={{
                fontSize: '0.8rem',
                padding: '0.4rem 0.75rem',
                color: isTrashed ? '#86efac' : '#fca5a5',
                borderColor: isTrashed ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'
              }}
              onClick={handleToggleTrash}
              disabled={isUpdating}
              title={isTrashed ? 'Restore photo from trash' : 'Tag photo for trash (file remains intact)'}
            >
              {isTrashed ? <RotateCcw size={14} /> : <Trash2 size={14} />}
              <span className="hide-on-mobile">{isTrashed ? 'Restore Photo' : 'Tag for Trash'}</span>
            </button>

            <button
              className="btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.4rem 0.75rem', color: '#94a3b8' }}
              onClick={() => setShowDeleteConfirm(true)}
              title="Immediately move file to Recycle Bin"
            >
              <Trash2 size={14} />
              <span className="hide-on-mobile">Delete Now</span>
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

            {/* People & Pets Bounding Box Toggle */}
            <button
              className={`btn-secondary ${showBoxes ? 'active-filter-btn' : ''}`}
              style={{
                fontSize: '0.8rem',
                padding: '0.4rem 0.75rem',
                borderColor: showBoxes ? '#6366f1' : 'rgba(255, 255, 255, 0.15)',
                color: showBoxes ? '#c7d2fe' : '#94a3b8'
              }}
              onClick={() => setShowBoxes((prev) => !prev)}
              title="Toggle People & Pets Bounding Boxes"
            >
              <User size={14} />
              <span className="hide-on-mobile">{showBoxes ? 'Tags Visible' : 'Show Tags'}</span>
              {photoBoxes.length > 0 && (
                <span className="nav-badge" style={{ padding: '1px 6px', fontSize: '0.68rem', background: 'rgba(99, 102, 241, 0.3)' }}>
                  {photoBoxes.length}
                </span>
              )}
            </button>

            {/* Manual Draw Tag Button */}
            <button
              className={`btn-secondary ${isDrawMode ? 'active-filter-btn' : ''}`}
              style={{
                fontSize: '0.8rem',
                padding: '0.4rem 0.75rem',
                borderColor: isDrawMode ? '#38bdf8' : 'rgba(56, 189, 248, 0.3)',
                color: isDrawMode ? '#38bdf8' : '#7dd3fc',
                background: isDrawMode ? 'rgba(56, 189, 248, 0.2)' : 'transparent'
              }}
              onClick={() => {
                setShowBoxes(true);
                setIsDrawMode((prev) => !prev);
              }}
              title="Add a person or pet tag manually by drawing a box"
            >
              <Plus size={14} />
              <span className="hide-on-mobile">{isDrawMode ? 'Drawing...' : 'Add Tag'}</span>
            </button>

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

        {/* Center Preview Image with Bounding Box Overlay */}
        <div
          className="lightbox-preview-area"
          ref={previewContainerRef}
          style={{ position: 'relative' }}
        >
          <img
            ref={imageRef}
            src={previewUrl}
            alt={details.file_name}
            className="lightbox-image"
          />
          {showBoxes && (
            <BoundingBoxOverlay
              photoId={photo.id}
              imageRef={imageRef}
              containerRef={previewContainerRef}
              onBoxesUpdated={handleBoxesUpdated}
              isDrawMode={isDrawMode}
              setIsDrawMode={setIsDrawMode}
              selectedBoxId={selectedBoxId}
              onSelectBox={setSelectedBoxId}
            />
          )}
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

        {/* People & Pets in this Photo */}
        <div className="exif-block">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#818cf8', fontSize: '0.85rem', fontWeight: 600 }}>
              <User size={16} />
              <span>People & Pets in Photo</span>
            </div>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
              {photoBoxes.length} tagged
            </span>
          </div>

          {photoBoxes.length === 0 ? (
            <div style={{ fontSize: '0.78rem', color: '#64748b', fontStyle: 'italic', lineHeight: '1.4' }}>
              No people or pets tagged yet. Click or drag a box on the photo to tag someone.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {photoBoxes.map((box) => (
                <div
                  key={box.id}
                  onClick={() => setSelectedBoxId(box.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 8px',
                    borderRadius: '6px',
                    background: selectedBoxId === box.id ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.04)',
                    border: selectedBoxId === box.id ? '1px solid #6366f1' : '1px solid rgba(255, 255, 255, 0.08)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <img
                      src={`/api/boxes/${box.id}/crop`}
                      alt="Crop"
                      style={{ width: '28px', height: '28px', borderRadius: '50%', objectFit: 'cover' }}
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                    <div>
                      <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#ffffff' }}>
                        {box.entity_name || 'Unnamed Face'}
                      </div>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>
                        {box.box_type === 'PET' ? 'Pet' : 'Person'}
                      </div>
                    </div>
                  </div>

                  <span
                    style={{
                      fontSize: '0.68rem',
                      padding: '2px 6px',
                      borderRadius: '9999px',
                      background: box.status === 'CONFIRMED' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                      color: box.status === 'CONFIRMED' ? '#6ee7b7' : '#fde68a',
                      border: '1px solid rgba(255, 255, 255, 0.1)'
                    }}
                  >
                    {box.status === 'CONFIRMED' ? 'Confirmed' : 'Auto-Match'}
                  </span>
                </div>
              ))}
            </div>
          )}
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
          {hasGps ? (
            <>
              <div className="exif-row">
                <span className="exif-label">GPS Coordinates</span>
                <span className="exif-value">
                  {Number(details.latitude).toFixed(4)}, {Number(details.longitude).toFixed(4)}
                  {details.altitude != null && !isNaN(Number(details.altitude)) ? ` (${Math.round(Number(details.altitude))}m alt)` : ''}
                </span>
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
          ) : (
            <div className="exif-row">
              <span className="exif-label">GPS Geotag</span>
              <span className="exif-value" style={{ color: '#64748b' }}>None</span>
            </div>
          )}
        </div>

        {/* Google Drive Backup Status */}
        <div className="exif-block">
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Cloud size={13} color="#38bdf8" />
            <span>Google Drive Backup</span>
          </div>
          <div className="exif-row">
            <span className="exif-label">Backup Status</span>
            <span
              className="exif-value"
              style={{
                color: details.gdrive_backup_status === 'backed_up'
                  ? '#34d399'
                  : details.gdrive_backup_status === 'uploading'
                  ? '#38bdf8'
                  : '#94a3b8',
                fontWeight: 600
              }}
            >
              {details.gdrive_backup_status === 'backed_up'
                ? '✓ Backed Up'
                : details.gdrive_backup_status === 'uploading'
                ? 'Uploading...'
                : 'Pending'}
            </span>
          </div>
          {details.gdrive_backed_up_at && (
            <div className="exif-row">
              <span className="exif-label">Backed Up At</span>
              <span className="exif-value">
                {new Date(details.gdrive_backed_up_at * 1000).toLocaleString()}
              </span>
            </div>
          )}
          {details.gdrive_error && (
            <div className="exif-row">
              <span className="exif-label" style={{ color: '#f87171' }}>Last Error</span>
              <span className="exif-value" style={{ color: '#fca5a5' }}>
                {details.gdrive_error}
              </span>
            </div>
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
