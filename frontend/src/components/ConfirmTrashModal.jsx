import React from 'react';
import { AlertTriangle, Trash2, X, RotateCcw, Check, Sparkles } from 'lucide-react';

export default function ConfirmTrashModal({
  isOpen,
  onClose,
  onConfirm,
  selectedPhotos = [],
  isLoading = false
}) {
  if (!isOpen) return null;

  const count = selectedPhotos.length;
  const totalBytes = selectedPhotos.reduce((acc, p) => acc + (p.file_size || 0), 0);
  const formattedSize = totalBytes > 1024 * 1024 * 1024
    ? `${(totalBytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
    : `${(totalBytes / (1024 * 1024)).toFixed(1)} MB`;

  const previewPhotos = selectedPhotos.slice(0, 8);
  const remainingCount = Math.max(0, count - previewPhotos.length);

  return (
    <div className="confirm-modal-backdrop" onClick={onClose}>
      <div className="confirm-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="confirm-modal-header">
          <div className="confirm-modal-icon-wrap">
            <Trash2 size={24} color="#ef4444" />
          </div>
          <div>
            <h3 className="confirm-modal-title">Move to Trash</h3>
            <p className="confirm-modal-subtitle">
              Mark {count.toLocaleString()} {count === 1 ? 'photo' : 'photos'} for deletion
            </p>
          </div>
          <button className="modal-close-btn" onClick={onClose} disabled={isLoading}>
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="confirm-modal-body">
          <p className="confirm-modal-desc">
            Are you sure you want to move <strong>{count.toLocaleString()} {count === 1 ? 'photo' : 'photos'}</strong> ({formattedSize}) to the Trash?
          </p>

          {/* Photo Previews */}
          {previewPhotos.length > 0 && (
            <div className="confirm-preview-grid">
              {previewPhotos.map((photo) => (
                <div key={photo.id} className="confirm-preview-thumb" title={photo.file_name}>
                  <img
                    src={`/api/photos/${photo.id}/thumbnail`}
                    alt={photo.file_name}
                    loading="lazy"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                </div>
              ))}
              {remainingCount > 0 && (
                <div className="confirm-preview-more">
                  +{remainingCount.toLocaleString()} more
                </div>
              )}
            </div>
          )}

          {/* Safety Notice */}
          <div className="confirm-modal-notice">
            <Sparkles size={16} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong>Files remain safe on disk:</strong> Photos are tagged for trash in your catalog. Original files stay intact in their folders until you explicitly empty the trash or automated storage space purge runs. You can restore them anytime from the <strong>Trash</strong> tab.
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="confirm-modal-footer">
          <button
            type="button"
            className="btn-modal-cancel"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-modal-confirm-delete"
            onClick={onConfirm}
            disabled={isLoading || count === 0}
          >
            {isLoading ? (
              <>
                <RotateCcw size={16} className="spin-icon" />
                <span>Moving to Trash...</span>
              </>
            ) : (
              <>
                <Trash2 size={16} />
                <span>Move {count.toLocaleString()} {count === 1 ? 'Photo' : 'Photos'} to Trash</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
