import React, { useEffect, useRef, useState } from 'react';
import { Image as ImageIcon, RefreshCw } from 'lucide-react';

const RETRY_DELAYS = [400, 900, 1400];

export function getPhotoImageSource(photoId, stage) {
  if (stage === 0) return `/api/photos/${photoId}/thumbnail`;
  if (stage === 1) return `/api/photos/${photoId}/thumbnail?refresh=true`;
  if (stage === 2) return `/api/photos/${photoId}/original`;
  if (stage === 3) return `/api/photos/${photoId}/original?retry=1`;
  return null;
}

export default function RetryImage({ photoId, alt, className = '', loading = 'lazy' }) {
  const [stage, setStage] = useState(0);
  const retryTimerRef = useRef(null);
  const source = getPhotoImageSource(photoId, stage);

  useEffect(() => {
    setStage(0);
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [photoId]);

  const handleError = (event) => {
    event.currentTarget.style.visibility = 'hidden';
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);

    if (stage >= 3) {
      setStage(4);
      return;
    }

    retryTimerRef.current = setTimeout(() => {
      setStage((currentStage) => currentStage === stage ? currentStage + 1 : currentStage);
    }, RETRY_DELAYS[stage]);
  };

  if (!source) {
    return (
      <div className="photo-card-image-fallback" role="img" aria-label={`${alt} could not be loaded`}>
        <ImageIcon size={28} aria-hidden="true" />
        <button
          type="button"
          className="photo-card-image-retry"
          title="Retry image"
          aria-label={`Retry loading ${alt}`}
          onClick={(event) => {
            event.stopPropagation();
            setStage(0);
          }}
        >
          <RefreshCw size={15} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <img
      key={stage}
      src={source}
      alt={alt}
      className={className}
      loading={loading}
      onError={handleError}
    />
  );
}