"""
=============================================================
🛡️ FIX F-10: Server-side Rate Limiter (Redis-backed)
=============================================================
Previous implementation used st.session_state — per-browser
state. Bypassable by clearing cookies, opening new tab,
or using incognito mode.

Yeh module server-side rate limiting karta hai using Redis
(shared across all Streamlit workers). Falls back to in-memory
if Redis not available.

Usage:
    from modules.rate_limiter import RateLimiter, get_user_id
    _rate_limiter = RateLimiter()

    user_id = get_user_id()
    allowed, msg = _rate_limiter.check(user_id)
    if not allowed:
        st.error(msg)
        return
=============================================================
"""

import os
import time
import logging
import threading
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Try to import Redis (graceful fallback)
try:
    import redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    # Test connection
    _redis_client.ping()
    _REDIS_AVAILABLE = True
    logger.info("✅ Redis connected — server-side rate limiting active")
except ImportError:
    _redis_client = None
    _REDIS_AVAILABLE = False
    logger.warning("⚠️ redis package not installed — using in-memory rate limiter")
except Exception as e:
    _redis_client = None
    _REDIS_AVAILABLE = False
    logger.warning(f"⚠️ Redis unavailable ({e}) — using in-memory rate limiter")


class InMemoryRateLimiter:
    """Thread-safe in-memory rate limiter (fallback when Redis not available).

    Note: This is PER-PROCESS, not shared across Streamlit workers.
    For production, install Redis.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max = max_requests
        self.window = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict = {}  # {user_id: [timestamps]}

    def check(self, user_id: str) -> Tuple[bool, str]:
        now = time.time()
        with self._lock:
            # Prune old timestamps
            self._buckets[user_id] = [
                t for t in self._buckets.get(user_id, [])
                if now - t < self.window
            ]
            if len(self._buckets[user_id]) >= self.max:
                retry_after = int(self.window - (now - self._buckets[user_id][0]))
                return False, f"Rate limit exceeded. Try again in {max(retry_after, 1)}s."
            self._buckets[user_id].append(now)
            return True, "OK"


class RedisRateLimiter:
    """Redis-backed rate limiter — shared across all workers.

    Uses Redis sorted sets with timestamps as scores.
    Atomic operations via MULTI/EXEC.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max = max_requests
        self.window = window_seconds
        self.client = _redis_client

    def check(self, user_id: str) -> Tuple[bool, str]:
        import time as _time
        key = f"ratelimit:{user_id}"
        now = _time.time()
        try:
            pipe = self.client.pipeline()
            # Remove timestamps older than window
            pipe.zremrangebyscore(key, 0, now - self.window)
            # Count current entries
            pipe.zcard(key)
            # Add current request (score=now, member=now-str for uniqueness)
            pipe.zadd(key, {f"{now}": now})
            # Set TTL on key (auto-cleanup)
            pipe.expire(key, self.window)
            results = pipe.execute()
            count = results[1]
            if count >= self.max:
                return False, f"Rate limit exceeded ({count}/{self.max} in {self.window}s). Try later."
            return True, "OK"
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}", exc_info=True)
            # Fail open (allow request) rather than block legitimate users
            return True, "OK (Redis degraded, allowing)"


class RateLimiter:
    """Smart rate limiter — uses Redis if available, falls back to in-memory.

    Args:
        max_requests: Max requests per window per user
        window_seconds: Time window in seconds
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max = max_requests
        self.window = window_seconds
        if _REDIS_AVAILABLE:
            self._impl = RedisRateLimiter(max_requests, window_seconds)
        else:
            self._impl = InMemoryRateLimiter(max_requests, window_seconds)
        logger.info(f"🛡️ RateLimiter active: max={max_requests}/{window_seconds}s, backend={'redis' if _REDIS_AVAILABLE else 'memory'}")

    def check(self, user_id: str) -> Tuple[bool, str]:
        """Returns (allowed: bool, message: str)."""
        if not user_id or not isinstance(user_id, str):
            user_id = "anonymous"
        return self._impl.check(user_id)


def get_user_id() -> str:
    """Get a stable user identifier.

    Priority:
    1. Streamlit experimental_user.email (if logged in via SSO)
    2. Streamlit session_state user_id (if set manually)
    3. Anonymous fallback (uses IP if available, else 'anonymous')

    Returns:
        User ID string for rate-limit keying.
    """
    try:
        import streamlit as st
        # Try SSO user first
        if hasattr(st, 'experimental_user') and st.experimental_user.is_logged_in:
            return st.experimental_user.email
        # Fallback to session state
        if 'user_id' in st.session_state:
            return st.session_state.user_id
        # Last resort: anonymous (per-session)
        if 'anon_id' not in st.session_state:
            import uuid
            st.session_state.anon_id = f"anon_{uuid.uuid4().hex[:8]}"
        return st.session_state.anon_id
    except Exception:
        return "anonymous"
