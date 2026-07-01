"""
=============================================================
🛡️ Centralized App Configuration (v3.0 — Tank Edition)
=============================================================
All magic numbers + security thresholds in ONE place.

🛡️ v3.0 Hardening:
- F-S7: Added input length limits for ALL user inputs
- F-S8: Added API call timeout defaults (prevents hanging)
- F-S9: Added max concurrent requests per session
- F-S10: Added session inactivity timeout
=============================================================
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Centralized configuration — frozen so values can't be mutated at runtime."""

    # ── File Upload Limits (F-07) ──
    MAX_FILE_SIZE_BYTES: int = 200 * 1024 * 1024          # 200MB per file
    MAX_TOTAL_UPLOAD_BYTES: int = 500 * 1024 * 1024       # 500MB total per session
    MAX_DECOMPRESSED_SIZE: int = 50 * 1024 * 1024         # 50MB per ZIP member (F-08)
    MAX_FILES_PER_UPLOAD: int = 10                        # 🛡️ v3.0: prevent upload flooding

    # ── Query / Input Limits (F-S7) ──
    MAX_QUERY_LENGTH: int = 5000                          # Max question length
    MAX_CONTEXT_CHUNKS: int = 50                          # Max chunks to send LLM
    MAX_EMAIL_LENGTH: int = 254                           # RFC 5321 max email length
    MAX_PASSWORD_LENGTH: int = 128                        # Prevent DoS via long passwords
    MIN_PASSWORD_LENGTH: int = 4                          # Minimum password length
    MAX_API_KEY_LENGTH: int = 256                         # Prevent buffer overflow attempts

    # ── Rate Limiting (F-10) ──
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 30

    # ── API Timeouts (F-S8) ──
    LLM_TIMEOUT_SEC: int = 120                            # LLM call timeout
    EMBEDDING_TIMEOUT_SEC: int = 60                       # Embedding API timeout
    RERANKER_TIMEOUT_SEC: int = 15                        # Re-ranker API timeout
    OCR_TIMEOUT_SEC: int = 300                            # OCR per file (5 min max)

    # ── Session Limits (F-S9, F-S10) ──
    SESSION_INACTIVE_TIMEOUT_SEC: int = 3600              # 1 hour idle = logout
    MAX_CONCURRENT_REQUESTS_PER_SESSION: int = 3          # Prevent request flooding

    # ── Semantic Cache ──
    CACHE_SIMILARITY_THRESHOLD: float = 0.92
    CACHE_MAX_SIZE: int = 100
    CACHE_TTL_SEC: int = 86400  # 24 hours

    # ── Embedding ──
    EMBEDDING_BATCH_SIZE: int = 20
    EMBEDDING_REQUESTS_PER_SEC: int = 5

    # ── Retry Strategy (F-11) ──
    MAX_RETRIES: int = 3
    INITIAL_BACKOFF_SEC: float = 1.0
    BACKOFF_MULTIPLIER: float = 2.0
    MAX_BACKOFF_SEC: float = 60.0

    # ── Connection Pool (F-22) ──
    POOL_CONNECTIONS: int = 10
    POOL_MAXSIZE: int = 10

    # ── Persistence (F-19, F-S4) ──
    # Uses tempfile.gettempdir() at runtime (Streamlit Cloud safe)
    FAISS_INDEX_FILENAME: str = "faiss.index"
    FAISS_META_FILENAME: str = "faiss_meta.json"
    CACHE_FILENAME: str = "semantic_cache.json"

    # -- Auth (F-03) --
    ALLOWED_EMAILS_ENV: str = "RAG_ALLOWED_EMAILS"
    ADMIN_EMAILS_ENV: str = "RAG_ADMIN_EMAILS"
    PASSWORD_HASH_ROUNDS: int = 10000  # SHA256 iterations

    # -- Hardcoded Admin (v3.0.6) --
    # Sirf yeh email admin hoga, chahe koi bhi pehle register kare.
    # Auto-first-user-admin feature HATA diya gaya hai.
    # Password bhi yahi fix hai (case-sensitive).
    HARDCODED_ADMIN_EMAIL: str = "bajiprabhu2915@gmail.com"
    HARDCODED_ADMIN_PASSWORD: str = "Mumbai"

    # ── Observability (F-16, F-17) ──
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN_ENV: str = "SENTRY_DSN"

    # ============================================================
    # 🌐 PUBLIC DEMO MODE (resume/portfolio apps)
    # ============================================================
    # When PUBLIC_MODE=True:
    #   - No authentication required (anyone can access)
    #   - Stricter rate limits (protect API credits)
    #   - Daily global quota (hard cap)
    #   - Demo banner + footer shown
    #   - Graceful "quota exceeded" message instead of API error
    #
    # When PUBLIC_MODE=False:
    #   - Auth required (email whitelist)
    #   - Generous rate limits
    #   - No quota cap
    # ============================================================
    PUBLIC_MODE: bool = True  # ← Set False for auth-protected app

    # ── Demo Quota (only enforced when PUBLIC_MODE=True) ──
    DEMO_DAILY_GLOBAL_QUOTA: int = 500       # Total queries/day across ALL users
    DEMO_PER_USER_QUOTA: int = 15            # Queries per user per 15-min window
    DEMO_PER_USER_WINDOW_SEC: int = 900      # 15 minutes
    DEMO_MAX_FILE_SIZE_MB: int = 200         # Max file size in demo mode
    DEMO_MAX_QUERY_LENGTH: int = 500         # Shorter queries in demo

    # ── Branding ──
    BUILDER_NAME: str = "Harsh Bokde"
    BUILDER_ROLE: str = "AI/ML Engineer"
    GITHUB_URL: str = ""
    LINKEDIN_URL: str = ""


# Singleton instance
CONFIG = AppConfig()
