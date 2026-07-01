"""
=============================================================
MODULE 3: Semantic Cache (Zero-latency Q&A repeat hits)
=============================================================
When user asks a question similar to one asked before,
return the cached answer instantly — no LLM call needed!

Features:
- Cosine similarity matching (configurable threshold, default 92%)
- Per-document hash isolation (cache invalidated on document change)
- In-memory + disk persistence (survives app restart)
- Thread-safe via locking
- LRU eviction (max 100 entries per document)
- Stats tracking (hits, misses, hit rate)

Usage:
    from modules.semantic_cache import SemanticCache
    cache = SemanticCache(similarity_threshold=0.92)
    cache.set_document_hash("doc_abc123")

    query_vector = [0.1, 0.2, ...]
    result = cache.lookup(query_vector)
    if result:
        return result.answer  # Cache hit!
    else:
        answer = llm.chat(...)
        cache.add("What is X?", query_vector, answer)

Algorithm:
    - Stores query vectors + answers in memory (numpy array)
    - On lookup: cosine similarity vs all cached queries
    - If best similarity >= threshold: cache hit
    - Else: cache miss → call LLM → store result
=============================================================
"""

import os
import json
import time
import logging
import threading
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Tuple
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# Cache entry data class
# ============================================================
@dataclass
class CacheEntry:
    """One cached Q&A pair."""
    query_text: str
    query_vector: List[float]
    answer: str
    timestamp: float
    hit_count: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "CacheEntry":
        return cls(**d)


@dataclass
class CacheLookupResult:
    """Result of a cache lookup."""
    answer: str
    similarity: float
    query_text: str
    timestamp: float


