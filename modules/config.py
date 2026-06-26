"""
=============================================================
🛡️ FIX F-12 (partial): Centralized App Configuration
=============================================================
Previously, magic numbers (200MB, 5000 chars, 0.92 threshold,
30 req/min, 60s timeout, etc.) were scattered across 5+ files.
Change karne ke liye har file edit karni padti thi.

Ab sab kuch yahan hai — ek hi jagah se configure karo.

Usage:
    from modules.config import CONFIG
    if file.size > CONFIG.MAX_FILE_SIZE_BYTES:
        ...
=============================================================
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Centralized configuration — frozen so values can't be mutated at runtime."""

    # ── File Upload Limits (F-07) ──
    MAX_FILE_SIZE_BYTES: int = 200 * 1024 * 1024          # 200MB per file
    MAX_TOTAL_UPLOAD_BYTES: int = 500 * 1024 * 1024       # 500MB total per session
    MAX_DECOMPRESSED_SIZE: int = 50 * 1024 * 1024         # 50MB per ZIP member (F-08)

    # ── Query / Input Limits ──
    MAX_QUERY_LENGTH: int = 5000
    MAX_CONTEXT_CHUNKS: int = 50

    # ── Rate Limiting (F-10) ──
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 30

    # ── API Timeouts ──
    LLM_TIMEOUT_SEC: int = 120
    EMBEDDING_TIMEOUT_SEC: int = 60
    RERANKER_TIMEOUT_SEC: int = 15

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

    # ── Persistence (F-19) ──
    FAISS_INDEX_PATH: str = "~/.cache/rag_app/faiss.index"
    FAISS_META_PATH: str = "~/.cache/rag_app/faiss_meta.json"

    # ── Auth (F-03) ──
    # Email whitelist — comma-separated env var or empty for "anyone logged in"
    ALLOWED_EMAILS_ENV: str = "RAG_ALLOWED_EMAILS"

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
    #   - Auth required (SSO + email whitelist)
    #   - Generous rate limits
    #   - No quota cap
    # ============================================================
    PUBLIC_MODE: bool = True  # ← Set False if you want auth-protected app

    # ── Demo Quota (only enforced when PUBLIC_MODE=True) ──
    DEMO_DAILY_GLOBAL_QUOTA: int = 500       # Total queries/day across ALL users (was 100)
    DEMO_PER_USER_QUOTA: int = 15            # Queries per user per 15-min window (was 5)
    DEMO_PER_USER_WINDOW_SEC: int = 900      # 15 minutes
    # 🛡️ FIX: Local testing ke liye badhaya. Streamlit Cloud pe 1GB RAM
    # limitation hai, isliye 50MB se bade files avoid karo.
    # Local PC pe 200MB tak chal jayega.
    DEMO_MAX_FILE_SIZE_MB: int = 200         # Was 5, now 200 for local testing
    DEMO_MAX_QUERY_LENGTH: int = 500         # Shorter queries in demo

    # ── Branding (shows in footer + banner) ──
    BUILDER_NAME: str = "Harsh Bokde"
    BUILDER_ROLE: str = "AI/ML Engineer"
    GITHUB_URL: str = ""                     # Optional: set in secrets.toml
    LINKEDIN_URL: str = ""                   # Optional: set in secrets.toml


# Singleton instance
CONFIG = AppConfig()
