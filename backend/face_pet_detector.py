"""
High-Precision People and Pets Detection, Visual Embedding, and Matching Engine for LuminaPhoto.
Combines YOLOv8 and OpenCV Cascade/DNN detection with CLIP multimodal embeddings (512-d).
Supports strict high-confidence auto-tagging and seamless human confirmation.
"""

import os
import io
import json
import threading
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image, ImageOps
import cv2
from ultralytics import YOLO

from backend.database import (
    get_connection,
    insert_detected_box,
    get_boxes_for_photo,
    delete_boxes_for_photo,
    get_confirmed_embeddings_for_entities,
    list_entities
)
from backend.vector_engine import VectorEngine

# Minimum embedding similarity required before a known identity is suggested.
STRICT_HIGH_CONFIDENCE_THRESHOLD = 0.85
# Minimum margin between top match and runner-up candidate to prevent ambiguous tagging
MIN_AMBIGUITY_MARGIN = 0.03

# PET class IDs from COCO (used by YOLOv8)
PET_CLASSES = {
    15: "cat",
    16: "dog",
    14: "bird",
    17: "horse",
    18: "sheep",
    19: "cow",
    21: "bear"
}

CROPS_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".lumina_cache", "crops")
os.makedirs(CROPS_CACHE_DIR, exist_ok=True)


class FacePetDetector:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self._yolo: Optional[YOLO] = None
        self._face_cascade: Optional[cv2.CascadeClassifier] = None
        self._profile_cascade: Optional[cv2.CascadeClassifier] = None
        self._yunet = None

    @classmethod
    def get_instance(cls) -> "FacePetDetector":
        with cls._lock:
            if cls._instance is None:
                cls._instance = FacePetDetector()
            return cls._instance

    @property
    def yolo(self) -> YOLO:
        if self._yolo is None:
            with self._lock:
                if self._yolo is None:
                    # Lightweight YOLOv8 nano model (fast CPU inference)
                    self._yolo = YOLO("yolov8n.pt")
        return self._yolo

    @property
    def yunet(self):
        if self._yunet is None:
            with self._lock:
                if self._yunet is None:
                    model_path = os.path.join(os.path.dirname(__file__), "face_detection_yunet_2023mar.onnx")
                    if not os.path.exists(model_path):
                        try:
                            import urllib.request
                            url = "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
                            urllib.request.urlretrieve(url, model_path)
                        except Exception as dl_err:
                            print(f"Could not auto-download YuNet ONNX: {dl_err}")
                    if os.path.exists(model_path):
                        self._yunet = cv2.FaceDetectorYN.create(
                            model=model_path,
                            config="",
                            input_size=(320, 320),
                            score_threshold=0.55,
                            nms_threshold=0.3,
                            top_k=5000
                        )
        return self._yunet

    @property
    def face_cascade(self) -> cv2.CascadeClassifier:
        if self._face_cascade is None:
            with self._lock:
                if self._face_cascade is None:
                    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                    self._face_cascade = cv2.CascadeClassifier(path)
        return self._face_cascade

    @property
    def profile_cascade(self) -> cv2.CascadeClassifier:
        if self._profile_cascade is None:
            with self._lock:
                if self._profile_cascade is None:
                    path = cv2.data.haarcascades + "haarcascade_profileface.xml"
                    self._profile_cascade = cv2.CascadeClassifier(path)
        return self._profile_cascade

    def detect_in_image(self, img_pil: Image.Image) -> List[Dict[str, Any]]:
        """
        Detects people (faces/persons) and pets in a PIL image.
        Returns a list of raw box dictionaries with normalized coordinates [0.0 - 1.0].
        """
        w, h = img_pil.size
        if w < 10 or h < 10:
            return []

        # Convert to RGB numpy array
        img_np = np.array(img_pil.convert("RGB"))
        boxes: List[Dict[str, Any]] = []

        # 1. Detect faces using deep-learning YuNet (handles hats, head tilts, profile angles, and lighting)
        if self.yunet is not None:
            try:
                scale = min(1.0, 1024.0 / max(w, h))
                nw, nh = max(32, int(w * scale)), max(32, int(h * scale))
                img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                small = cv2.resize(img_bgr, (nw, nh))
                self.yunet.setInputSize((nw, nh))
                _, faces = self.yunet.detect(small)
                if faces is not None:
                    for face in faces:
                        fx, fy, fw, fh, conf = float(face[0]), float(face[1]), float(face[2]), float(face[3]), float(face[-1])
                        if conf >= 0.55 and (fw / nw) >= 0.04 and (fh / nh) >= 0.04:
                            # Slight natural padding around face
                            pad_w = fw * 0.06
                            pad_h = fh * 0.06
                            x_min = max(0.0, (fx - pad_w) / nw)
                            y_min = max(0.0, (fy - pad_h) / nh)
                            x_max = min(1.0, (fx + fw + pad_w) / nw)
                            y_max = min(1.0, (fy + fh + pad_h) / nh)
                            boxes.append({
                                "box_type": "FACE",
                                "source": "yunet",
                                "label": "person",
                                "confidence": conf,
                                "x_min": x_min,
                                "y_min": y_min,
                                "x_max": x_max,
                                "y_max": y_max
                            })
            except Exception as e:
                print(f"YuNet detection error: {e}")

        # Fallback to Haar Cascades only if YuNet found nothing
        if len(boxes) == 0:
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(int(min(w, h) * 0.08), int(min(w, h) * 0.08))
            )
            for (fx, fy, fw, fh) in faces:
                if (fw / w) < 0.08 or (fh / h) < 0.08:
                    continue
                boxes.append({
                    "box_type": "FACE",
                    "source": "haar",
                    "label": "person",
                    "confidence": 0.90,
                    "x_min": max(0.0, float(fx) / w),
                    "y_min": max(0.0, float(fy) / h),
                    "x_max": min(1.0, float(fx + fw) / w),
                    "y_max": min(1.0, float(fy + fh) / h)
                })

        # 2. Run YOLOv8 for Person body and Pets
        try:
            results = self.yolo(img_np, verbose=False, conf=0.35)
            if results and len(results) > 0:
                det = results[0]
                for box in det.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                    
                    x1 = max(0.0, xyxy[0] / w)
                    y1 = max(0.0, xyxy[1] / h)
                    x2 = min(1.0, xyxy[2] / w)
                    y2 = min(1.0, xyxy[3] / h)
                    person_h = y2 - y1

                    if cls_id == 0:
                        # Only purge tiny Haar false-positives (< 8% of person height) inside this person box;
                        # NEVER purge deep-learning YuNet detections.
                        boxes = [
                            b for b in boxes
                            if not (
                                b.get("source") == "haar" and
                                b["box_type"] == "FACE" and
                                b["x_min"] >= x1 - 0.08 and b["x_max"] <= x2 + 0.08 and
                                b["y_min"] >= y1 - 0.25 and b["y_max"] <= y2 + 0.05 and
                                (b["y_max"] - b["y_min"]) < person_h * 0.08
                            )
                        ]

                        # Check if a valid face was detected in the upper body region of this person
                        has_face = any(
                            b["box_type"] == "FACE" and 
                            (x1 - 0.05) <= (b["x_min"] + b["x_max"]) / 2 <= (x2 + 0.05) and
                            (y1 - 0.15) <= (b["y_min"] + b["y_max"]) / 2 <= (y1 + person_h * 0.55)
                            for b in boxes
                        )
                        if not has_face:
                            # Frame upper head and face region of person as fallback
                            head_h = person_h * 0.35
                            head_y2 = min(1.0, y1 + head_h)
                            head_w = min(x2 - x1, person_h * 0.35)
                            center_x = (x1 + x2) / 2
                            head_x1 = max(0.0, center_x - head_w / 2)
                            head_x2 = min(1.0, center_x + head_w / 2)

                            boxes.append({
                                "box_type": "FACE",
                                "source": "yolo_fallback",
                                "label": "person",
                                "confidence": conf,
                                "x_min": head_x1,
                                "y_min": y1,
                                "x_max": head_x2,
                                "y_max": head_y2
                            })

                    elif cls_id in PET_CLASSES:
                        pet_name = PET_CLASSES[cls_id]
                        boxes.append({
                            "box_type": "PET",
                            "label": pet_name,
                            "confidence": conf,
                            "x_min": x1,
                            "y_min": y1,
                            "x_max": x2,
                            "y_max": y2
                        })
        except Exception as e:
            print(f"YOLO detection error: {e}")

        # Filter out false-positive human face detections that are located inside pet bounding boxes
        pet_boxes = [b for b in boxes if b.get("box_type") == "PET"]
        if pet_boxes:
            cleaned_boxes = []
            for b in boxes:
                if b.get("box_type") == "FACE" and b.get("label") == "person":
                    cx = (b["x_min"] + b["x_max"]) / 2
                    cy = (b["y_min"] + b["y_max"]) / 2
                    # Check if the face center falls within any detected pet box
                    is_inside_pet = any(
                        (pb["x_min"] - 0.02) <= cx <= (pb["x_max"] + 0.02) and
                        (pb["y_min"] - 0.02) <= cy <= (pb["y_max"] + 0.02)
                        for pb in pet_boxes
                    )
                    if is_inside_pet:
                        # Animal muzzle/eyes erroneously flagged as human face
                        continue
                cleaned_boxes.append(b)
            boxes = cleaned_boxes

        # Remove duplicate or heavily overlapping boxes (IoU suppression)
        filtered = self._non_max_suppression(boxes, iou_thresh=0.6)
        return filtered

    def _non_max_suppression(self, boxes: List[Dict[str, Any]], iou_thresh: float = 0.6) -> List[Dict[str, Any]]:
        """Removes duplicate detections with high intersection-over-union."""
        if len(boxes) <= 1:
            return boxes

        # Sort by confidence descending
        sorted_boxes = sorted(boxes, key=lambda b: b.get("confidence", 0.0), reverse=True)
        keep = []

        while sorted_boxes:
            current = sorted_boxes.pop(0)
            keep.append(current)
            remaining = []
            for b in sorted_boxes:
                iou = self._calculate_iou(current, b)
                if iou < iou_thresh:
                    remaining.append(b)
            sorted_boxes = remaining

        return keep

    @staticmethod
    def _calculate_iou(boxA: Dict[str, Any], boxB: Dict[str, Any]) -> float:
        xA = max(boxA["x_min"], boxB["x_min"])
        yA = max(boxA["y_min"], boxB["y_min"])
        xB = min(boxA["x_max"], boxB["x_max"])
        yB = min(boxA["y_max"], boxB["y_max"])

        interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
        if interArea == 0.0:
            return 0.0

        boxAArea = (boxA["x_max"] - boxA["x_min"]) * (boxA["y_max"] - boxA["y_min"])
        boxBArea = (boxB["x_max"] - boxB["x_min"]) * (boxB["y_max"] - boxB["y_min"])
        denom = boxAArea + boxBArea - interArea
        return interArea / denom if denom > 0 else 0.0

    def extract_crop_embedding(self, img_pil: Image.Image, box: Dict[str, Any]) -> Tuple[List[float], Image.Image]:
        """
        Crops the bounding box with tight padding for faces (6%) or natural padding (15%) for pets,
        and extracts normalized 512-d CLIP embedding.
        Returns (embedding_as_list, cropped_pil_image).
        """
        w, h = img_pil.size
        # Use tight 6% padding on FACE boxes to prevent bleeding into adjacent people;
        # 15% padding on PET / body boxes.
        bw = box["x_max"] - box["x_min"]
        bh = box["y_max"] - box["y_min"]
        pad_ratio = 0.06 if box.get("box_type") == "FACE" else 0.15
        pad_x = bw * pad_ratio
        pad_y = bh * pad_ratio

        x1 = max(0, int((box["x_min"] - pad_x) * w))
        y1 = max(0, int((box["y_min"] - pad_y) * h))
        x2 = min(w, int((box["x_max"] + pad_x) * w))
        y2 = min(h, int((box["y_max"] + pad_y) * h))

        if x2 <= x1 or y2 <= y1:
            crop = img_pil.resize((224, 224))
        else:
            crop = img_pil.crop((x1, y1, x2, y2))

        crop = crop.convert("RGB")
        # Resize crop for embedding model
        model = VectorEngine.get_instance().model
        raw_emb = model.encode(crop, convert_to_numpy=True, normalize_embeddings=True)
        norm_emb = raw_emb / np.linalg.norm(raw_emb)
        return norm_emb.tolist(), crop

    def rank_entity_candidates(
        self,
        query_embedding: List[float],
        entity_embeddings: Dict[int, List[List[float]]],
        threshold: float = STRICT_HIGH_CONFIDENCE_THRESHOLD,
        min_margin: float = MIN_AMBIGUITY_MARGIN
    ) -> List[Tuple[int, float]]:
        """
        Computes robust similarity scores for all entities against query embedding.
        Returns a single clear winner or up to three close candidates above threshold.
        """
        if not entity_embeddings:
            return []

        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        q_vec = q_vec / q_norm

        entity_scores: List[Tuple[int, float]] = []

        for eid, exemplars in entity_embeddings.items():
            if exemplars is None or len(exemplars) == 0:
                continue
            ex_mat = exemplars if isinstance(exemplars, np.ndarray) else np.array(exemplars, dtype=np.float32)
            sims = np.dot(ex_mat, q_vec)

            # Robust scoring: if >= 3 exemplars, average top 3 to prevent single-outlier false matches
            if len(sims) >= 3:
                top_k = np.sort(sims)[-3:]
                score = float(np.mean(top_k))
            else:
                score = float(np.max(sims))

            entity_scores.append((eid, score))

        if not entity_scores:
            return []

        entity_scores.sort(key=lambda x: x[1], reverse=True)

        valid = [(eid, round(score, 4)) for eid, score in entity_scores if score >= threshold]
        if len(valid) > 1 and valid[0][1] - valid[1][1] < min_margin:
            return valid[:3]
        return valid[:1]

    def match_against_entities(
        self,
        query_embedding: List[float],
        entity_embeddings: Dict[int, List[List[float]]],
        threshold: float = STRICT_HIGH_CONFIDENCE_THRESHOLD,
        min_margin: float = MIN_AMBIGUITY_MARGIN
    ) -> Tuple[Optional[int], float, str]:
        """
        Matches a query embedding against confirmed exemplar embeddings for all known entities.
        Matches >= threshold are suggested for human review, including ambiguous top matches.
        Returns: (matched_entity_id, highest_similarity, status)
        """
        candidates = self.rank_entity_candidates(
            query_embedding, entity_embeddings, threshold=threshold, min_margin=min_margin
        )
        if candidates:
            best_eid, best_sim = candidates[0]
            return best_eid, best_sim, "PENDING_REVIEW"

        # Compute raw top similarity for reporting if available
        if entity_embeddings:
            q_vec = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm > 0:
                q_vec = q_vec / q_norm
                raw_max = 0.0
                for exemplars in entity_embeddings.values():
                    if exemplars:
                        sims = np.dot(np.array(exemplars, dtype=np.float32), q_vec)
                        raw_max = max(raw_max, float(np.max(sims)))
                return None, round(max(0.0, raw_max), 4), "UNASSIGNED"

        return None, 0.0, "UNASSIGNED"

    def process_photo(
        self,
        photo_id: int,
        file_path: str,
        entity_embeddings: Optional[Dict[int, List[List[float]]]] = None,
        force_reprocess: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Detects boxes for a photo, extracts embeddings, matches against known entities
        with per-photo mutual exclusion (an entity can only be assigned to at most one box per photo),
        and saves records to the database.
        """
        if not force_reprocess:
            existing = get_boxes_for_photo(photo_id)
            if existing:
                return existing
        else:
            delete_boxes_for_photo(photo_id)

        if not os.path.exists(file_path):
            return []

        try:
            with Image.open(file_path) as img:
                img_oriented = ImageOps.exif_transpose(img)
                raw_boxes = self.detect_in_image(img_oriented)

                if entity_embeddings is None:
                    person_embeddings = get_confirmed_embeddings_for_entities(entity_type="PERSON")
                    pet_embeddings = get_confirmed_embeddings_for_entities(entity_type="PET")
                else:
                    person_embeddings = entity_embeddings
                    pet_embeddings = entity_embeddings

                extracted_data = []
                for b in raw_boxes:
                    emb, crop_pil = self.extract_crop_embedding(img_oriented, b)
                    target_embs = pet_embeddings if b.get("box_type") == "PET" else person_embeddings
                    candidates = self.rank_entity_candidates(
                        emb, target_embs, threshold=STRICT_HIGH_CONFIDENCE_THRESHOLD
                    )
                    top_sim = candidates[0][1] if candidates else 0.0
                    extracted_data.append({
                        "box": b,
                        "emb": emb,
                        "crop_pil": crop_pil,
                        "candidates": candidates,
                        "is_ambiguous": (
                            len(candidates) > 1 and
                            candidates[0][1] - candidates[1][1] < MIN_AMBIGUITY_MARGIN
                        ),
                        "top_sim": top_sim
                    })

                # Per-photo mutual exclusion: greedy 1-to-1 bipartite matching
                all_matches = []
                for idx, item in enumerate(extracted_data):
                    for eid, score in item["candidates"]:
                        all_matches.append((score, idx, eid))

                all_matches.sort(key=lambda x: x[0], reverse=True)
                assigned_entities = set()
                assigned_boxes = {}

                for score, idx, eid in all_matches:
                    if idx not in assigned_boxes and eid not in assigned_entities:
                        assigned_boxes[idx] = (eid, score, "PENDING_REVIEW")
                        assigned_entities.add(eid)

                saved_boxes = []
                for idx, item in enumerate(extracted_data):
                    b = item["box"]
                    emb = item["emb"]
                    crop_pil = item["crop_pil"]

                    if idx in assigned_boxes:
                        matched_eid, sim, status = assigned_boxes[idx]
                    else:
                        matched_eid = None
                        sim = item["top_sim"]
                        status = "UNASSIGNED"

                    candidate_pairs = item["candidates"] if item["is_ambiguous"] else (
                        [(matched_eid, sim)] if matched_eid is not None else []
                    )
                    candidate_pairs = [
                        (eid, score)
                        for eid, score in candidate_pairs
                        if eid not in assigned_entities or eid == matched_eid
                    ][:3]
                    candidate_entities = [
                        {"entity_id": eid, "score": score}
                        for eid, score in candidate_pairs
                        if eid is not None
                    ]

                    box_record = {
                        "photo_id": photo_id,
                        "entity_id": matched_eid,
                        "box_type": b["box_type"],
                        "label": b.get("label", "person"),
                        "confidence": b.get("confidence", 1.0),
                        "x_min": b["x_min"],
                        "y_min": b["y_min"],
                        "x_max": b["x_max"],
                        "y_max": b["y_max"],
                        "embedding_json": json.dumps(emb),
                        "candidate_entities_json": json.dumps(candidate_entities),
                        "status": status,
                        "match_confidence": sim
                    }
                    box_id = insert_detected_box(box_record)
                    box_record["id"] = box_id

                    # Save crop thumbnail
                    crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
                    crop_pil.thumbnail((320, 320), Image.Resampling.LANCZOS)
                    crop_pil.save(crop_path, "JPEG", quality=90)

                    saved_boxes.append(box_record)

                return saved_boxes
        except Exception as e:
            print(f"Error processing photo {photo_id} ({file_path}): {e}")
            return []

    def rematch_unassigned_boxes(
        self,
        db_path: Optional[str] = None,
        threshold: float = STRICT_HIGH_CONFIDENCE_THRESHOLD
    ) -> int:
        """
        Fast in-memory re-evaluation of all UNASSIGNED detected boxes (including on group photos
        where another person is already tagged) against the latest CONFIRMED exemplar embeddings.
        Enforces strict PERSON vs PET type matching and per-photo mutual exclusion.
        Returns the number of newly matched boxes moved to PENDING_REVIEW.
        """
        person_embs_raw = get_confirmed_embeddings_for_entities(db_path=db_path, entity_type="PERSON")
        pet_embs_raw = get_confirmed_embeddings_for_entities(db_path=db_path, entity_type="PET")
        if not person_embs_raw and not pet_embs_raw:
            return 0

        person_embs: Dict[int, Any] = {
            eid: np.array(vecs, dtype=np.float32) for eid, vecs in person_embs_raw.items() if vecs
        }
        pet_embs: Dict[int, Any] = {
            eid: np.array(vecs, dtype=np.float32) for eid, vecs in pet_embs_raw.items() if vecs
        }

        conn = get_connection(db_path)
        try:
            # 1. Find entities already assigned on each photo (CONFIRMED or PENDING_REVIEW)
            existing_rows = conn.execute(
                "SELECT photo_id, entity_id FROM detected_boxes "
                "WHERE status IN ('CONFIRMED', 'PENDING_REVIEW') AND entity_id IS NOT NULL"
            ).fetchall()
            photo_assigned_entities: Dict[int, set] = {}
            for r in existing_rows:
                photo_assigned_entities.setdefault(int(r["photo_id"]), set()).add(int(r["entity_id"]))

            # 2. Fetch all UNASSIGNED boxes with valid embeddings on non-trashed photos
            unassigned_rows = conn.execute(
                "SELECT b.id, b.photo_id, b.box_type, b.embedding_json "
                "FROM detected_boxes b "
                "JOIN photos p ON p.id = b.photo_id "
                "WHERE b.status = 'UNASSIGNED' AND b.embedding_json IS NOT NULL AND p.is_trashed = 0 "
                "ORDER BY b.photo_id ASC, b.confidence DESC"
            ).fetchall()
        finally:
            conn.close()

        if not unassigned_rows:
            return 0

        # Group unassigned boxes by photo_id for per-photo mutual exclusion
        boxes_by_photo: Dict[int, List[Dict[str, Any]]] = {}
        for r in unassigned_rows:
            boxes_by_photo.setdefault(int(r["photo_id"]), []).append(dict(r))

        updates_to_apply: List[Tuple[int, str, float, str, int]] = []

        for pid, p_boxes in boxes_by_photo.items():
            assigned_on_photo = set(photo_assigned_entities.get(pid, set()))
            extracted = []

            for b in p_boxes:
                try:
                    emb = json.loads(b["embedding_json"])
                except Exception:
                    continue
                if not isinstance(emb, list) or not emb:
                    continue

                target_embs = pet_embs if b.get("box_type") == "PET" else person_embs
                if not target_embs:
                    continue

                raw_candidates = self.rank_entity_candidates(emb, target_embs, threshold=threshold)
                # Filter out entities already assigned to another box in this photo
                candidates = [(eid, score) for eid, score in raw_candidates if eid not in assigned_on_photo]
                if not candidates:
                    continue

                extracted.append({
                    "box_id": int(b["id"]),
                    "candidates": candidates,
                    "is_ambiguous": (
                        len(candidates) > 1 and
                        candidates[0][1] - candidates[1][1] < MIN_AMBIGUITY_MARGIN
                    )
                })

            if not extracted:
                continue

            # Greedy 1-to-1 bipartite matching across unassigned boxes in this photo
            all_matches = []
            for idx, item in enumerate(extracted):
                for eid, score in item["candidates"]:
                    all_matches.append((score, idx, eid))

            all_matches.sort(key=lambda x: x[0], reverse=True)
            matched_indices: Dict[int, Tuple[int, float]] = {}

            for score, idx, eid in all_matches:
                if idx not in matched_indices and eid not in assigned_on_photo:
                    matched_indices[idx] = (eid, score)
                    assigned_on_photo.add(eid)

            for idx, (matched_eid, sim) in matched_indices.items():
                item = extracted[idx]
                candidate_pairs = item["candidates"] if item["is_ambiguous"] else [(matched_eid, sim)]
                candidate_pairs = [
                    (eid, score)
                    for eid, score in candidate_pairs
                    if eid not in assigned_on_photo or eid == matched_eid
                ][:3]
                candidate_entities = [
                    {"entity_id": eid, "score": score}
                    for eid, score in candidate_pairs
                ]
                updates_to_apply.append((
                    matched_eid,
                    "PENDING_REVIEW",
                    round(float(sim), 4),
                    json.dumps(candidate_entities),
                    item["box_id"]
                ))

        if not updates_to_apply:
            return 0

        conn = get_connection(db_path)
        try:
            with conn:
                conn.executemany(
                    "UPDATE detected_boxes "
                    "SET entity_id = ?, status = ?, match_confidence = ?, candidate_entities_json = ? "
                    "WHERE id = ? AND status = 'UNASSIGNED'",
                    updates_to_apply
                )
        finally:
            conn.close()

        return len(updates_to_apply)


    def get_or_generate_crop(self, box_data: Dict[str, Any]) -> Optional[str]:
        """
        Returns cached crop file path or extracts and caches it on the fly.
        """
        box_id = box_data.get("id")
        crop_path = os.path.join(CROPS_CACHE_DIR, f"{box_id}.jpg")
        if os.path.exists(crop_path):
            return crop_path

        file_path = box_data.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            with Image.open(file_path) as img:
                img_oriented = ImageOps.exif_transpose(img)
                w, h = img_oriented.size

                x_min = box_data.get("x_min", 0.0)
                y_min = box_data.get("y_min", 0.0)
                x_max = box_data.get("x_max", 1.0)
                y_max = box_data.get("y_max", 1.0)

                bw = x_max - x_min
                bh = y_max - y_min
                pad_x = bw * 0.15
                pad_y = bh * 0.15

                x1 = max(0, int((x_min - pad_x) * w))
                y1 = max(0, int((y_min - pad_y) * h))
                x2 = min(w, int((x_max + pad_x) * w))
                y2 = min(h, int((y_max + pad_y) * h))

                if x2 > x1 and y2 > y1:
                    crop = img_oriented.crop((x1, y1, x2, y2)).convert("RGB")
                    crop.thumbnail((320, 320), Image.Resampling.LANCZOS)
                    crop.save(crop_path, "JPEG", quality=90)
                    return crop_path
        except Exception as e:
            print(f"Failed to generate crop for box {box_id}: {e}")

        return None