# ============================================================
# Semantic Cache
# ============================================================
class SemanticCache:
    """Cosine-similarity-based Q&A cache.

    Args:
        similarity_threshold: Min cosine similarity for cache hit (0.0 - 1.0).
            0.92 = very strict (only near-identical questions hit cache).
            0.85 = moderate (similar questions hit cache).
            0.70 = loose (risky — different questions may hit cache).
        max_size: Max entries per document (LRU eviction when full).
        persist_path: Path to JSON file for disk persistence (None = no persistence).
    """

    def __init__(
        self,
        similarity_threshold: float = 0.92,
        max_size: int = 100,
        persist_path: Optional[str] = None,
    ):
        # Validate threshold
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError(f"similarity_threshold must be 0.0-1.0, got {similarity_threshold}")
        self.similarity_threshold = float(similarity_threshold)
        self.max_size = max(1, int(max_size))

        # Use temp dir if no path given (Streamlit Cloud safe)
        if persist_path is None:
            import tempfile
            persist_dir = Path(tempfile.gettempdir()) / "rag_app"
            persist_dir.mkdir(parents=True, exist_ok=True)
            persist_path = str(persist_dir / "semantic_cache.json")

        self.persist_path = Path(persist_path)

        # Per-document cache: {doc_hash: List[CacheEntry]}
        self._caches: Dict[str, List[CacheEntry]] = {}
        self._current_doc_hash: str = "default"
        self._lock = threading.Lock()

        # Stats
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_lookups": 0,
        }

        # Load from disk
        self._load_from_disk()

        logger.info(
            f"🛡️ Semantic Cache initialized: "
            f"threshold={self.similarity_threshold:.2f}, "
            f"max_size={self.max_size}, "
            f"persist_path={self.persist_path}"
        )

    # ============================================================
    # Document hash management
    # ============================================================
    def set_document_hash(self, doc_hash: str) -> None:
        """Set the current document hash (isolates cache per document).

        Args:
            doc_hash: Any string uniquely identifying the current document.
                      (e.g., SHA256 of file content, first 16 chars)
        """
        if not doc_hash:
            doc_hash = "default"
        with self._lock:
            if doc_hash != self._current_doc_hash:
                logger.info(f"🔄 Switching cache document: {self._current_doc_hash} → {doc_hash}")
                self._current_doc_hash = doc_hash
                if doc_hash not in self._caches:
                    self._caches[doc_hash] = []

    def invalidate_document(self, doc_hash: str) -> None:
        """Remove all cache entries for a specific document."""
        with self._lock:
            if doc_hash in self._caches:
                count = len(self._caches[doc_hash])
                del self._caches[doc_hash]
                logger.info(f"🗑️ Invalidated {count} cache entries for document {doc_hash}")
                self._save_to_disk()

    def clear_all(self) -> None:
        """Clear all cache entries (all documents)."""
        with self._lock:
            total = sum(len(entries) for entries in self._caches.values())
            self._caches.clear()
            self._stats["cache_hits"] = 0
            self._stats["cache_misses"] = 0
            self._stats["total_lookups"] = 0
            logger.info(f"🗑️ Cleared all cache ({total} entries removed)")
            self._save_to_disk()

    # ============================================================
    # Lookup (cache hit check)
    # ============================================================
    def lookup(self, query_vector: List[float]) -> Optional[CacheLookupResult]:
        """Check if a similar query exists in cache.

        Args:
            query_vector: Embedding of the user's query.

        Returns:
            CacheLookupResult if cache hit, None if miss.
        """
        with self._lock:
            self._stats["total_lookups"] += 1

            entries = self._caches.get(self._current_doc_hash, [])
            if not entries:
                self._stats["cache_misses"] += 1
                return None

            # Build matrix of cached query vectors
            cached_vectors = np.array([e.query_vector for e in entries], dtype=np.float32)
            query_np = np.array([query_vector], dtype=np.float32)

            # Normalize for cosine similarity
            cached_norms = np.linalg.norm(cached_vectors, axis=1, keepdims=True)
            cached_norms[cached_norms == 0] = 1.0  # Avoid division by zero
            cached_normalized = cached_vectors / cached_norms

            query_norm = np.linalg.norm(query_np)
            if query_norm == 0:
                self._stats["cache_misses"] += 1
                return None
            query_normalized = query_np / query_norm

            # Compute cosine similarities
            similarities = (cached_normalized @ query_normalized.T).flatten()

            # Find best match
            best_idx = int(np.argmax(similarities))
            best_sim = float(similarities[best_idx])

            if best_sim >= self.similarity_threshold:
                entry = entries[best_idx]
                entry.hit_count += 1
                self._stats["cache_hits"] += 1
                logger.info(
                    f"⚡ CACHE HIT! similarity={best_sim:.3f} "
                    f"(threshold={self.similarity_threshold:.2f}), "
                    f"hits={entry.hit_count}"
                )
                # Move to end (LRU)
                entries.pop(best_idx)
                entries.append(entry)
                # Persist asynchronously (best effort)
                try:
                    self._save_to_disk()
                except Exception as e:
                    logger.warning(f"Cache persist failed (non-fatal): {e}")
                return CacheLookupResult(
                    answer=entry.answer,
                    similarity=best_sim,
                    query_text=entry.query_text,
                    timestamp=entry.timestamp,
                )
            else:
                self._stats["cache_misses"] += 1
                logger.debug(
                    f"Cache miss: best_sim={best_sim:.3f} "
                    f"< threshold={self.similarity_threshold:.2f}"
                )
                return None

    # ============================================================
    # Add new entry
    # ============================================================
    def add(
        self,
        query_text: str,
        query_vector: List[float],
        answer: str,
    ) -> None:
        """Add a new Q&A pair to the cache.

        Args:
            query_text: Original user question
            query_vector: Embedding of the question
            answer: LLM-generated answer
        """
        if not query_text or not query_vector or not answer:
            return

        # Cap entry size to prevent memory bloat
        if len(query_text) > 5000:
            query_text = query_text[:5000]
        if len(answer) > 50000:
            answer = answer[:50000]

        entry = CacheEntry(
            query_text=query_text,
            query_vector=list(query_vector),
            answer=answer,
            timestamp=time.time(),
            hit_count=0,
        )

        with self._lock:
            entries = self._caches.setdefault(self._current_doc_hash, [])
            entries.append(entry)

            # LRU eviction: remove oldest if over capacity
            while len(entries) > self.max_size:
                evicted = entries.pop(0)
                logger.debug(f"LRU evicted cache entry (hits={evicted.hit_count})")

            # Persist
            try:
                self._save_to_disk()
            except Exception as e:
                logger.warning(f"Cache persist failed (non-fatal): {e}")

        logger.info(
            f"➕ Added cache entry: '{query_text[:50]}...' "
            f"(total in current doc: {len(self._caches.get(self._current_doc_hash, []))})"
        )

    # ============================================================
    # Stats
    # ============================================================
    def get_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            total_entries = sum(len(entries) for entries in self._caches.values())
            current_doc_entries = len(self._caches.get(self._current_doc_hash, []))
            total_lookups = self._stats["total_lookups"]
            hit_rate = (
                (self._stats["cache_hits"] / total_lookups * 100)
                if total_lookups > 0 else 0.0
            )
            return {
                "cache_hits": self._stats["cache_hits"],
                "cache_misses": self._stats["cache_misses"],
                "total_lookups": total_lookups,
                "hit_rate_pct": round(hit_rate, 2),
                "total_entries": total_entries,
                "current_doc_entries": current_doc_entries,
                "current_doc_hash": self._current_doc_hash,
                "similarity_threshold": self.similarity_threshold,
                "max_size": self.max_size,
            }

    # ============================================================
    # Disk persistence
    # ============================================================
    def _save_to_disk(self) -> None:
        """Save cache to disk (atomic via temp file)."""
        try:
            serializable = {
                "stats": self._stats,
                "current_doc_hash": self._current_doc_hash,
                "caches": {
                    doc_hash: [entry.to_dict() for entry in entries]
                    for doc_hash, entries in self._caches.items()
                },
            }
            tmp_file = self.persist_path.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            tmp_file.replace(self.persist_path)
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"Cache save failed: {e}")

    def _load_from_disk(self) -> None:
        """Load cache from disk (best effort)."""
        try:
            if not self.persist_path.exists():
                return
            with open(self.persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._stats = data.get("stats", self._stats)
            self._current_doc_hash = data.get("current_doc_hash", "default")
            for doc_hash, entries_data in data.get("caches", {}).items():
                self._caches[doc_hash] = [
                    CacheEntry.from_dict(e) for e in entries_data
                ]
            total = sum(len(entries) for entries in self._caches.values())
            logger.info(f"📂 Loaded {total} cache entries from disk ({len(self._caches)} documents)")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Cache load failed ({e}) — starting fresh")
            self._caches = {}


# ============================================================
# Singleton
# ============================================================
_semantic_cache: Optional[SemanticCache] = None


def get_semantic_cache(threshold: float = 0.92) -> SemanticCache:
    """Get singleton SemanticCache instance."""
    global _semantic_cache
    if _semantic_cache is None:
        _semantic_cache = SemanticCache(similarity_threshold=threshold)
    return _semantic_cache
