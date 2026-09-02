import React from 'react';
import { Trash2, X, CheckSquare, Square, Layers, Sparkles } from 'lucide-react';

export default function TrashSelectionBar({
  selectedCount = 0,
  totalVisible = 0,
  onSelectAll,
  onDeselectAll,
  onOpenConfirm,
  onCancel,
  totalBytes = 0
}) {
  const allSelected = selectedCount > 0 && selectedCount === totalVisible;

  const formattedSize = totalBytes > 0
    ? (totalBytes > 1024 * 1024 * 1024
        ? ` (${(totalBytes / (1024 * 1024 * 1024)).toFixed(2)} GB)`
        : ` (${(totalBytes / (1024 * 1024)).toFixed(1)} MB)`)
    : '';

  return (
    <div className="trash-selection-bar">
      <div className="trash-selection-bar-content">
        {/* Left: Info */}
        <div className="trash-selection-info">
          <div className="trash-selection-count-pill">
            <Trash2 size={16} color="#f87171" />
            <span>
              <strong>{selectedCount.toLocaleString()}</strong> selected{formattedSize}
            </span>
          </div>
          <span className="trash-selection-hint">
            Click photos to mark / unmark
          </span>
        </div>

        {/* Center / Right: Actions */}
        <div className="trash-selection-actions">
          <button
            type="button"
            className="btn-select-toggle"
            onClick={allSelected ? onDeselectAll : onSelectAll}
            title={allSelected ? 'Deselect all visible photos' : 'Select all visible photos'}
          >
            {allSelected ? (
              <>
                <Square size={14} />
                <span>Deselect All</span>
              </>
            ) : (
              <>
                <CheckSquare size={14} />
                <span>Select All ({totalVisible})</span>
              </>
            )}
          </button>

          <button
            type="button"
            className="btn-trash-delete-all"
            onClick={onOpenConfirm}
            disabled={selectedCount === 0}
            title="Confirm moving all selected photos to trash"
          >
            <Trash2 size={16} />
            <span>Delete All / Move to Trash</span>
          </button>

          <button
            type="button"
            className="btn-trash-cancel"
            onClick={onCancel}
            title="Cancel selection mode (Esc)"
          >
            <X size={16} />
            <span>Cancel</span>
          </button>
        </div>
      </div>
    </div>
  );
}
