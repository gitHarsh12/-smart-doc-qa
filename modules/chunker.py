"""
=============================================================
MODULE 1 - Step 1.2 & 1.3: Smart Chunker with Overlap
=============================================================
Yeh module text ko chhote tukdon (chunks) me kaatta hai.

Features:
- 500 words per chunk (configurable)
- 20% Overlap (100 words) between consecutive chunks
- Sentence-aware splitting (sentences beech me nahi toot te)
- Metadata tracking (chunk index, source info)
=============================================================
"""

import logging
from typing import List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TextChunk:
    """
    Ek text chunk ka data structure.

    Attributes:
        chunk_id: Unique identifier (0, 1, 2, ...)
        text: Actual chunk text
        word_count: Number of words in this chunk
        start_position: Original text me yeh chunk kahan se shuru hota hai
        source_page: Kaunsi page se aaya hai (agar PDF hai)
        overlap_with_previous: Previous chunk ke sath kitna overlap hai
    """
    chunk_id: int
    text: str
    word_count: int = 0
    start_position: int = 0
    source_page: int = 0
    overlap_with_previous: int = 0

    def __post_init__(self):
        self.word_count = len(self.text.split())


class SmartChunker:
    """
    The Cutter & The Glue - Text ko smart tukdon me kaato aur overlap jodo.

    Algorithm:
    1. Poora text word list me badlo
    2. CHUNK_SIZE words ke tukde karo
    3. Har tukde ki shuruaat me pichle tukde ke aakhri OVERLAP words jodo
    4. Sentence boundaries ka dhyan rakho (period ke baad hi kaato)
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        respect_sentences: bool = True
    ):
        """
        Initialize Chunker.

        Args:
            chunk_size: Har chunk me kitne words (default: 500)
            chunk_overlap: Overlap kitne words (default: 100 = 20%)
            respect_sentences: Sentence boundary ka respect kare? (default: True)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.respect_sentences = respect_sentences

        # Validation
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"Overlap ({chunk_overlap}) must be less than chunk size ({chunk_size})"
            )

        overlap_pct = (self.chunk_overlap / self.chunk_size) * 100
        logger.info(
            f"✂️ Chunker initialized: size={chunk_size} words, "
            f"overlap={chunk_overlap} words ({overlap_pct:.0f}%)"
        )

    def chunk_text(self, text: str, source_name: str = "document") -> List[TextChunk]:
        """
        Poora text ko chunks me kaato.

        Args:
            text: Original text string
            source_name: Document ka naam (metadata ke liye)

        Returns:
            List of TextChunk objects
        """
        if not text or len(text.strip()) == 0:
            logger.warning("⚠️ Empty text received for chunking")
            return []

        # Step 1: Text ko words me split karo
        words = text.split()
        total_words = len(words)
        logger.info(f"📝 Total words to chunk: {total_words}")

        # Step 2: Agar text chhota hai, ek hi chunk bana do
        if total_words <= self.chunk_size:
            chunk = TextChunk(
                chunk_id=0,
                text=text.strip(),
                start_position=0,
            )
            logger.info(f"📦 Text is small, created 1 chunk")
            return [chunk]

        # Step 3: Sliding window se chunks banao
        chunks = []
        chunk_id = 0
        start = 0

        while start < total_words:
            # Calculate end position for this chunk
            end = start + self.chunk_size

            # Extract words for this chunk
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)

            # Step 4: Sentence boundary adjustment
            if self.respect_sentences and end < total_words:
                chunk_text = self._adjust_to_sentence_boundary(
                    chunk_text, " ".join(words[end:end + 50])
                )

            # Calculate overlap with previous chunk
            # 🛡️ FIX F-26: Previous logic was buggy (start < chunk_overlap
            # never true after first chunk). Sliding window guarantees overlap,
            # so just use the configured value when chunk_id > 0.
            overlap = self.chunk_overlap if chunk_id > 0 else 0

            # Create chunk object
            chunk = TextChunk(
                chunk_id=chunk_id,
                text=chunk_text.strip(),
                start_position=start,
                overlap_with_previous=self.chunk_overlap if chunk_id > 0 else 0,
            )
            chunks.append(chunk)

            # Step 5: Move window (chunk_size - overlap)
            # Yeh Glue magic hai - agla chunk pichle ke aakhri words se shuru hoga
            start = end - self.chunk_overlap
            chunk_id += 1

            # Safety: Agar sirf overlap bacha hai, break karo
            if start >= total_words - self.chunk_overlap:
                break

        logger.info(
            f"📦 Created {len(chunks)} chunks from {total_words} words "
            f"(overlap: {self.chunk_overlap} words = "
            f"{(self.chunk_overlap/self.chunk_size)*100:.0f}%)"
        )

        return chunks

    def _adjust_to_sentence_boundary(self, chunk_text: str, next_text: str) -> str:
        """
        Chunk ko sentence boundary pe adjust karo.

        Agar chunk beech me kaata gaya hai (sentence adhoora hai),
        toh us sentence ko poora chunk me include karo ya hata do.

        Args:
            chunk_text: Current chunk text
            next_text: Agle chunk ki shuruaat

        Returns:
            Adjusted chunk text
        """
        # Sentence-ending markers
        sentence_enders = ['. ', '! ', '? ', '। ', '.\n', '!\n', '?\n']

        # Check if chunk already ends at sentence boundary
        for ender in sentence_enders:
            if chunk_text.rstrip().endswith(ender.strip()):
                return chunk_text  # Already clean ending

        # Find the last sentence-ending position in the chunk
        last_sentence_end = -1
        for ender in sentence_enders:
            pos = chunk_text.rfind(ender)
            if pos > last_sentence_end:
                last_sentence_end = pos + len(ender) - 1

        # Agar sentence boundary mil gayi aur significant text bacha hai
        if last_sentence_end > len(chunk_text) * 0.7:
            # Cut at sentence boundary
            return chunk_text[:last_sentence_end + 1]

        # Warna original chunk hi rakho (sentence beech me toot jayegi)
        return chunk_text

    def get_chunk_summary(self, chunks: List[TextChunk]) -> Dict:
        """
        Chunks ka summary return karo (debugging/display ke liye).
        """
        if not chunks:
            return {"total_chunks": 0}

        return {
            "total_chunks": len(chunks),
            "total_words": sum(c.word_count for c in chunks),
            "avg_chunk_size": sum(c.word_count for c in chunks) / len(chunks),
            "overlap_words": self.chunk_overlap,
            "overlap_percentage": (self.chunk_overlap / self.chunk_size) * 100,
            "chunk_sizes": [c.word_count for c in chunks],
        }
