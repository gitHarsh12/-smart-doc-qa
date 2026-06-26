"""
=============================================================
MODULE 4: Advanced Retrieval & Re-ranking Layer
=============================================================
Yeh module sabse accurate jaankari dhoondhta hai.

Step 4.1: Broad Vector Search (FAISS se Top 8)
Step 4.2: NVIDIA Re-ranking (Top 8 → Top 3)

Features:
- Two-stage retrieval (broad search → fine filter)
- NVIDIA NeMo Re-ranker for precision
- Relevance scores for transparency
- Fallback when re-ranker unavailable
=============================================================
"""

import os
import logging
import time
from typing import List, Dict, Tuple, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class CandidateChunk:
    """
    Ek candidate chunk jo retrieval me mila hai.

    Attributes:
        chunk_id: FAISS index me position
        text: Chunk ka actual text
        vector_score: FAISS similarity score
        rerank_score: NVIDIA Re-ranker score (agar available)
        final_rank: Final ranking position
    """
    def __init__(
        self,
        chunk_id: int,
        text: str,
        vector_score: float,
        rerank_score: float = 0.0,
    ):
        self.chunk_id = chunk_id
        self.text = text
        self.vector_score = vector_score
        self.rerank_score = rerank_score
        self.final_rank = 0


class RetrievalEngine:
    """
    Sahi Jawab Chunne wala department.

    Two-Stage Process:
    ┌──────────────────────────────────────────┐
    │ Stage 1: FAISS Vector Search             │
    │ Query vector → FAISS → Top 8 candidates  │
    │ (Broad but fast match)                    │
    └──────────────┬───────────────────────────┘
                   ▼
    ┌──────────────────────────────────────────┐
    │ Stage 2: NVIDIA Re-ranker                │
    │ Top 8 chunks → NeMo Re-ranker → Top 3    │
    │ (Deep analysis, precise ranking)          │
    └──────────────────────────────────────────┘
    """

    # NVIDIA API Configuration
    API_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_RERANK_MODEL = "nvidia/nv-rerankqa-mistral-4b-v3"

    def __init__(
        self,
        vector_store=None,
        embedder=None,
        api_key: Optional[str] = None,
        top_k_candidates: int = 8,
        top_n_results: int = 3,
    ):
        """
        Initialize Retrieval Engine.

        Args:
            vector_store: FAISSVectorStore instance
            embedder: NVIDIAEmbedder instance
            api_key: NVIDIA API key
            top_k_candidates: Stage 1 me kitne candidates (default: 8)
            top_n_results: Stage 2 ke baad kitne results (default: 3)
        """
        self.vector_store = vector_store
        self.embedder = embedder
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.rerank_model = os.getenv(
            "NVIDIA_RERANK_MODEL", self.DEFAULT_RERANK_MODEL
        )
        self.top_k_candidates = top_k_candidates
        self.top_n_results = top_n_results

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info(
            f"🔍 Retrieval Engine initialized: "
            f"top_k={top_k_candidates}, top_n={top_n_results}"
        )

    def retrieve(self, query: str) -> List[CandidateChunk]:
        """
        Complete two-stage retrieval process.

        Args:
            query: User ka sawal

        Returns:
            List of top N re-ranked CandidateChunks
        """
        if not self.embedder or not self.vector_store:
            logger.error("❌ Embedder or Vector Store not set!")
            return []

        # =====================================================
        # Step 4.1: Broad Vector Search (FAISS)
        # =====================================================
        logger.info(f"🔎 Stage 1: Vector search for '{query[:50]}...'")
        query_vector = self.embedder.embed_query(query)

        raw_results = self.vector_store.search(
            query_vector,
            top_k=self.top_k_candidates
        )

        if not raw_results:
            logger.warning("⚠️ No results found in vector search!")
            return []

        # Convert to CandidateChunks
        candidates = []
        for chunk_id, score, text in raw_results:
            candidates.append(CandidateChunk(
                chunk_id=chunk_id,
                text=text,
                vector_score=score,
            ))

        logger.info(f"   Found {len(candidates)} candidates from FAISS")

        # =====================================================
        # Step 4.2: NVIDIA Re-ranking (The Filter)
        # =====================================================
        logger.info(f"🔄 Stage 2: Re-ranking top {len(candidates)} candidates...")
        reranked_candidates = self._rerank_with_nvidia(query, candidates)

        # Assign final ranks
        for i, candidate in enumerate(reranked_candidates):
            candidate.final_rank = i + 1

        logger.info(
            f"✅ Final: Top {len(reranked_candidates)} chunks selected"
        )
        for c in reranked_candidates:
            logger.info(
                f"   #{c.final_rank}: vector_score={c.vector_score:.3f}, "
                f"rerank_score={c.rerank_score:.3f}"
            )

        return reranked_candidates

    def _rerank_with_nvidia(
        self,
        query: str,
        candidates: List[CandidateChunk]
    ) -> List[CandidateChunk]:
        """
        NVIDIA NeMo Re-ranker se Top N chunks select karo.

        Re-ranker ek-ek chunk ko deep-study karta hai aur
        unhe relevance ke hisab se re-arrange karta hai.

        Args:
            query: User ka sawal
            candidates: Stage 1 ke candidates

        Returns:
            Top N re-ranked candidates
        """
        try:
            # Prepare passages for re-ranking
            passages = [c.text for c in candidates]

            payload = {
                "model": self.rerank_model,
                "query": query,
                "passages": passages,
                "top_n": self.top_n_results,
                "truncate": "END",
            }

            response = requests.post(
                f"{self.API_BASE_URL}/reranking",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                rankings = data.get("rankings", [])

                # Map re-ranker results back to candidates
                reranked = []
                for rank_info in rankings:
                    idx = rank_info.get("index", 0)
                    log_prob = rank_info.get("log_probability", 0.0)

                    if idx < len(candidates):
                        candidate = candidates[idx]
                        candidate.rerank_score = log_prob
                        reranked.append(candidate)

                # Sort by re-ranker score (descending)
                reranked.sort(key=lambda x: x.rerank_score, reverse=True)

                # Return top N
                result = reranked[:self.top_n_results]
                logger.info(f"   ✅ NVIDIA Re-ranker: {len(result)} chunks selected")
                return result

            else:
                logger.warning(
                    f"⚠️ Re-ranker API error {response.status_code}: "
                    f"{response.text[:200]}"
                )
                return self._fallback_rerank(candidates)

        except Exception as e:
            logger.warning(f"⚠️ Re-ranker failed: {e}. Using fallback.")
            return self._fallback_rerank(candidates)

    def _fallback_rerank(self, candidates: List[CandidateChunk]) -> List[CandidateChunk]:
        """
        Fallback: Agar NVIDIA Re-ranker na kaam kare,
        toh FAISS vector scores se hi top N select karo.
        """
        logger.info("   📊 Using fallback ranking (vector scores only)")

        sorted_candidates = sorted(
            candidates,
            key=lambda x: x.vector_score,
            reverse=True
        )

        result = sorted_candidates[:self.top_n_results]
        for c in result:
            c.rerank_score = c.vector_score  # Use vector score as rerank score

        return result
