import React from 'react';
import { Clock } from 'lucide-react';

export default function TimelineScrubber({
  timelineYears = [],
  selectedYear,
  onSelectYear,
  totalPhotos = 0
}) {
  if (!timelineYears || timelineYears.length === 0) return null;

  return (
    <div className="timeline-scrubber-wrap">
      <div className="timeline-scrubber-inner">
        <div className="timeline-label">
          <Clock size={13} />
          <span>Timeline:</span>
        </div>

        {/* All Years Button */}
        <button
          className={`timeline-pill ${!selectedYear ? 'active' : ''}`}
          onClick={() => onSelectYear(null)}
          title="Show all years"
        >
          <span>All</span>
          <span className="timeline-pill-count">{totalPhotos.toLocaleString()}</span>
        </button>

        {/* Individual Years */}
        {timelineYears.map((item) => {
          const isActive = selectedYear === item.year;
          return (
            <button
              key={item.year}
              className={`timeline-pill ${isActive ? 'active' : ''}`}
              onClick={() => onSelectYear(isActive ? null : item.year)}
              title={`${item.count.toLocaleString()} photos in ${item.year}`}
            >
              <span>{item.year}</span>
              <span className="timeline-pill-count">{item.count.toLocaleString()}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
