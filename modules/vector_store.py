"""
=============================================================
MODULE 2 - Step 2.2: FAISS Vector Store (The Shelf)
=============================================================
Yeh module vectors ko FAISS database me store karta hai.

Features:
- FAISS IndexFlatIP (Inner Product / Cosine Similarity)
- In-memory storage (8GB RAM ke liye perfect)
- Add, Search, Delete operations
- Automatic vector normalization
- Metadata tracking (chunk text + IDs)
=============================================================
"""

import logging
from typing import List, Dict, Tuple, Optional
import os 

import numpy as np
import faiss

logger = logging.getLogger(__name__)


class FAISSVectorStore:
    """
    The Shelf - Vectors ko line se saja kar rakhne ki jagah.

    FAISS (Facebook AI Similarity Search) use karta hai jo
    lightning-fast similarity search provide karta hai.

    🛡️ Hardened with:
    - F-18: HNSW index option (10x faster at scale, no training needed)
    - F-19: save_to_disk/load_from_disk helpers for persistence

    Storage Strategy:
    - FAISS Index: Sirf vectors (fast search ke liye)
    - Python Dict: Chunk texts + metadata (results ke liye)
    - Sab kuch RAM me (8GB RAM ke liye suitable)
    """

    def __init__(self, dimension: int = 1024, use_hnsw: bool = False):
        """
        Initialize FAISS Vector Store.

        Args:
            dimension: Vector dimension (default: 1024 for NVIDIA nv-embedqa)
            use_hnsw: 🛡️ F-18: Use HNSW index for faster search at scale.
                      HNSW ~10x faster but ~1.5x more memory.
                      For <10k vectors, IndexFlatIP is fine.
                      For 10k-1M vectors, HNSW recommended.
        """
        self.dimension = dimension
        self.use_hnsw = use_hnsw
        self.index = None
        self.chunks_metadata = {}  # {chunk_id: {"text": ..., "source": ...}}
        self.total_vectors = 0

        self._initialize_index()
        idx_type = "HNSWFlat" if use_hnsw else "IndexFlatIP"
        logger.info(f"📚 FAISS Store initialized: dimension={dimension}, index={idx_type}")

    def _initialize_index(self):
        """FAISS index create karo.

        🛡️ F-18: Support both flat (exact, slow at scale) and HNSW (approximate, fast).
        """
        if self.use_hnsw:
            # HNSW: 10x faster search, 1.5x more memory, no training needed
            # Note: M as positional arg (FAISS 1.7+ API)
            self.index = faiss.IndexHNSWFlat(self.dimension, 32)  # M=32
            try:
                self.index.hnsw.efConstruction = 200
                self.index.hnsw.efSearch = 64  # tune: higher = more accurate, slower
            except AttributeError:
                pass  # older FAISS versions
        else:
            # IndexFlatIP = Inner Product (exact, O(N) brute-force)
            # Fine for <10k vectors. Use HNSW for larger datasets.
            self.index = faiss.IndexFlatIP(self.dimension)
        self.chunks_metadata = {}
        self.total_vectors = 0

    def add_vectors(
        self,
        vectors: List[List[float]],
        chunk_texts: List[str],
        metadata_list: Optional[List[Dict]] = None
    ) -> int:
        """
        Vectors ko FAISS index me add karo.

        Args:
            vectors: List of embedding vectors
            chunk_texts: Corresponding chunk texts
            metadata_list: Optional metadata for each chunk

        Returns:
            Number of vectors added
        """
        if not vectors or len(vectors) != len(chunk_texts):
            logger.error("❌ Vectors and texts count mismatch!")
            return 0

        # Convert to numpy array
        vectors_np = np.array(vectors, dtype=np.float32)

        # Normalize vectors (for cosine similarity via inner product)
        faiss.normalize_L2(vectors_np)

        # Add to FAISS index
        start_id = self.total_vectors
        self.index.add(vectors_np)

        # Store metadata
        for i, (text, vector) in enumerate(zip(chunk_texts, vectors)):
            chunk_id = start_id + i
            self.chunks_metadata[chunk_id] = {
                "text": text,
                "chunk_id": chunk_id,
                "metadata": metadata_list[i] if metadata_list else {},
            }

        self.total_vectors += len(vectors)
        logger.info(f"➕ Added {len(vectors)} vectors. Total: {self.total_vectors}")

        return len(vectors)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 8
    ) -> List[Tuple[int, float, str]]:
        """
        Query vector ke liye sabse similar vectors dhoondho.

        Args:
            query_vector: User query ka embedding vector
            top_k: Kitne results chahiye (default: 8)

        Returns:
            List of (chunk_id, similarity_score, chunk_text)
        """
        if self.total_vectors == 0:
            logger.warning("⚠️ Index is empty! No vectors to search.")
            return []

        # Prepare query vector
        query_np = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(query_np)

        # Search
        scores, indices = self.index.search(query_np, min(top_k, self.total_vectors))

        # Format results
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx in self.chunks_metadata:
                results.append((
                    int(idx),
                    float(score),
                    self.chunks_metadata[idx]["text"],
                ))

        logger.info(f"🔍 Found {len(results)} results for query")
        return results

    def delete_all(self):
        """Sab vectors delete karo (naya document upload ke liye)."""
        self._initialize_index()
        logger.info("🗑️ All vectors deleted. Index reset.")

    def get_stats(self) -> Dict:
        """Vector store ka stats return karo."""
        return {
            "total_vectors": self.total_vectors,
            "dimension": self.dimension,
            "index_type": type(self.index).__name__,
            "is_trained": self.index.is_trained if self.index else False,
        }

    def save_index(self, filepath: str):
        """FAISS index ko file me save karo (persistence ke liye)."""
        if self.index and self.total_vectors > 0:
            faiss.write_index(self.index, filepath)
            logger.info(f"💾 Index saved: {filepath} ({self.total_vectors} vectors)")

    def load_index(self, filepath: str):
        """File se FAISS index load karo."""
        if os.path.exists(filepath):
            self.index = faiss.read_index(filepath)
            self.total_vectors = self.index.ntotal
            logger.info(f"📂 Index loaded: {filepath} ({self.total_vectors} vectors)")

    # ============================================================
    # 🛡️ FIX F-19: Persistence helpers (index + metadata together)
    # ============================================================
    def save_to_disk(self, index_path: str, metadata_path: str) -> bool:
        """Save both FAISS index and chunk metadata to disk.

        Call after every document upload so app restart doesn't lose data.
        """
        try:
            import json
            if not self.index or self.total_vectors == 0:
                logger.warning("⚠️ Nothing to save — index is empty")
                return False
            os.makedirs(os.path.dirname(index_path) or ".", exist_ok=True)
            faiss.write_index(self.index, index_path)
            # Save metadata as JSON
            serializable = {str(k): v for k, v in self.chunks_metadata.items()}
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 Saved index ({self.total_vectors} vectors) + metadata to disk")
            return True
        except (OSError, IOError, ValueError) as e:
            logger.error(f"❌ save_to_disk failed: {e}", exc_info=True)
            return False

    def load_from_disk(self, index_path: str, metadata_path: str) -> bool:
        """Load FAISS index + chunk metadata from disk.

        Call at app startup to restore state after restart.
        """
        try:
            import json
            if not (os.path.exists(index_path) and os.path.exists(metadata_path)):
                logger.info("ℹ️ No saved index found — starting fresh")
                return False
            self.index = faiss.read_index(index_path)
            self.total_vectors = self.index.ntotal
            with open(metadata_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self.chunks_metadata = {int(k): v for k, v in loaded.items()}
            logger.info(f"📂 Loaded {self.total_vectors} vectors + {len(self.chunks_metadata)} chunks from disk")
            return True
        except (OSError, IOError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"❌ load_from_disk failed: {e}", exc_info=True)
            return False
