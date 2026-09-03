import React from 'react';
import { Search, Sparkles, X, Compass, Calendar, Folder, User, Eye, AlertCircle, ShieldCheck } from 'lucide-react';

const SUGGESTED_PROMPTS = [
  'Photos of Dobby at the beach',
  'Dobby playing in the grass',
  'Sunset over the ocean summer 2024',
  'Birthday party with cake',
  'Mountain hiking trip',
  'Snowy winter trees',
  'Screenshots from last year'
];

export default function SemanticSearch({ query, setQuery, onSearch, isLoading, parsedQuery }) {
  const handleSubmit = (e) => {
    e.preventDefault();
    onSearch(query);
  };

  const handleChipClick = (prompt) => {
    setQuery(prompt);
    onSearch(prompt);
  };

  const handleClear = () => {
    setQuery('');
    onSearch('');
  };

  const hasFacets = parsedQuery && query && (
    parsedQuery.visual_prompt ||
    (parsedQuery.entities && parsedQuery.entities.length > 0) ||
    (parsedQuery.folder_keywords && parsedQuery.folder_keywords.length > 0) ||
    parsedQuery.date_label ||
    parsedQuery.classification
  );

  return (
    <div className="search-hero">
      <div className="search-box-wrapper">
        <form onSubmit={handleSubmit} className="search-box">
          <Search size={20} color="#6366f1" style={{ flexShrink: 0 }} />
          <input
            type="text"
            className="search-input"
            placeholder="Ask naturally (e.g., 'photos of dobby at the beach', 'sunset summer 2024', 'screenshots last year')..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              type="button"
              onClick={handleClear}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center'
              }}
            >
              <X size={18} />
            </button>
          )}
          <div className="search-ai-tag">
            <Sparkles size={13} />
            <span>Hybrid NL Search</span>
          </div>
        </form>
      </div>

      {/* Smart Query Interpretation Facets */}
      {hasFacets && (
        <div className="search-facets-bar">
          {parsedQuery.visual_prompt && (
            <span className="facet-pill facet-pill-visual" title="Visual concept searched by CLIP model">
              <Eye size={12} />
              <span>Scene: "{parsedQuery.visual_prompt}"</span>
            </span>
          )}

          {parsedQuery.entities && parsedQuery.entities.map((ent, i) => (
            <span key={i} className="facet-pill facet-pill-entity" title={`Identified subject: ${ent.type}`}>
              <User size={12} />
              <span>{ent.name} ({ent.type})</span>
            </span>
          ))}

          {parsedQuery.folder_keywords && parsedQuery.folder_keywords.map((kw, i) => (
            <span key={i} className="facet-pill facet-pill-folder" title="Matched album / folder">
              <Folder size={12} />
              <span>Folder: {kw}</span>
            </span>
          ))}

          {parsedQuery.date_label && (
            <span className="facet-pill facet-pill-date" title="Parsed EXIF date filter">
              <Calendar size={12} />
              <span>Date: {parsedQuery.date_label}</span>
            </span>
          )}

          {parsedQuery.classification && (
            <span className="facet-pill facet-pill-filter" title="Classification target">
              <ShieldCheck size={12} />
              <span>
                {parsedQuery.classification === 'SCREENSHOT'
                  ? 'Screenshots'
                  : parsedQuery.classification === 'ALL'
                  ? 'All Media'
                  : 'Real Photos Only'}
              </span>
            </span>
          )}
        </div>
      )}

      {/* Fallback / Date Relaxation Banner */}
      {parsedQuery?.fallback_applied && parsedQuery?.fallback_message && (
        <div className="search-fallback-banner">
          <AlertCircle size={17} color="#f59e0b" style={{ flexShrink: 0 }} />
          <span>{parsedQuery.fallback_message}</span>
        </div>
      )}

      {/* Suggested Quick Prompts */}
      <div className="quick-prompts">
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#64748b', fontSize: '0.75rem', marginRight: '4px' }}>
          <Compass size={13} />
          <span>Try:</span>
        </div>
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="prompt-chip"
            onClick={() => handleChipClick(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
