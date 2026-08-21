import React from 'react';
import { Search, Sparkles, X, Compass } from 'lucide-react';

const SUGGESTED_PROMPTS = [
  'Sunset over the ocean',
  'Dog or pet portrait',
  'Birthday cake with candles',
  'Mountain landscape',
  'Snowy winter trees',
  'Night city skyline',
  'Delicious restaurant food',
  'Vintage car on the road'
];

export default function SemanticSearch({ query, setQuery, onSearch, isLoading }) {
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

  return (
    <div className="search-hero">
      <div className="search-box-wrapper">
        <form onSubmit={handleSubmit} className="search-box">
          <Search size={20} color="#6366f1" style={{ flexShrink: 0 }} />
          <input
            type="text"
            className="search-input"
            placeholder="Search photos semantically (e.g., 'sunset on the beach', 'happy dog in grass', 'birthday party')..."
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
            <span>CLIP 512D</span>
          </div>
        </form>
      </div>

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
