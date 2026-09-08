import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  User,
  Heart,
  Check,
  X,
  Plus,
  Edit2,
  Trash2,
  Tag,
  Sparkles,
  AlertCircle,
  Camera,
  UserMinus
} from 'lucide-react';
import {
  fetchPhotoBoxes,
  createPhotoBox,
  updatePhotoBox,
  deletePhotoBox,
  confirmBox,
  rejectBox,
  fetchEntities,
  setEntityAvatar,
  unlinkBox
} from '../api';

export default function BoundingBoxOverlay({
  photoId,
  imageRef,
  containerRef,
  onBoxesUpdated,
  isDrawMode = false,
  setIsDrawMode,
  selectedBoxId: externalSelectedBoxId,
  onSelectBox
}) {
  const [boxes, setBoxes] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [internalSelectedBoxId, setInternalSelectedBoxId] = useState(null);
  const selectedBoxId = externalSelectedBoxId !== undefined ? externalSelectedBoxId : internalSelectedBoxId;
  const setSelectedBoxId = useCallback((id) => {
    setInternalSelectedBoxId(id);
    onSelectBox?.(id);
  }, [onSelectBox]);
  const [hoveredBoxId, setHoveredBoxId] = useState(null);
  
  // Tagging popover state
  const [editingBoxId, setEditingBoxId] = useState(null);
  const [inputName, setInputName] = useState('');
  const [selectedType, setSelectedType] = useState('PERSON');
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // Drawing manual bounding box state
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState(null);
  const [currentDraw, setCurrentDraw] = useState(null);

  // Resizing and moving bounding box state
  const [resizingBox, setResizingBox] = useState(null);
  const [movingBox, setMovingBox] = useState(null);

  // Image layout calculation state
  const [imgLayout, setImgLayout] = useState({ left: 0, top: 0, width: 0, height: 0 });

  // Update layout of the rendered image within container
  const updateImageLayout = useCallback(() => {
    if (!imageRef?.current || !containerRef?.current) return;
    const img = imageRef.current;
    const container = containerRef.current;

    const imgRect = img.getBoundingClientRect();
    const contRect = container.getBoundingClientRect();

    setImgLayout({
      left: imgRect.left - contRect.left,
      top: imgRect.top - contRect.top,
      width: imgRect.width,
      height: imgRect.height
    });
  }, [imageRef, containerRef]);

  useEffect(() => {
    updateImageLayout();
    window.addEventListener('resize', updateImageLayout);
    return () => window.removeEventListener('resize', updateImageLayout);
  }, [updateImageLayout]);

  const onBoxesUpdatedRef = useRef(onBoxesUpdated);
  useEffect(() => {
    onBoxesUpdatedRef.current = onBoxesUpdated;
  }, [onBoxesUpdated]);

  // Keep parent notified whenever boxes update
  useEffect(() => {
    onBoxesUpdatedRef.current?.(boxes);
  }, [boxes]);

  // Load boxes and existing entities
  const loadData = useCallback(() => {
    if (!photoId) return;
    setLoading(true);
    Promise.all([fetchPhotoBoxes(photoId), fetchEntities()])
      .then(([boxesRes, entitiesRes]) => {
        setBoxes(boxesRes.boxes || []);
        setEntities(entitiesRes || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load boxes:', err);
        setLoading(false);
      });
  }, [photoId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle Box Confirm / Reject
  const handleConfirm = async (boxId, e) => {
    e?.stopPropagation();
    try {
      await confirmBox(boxId);
      setBoxes((prev) =>
        prev.map((b) => (b.id === boxId ? { ...b, status: 'CONFIRMED' } : b))
      );
      setEditingBoxId(null);
      if (onBoxesUpdated) onBoxesUpdated();
    } catch (err) {
      alert('Error confirming tag: ' + err.message);
    }
  };

  const handleReject = async (boxId, e) => {
    e?.stopPropagation();
    try {
      await rejectBox(boxId);
      setBoxes((prev) => prev.filter((b) => b.id !== boxId));
      if (selectedBoxId === boxId) setSelectedBoxId(null);
      if (editingBoxId === boxId) setEditingBoxId(null);
      if (onBoxesUpdated) onBoxesUpdated();
    } catch (err) {
      alert('Error rejecting tag: ' + err.message);
    }
  };

  const handleDelete = async (boxId, e) => {
    e?.stopPropagation();
    try {
      await deletePhotoBox(photoId, boxId);
      setBoxes((prev) => prev.filter((b) => b.id !== boxId));
      if (selectedBoxId === boxId) setSelectedBoxId(null);
      if (editingBoxId === boxId) setEditingBoxId(null);
      if (onBoxesUpdated) onBoxesUpdated();
    } catch (err) {
      alert('Error deleting box: ' + err.message);
    }
  };

  const handleUnlink = async (boxId, e) => {
    e?.stopPropagation();
    try {
      await unlinkBox(boxId);
      setBoxes((prev) =>
        prev.map((b) =>
          b.id === boxId
            ? { ...b, entity_id: null, entity_name: null, status: 'UNASSIGNED', match_confidence: 0 }
            : b
        )
      );
      if (selectedBoxId === boxId) setSelectedBoxId(null);
      if (editingBoxId === boxId) setEditingBoxId(null);
      if (onBoxesUpdated) onBoxesUpdated();
    } catch (err) {
      alert('Error unlinking tag: ' + err.message);
    }
  };

  // Save Name / Entity
  const handleSaveTag = async (boxId) => {
    if (!inputName.trim()) return;
    try {
      setIsSaving(true);
      await updatePhotoBox(photoId, boxId, {
        entity_name: inputName.trim(),
        entity_type: selectedType,
        status: 'CONFIRMED'
      });
      loadData();
      setEditingBoxId(null);
      setInputName('');
    } catch (err) {
      alert('Failed to save tag: ' + err.message);
    } finally {
      setIsSaving(false);
    }
  };

  // Start Resizing Bounding Box
  const handleResizeStart = (e, box, corner) => {
    e.stopPropagation();
    e.preventDefault();
    if (!imageRef?.current) return;
    const imgRect = imageRef.current.getBoundingClientRect();
    const relX = (e.clientX - imgRect.left) / imgRect.width;
    const relY = (e.clientY - imgRect.top) / imgRect.height;
    setResizingBox({
      boxId: box.id,
      corner,
      origBox: { ...box },
      startRelX: relX,
      startRelY: relY
    });
  };

  // Helper to find all boxes containing relative coordinate (relX, relY) sorted by smallest area first
  const getBoxesAtPoint = useCallback((relX, relY) => {
    return boxes
      .filter((b) => relX >= b.x_min && relX <= b.x_max && relY >= b.y_min && relY <= b.y_max)
      .sort((a, b) => {
        const areaA = (a.x_max - a.x_min) * (a.y_max - a.y_min);
        const areaB = (b.x_max - b.x_min) * (b.y_max - b.y_min);
        return areaA - areaB;
      });
  }, [boxes]);

  // Start Moving Bounding Box / Selection
  const handleBoxMouseDown = (e, box) => {
    if (e.target.closest('.box-popover') || e.target.closest('.box-action-btn') || e.target.closest('.box-resize-handle')) return;
    e.stopPropagation();

    if (!imageRef?.current) return;
    const imgRect = imageRef.current.getBoundingClientRect();
    const relX = (e.clientX - imgRect.left) / imgRect.width;
    const relY = (e.clientY - imgRect.top) / imgRect.height;

    // Check for overlapping boxes under the mouse click
    const hitBoxes = getBoxesAtPoint(relX, relY);

    // If clicking an already selected box and there are other overlapping boxes at this coordinate,
    // cycle selection to the next overlapping box!
    if (hitBoxes.length > 1 && selectedBoxId === box.id) {
      const currentIndex = hitBoxes.findIndex((b) => b.id === selectedBoxId);
      const nextBox = hitBoxes[(currentIndex + 1) % hitBoxes.length];
      setSelectedBoxId(nextBox.id);
      if (!nextBox.entity_name) {
        setEditingBoxId(nextBox.id);
        setInputName('');
        setShowSuggestions(true);
      } else {
        setEditingBoxId(null);
      }
      return;
    }

    setSelectedBoxId(box.id);
    if (!box.entity_name) {
      setEditingBoxId(box.id);
      setInputName('');
      setShowSuggestions(true);
    }

    setMovingBox({
      boxId: box.id,
      origBox: { ...box },
      startRelX: relX,
      startRelY: relY
    });
  };

  // Create standard box in center
  const handleCreateCenterBox = async () => {
    try {
      const res = await createPhotoBox(photoId, {
        x_min: 0.35,
        y_min: 0.25,
        x_max: 0.65,
        y_max: 0.55,
        box_type: 'FACE',
        label: 'person'
      });
      const newBox = res.box;
      setBoxes((prev) => [...prev, newBox]);
      setSelectedBoxId(newBox.id);
      setEditingBoxId(newBox.id);
      setInputName('');
      if (setIsDrawMode) setIsDrawMode(false);
      if (onBoxesUpdated) onBoxesUpdated();
    } catch (err) {
      alert('Failed to place box: ' + err.message);
    }
  };

  // Start Drawing Manual Bounding Box
  const handleMouseDown = (e) => {
    // Only trigger if clicking on background container or image (not on existing box popover or resize handle)
    if (e.target.closest('.box-popover') || e.target.closest('.box-action-btn') || e.target.closest('.box-resize-handle')) return;
    if (!imageRef?.current || !containerRef?.current) return;

    const contRect = containerRef.current.getBoundingClientRect();
    const imgRect = imageRef.current.getBoundingClientRect();

    const mouseX = e.clientX;
    const mouseY = e.clientY;

    // Must be inside image
    if (
      mouseX < imgRect.left ||
      mouseX > imgRect.right ||
      mouseY < imgRect.top ||
      mouseY > imgRect.bottom
    ) {
      return;
    }

    const relX = (mouseX - imgRect.left) / imgRect.width;
    const relY = (mouseY - imgRect.top) / imgRect.height;

    setIsDrawing(true);
    setDrawStart({ x: relX, y: relY });
    setCurrentDraw({ x1: relX, y1: relY, x2: relX, y2: relY });
  };

  const handleMouseMove = (e) => {
    if (!imageRef?.current) return;
    const imgRect = imageRef.current.getBoundingClientRect();

    // 1. Resizing active
    if (resizingBox) {
      const relX = (e.clientX - imgRect.left) / imgRect.width;
      const relY = (e.clientY - imgRect.top) / imgRect.height;
      const dx = relX - resizingBox.startRelX;
      const dy = relY - resizingBox.startRelY;
      const { origBox, corner, boxId } = resizingBox;

      setBoxes((prev) =>
        prev.map((b) => {
          if (b.id !== boxId) return b;
          let x_min = origBox.x_min;
          let y_min = origBox.y_min;
          let x_max = origBox.x_max;
          let y_max = origBox.y_max;

          if (corner === 'se') {
            x_max = Math.max(x_min + 0.03, Math.min(1.0, origBox.x_max + dx));
            y_max = Math.max(y_min + 0.03, Math.min(1.0, origBox.y_max + dy));
          } else if (corner === 'sw') {
            x_min = Math.min(x_max - 0.03, Math.max(0.0, origBox.x_min + dx));
            y_max = Math.max(y_min + 0.03, Math.min(1.0, origBox.y_max + dy));
          } else if (corner === 'ne') {
            x_max = Math.max(x_min + 0.03, Math.min(1.0, origBox.x_max + dx));
            y_min = Math.min(y_max - 0.03, Math.max(0.0, origBox.y_min + dy));
          } else if (corner === 'nw') {
            x_min = Math.min(x_max - 0.03, Math.max(0.0, origBox.x_min + dx));
            y_min = Math.min(y_max - 0.03, Math.max(0.0, origBox.y_min + dy));
          }
          return { ...b, x_min, y_min, x_max, y_max };
        })
      );
      return;
    }

    // 2. Moving active
    if (movingBox) {
      const relX = (e.clientX - imgRect.left) / imgRect.width;
      const relY = (e.clientY - imgRect.top) / imgRect.height;
      const dx = relX - movingBox.startRelX;
      const dy = relY - movingBox.startRelY;
      const { origBox, boxId } = movingBox;
      const bw = origBox.x_max - origBox.x_min;
      const bh = origBox.y_max - origBox.y_min;

      let newX1 = Math.max(0.0, Math.min(1.0 - bw, origBox.x_min + dx));
      let newY1 = Math.max(0.0, Math.min(1.0 - bh, origBox.y_min + dy));
      let newX2 = newX1 + bw;
      let newY2 = newY1 + bh;

      setBoxes((prev) =>
        prev.map((b) => (b.id === boxId ? { ...b, x_min: newX1, y_min: newY1, x_max: newX2, y_max: newY2 } : b))
      );
      return;
    }

    // 3. Drawing active
    if (!isDrawing || !drawStart) return;

    const mouseX = Math.max(imgRect.left, Math.min(imgRect.right, e.clientX));
    const mouseY = Math.max(imgRect.top, Math.min(imgRect.bottom, e.clientY));

    const relX = (mouseX - imgRect.left) / imgRect.width;
    const relY = (mouseY - imgRect.top) / imgRect.height;

    setCurrentDraw({
      x1: Math.min(drawStart.x, relX),
      y1: Math.min(drawStart.y, relY),
      x2: Math.max(drawStart.x, relX),
      y2: Math.max(drawStart.y, relY)
    });
  };

  const handleMouseUp = async () => {
    // 1. Save resized box if resizing
    if (resizingBox) {
      const currentBox = boxes.find((b) => b.id === resizingBox.boxId);
      if (currentBox) {
        updatePhotoBox(photoId, currentBox.id, {
          x_min: currentBox.x_min,
          y_min: currentBox.y_min,
          x_max: currentBox.x_max,
          y_max: currentBox.y_max
        }).catch((err) => console.error('Failed to save resized box:', err));
        if (onBoxesUpdated) onBoxesUpdated();
      }
      setResizingBox(null);
      return;
    }

    // 2. Save moved box if moving
    if (movingBox) {
      const currentBox = boxes.find((b) => b.id === movingBox.boxId);
      if (currentBox) {
        updatePhotoBox(photoId, currentBox.id, {
          x_min: currentBox.x_min,
          y_min: currentBox.y_min,
          x_max: currentBox.x_max,
          y_max: currentBox.y_max
        }).catch((err) => console.error('Failed to save moved box:', err));
        if (onBoxesUpdated) onBoxesUpdated();
      }
      setMovingBox(null);
      return;
    }

    // 3. Save manual drawn box
    if (!isDrawing || !currentDraw) {
      setIsDrawing(false);
      return;
    }
    setIsDrawing(false);

    const width = currentDraw.x2 - currentDraw.x1;
    const height = currentDraw.y2 - currentDraw.y1;

    // Minimum size check (at least 2% of dimension)
    if (width > 0.02 && height > 0.02) {
      try {
        const res = await createPhotoBox(photoId, {
          x_min: currentDraw.x1,
          y_min: currentDraw.y1,
          x_max: currentDraw.x2,
          y_max: currentDraw.y2,
          box_type: 'FACE',
          label: 'person'
        });
        const newBox = res.box;
        setBoxes((prev) => [...prev, newBox]);
        setSelectedBoxId(newBox.id);
        setEditingBoxId(newBox.id);
        setInputName('');
        if (setIsDrawMode) setIsDrawMode(false);
        if (onBoxesUpdated) onBoxesUpdated();
      } catch (err) {
        console.error('Failed to create manual box:', err);
      }
    }
    setCurrentDraw(null);
    setDrawStart(null);
  };

  if (!imgLayout.width || !imgLayout.height) return null;

  return (
    <div
      className="bounding-box-layer"
      style={{
        position: 'absolute',
        left: `${imgLayout.left}px`,
        top: `${imgLayout.top}px`,
        width: `${imgLayout.width}px`,
        height: `${imgLayout.height}px`,
        pointerEvents: 'all',
        userSelect: 'none',
        cursor: isDrawMode ? 'crosshair' : 'default'
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      {/* Draw Mode Active Floating Banner */}
      {isDrawMode && (
        <div
          style={{
            position: 'absolute',
            top: '12px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 90,
            background: 'rgba(15, 23, 42, 0.92)',
            border: '1px solid #38bdf8',
            borderRadius: '30px',
            padding: '6px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            color: '#ffffff',
            fontSize: '0.82rem',
            boxShadow: '0 8px 30px rgba(0,0,0,0.6)',
            backdropFilter: 'blur(12px)',
            pointerEvents: 'all'
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <Edit2 size={13} color="#38bdf8" />
          <span>Click & drag across any face to create a tag</span>
          <button
            type="button"
            className="btn-secondary"
            style={{ padding: '2px 8px', fontSize: '0.72rem', background: 'rgba(56, 189, 248, 0.2)', borderColor: '#38bdf8', color: '#ffffff' }}
            onClick={handleCreateCenterBox}
            title="Place a standard bounding box in center to position manually"
          >
            + Place Box
          </button>
          <button
            type="button"
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', padding: 0 }}
            onClick={() => setIsDrawMode && setIsDrawMode(false)}
            title="Cancel Draw Mode"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {/* Existing Detected Boxes (sorted by area descending so smaller boxes naturally stack on top) */}
      {[...boxes]
        .sort((a, b) => {
          const areaA = (a.x_max - a.x_min) * (a.y_max - a.y_min);
          const areaB = (b.x_max - b.x_min) * (b.y_max - b.y_min);
          return areaB - areaA;
        })
        .map((box) => {
          const x = box.x_min * imgLayout.width;
          const y = box.y_min * imgLayout.height;
          const w = (box.x_max - box.x_min) * imgLayout.width;
          const h = (box.y_max - box.y_min) * imgLayout.height;

          const area = (box.x_max - box.x_min) * (box.y_max - box.y_min);
          // Smaller boxes have higher baseZ (e.g. 45 vs 25) so they float on top
          const baseZ = Math.min(48, 20 + Math.round((1 - Math.min(1, area)) * 25));

          const isSelected = selectedBoxId === box.id;
          const isHovered = hoveredBoxId === box.id;
          const isEditing = editingBoxId === box.id;
          const isPending = box.status === 'PENDING_REVIEW';
          const isConfirmed = box.status === 'CONFIRMED';
          const isPet = box.box_type === 'PET' || box.entity_type === 'PET';

          // Box body elevation: selected gets small elevation (+5), keeping smaller inner boxes above it
          const boxZ = baseZ + (isSelected ? 5 : isHovered ? 2 : 0);

          // Find any unassigned face box inside this box
          const innerUnassignedBoxes = boxes.filter((b) => {
            if (b.id === box.id || b.entity_name || b.status !== 'UNASSIGNED') return false;
            const cx = (b.x_min + b.x_max) / 2;
            const cy = (b.y_min + b.y_max) / 2;
            return (
              cx >= box.x_min - 0.02 &&
              cx <= box.x_max + 0.02 &&
              cy >= box.y_min - 0.02 &&
              cy <= box.y_max + 0.02
            );
          });

          // Color coding
          let borderColor = 'rgba(99, 102, 241, 0.6)'; // Indigo for unassigned
          let bgColor = 'rgba(99, 102, 241, 0.12)';
          if (isConfirmed) {
            borderColor = 'rgba(16, 185, 129, 0.85)'; // Emerald
            bgColor = 'rgba(16, 185, 129, 0.12)';
          } else if (isPending) {
            borderColor = 'rgba(245, 158, 11, 0.9)'; // Amber gold for pending strong match
            bgColor = 'rgba(245, 158, 11, 0.15)';
          }

          if (isSelected || isHovered) {
            borderColor = isPending ? '#fbbf24' : isConfirmed ? '#34d399' : '#818cf8';
          }

          const matchPercent = box.match_confidence
            ? Math.round(box.match_confidence * 100)
            : null;

          return (
            <div
              key={box.id}
              className={`bounding-box-rect ${isPending ? 'pending-glow' : ''} ${isSelected ? 'selected' : ''}`}
              style={{
                position: 'absolute',
                left: `${x}px`,
                top: `${y}px`,
                width: `${w}px`,
                height: `${h}px`,
                border: `2px solid ${borderColor}`,
                borderRadius: '6px',
                backgroundColor: isHovered || isSelected ? bgColor : 'transparent',
                transition: resizingBox || movingBox ? 'none' : 'all 0.15s ease',
                cursor: isDrawMode ? 'crosshair' : 'move',
                zIndex: boxZ
              }}
              onMouseDown={(e) => handleBoxMouseDown(e, box)}
              onClick={(e) => {
                e.stopPropagation();
                setSelectedBoxId(box.id);
                if (!box.entity_name) {
                  setEditingBoxId(box.id);
                  setInputName('');
                  setShowSuggestions(true);
                }
              }}
              onMouseEnter={() => setHoveredBoxId(box.id)}
              onMouseLeave={() => setHoveredBoxId(null)}
            >
              {/* Tag Badge on top of box */}
              <div
                className="box-badge-label"
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedBoxId(box.id);
                  if (!box.entity_name) {
                    setEditingBoxId(box.id);
                    setInputName('');
                    setShowSuggestions(true);
                  }
                }}
                style={{
                  position: 'absolute',
                  top: '-24px',
                  left: '-1px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '2px 8px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  borderRadius: '4px 4px 0 0',
                  backgroundColor: isConfirmed ? '#065f46' : isPending ? '#78350f' : '#312e81',
                  color: '#ffffff',
                  border: `1px solid ${borderColor}`,
                  borderBottom: 'none',
                  whiteSpace: 'nowrap',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
                  cursor: 'pointer',
                  pointerEvents: 'all',
                  zIndex: isSelected ? 88 : 82
                }}
              >
                {isPet ? <Heart size={11} color="#f472b6" /> : <User size={11} color="#67e8f9" />}
                <span>{box.entity_name || (box.label === 'person' ? 'Unnamed Face' : box.label || 'Detect')}</span>
                {isPending && matchPercent && (
                  <span style={{ color: '#fde68a', fontSize: '0.68rem', marginLeft: '2px' }}>
                    ({matchPercent}%)
                  </span>
                )}
              </div>

            {/* Corner Resize Handles */}
            {(isSelected || isHovered) && (
              <>
                <div
                  className="box-resize-handle nw"
                  style={{
                    position: 'absolute',
                    top: '-5px',
                    left: '-5px',
                    width: '10px',
                    height: '10px',
                    background: '#ffffff',
                    border: '2px solid #6366f1',
                    borderRadius: '2px',
                    cursor: 'nwse-resize',
                    zIndex: 80
                  }}
                  onMouseDown={(e) => handleResizeStart(e, box, 'nw')}
                  title="Drag to resize"
                />
                <div
                  className="box-resize-handle ne"
                  style={{
                    position: 'absolute',
                    top: '-5px',
                    right: '-5px',
                    width: '10px',
                    height: '10px',
                    background: '#ffffff',
                    border: '2px solid #6366f1',
                    borderRadius: '2px',
                    cursor: 'nesw-resize',
                    zIndex: 80
                  }}
                  onMouseDown={(e) => handleResizeStart(e, box, 'ne')}
                  title="Drag to resize"
                />
                <div
                  className="box-resize-handle sw"
                  style={{
                    position: 'absolute',
                    bottom: '-5px',
                    left: '-5px',
                    width: '10px',
                    height: '10px',
                    background: '#ffffff',
                    border: '2px solid #6366f1',
                    borderRadius: '2px',
                    cursor: 'nesw-resize',
                    zIndex: 80
                  }}
                  onMouseDown={(e) => handleResizeStart(e, box, 'sw')}
                  title="Drag to resize"
                />
                <div
                  className="box-resize-handle se"
                  style={{
                    position: 'absolute',
                    bottom: '-5px',
                    right: '-5px',
                    width: '10px',
                    height: '10px',
                    background: '#ffffff',
                    border: '2px solid #6366f1',
                    borderRadius: '2px',
                    cursor: 'nwse-resize',
                    zIndex: 80
                  }}
                  onMouseDown={(e) => handleResizeStart(e, box, 'se')}
                  title="Drag to resize"
                />
              </>
            )}

            {/* Hover / Selection Interactive Popover */}
            {(isHovered || isSelected || isEditing) && (
              <div
                className="box-popover glass-card"
                style={{
                  position: 'absolute',
                  top: `${h + 6}px`,
                  left: '0',
                  minWidth: '220px',
                  zIndex: 100,
                  padding: '8px 10px',
                  borderRadius: '8px',
                  background: 'rgba(15, 23, 42, 0.95)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  backdropFilter: 'blur(12px)',
                  boxShadow: '0 10px 25px rgba(0,0,0,0.6)',
                  color: '#ffffff'
                }}
                onClick={(e) => e.stopPropagation()}
              >
                {/* 1. Pending Review State (Google-Grade Confirm/Reject) */}
                {isPending && !isEditing && (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                      <Sparkles size={14} color="#fbbf24" />
                      <span style={{ fontSize: '0.78rem', color: '#fde68a', fontWeight: 600 }}>
                        Strong Match: {matchPercent}%
                      </span>
                    </div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#ffffff', marginBottom: '8px' }}>
                      Tag as "{box.entity_name}"?
                    </div>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <button
                        className="btn-primary"
                        style={{ flex: 1, padding: '4px 8px', fontSize: '0.75rem', background: '#059669' }}
                        onClick={(e) => handleConfirm(box.id, e)}
                        title="Confirm this tag"
                      >
                        <Check size={13} />
                        <span>Confirm</span>
                      </button>
                      <button
                        className="btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.75rem', color: '#f87171' }}
                        onClick={(e) => handleReject(box.id, e)}
                        title="Not this person / pet"
                      >
                        <X size={13} />
                        <span>Not Them</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* 2. Confirmed State */}
                {isConfirmed && !isEditing && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Check size={14} color="#34d399" />
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#34d399' }}>
                        {box.entity_name}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {box.entity_id && (
                        <button
                          className="btn-secondary box-action-btn"
                          style={{ padding: '3px 6px', fontSize: '0.7rem', color: '#fbbf24' }}
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              await setEntityAvatar(box.entity_id, box.id);
                              alert(`Set this face as ${box.entity_name}'s profile photo!`);
                              if (onBoxesUpdated) onBoxesUpdated();
                            } catch (err) {
                              alert('Failed to set profile photo: ' + err.message);
                            }
                          }}
                          title={`Set this face as ${box.entity_name}'s profile picture`}
                        >
                          <Camera size={12} />
                        </button>
                      )}
                      <button
                        className="btn-secondary box-action-btn"
                        style={{ padding: '3px 6px', fontSize: '0.7rem' }}
                        onClick={() => {
                          setEditingBoxId(box.id);
                          setInputName(box.entity_name || '');
                          setSelectedType(box.entity_type || 'PERSON');
                          setShowSuggestions(false);
                        }}
                        title="Rename or change person"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        className="btn-secondary box-action-btn"
                        style={{ padding: '3px 6px', fontSize: '0.7rem', color: '#f87171' }}
                        onClick={(e) => handleUnlink(box.id, e)}
                        title="Remove tag (unlink name from face)"
                      >
                        <UserMinus size={12} />
                      </button>
                    </div>

                    {/* Redundant inner unassigned tag helper for named pet/person */}
                    {innerUnassignedBoxes.length > 0 && (
                      <div
                        style={{
                          marginTop: '8px',
                          paddingTop: '8px',
                          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px'
                        }}
                      >
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '5px' }}>
                          <Sparkles size={12} color="#f472b6" />
                          <span>Inner face tag detected inside {box.entity_name}</span>
                        </div>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            className="btn-secondary box-action-btn"
                            style={{
                              flex: 1,
                              padding: '3px 8px',
                              fontSize: '0.7rem',
                              color: '#38bdf8',
                              borderColor: 'rgba(56, 189, 248, 0.3)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '4px'
                            }}
                            onClick={async (e) => {
                              e.stopPropagation();
                              const faceBox = innerUnassignedBoxes[0];
                              try {
                                if (box.entity_id) {
                                  await setEntityAvatar(box.entity_id, faceBox.id);
                                }
                                await deletePhotoBox(photoId, faceBox.id);
                                setBoxes((prev) => prev.filter((b) => b.id !== faceBox.id));
                                if (onBoxesUpdated) onBoxesUpdated();
                              } catch (err) {
                                alert('Failed to set avatar: ' + err.message);
                              }
                            }}
                            title="Set inner face as profile photo and remove redundant tag"
                          >
                            <Camera size={11} />
                            <span>Use Face as Avatar</span>
                          </button>
                          <button
                            type="button"
                            className="btn-secondary box-action-btn"
                            style={{
                              padding: '3px 8px',
                              fontSize: '0.7rem',
                              color: '#f87171',
                              borderColor: 'rgba(248, 113, 113, 0.3)',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px'
                            }}
                            onClick={async (e) => {
                              e.stopPropagation();
                              try {
                                for (const fb of innerUnassignedBoxes) {
                                  await deletePhotoBox(photoId, fb.id);
                                }
                                setBoxes((prev) => prev.filter((b) => !innerUnassignedBoxes.some((ib) => ib.id === b.id)));
                                if (onBoxesUpdated) onBoxesUpdated();
                              } catch (err) {
                                alert('Failed to remove extra tag: ' + err.message);
                              }
                            }}
                            title="Remove redundant unassigned face tag since pet is already named"
                          >
                            <Trash2 size={11} />
                            <span>Dismiss Extra</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* 3. Unassigned / Editing Form */}
                {(!box.entity_name || isEditing) && (
                  <div>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '6px', fontWeight: 600 }}>
                      {box.entity_name ? 'Edit Person or Pet' : 'Name this Person or Pet'}
                    </div>

                    {/* Entity Type Toggle */}
                    <div style={{ display: 'flex', gap: '4px', marginBottom: '8px' }}>
                      <button
                        type="button"
                        className={`btn-secondary ${selectedType === 'PERSON' ? 'active-filter-btn' : ''}`}
                        style={{
                          flex: 1,
                          padding: '3px',
                          fontSize: '0.72rem',
                          background: selectedType === 'PERSON' ? 'rgba(99, 102, 241, 0.3)' : 'transparent',
                          borderColor: selectedType === 'PERSON' ? '#6366f1' : 'rgba(255,255,255,0.1)'
                        }}
                        onClick={() => setSelectedType('PERSON')}
                      >
                        <User size={12} />
                        <span>Person</span>
                      </button>
                      <button
                        type="button"
                        className={`btn-secondary ${selectedType === 'PET' ? 'active-filter-btn' : ''}`}
                        style={{
                          flex: 1,
                          padding: '3px',
                          fontSize: '0.72rem',
                          background: selectedType === 'PET' ? 'rgba(236, 72, 153, 0.3)' : 'transparent',
                          borderColor: selectedType === 'PET' ? '#ec4899' : 'rgba(255,255,255,0.1)'
                        }}
                        onClick={() => setSelectedType('PET')}
                      >
                        <Heart size={12} />
                        <span>Pet</span>
                      </button>
                    </div>

                    {/* Name Input with Autocomplete List */}
                    <div style={{ marginBottom: '6px' }}>
                      <input
                        type="text"
                        placeholder="Enter name (e.g. Emma, Buddy)..."
                        className="input-styled"
                        style={{ width: '100%', fontSize: '0.78rem', padding: '4px 8px' }}
                        value={inputName}
                        onChange={(e) => {
                          setInputName(e.target.value);
                          setShowSuggestions(true);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveTag(box.id);
                          if (e.key === 'Escape') setEditingBoxId(null);
                        }}
                        autoFocus
                      />
                    </div>

                    {/* Suggestions from existing entities - rendered in layout flow so it never covers action buttons */}
                    {showSuggestions && inputName.trim().length > 0 && entities.length > 0 && (() => {
                      const matched = entities
                        .filter((ent) =>
                          ent.name.toLowerCase().includes(inputName.trim().toLowerCase()) &&
                          ent.name.toLowerCase() !== inputName.trim().toLowerCase()
                        )
                        .slice(0, 4);
                      if (matched.length === 0) return null;
                      return (
                        <div
                          style={{
                            background: 'rgba(30, 41, 59, 0.95)',
                            border: '1px solid rgba(255,255,255,0.15)',
                            borderRadius: '6px',
                            maxHeight: '110px',
                            overflowY: 'auto',
                            marginBottom: '6px',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.3)'
                          }}
                        >
                          {matched.map((ent) => (
                            <div
                              key={ent.id}
                              style={{
                                padding: '5px 8px',
                                fontSize: '0.75rem',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                borderBottom: '1px solid rgba(255,255,255,0.05)'
                              }}
                              className="suggestion-item"
                              onClick={() => {
                                setInputName(ent.name);
                                setSelectedType(ent.entity_type || 'PERSON');
                                setShowSuggestions(false);
                              }}
                            >
                              <span style={{ fontWeight: 500, color: '#f8fafc' }}>{ent.name}</span>
                              <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>
                                {ent.entity_type}
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    })()}

                    {/* Action buttons */}
                    <div style={{ display: 'flex', gap: '6px', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                      <button
                        type="button"
                        className="btn-secondary box-action-btn"
                        style={{ padding: '3px 8px', fontSize: '0.72rem', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                        onClick={(e) => handleDelete(box.id, e)}
                        title="Delete this bounding box"
                      >
                        <Trash2 size={12} />
                        <span>Delete</span>
                      </button>

                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '3px 8px', fontSize: '0.72rem' }}
                          onClick={() => setEditingBoxId(null)}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="btn-primary"
                          style={{ padding: '3px 10px', fontSize: '0.72rem' }}
                          onClick={() => handleSaveTag(box.id)}
                          disabled={isSaving || !inputName.trim()}
                        >
                          {isSaving ? 'Saving...' : 'Save Tag'}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Manual Dragging Box Preview */}
      {isDrawing && currentDraw && (
        <div
          style={{
            position: 'absolute',
            left: `${currentDraw.x1 * imgLayout.width}px`,
            top: `${currentDraw.y1 * imgLayout.height}px`,
            width: `${(currentDraw.x2 - currentDraw.x1) * imgLayout.width}px`,
            height: `${(currentDraw.y2 - currentDraw.y1) * imgLayout.height}px`,
            border: '2px dashed #38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.15)',
            pointerEvents: 'none',
            zIndex: 60
          }}
        />
      )}
    </div>
  );
}
