"""
Semantic vector search engine for documents using SentenceTransformers.
Embeds document chunks into dense vector representations for instant natural language retrieval.
"""

import os
import threading
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sentence_transformers import SentenceTransformer
from backend.documents_db import (
    get_all_document_chunks_with_embeddings,
    save_document_chunks,
    get_documents_connection
)

DOC_VECTOR_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".lumina_cache", "doc_embeddings.npz")

class DocumentVectorEngine:
    _instance = None
    _lock = threading.RLock()

    def __init__(self):
        # High performance, low latency text embedding model
        self.model_name = "all-MiniLM-L6-v2"
        self._model: Optional[SentenceTransformer] = None
        self.chunk_ids: List[int] = []
        self.doc_ids: List[int] = []
        self.chunk_texts: List[str] = []
        self.embeddings: Optional[np.ndarray] = None  # shape: (N, 384)
        self.load_index()

    @classmethod
    def get_instance(cls) -> "DocumentVectorEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DocumentVectorEngine()
            return cls._instance

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = SentenceTransformer(self.model_name)
        return self._model

    def reset_index(self):
        """Clears in-memory embeddings and indices."""
        with self._lock:
            self.chunk_ids = []
            self.doc_ids = []
            self.chunk_texts = []
            self.embeddings = None

    def load_index(self):
        """Loads vector index from database or cache."""
        with self._lock:
            try:
                chunks = get_all_document_chunks_with_embeddings()
                if not chunks:
                    self.chunk_ids = []
                    self.doc_ids = []
                    self.chunk_texts = []
                    self.embeddings = None
                    return

                c_ids = []
                d_ids = []
                c_texts = []
                embs = []

                for row in chunks:
                    try:
                        emb = json.loads(row["embedding_json"])
                        if emb:
                            c_ids.append(row["id"])
                            d_ids.append(row["document_id"])
                            c_texts.append(row["chunk_text"])
                            embs.append(emb)
                    except Exception:
                        continue

                if embs:
                    self.chunk_ids = c_ids
                    self.doc_ids = d_ids
                    self.chunk_texts = c_texts
                    arr = np.array(embs, dtype=np.float32)
                    # Normalize for fast dot-product cosine similarity
                    norms = np.linalg.norm(arr, axis=1, keepdims=True)
                    norms[norms == 0] = 1e-10
                    self.embeddings = arr / norms
                else:
                    self.embeddings = None
            except Exception as e:
                print(f"[DocVectorEngine] Error loading index: {e}")

    def embed_text(self, text: str) -> List[float]:
        """Generates a 384-dimensional embedding vector for a piece of text."""
        emb = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return emb.tolist()

    def index_document(self, doc_id: int, chunks: List[str]):
        """Generates embeddings for document chunks and updates vector index."""
        if not chunks:
            return

        with self._lock:
            embeddings = self.model.encode(chunks, convert_to_numpy=True, normalize_embeddings=True)
            chunks_data = []
            for idx, (text, emb) in enumerate(zip(chunks, embeddings)):
                chunks_data.append((idx, text, emb.tolist()))

            save_document_chunks(doc_id, chunks_data)
            self.load_index()

    def search(self, query: str, top_k: int = 30) -> List[Dict[str, Any]]:
        """
        Performs semantic search with query vector cosine similarity.
        Returns deduplicated document matches with best matched snippet and score.
        """
        query = query.strip()
        if not query:
            return []

        with self._lock:
            if self.embeddings is None or len(self.doc_ids) == 0:
                # If embeddings not built yet, fallback to SQL keyword matching
                return self._fallback_keyword_search(query, top_k)

            try:
                q_emb = self.model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
                scores = np.dot(self.embeddings, q_emb)

                # Rank by score descending
                top_indices = np.argsort(-scores)

                # Group by document_id to return best snippet per document
                seen_docs = set()
                results = []

                conn = get_documents_connection()
                for idx in top_indices:
                    score = float(scores[idx])
                    if score < 0.15:  # Minimum relevance threshold
                        break

                    d_id = self.doc_ids[idx]
                    if d_id in seen_docs:
                        continue
                    seen_docs.add(d_id)

                    snippet = self.chunk_texts[idx]
                    doc_row = conn.execute("SELECT * FROM documents WHERE id = ?", (d_id,)).fetchone()
                    if doc_row:
                        item = dict(doc_row)
                        item["score"] = round(score, 4)
                        item["match_snippet"] = snippet[:350] + ("..." if len(snippet) > 350 else "")
                        results.append(item)

                    if len(results) >= top_k:
                        break

                conn.close()
                return results
            except Exception as e:
                print(f"[DocVectorEngine] Search error: {e}")
                return self._fallback_keyword_search(query, top_k)

    def _fallback_keyword_search(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """Fallback keyword search using SQL LIKE query."""
        conn = get_documents_connection()
        s_term = f"%{query}%"
        rows = conn.execute("""
            SELECT *, SUBSTR(extracted_text, 1, 300) as snippet
            FROM documents
            WHERE file_name LIKE ? OR title LIKE ? OR extracted_text LIKE ?
            ORDER BY modified_at DESC
            LIMIT ?
        """, (s_term, s_term, s_term, top_k)).fetchall()
        conn.close()

        results = []
        for r in rows:
            item = dict(r)
            item["score"] = 0.5
            item["match_snippet"] = item.get("snippet", "")
            results.append(item)
        return results
