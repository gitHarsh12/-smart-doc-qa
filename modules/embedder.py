"""
=============================================================
MODULE 2 - Step 2.1: NVIDIA Embedding Generator
=============================================================
Yeh module text chunks ko vectors (numbers) me badalta hai
using NVIDIA's Embedding API.

Features:
- NVIDIA nv-embedqa-e5-v5 model (best for Q&A tasks)
- Batch processing (multiple chunks ek saal)
- Input type optimization (passage vs query)
- Error handling with retry logic
=============================================================
"""

import os
import logging
import time
from typing import List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class NVIDIAEmbedder:
    """
    Text ko mathematical vectors me badalne ki machine.

    NVIDIA API se har chunk ka 1024-dimensional vector banata hai.
    Yeh vector us chunk ke 'semantic meaning' ko capture karta hai.

    Example:
        "Invoice total is ₹50,000" → [0.023, -0.891, 0.456, ...]
        "Bill amount equals 50000 rupees" → [0.021, -0.887, 0.451, ...]
        (Similar meaning → Similar vectors!)
    """

    # NVIDIA API Configuration
    API_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "nvidia/nv-embedqa-e5-v5"
    EMBEDDING_DIMENSION = 1024

    # Rate limiting
    REQUESTS_PER_SECOND = 5
    BATCH_SIZE = 20  # Max chunks per API call

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize NVIDIA Embedder.

        Args:
            api_key: NVIDIA API key (default: from .env file)
            model: Model name (default: nvidia/nv-embedqa-e5-v5)
        """
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = model or os.getenv("NVIDIA_EMBEDDING_MODEL", self.DEFAULT_MODEL)

        if not self.api_key:
            raise ValueError(
                "❌ NVIDIA API Key missing! \n"
                "Set it in .env file: NVIDIA_API_KEY=nvapi-xxxxx\n"
                "Get FREE key from: https://build.nvidia.com/"
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info(f"🧮 Embedder initialized: model={self.model}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Document chunks ko vectors me badlo.

        Yeh "passage" type embedding hai - document text ke liye optimized.

        Args:
            texts: List of text chunks

        Returns:
            List of embedding vectors (each is List[float])
        """
        if not texts:
            return []

        all_embeddings = []

        # Process in batches (API limit)
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            logger.info(
                f"🔢 Embedding batch {i//self.BATCH_SIZE + 1}: "
                f"{len(batch)} chunks"
            )

            # Add "passage" prefix for document chunks (E5 model requirement)
            prefixed_texts = [f"passage: {text}" for text in batch]

            try:
                embeddings = self._call_embedding_api(prefixed_texts)
                all_embeddings.extend(embeddings)

                # Rate limiting
                if i + self.BATCH_SIZE < len(texts):
                    time.sleep(1.0 / self.REQUESTS_PER_SECOND)

            except Exception as e:
                logger.error(f"❌ Embedding batch failed: {e}")
                # Retry once
                try:
                    time.sleep(2)
                    embeddings = self._call_embedding_api(prefixed_texts)
                    all_embeddings.extend(embeddings)
                except Exception as e2:
                    logger.error(f"❌ Retry also failed: {e2}")
                    # Fill with zero vectors as fallback
                    all_embeddings.extend(
                        [[0.0] * self.EMBEDDING_DIMENSION for _ in batch]
                    )

        logger.info(f"✅ Total embeddings generated: {len(all_embeddings)}")
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        User ke sawal ko vector me badlo.

        Yeh "query" type embedding hai - questions ke liye optimized.

        Args:
            query: User ka sawal

        Returns:
            Single embedding vector (List[float])
        """
        # Add "query" prefix for user questions (E5 model requirement)
        prefixed_query = f"query: {query}"

        try:
            embeddings = self._call_embedding_api([prefixed_query])
            return embeddings[0] if embeddings else [0.0] * self.EMBEDDING_DIMENSION
        except Exception as e:
            logger.error(f"❌ Query embedding failed: {e}")
            return [0.0] * self.EMBEDDING_DIMENSION

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """
        NVIDIA Embedding API ko call karo.

        Args:
            texts: List of prefixed text strings

        Returns:
            List of embedding vectors
        """
        payload = {
            "model": self.model,
            "input": texts,
            "input_type": "query",  # Required for E5 models
            "encoding_format": "float",
            "truncate": "END",
        }

        response = requests.post(
            f"{self.API_BASE_URL}/embeddings",
            headers=self.headers,
            json=payload,
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            # Sort by index to maintain order
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            embeddings = [item["embedding"] for item in sorted_data]
            return embeddings
        elif response.status_code == 429:
            # Rate limited - wait and retry
            logger.warning("⚠️ Rate limited! Waiting 5 seconds...")
            time.sleep(5)
            raise Exception("Rate limited - will retry")
        else:
            raise Exception(
                f"API Error {response.status_code}: {response.text}"
            )

    def test_connection(self) -> bool:
        """
        NVIDIA API connection test karo.
        """
        try:
            test_embedding = self.embed_query("test connection")
            is_valid = len(test_embedding) == self.EMBEDDING_DIMENSION
            if is_valid:
                logger.info("✅ NVIDIA API connection successful!")
            else:
                logger.error("❌ Invalid embedding dimension received")
            return is_valid
        except Exception as e:
            logger.error(f"❌ NVIDIA API connection failed: {e}")
            return False
