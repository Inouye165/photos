import React from 'react';
import { Camera, Calendar, Copy, Sparkles, Image as ImageIcon, MapPin } from 'lucide-react';

export default function PhotoGrid({ photos, onSelectPhoto, query, isLoading }) {
  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '5rem 0', color: '#94a3b8' }}>
        <div style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>
          <Sparkles size={32} color="#10b981" />
        </div>
        <p style={{ marginTop: '1rem', fontSize: '0.95rem' }}>Searching vector database...</p>
      </div>
    );
  }

  if (!photos || photos.length === 0) {
    return (
      <div style={{
        textAlign: 'center',
        padding: '5rem 2rem',
        background: 'rgba(255, 255, 255, 0.02)',
        borderRadius: '16px',
        border: '1px dashed rgba(255, 255, 255, 0.1)',
        maxWidth: '600px',
        margin: '2rem auto'
      }}>
        <ImageIcon size={48} color="#475569" style={{ marginBottom: '1rem' }} />
        <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>
          {query ? `No matching photos for "${query}"` : 'No photos indexed yet'}
        </h3>
        <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
          {query
            ? 'Try another search prompt or scan a folder with more pictures.'
            : 'Click "Scan Folder" in the top right to index your photos and build the vector database.'}
        </p>
      </div>
    );
  }

  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    } catch {
      return '';
    }
  };

  return (
    <div className="photo-grid">
      {photos.map((photo) => {
        const thumbUrl = `/api/photos/${photo.id}/thumbnail`;
        const hasDups = photo.duplicate_count > 0;
        const simScore = photo.similarity_score !== undefined
          ? Math.round(photo.similarity_score * 100)
          : null;

        return (
          <div
            key={photo.id}
            className="photo-card"
            onClick={() => onSelectPhoto(photo)}
          >
            <div className="photo-card-img-wrap">
              <img
                src={thumbUrl}
                alt={photo.file_name}
                className="photo-card-img"
                loading="lazy"
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
              
              {/* Badges */}
              <div className="photo-badge-top-left">
                {simScore !== null && (
                  <span className="badge-sim">
                    <Sparkles size={10} />
                    <span>{simScore}% Match</span>
                  </span>
                )}
                {hasDups && (
                  <span className="badge-dup">
                    <Copy size={10} />
                    <span>{photo.duplicate_count + 1} Duplicates</span>
                  </span>
                )}
              </div>
            </div>

            <div className="photo-card-info">
              <div className="photo-card-name" title={photo.file_name}>
                {photo.file_name}
              </div>
              <div className="photo-card-meta">
                <span className="photo-card-camera">
                  {photo.camera_model || photo.camera_make || (photo.width ? `${photo.width}×${photo.height}` : 'Photo')}
                </span>
                <span>{formatDate(photo.date_taken)}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
