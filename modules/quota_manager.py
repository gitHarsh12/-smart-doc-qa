"""
=============================================================
🌐 Public Demo Mode — Quota Manager
=============================================================
When the app is PUBLIC (no auth), we need to protect API credits
from being burned by random visitors / bots.

This module enforces:
1. Daily global quota (e.g., 100 queries/day total across all users)
2. Per-user quota (e.g., 5 queries per 15 minutes per user)
3. Graceful "quota exceeded" messages (no API errors for recruiter)

Storage: JSON file in working directory.
On Streamlit Cloud, this file persists as long as the app runs.
If app restarts, quota resets — acceptable for a demo app.

Usage:
    from modules.quota_manager import QuotaManager
    qm = QuotaManager()

    user_id = "anon_abc123"  # from rate_limiter.get_user_id()
    allowed, reason = qm.check_and_increment(user_id)
    if not allowed:
        st.warning(reason)
        return

    # ... proceed with query ...

    # For sidebar display:
    stats = qm.get_stats()
    st.sidebar.metric("Today's queries", f"{stats['used']}/{stats['daily_limit']}")
=============================================================
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Tuple, Dict, Optional
from pathlib import Path

from .config import CONFIG

logger = logging.getLogger(__name__)


class QuotaManager:
    """File-based quota tracker for public demo mode.

    Enforces:
    - Daily global quota (across all users)
    - Per-user sliding window quota

    Thread-safe via file locking (best-effort on Streamlit Cloud).
    """

    def __init__(self, state_file: str = ".quota_state.json"):
        self.state_file = Path(state_file)
        self.daily_limit = CONFIG.DEMO_DAILY_GLOBAL_QUOTA
        self.per_user_limit = CONFIG.DEMO_PER_USER_QUOTA
        self.per_user_window = CONFIG.DEMO_PER_USER_WINDOW_SEC
        self._lock = threading.Lock()

        # Initialize state file if missing
        if not self.state_file.exists():
            self._write_state(self._fresh_state())

    def _fresh_state(self) -> Dict:
        """Create a fresh state dict for a new day."""
        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "global_count": 0,
            "per_user": {},  # {user_id: [timestamps]}
            "last_reset": time.time(),
        }

    def _read_state(self) -> Dict:
        """Read state from JSON file (with error recovery)."""
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # Reset if date changed (new day = fresh quota)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if state.get("date") != today:
                logger.info(f"🌅 New day ({today}) — resetting quota")
                state = self._fresh_state()
                self._write_state(state)
            return state
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Quota state read failed ({e}), starting fresh")
            state = self._fresh_state()
            self._write_state(state)
            return state

    def _write_state(self, state: Dict) -> None:
        """Write state to JSON file (atomic-ish via temp file)."""
        try:
            tmp_file = self.state_file.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            tmp_file.replace(self.state_file)
        except OSError as e:
            logger.error(f"Quota state write failed: {e}")

    def check_and_increment(self, user_id: str) -> Tuple[bool, str]:
        """Check if user can query, then increment counters.

        Returns:
            (allowed: bool, reason: str)
            - allowed=True, reason="OK" — proceed with query
            - allowed=False, reason="..." — show reason to user
        """
        if not CONFIG.PUBLIC_MODE:
            return True, "OK"  # No quota in private mode

        if not user_id or not isinstance(user_id, str):
            user_id = "anonymous"

        with self._lock:
            state = self._read_state()
            now = time.time()

            # ── Check 1: Daily global quota ──
            if state["global_count"] >= self.daily_limit:
                logger.warning(f"Daily global quota hit: {state['global_count']}/{self.daily_limit}")
                return False, (
                    f"🌙 **Daily demo quota reached** ({self.daily_limit} queries/day).\n\n"
                    f"This is a portfolio demo app with limited API credits. "
                    f"Please come back tomorrow to test more, or contact the builder "
                    f"for a private demo."
                )

            # ── Check 2: Per-user sliding window ──
            user_history = state["per_user"].get(user_id, [])
            # Prune old timestamps
            user_history = [t for t in user_history if now - t < self.per_user_window]
            if len(user_history) >= self.per_user_limit:
                oldest = user_history[0]
                retry_after = int(self.per_user_window - (now - oldest))
                logger.info(f"Per-user quota hit for {user_id}: {len(user_history)}/{self.per_user_limit}")
                return False, (
                    f"⏱️ **Rate limit**: You've used {self.per_user_limit} queries in the last "
                    f"{self.per_user_window // 60} minutes. "
                    f"Try again in ~{max(retry_after // 60, 1)} minute(s).\n\n"
                    f"_This keeps the demo fair for all visitors._"
                )

            # ── All checks passed — increment counters ──
            user_history.append(now)
            state["per_user"][user_id] = user_history
            state["global_count"] += 1
            self._write_state(state)

            logger.info(
                f"Quota OK: user={user_id}, "
                f"global={state['global_count']}/{self.daily_limit}, "
                f"user_window={len(user_history)}/{self.per_user_limit}"
            )
            return True, "OK"

    def get_stats(self) -> Dict:
        """Get current quota stats for UI display."""
        if not CONFIG.PUBLIC_MODE:
            return {"mode": "private", "used": 0, "daily_limit": 0, "remaining": 0}

        state = self._read_state()
        used = state["global_count"]
        return {
            "mode": "public",
            "used": used,
            "daily_limit": self.daily_limit,
            "remaining": max(0, self.daily_limit - used),
            "per_user_limit": self.per_user_limit,
            "per_user_window_min": self.per_user_window // 60,
            "active_users_today": len(state["per_user"]),
        }

    def get_user_remaining(self, user_id: str) -> int:
        """How many queries this user has left in current window."""
        if not CONFIG.PUBLIC_MODE:
            return -1  # unlimited

        state = self._read_state()
        now = time.time()
        user_history = [t for t in state["per_user"].get(user_id, [])
                        if now - t < self.per_user_window]
        return max(0, self.per_user_limit - len(user_history))

    def reset(self) -> None:
        """Force-reset quota (admin only — call from a hidden admin page)."""
        with self._lock:
            self._write_state(self._fresh_state())
            logger.info("🔄 Quota manually reset")


# Singleton
_quota_manager: Optional[QuotaManager] = None


def get_quota_manager() -> QuotaManager:
    """Get singleton QuotaManager instance."""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager
