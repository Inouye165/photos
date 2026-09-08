"""
CLIP Multimodal Vector Database & Semantic Search Engine for LuminaPhoto.
Maps natural language text queries and images into a shared 512-dimensional vector space.
Enables instant sub-millisecond semantic search across thousands of photos.
"""

import os
import threading
import numpy as np
from PIL import Image
from typing import List, Tuple, Dict, Any, Optional, cast
from sentence_transformers import SentenceTransformer
from backend.database import get_connection, DB_PATH
from backend.thumbnails import get_thumbnail_path

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

VECTOR_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".lumina_cache", "embeddings.npz")

class VectorEngine:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        self.model_name = "clip-ViT-B-32"
        self._model: Optional[SentenceTransformer] = None
        self.photo_ids: List[int] = []
        self.embeddings: Optional[np.ndarray] = None  # shape: (N, 512)
        self.load_index()

    @classmethod
    def get_instance(cls) -> "VectorEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = VectorEngine()
            return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def reset_index(self):
        """Resets in-memory and on-disk vector cache."""
        with self._lock:
            self.photo_ids = []
            self.embeddings = None
            if os.path.exists(VECTOR_CACHE_PATH):
                try:
                    os.remove(VECTOR_CACHE_PATH)
                except Exception:
                    pass

    def sync_with_db(self, db_path: str = DB_PATH):
        """Ensures vector index contains valid existing photo IDs from DB."""
        try:
            conn = get_connection(db_path)
            cursor = conn.execute("SELECT id FROM photos")
            db_ids = {r["id"] for r in cursor.fetchall()}
            conn.close()
        except Exception:
            return

        with self._lock:
            if self.embeddings is not None and len(self.photo_ids) > 0:
                valid_indices = [i for i, pid in enumerate(self.photo_ids) if pid in db_ids]
                if len(valid_indices) != len(self.photo_ids):
                    self.photo_ids = [self.photo_ids[i] for i in valid_indices]
                    self.embeddings = self.embeddings[valid_indices] if valid_indices else None
                    self.save_index()

    def clear_index(self):
        """Clears all in-memory embeddings and deletes vector cache file."""
        with self._lock:
            self.photo_ids = []
            self.embeddings = None
            if os.path.exists(VECTOR_CACHE_PATH):
                try:
                    os.remove(VECTOR_CACHE_PATH)
                except Exception:
                    pass

    def load_index(self):
        """Loads cached embeddings from disk and prunes stale IDs."""
        if os.path.exists(VECTOR_CACHE_PATH):
            try:
                data = np.load(VECTOR_CACHE_PATH)
                self.photo_ids = [int(x) for x in data["photo_ids"]]
                self.embeddings = data["embeddings"]
                self.sync_with_db()
            except Exception:
                self.photo_ids = []
                self.embeddings = None

    def save_index(self):
        """Persists photo embeddings and IDs to disk."""
        os.makedirs(os.path.dirname(VECTOR_CACHE_PATH), exist_ok=True)
        if self.embeddings is not None and len(self.photo_ids) > 0:
            np.savez_compressed(
                VECTOR_CACHE_PATH,
                photo_ids=np.array(self.photo_ids, dtype=np.int64),
                embeddings=self.embeddings
            )

    def _open_efficient_image(self, file_path: str, photo_id: Optional[int] = None) -> Optional[Image.Image]:
        """Loads cached thumbnail if available or downsamples original to 512px to minimize RAM usage."""
        if photo_id is not None:
            # Check for fast cached preview or thumb first
            for size_name in ("preview", "thumb"):
                cached_thumb = get_thumbnail_path(photo_id, size_name)
                if os.path.exists(cached_thumb):
                    try:
                        with Image.open(cached_thumb) as t_img:
                            return t_img.convert("RGB")
                    except Exception:
                        pass

        # Fall back to opening original, downsampled immediately
        try:
            with Image.open(file_path) as img:
                img_copy = img.copy()
                if max(img_copy.size) > 512:
                    img_copy.thumbnail((512, 512), Image.Resampling.BILINEAR)
                return img_copy.convert("RGB") if img_copy.mode != "RGB" else img_copy
        except Exception:
            return None

    def encode_image(self, file_path: str, photo_id: Optional[int] = None) -> Optional[np.ndarray]:
        """Encodes an image file into a normalized 512-dim embedding vector using efficient image loading."""
        rgb_img = self._open_efficient_image(file_path, photo_id)
        if rgb_img is None:
            return None
        try:
            emb = cast(Any, self.model).encode([rgb_img], show_progress_bar=False, normalize_embeddings=True)[0]
            return np.array(emb, dtype=np.float32)
        except Exception:
            return None

    def add_or_update_photo(self, photo_id: int, file_path: str, db_path: str = DB_PATH) -> bool:
        """Computes and indexes embedding for a single photo."""
        emb = self.encode_image(file_path, photo_id)
        if emb is None:
            return False

        with self._lock:
            if photo_id in self.photo_ids and self.embeddings is not None:
                idx = self.photo_ids.index(photo_id)
                self.embeddings[idx] = emb
            else:
                if photo_id not in self.photo_ids:
                    self.photo_ids.append(photo_id)
                if self.embeddings is None or len(self.embeddings) == 0:
                    self.embeddings = np.expand_dims(emb, axis=0)
                else:
                    self.embeddings = np.vstack([self.embeddings, emb])

        # Mark in DB
        try:
            conn = get_connection(db_path)
            conn.execute("UPDATE photos SET has_embedding = 1 WHERE id = ?", (photo_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return True

    def batch_index_photos(self, photos: List[Tuple[int, str]], batch_size: int = 32, progress_callback=None, db_path: str = DB_PATH):
        """Batched embedding computation utilizing cached thumbnails for fast, low-RAM indexing."""
        total = len(photos)
        indexed_count = 0

        for i in range(0, total, batch_size):
            batch = photos[i:i + batch_size]
            valid_ids = []
            valid_images = []

            for pid, fpath in batch:
                img = self._open_efficient_image(fpath, pid)
                if img is not None:
                    valid_images.append(img)
                    valid_ids.append(pid)

            if valid_images:
                try:
                    batch_embs = cast(Any, self.model).encode(
                        valid_images,
                        batch_size=len(valid_images),
                        show_progress_bar=False,
                        normalize_embeddings=True
                    )
                    batch_embs = np.array(batch_embs, dtype=np.float32)

                    with self._lock:
                        for idx, pid in enumerate(valid_ids):
                            emb = batch_embs[idx]
                            if pid in self.photo_ids and self.embeddings is not None:
                                p_idx = self.photo_ids.index(pid)
                                self.embeddings[p_idx] = emb
                            else:
                                if pid not in self.photo_ids:
                                    self.photo_ids.append(pid)
                                if self.embeddings is None or len(self.embeddings) == 0:
                                    self.embeddings = np.expand_dims(emb, axis=0)
                                else:
                                    self.embeddings = np.vstack([self.embeddings, emb])

                    conn = get_connection(db_path)
                    placeholders = ",".join("?" for _ in valid_ids)
                    conn.execute(f"UPDATE photos SET has_embedding = 1 WHERE id IN ({placeholders})", valid_ids)
                    conn.commit()
                    conn.close()

                    indexed_count += len(valid_ids)
                except Exception:
                    pass

            if progress_callback:
                progress_callback(indexed_count, total)

        self.save_index()
        return indexed_count

    def search_text(
        self,
        query: str,
        top_k: int = 50,
        min_similarity: float = 0.16,
        allowed_photo_ids: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic natural language search.
        Encodes query text into vector space and computes cosine similarity with indexed photos.
        If allowed_photo_ids is specified, restricts similarity ranking strictly to matching metadata candidates.
        """
        if not query or not query.strip() or self.embeddings is None or len(self.photo_ids) == 0:
            return []

        # Encode query text
        query_emb = self.model.encode(query.strip(), show_progress_bar=False, normalize_embeddings=True)
        query_emb = np.array(query_emb, dtype=np.float32)

        # Cosine similarity is dot product of normalized vectors
        scores = np.dot(self.embeddings, query_emb)

        # If filtered candidates are provided, slice down to the candidate subset before top_k
        if allowed_photo_ids is not None:
            allowed_set = set(allowed_photo_ids) if not isinstance(allowed_photo_ids, set) else allowed_photo_ids
            candidate_indices = [i for i, pid in enumerate(self.photo_ids) if pid in allowed_set]
            if not candidate_indices:
                return []

            sub_scores = scores[candidate_indices]
            sorted_sub_order = np.argsort(sub_scores)[::-1]

            results = []
            for rank in sorted_sub_order[:top_k]:
                orig_idx = candidate_indices[rank]
                score = float(scores[orig_idx])
                if score < min_similarity and len(results) >= 10:
                    break
                results.append({
                    "photo_id": int(self.photo_ids[orig_idx]),
                    "similarity_score": round(score, 4)
                })
            return results

        # Global ranking without pre-filter
        top_indices = np.argsort(scores)[::-1]

        results = []
        for idx in top_indices[:top_k]:
            score = float(scores[idx])
            if score < min_similarity and len(results) >= 10:
                break
            results.append({
                "photo_id": int(self.photo_ids[idx]),
                "similarity_score": round(score, 4)
            })

        return results

