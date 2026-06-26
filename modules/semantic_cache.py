"""
=============================================================
MODULE 3: Semantic Cache (Speed & Cost Optimizer)
=============================================================
Yeh module same sawalon ke liye purane jawabon ko yaad rakhta hai.

Features:
- Semantic matching (Cosine Similarity >= 92%)
- 0ms latency for cache hits (NO API call!)
- Cost savings (tokens bachao!)
- In-memory storage (Python dict)
- Automatic cache expiration
=============================================================
"""

import os
import hashlib
import logging
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """
    Ek cache entry ka data structure.

    Attributes:
        query_text: Original sawal
        query_vector: Sawaal ka embedding vector
        answer: System ka jawab
        timestamp: Kab cache me add kiya
        hit_count: Kitni baar yeh cache use hua
    """
    query_text: str
    query_vector: List[float]
    answer: str
    timestamp: float = 0.0
    hit_count: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class SemanticCache:
    """
    Silicon Valley ka sabse bada hack - Semantic Caching!

    🛡️ Hardened with:
    - F-20: Vectorized cosine similarity (O(N) → 1 matrix multiply)
    - F-05: Document hash in cache key (no stale answers after doc change)

    Kaise kaam karta hai:
    1. User ne sawal pucha → Query vector banao
    2. Cache me har entry ke vector se Cosine Similarity check karo
       (ab matrix multiply se — bahut fast)
    3. Agar kisi entry ka similarity >= 92% → CACHE HIT!
       → Bina API call kiye turant jawab do (0ms)
    4. Agar koi match nahi → CACHE MISS → Module 4 pe jao
    """

    # Default similarity threshold (92%)
    DEFAULT_THRESHOLD = 0.92

    def __init__(
        self,
        similarity_threshold: float = None,
        max_cache_size: int = 100,
        ttl_seconds: int = 86400,  # 24 hours
        document_hash: str = "",
    ):
        """
        Initialize Semantic Cache.

        Args:
            similarity_threshold: Kitna % match chahiye cache hit ke liye (default: 0.92)
            max_cache_size: Maximum cache entries (memory control)
            ttl_seconds: Cache entry kitni der valid hai (default: 24 hours)
            document_hash: Current document ka hash — agar badle to cache invalidate.
        """
        self.similarity_threshold = similarity_threshold or float(
            os.getenv("CACHE_SIMILARITY_THRESHOLD", self.DEFAULT_THRESHOLD)
        )
        self.max_cache_size = max_cache_size
        self.ttl_seconds = ttl_seconds
        # 🛡️ F-05: Document hash for invalidation
        self.document_hash = document_hash

        # In-memory cache storage
        self.cache: Dict[str, CacheEntry] = {}

        # 🛡️ F-20: Cached vectors matrix (rebuilt on add/clear)
        self._vectors_matrix: Optional[np.ndarray] = None
        self._cache_keys_in_order: List[str] = []  # for index → key mapping
        self._vectors_dirty = True

        # Stats tracking
        self.stats = {
            "hits": 0,
            "misses": 0,
            "total_queries": 0,
        }

        logger.info(
            f"🛡️ Semantic Cache initialized: "
            f"threshold={self.similarity_threshold*100:.0f}%, "
            f"max_size={max_cache_size}, ttl={ttl_seconds}s, "
            f"doc_hash={document_hash[:8] or 'none'}"
        )

    def set_document_hash(self, document_hash: str) -> None:
        """Update document hash and clear cache if it changed (F-05)."""
        if self.document_hash and self.document_hash != document_hash:
            logger.info("🔄 Document changed — clearing cache (F-05 fix)")
            self.clear()
        self.document_hash = document_hash

    def _rebuild_vectors_matrix(self) -> None:
        """🛡️ F-20: Build a (N, D) matrix from all cached vectors."""
        if not self.cache:
            self._vectors_matrix = None
            self._cache_keys_in_order = []
            self._vectors_dirty = False
            return
        # Preserve insertion order for index mapping
        self._cache_keys_in_order = list(self.cache.keys())
        vectors = [self.cache[k].query_vector for k in self._cache_keys_in_order]
        self._vectors_matrix = np.array(vectors, dtype=np.float32)
        # Normalize rows for cosine similarity via dot product
        norms = np.linalg.norm(self._vectors_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0  # avoid div by zero
        self._vectors_matrix = self._vectors_matrix / norms
        self._vectors_dirty = False

    def lookup(self, query_vector: List[float]) -> Optional[CacheEntry]:
        """
        Cache me check karo - kya yeh sawal pehle bhi pucha gaya?

        🛡️ F-20: Vectorized lookup — single matrix multiply instead of N loops.

        Args:
            query_vector: User query ka embedding vector

        Returns:
            CacheEntry agar match mila (>= 92%), else None
        """
        self.stats["total_queries"] += 1

        if not self.cache:
            self.stats["misses"] += 1
            logger.info("📭 Cache empty → MISS")
            return None

        # Check for expired entries first
        self._cleanup_expired()
        if not self.cache:
            self.stats["misses"] += 1
            return None

        # 🛡️ F-20: Rebuild matrix if dirty
        if self._vectors_dirty:
            self._rebuild_vectors_matrix()

        # Query vector normalize
        q = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            self.stats["misses"] += 1
            return None
        q = q / q_norm

        # 🛡️ F-20: Batch cosine similarity — 1 matmul, not N loops
        similarities = self._vectors_matrix @ q  # (N,) vector
        best_idx = int(np.argmax(similarities))
        best_similarity = float(similarities[best_idx])

        if best_similarity >= self.similarity_threshold:
            best_key = self._cache_keys_in_order[best_idx]
            best_match = self.cache[best_key]
            self.stats["hits"] += 1
            best_match.hit_count += 1
            logger.info(
                f"🎯 CACHE HIT! Similarity: {best_similarity*100:.1f}% "
                f"(>= {self.similarity_threshold*100:.0f}%)"
            )
            logger.info(f"   Cached Q: '{best_match.query_text[:50]}...'")
            return best_match
        else:
            self.stats["misses"] += 1
            logger.info(
                f"📭 CACHE MISS. Best similarity: {best_similarity*100:.1f}% "
                f"(< {self.similarity_threshold*100:.0f}%)"
            )
            return None

    def add(
        self,
        query_text: str,
        query_vector: List[float],
        answer: str
    ) -> None:
        """
        Naya sawal-jawab pair cache me add karo.

        🛡️ F-05: Cache key includes document hash.
        """
        # Cache size check - agar full hai toh sabse purana delete karo
        if len(self.cache) >= self.max_cache_size:
            self._evict_oldest()

        # 🛡️ F-05: Cache key includes document hash
        # Same question on different document → different cache entry
        text_hash = hashlib.sha256(query_text.encode()).hexdigest()[:16]
        cache_key = f"doc_{self.document_hash[:8]}_q_{text_hash}"

        entry = CacheEntry(
            query_text=query_text,
            query_vector=query_vector,
            answer=answer,
        )

        self.cache[cache_key] = entry
        # 🛡️ F-20: Mark matrix dirty for rebuild on next lookup
        self._vectors_dirty = True
        logger.info(
            f"📝 Cached: '{query_text[:40]}...' "
            f"(Cache size: {len(self.cache)}/{self.max_cache_size})"
        )

    def clear(self):
        """Poori cache khaali karo."""
        self.cache.clear()
        self._vectors_matrix = None
        self._cache_keys_in_order = []
        self._vectors_dirty = True
        logger.info("🗑️ Cache cleared")

    def get_stats(self) -> Dict:
        """Cache statistics return karo."""
        hit_rate = 0.0
        if self.stats["total_queries"] > 0:
            hit_rate = (self.stats["hits"] / self.stats["total_queries"]) * 100

        return {
            "cache_size": len(self.cache),
            "max_size": self.max_cache_size,
            "similarity_threshold": self.similarity_threshold,
            "total_queries": self.stats["total_queries"],
            "cache_hits": self.stats["hits"],
            "cache_misses": self.stats["misses"],
            "hit_rate_percent": round(hit_rate, 1),
            "document_hash": self.document_hash[:8] if self.document_hash else "",
        }

    def _cleanup_expired(self):
        """Expire ho chuke entries delete karo."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry.timestamp > self.ttl_seconds
        ]

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            self._vectors_dirty = True  # 🛡️ F-20: matrix needs rebuild
            logger.info(f"⏰ Removed {len(expired_keys)} expired cache entries")

    def _evict_oldest(self):
        """Sabse purani entry delete karo (LRU eviction)."""
        if not self.cache:
            return

        oldest_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].timestamp
        )
        del self.cache[oldest_key]
        self._vectors_dirty = True  # 🛡️ F-20: matrix needs rebuild
        logger.info("♻️ Evicted oldest cache entry (cache full)")
