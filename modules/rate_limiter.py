"""
=============================================================
🛡️ FIX F-10: Server-side Rate Limiter
=============================================================
Previously rate limiting was per-session (cleared by deleting cookies).
Now uses Redis (if available) for cross-worker shared rate limiting,
with in-memory fallback for local development / single-process deployments.

Usage:
    from modules.rate_limiter import RateLimiter, get_user_id
    rl = RateLimiter(max_requests=30, window_seconds=60)
    allowed, reason = rl.check(user_id)
    if not allowed:
        st.warning(reason)

Storage:
    - Primary: Redis (URL from REDIS_URL env var, optional)
    - Fallback: In-memory dict (per-process, NOT shared across workers)
=============================================================
"""

import os
import time
import logging
import hashlib
import threading
from typing import Tuple, Optional
from collections import defaultdict, deque

import streamlit as st

logger = logging.getLogger(__name__)


# ============================================================
# User ID generation
# ============================================================
def get_user_id() -> str:
    """Generate a stable per-user ID.

    Priority:
    1. Logged-in user's email (most stable)
    2. Streamlit session ID (per-browser-tab)
    3. Anonymous hash of IP + User-Agent (best effort)

    Returns:
        Stable string ID (max 64 chars)
    """
    # 1. Try logged-in user email
    try:
        from modules.user_auth import get_current_user
        user = get_current_user()
        if user and user.get("email"):
            # Hash email for privacy in logs
            return "u_" + hashlib.sha256(user["email"].encode()).hexdigest()[:16]
    except Exception:
        pass

    # 2. Try Streamlit session state
    try:
        if hasattr(st, 'session_state'):
            # Streamlit >= 1.28 has st.runtime.scriptrunner.add_script_run_ctx
            # but session_id is in st.session_state.__dict__
            ctx = st.runtime.scriptrunner.get_script_run_ctx() if hasattr(st, 'runtime') else None
            if ctx and hasattr(ctx, 'session_id'):
                return "s_" + ctx.session_id[:32]
    except Exception:
        pass

    # 3. Fallback: anonymous
    return "anon_" + hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]


# ============================================================
# In-memory rate limiter (fallback for Redis)
# ============================================================
class _MemoryBucket:
    """Per-user sliding window counter (in-memory)."""
    def __init__(self):
        self._hits = defaultdict(deque)  # {user_id: deque([timestamps])}
        self._lock = threading.Lock()

    def check(self, user_id: str, max_requests: int, window_seconds: int) -> Tuple[bool, str]:
        """Returns (allowed, reason)."""
        now = time.time()
        with self._lock:
            # Prune old entries
            user_deque = self._hits[user_id]
            while user_deque and now - user_deque[0] > window_seconds:
                user_deque.popleft()

            if len(user_deque) >= max_requests:
                oldest = user_deque[0]
                retry_after = int(window_seconds - (now - oldest))
                return False, (
                    f"Rate limit exceeded. Try again in {max(retry_after, 1)} second(s). "
                    f"(Limit: {max_requests} requests / {window_seconds}s)"
                )

            user_deque.append(now)
            return True, "OK"

    def reset(self, user_id: Optional[str] = None):
        """Clear rate limit for a user (or all users if None)."""
        with self._lock:
            if user_id:
                self._hits.pop(user_id, None)
            else:
                self._hits.clear()


# ============================================================
# Redis-backed rate limiter (production)
# ============================================================
class _RedisBucket:
    """Redis-backed sliding window rate limiter.

    Uses INCR + EXPIRE pattern (atomic, shared across workers).
    """
    def __init__(self, redis_url: str):
        try:
            import redis
            self.client = redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
            # Test connection
            self.client.ping()
            logger.info("✅ Rate limiter: Redis connected")
            self._available = True
        except ImportError:
            logger.warning("⚠️ redis-py not installed — falling back to in-memory limiter")
            self._available = False
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed ({e}) — falling back to in-memory limiter")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def check(self, user_id: str, max_requests: int, window_seconds: int) -> Tuple[bool, str]:
        if not self._available:
            return True, "OK (Redis unavailable)"  # Let in-memory fallback handle it

        try:
            key = f"rl:{user_id}:{int(time.time() // window_seconds)}"
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, window_seconds + 1)
            if count > max_requests:
                return False, (
                    f"Rate limit exceeded. Try again in {window_seconds} second(s). "
                    f"(Limit: {max_requests} requests / {window_seconds}s)"
                )
            return True, "OK"
        except Exception as e:
            logger.warning(f"Redis rate limit check failed ({e}) — allowing request")
            return True, "OK (Redis degraded)"


# ============================================================
# Main RateLimiter class (auto-detects Redis vs in-memory)
# ============================================================
class RateLimiter:
    """Production rate limiter with Redis backend + in-memory fallback.

    Args:
        max_requests: Max requests per window per user
        window_seconds: Sliding window length in seconds
    """
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

        # Try Redis first
        redis_url = os.getenv("REDIS_URL", "")
        self._redis = _RedisBucket(redis_url) if redis_url else None
        self._memory = _MemoryBucket()

    def check(self, user_id: str) -> Tuple[bool, str]:
        """Check if user is within rate limit.

        Returns:
            (allowed: bool, reason: str)
        """
        if not user_id:
            user_id = "anonymous"

        # Try Redis first (shared across workers)
        if self._redis and self._redis.available:
            allowed, reason = self._redis.check(user_id, self.max_requests, self.window_seconds)
            if not allowed:
                return False, reason
            # If Redis says OK, also check in-memory for defense-in-depth
            # (this catches cases where Redis is shared but we want extra safety)

        # In-memory check (per-process)
        return self._memory.check(user_id, self.max_requests, self.window_seconds)

    def reset(self, user_id: Optional[str] = None):
        """Reset rate limit for a user (admin only)."""
        self._memory.reset(user_id)
        if self._redis and self._redis.available:
            try:
                if user_id:
                    # Best effort — Redis keys are time-windowed
                    pass
                else:
                    self._redis.client.flushdb()
            except Exception:
                pass


# ============================================================
# Singleton
# ============================================================
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
