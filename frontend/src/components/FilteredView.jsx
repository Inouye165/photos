import React, { useState, useEffect } from 'react';
import { ShieldAlert, Check, RefreshCw, Sparkles, Image as ImageIcon } from 'lucide-react';
import { fetchFilteredAssets, reclassifyPhoto } from '../api';

export default function FilteredView({ onSelectPhoto, onRefreshStats }) {
  const [data, setData] = useState({ screenshots: [], system_assets: [] });
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState(null);

  const loadData = () => {
    setLoading(true);
    fetchFilteredAssets()
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleReclassify = async (e, photoId) => {
    e.stopPropagation();
    try {
      setUpdatingId(photoId);
      await reclassifyPhoto(photoId, 'VERIFIED_PHOTO');
      loadData();
      if (onRefreshStats) onRefreshStats();
    } catch (err) {
      alert('Error reclassifying: ' + err.message);
    } finally {
      setUpdatingId(null);
    }
  };

  const allFiltered = [...(data.screenshots || []), ...(data.system_assets || [])];

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '5rem 0', color: '#94a3b8' }}>
        <p>Loading filtered computer assets...</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{
        background: 'rgba(99, 102, 241, 0.08)',
        border: '1px solid rgba(99, 102, 241, 0.2)',
        borderRadius: '12px',
        padding: '1rem 1.25rem',
        marginBottom: '1.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ShieldAlert size={20} color="#a5b4fc" />
          <span style={{ fontSize: '0.875rem', color: '#e0e7ff' }}>
            These items were automatically filtered out as screenshots, computer UI graphics, or icons. You can override any item with one click.
          </span>
        </div>
        <button className="btn-secondary" onClick={loadData} style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}>
          <RefreshCw size={13} />
          <span>Refresh</span>
        </button>
      </div>

      {allFiltered.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '5rem 2rem',
          background: 'rgba(255, 255, 255, 0.02)',
          borderRadius: '16px',
          border: '1px dashed rgba(255, 255, 255, 0.1)',
          maxWidth: '600px',
          margin: '2rem auto'
        }}>
          <Check size={48} color="#10b981" style={{ marginBottom: '1rem' }} />
          <h3 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', marginBottom: '0.5rem', color: '#f1f5f9' }}>
            No Filtered Computer Graphics
          </h3>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
            All discovered media passed as authentic camera photos.
          </p>
        </div>
      ) : (
        <div className="photo-grid">
          {allFiltered.map((item) => (
            <div
              key={item.id}
              className="photo-card"
              onClick={() => onSelectPhoto(item)}
            >
              <div className="photo-card-img-wrap">
                <img
                  src={`/api/photos/${item.id}/thumbnail`}
                  alt={item.file_name}
                  className="photo-card-img"
                  loading="lazy"
                />
                <div className="photo-badge-top-left">
                  <span style={{
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    padding: '2px 7px',
                    borderRadius: '9999px',
                    background: 'rgba(239, 68, 68, 0.85)',
                    color: '#ffffff'
                  }}>
                    {item.classification === 'SCREENSHOT' ? 'Screenshot' : 'System Asset'}
                  </span>
                </div>
              </div>

              <div className="photo-card-info">
                <div className="photo-card-name" title={item.file_name}>
                  {item.file_name}
                </div>
                <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginBottom: '0.5rem', lineHeight: '1.3' }}>
                  {item.classification_reason || 'Identified as computer image'}
                </div>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{
                    width: '100%',
                    justifyContent: 'center',
                    fontSize: '0.75rem',
                    padding: '0.35rem 0.6rem',
                    background: 'rgba(16, 185, 129, 0.15)',
                    borderColor: 'rgba(16, 185, 129, 0.3)',
                    color: '#6ee7b7'
                  }}
                  disabled={updatingId === item.id}
                  onClick={(e) => handleReclassify(e, item.id)}
                >
                  <Sparkles size={12} />
                  <span>{updatingId === item.id ? 'Reclassifying...' : 'Mark as Real Photo'}</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
