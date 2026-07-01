"""
=============================================================
🔐 User Authentication Module (F-03)
=============================================================
Simple email + password authentication with:
- SHA256 + per-user salt password hashing
- Email whitelist support (RAG_ALLOWED_EMAILS env var)
- Activity logging (login, page_view, asked_question)
- Admin role detection (RAG_ADMIN_EMAILS env var)
- File-based storage (JSON, atomic writes)
- Thread-safe via file locking

Usage:
    from modules.user_auth import register_or_login, is_logged_in
    if not is_logged_in():
        # Show login form
        ...
    register_or_login(email, password)

Storage:
    ~/.smart_doc_qa/users.json    — User accounts (hashed passwords)
    ~/.smart_doc_qa/activity.json — Activity log
=============================================================
"""

import os
import json
import time
import uuid
import hashlib
import secrets
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from pathlib import Path

import streamlit as st

from .config import CONFIG

logger = logging.getLogger(__name__)


# ============================================================
# Storage paths (XDG-compatible, user-writable)
# ============================================================
_DATA_DIR = Path(os.getenv("RAG_DATA_DIR", Path.home() / ".smart_doc_qa"))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = _DATA_DIR / "users.json"
ACTIVITY_FILE = _DATA_DIR / "activity.json"

# In-memory cache (refreshed on writes)
_users_cache: Optional[Dict] = None
_activity_cache: Optional[List] = None
_lock = threading.Lock()


# ============================================================
# Password hashing (SHA256 + per-user salt)
# ============================================================
def _hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    """Hash password with salt using SHA256.

    Args:
        password: Plain text password
        salt: Hex salt (if None, generate new)

    Returns:
        (hashed_password_hex, salt_hex)
    """
    if salt is None:
        salt = secrets.token_hex(16)
    # PBKDF2-style: 10000 rounds of SHA256
    hashed = password
    for _ in range(10000):
        hashed = hashlib.sha256((hashed + salt).encode()).hexdigest()
    return hashed, salt


def _verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify password against hash."""
    computed, _ = _hash_password(password, salt)
    # Constant-time comparison (prevents timing attacks)
    return secrets.compare_digest(computed, hashed)


# ============================================================
# JSON storage (atomic writes via temp file)
# ============================================================
def _read_users() -> Dict:
    """Read users from JSON file (cached)."""
    global _users_cache
    if _users_cache is not None:
        return _users_cache
    try:
        if USERS_FILE.exists():
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                _users_cache = json.load(f)
        else:
            _users_cache = {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read users file ({e}) — starting fresh")
        _users_cache = {}
    return _users_cache


def _write_users(users: Dict) -> None:
    """Write users to JSON file (atomic via temp file)."""
    global _users_cache
    with _lock:
        try:
            tmp_file = USERS_FILE.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
            tmp_file.replace(USERS_FILE)
            _users_cache = users
        except OSError as e:
            logger.error(f"Failed to write users file: {e}")
            raise


def _read_activity() -> List:
    """Read activity log from JSON file."""
    global _activity_cache
    if _activity_cache is not None:
        return _activity_cache
    try:
        if ACTIVITY_FILE.exists():
            with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
                _activity_cache = json.load(f)
        else:
            _activity_cache = []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read activity file ({e}) — starting fresh")
        _activity_cache = []
    return _activity_cache


def _write_activity(activity: List) -> None:
    """Write activity log to JSON file (keep last 1000 entries)."""
    global _activity_cache
    with _lock:
        try:
            # Keep only last 1000 entries
            trimmed = activity[-1000:]
            tmp_file = ACTIVITY_FILE.with_suffix('.tmp')
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(trimmed, f, indent=2, ensure_ascii=False)
            tmp_file.replace(ACTIVITY_FILE)
            _activity_cache = trimmed
        except OSError as e:
            logger.error(f"Failed to write activity file: {e}")


# ============================================================
# Email validation / whitelist
# ============================================================
def _is_email_allowed(email: str) -> bool:
    """Check if email is in whitelist (if whitelist is set).

    If RAG_ALLOWED_EMAILS env var is empty, anyone can register.
    If set, only those emails can log in.
    """
    if not email:
        return False
    whitelist = os.getenv(CONFIG.ALLOWED_EMAILS_ENV, "").strip()
    if not whitelist:
        return True  # No whitelist = anyone allowed
    allowed = [e.strip().lower() for e in whitelist.split(",") if e.strip()]
    return email.lower() in allowed


def _get_allowed_emails_hint() -> str:
    """Get a human-readable hint about the current whitelist state.

    Returns:
        - "No whitelist active (anyone can register)" if empty
        - "Allowed emails: a@x.com, b@y.com" if whitelist is set
    """
    whitelist = os.getenv(CONFIG.ALLOWED_EMAILS_ENV, "").strip()
    if not whitelist:
        return "No whitelist active (anyone can register)"
    allowed = [e.strip() for e in whitelist.split(",") if e.strip()]
    if len(allowed) <= 3:
        return f"Allowed emails: {', '.join(allowed)}"
    return f"Allowed emails: {', '.join(allowed[:3])}, ... (+{len(allowed) - 3} more)"


def _is_admin_email(email: str) -> bool:
    """Check if email is in admin list."""
    if not email:
        return False
    admins = os.getenv("RAG_ADMIN_EMAILS", "").strip()
    if not admins:
        # First registered user becomes admin automatically
        users = _read_users()
        if len(users) == 0:
            return True
        # Otherwise, the first user in the users file is admin
        first_email = sorted(users.keys())[0]
        return email.lower() == first_email.lower()
    admin_list = [e.strip().lower() for e in admins.split(",") if e.strip()]
    return email.lower() in admin_list


def _is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    if not email or len(email) > 254:
        return False
    # Simple regex (good enough for demo, not for production SMTP)
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# ============================================================
# Authentication functions
# ============================================================
def register_or_login(email: str, password: str) -> Tuple[bool, str]:
    """Register a new user OR login existing user.

    Args:
        email: User email
        password: Plain text password

    Returns:
        (success: bool, message: str)
    """
    # Validate inputs
    email = (email or "").strip().lower()
    if not _is_valid_email(email):
        return False, "Invalid email format."
    if not password or len(password) < 4:
        return False, "Password must be at least 4 characters."
    if len(password) > 128:
        return False, "Password too long (max 128 chars)."

    # Check whitelist
    if not _is_email_allowed(email):
        hint = _get_allowed_emails_hint()
        logger.warning(f"Login attempt for non-whitelisted email: {email} | {hint}")
        return False, (
            f"⚠️ This email is not authorized to use this app.\n\n"
            f"**Your email:** `{email}`\n\n"
            f"**Current whitelist:** {hint}\n\n"
            f"**To fix this:**\n"
            f"1. Open `.streamlit/secrets.toml` (or Streamlit Cloud → Settings → Secrets)\n"
            f"2. Find `RAG_ALLOWED_EMAILS` line\n"
            f"3. Either:\n"
            f"   - Set it to empty: `RAG_ALLOWED_EMAILS = \"\"` (anyone can register)\n"
            f"   - Or add your email: `RAG_ALLOWED_EMAILS = \"{email},other@email.com\"`\n"
            f"4. Save and restart the app"
        )

    users = _read_users()
    now = int(time.time())

    if email in users:
        # Existing user — verify password
        user = users[email]
        if not _verify_password(password, user["password_hash"], user["salt"]):
            logger.warning(f"Failed login attempt for {email}")
            return False, "Incorrect password."
        # Update last login
        user["last_login"] = now
        user["last_active"] = now
        user["login_count"] = user.get("login_count", 0) + 1
        users[email] = user
        _write_users(users)
        logger.info(f"User logged in: {email}")
    else:
        # New user — register
        is_first_user = len(users) == 0
        hashed, salt = _hash_password(password)
        users[email] = {
            "email": email,
            "password_hash": hashed,
            "salt": salt,
            "is_admin": is_first_user or _is_admin_email(email),
            "first_seen": now,
            "last_login": now,
            "last_active": now,
            "login_count": 1,
            "query_count": 0,
        }
        _write_users(users)
        logger.info(f"New user registered: {email} (admin={users[email]['is_admin']})")

    # Set session state
    st.session_state["user_email"] = email
    st.session_state["user_is_admin"] = users[email]["is_admin"]

    # Log activity
    _log_activity_internal(email, "login")

    return True, f"Welcome, {email}! Logged in successfully."


def logout() -> None:
    """Logout current user."""
    email = st.session_state.get("user_email")
    if email:
        _log_activity_internal(email, "logout")
        logger.info(f"User logged out: {email}")
    st.session_state.pop("user_email", None)
    st.session_state.pop("user_is_admin", None)


def is_logged_in() -> bool:
    """Check if current session has a logged-in user."""
    return bool(st.session_state.get("user_email"))


def is_admin() -> bool:
    """Check if current user is admin."""
    return bool(st.session_state.get("user_is_admin"))


def get_current_user() -> Optional[Dict]:
    """Get current logged-in user dict (or None)."""
    email = st.session_state.get("user_email")
    if not email:
        return None
    users = _read_users()
    user = users.get(email)
    if not user:
        return None
    # Update last_active (best effort, don't write every time to avoid file thrash)
    now = int(time.time())
    if now - user.get("last_active", 0) > 60:  # Update at most once per minute
        user["last_active"] = now
        try:
            _write_users(users)
        except Exception:
            pass
    return {
        "email": user["email"],
        "is_admin": user.get("is_admin", False),
        "first_seen": user.get("first_seen", 0),
        "last_login": user.get("last_login", 0),
        "last_active": user.get("last_active", 0),
        "login_count": user.get("login_count", 0),
        "query_count": user.get("query_count", 0),
    }


# ============================================================
# Activity logging
# ============================================================
def _log_activity_internal(email: str, action: str, details: str = "") -> None:
    """Internal: append activity entry."""
    activity = _read_activity()
    activity.append({
        "datetime": datetime.now(timezone.utc).isoformat(),
        "timestamp": int(time.time()),
        "email": email,
        "action": action,
        "details": details[:500] if details else "",  # Cap length
    })
    _write_activity(activity)


def log_user_activity(email: str, action: str, details: str = "") -> None:
    """Log user activity (public API).

    Args:
        email: User email
        action: Action name (e.g., "page_view", "asked_question", "logout")
        details: Optional details (capped at 500 chars)
    """
    if not email:
        return
    _log_activity_internal(email, action, details)

    # Update query_count if action is "asked_question"
    if action == "asked_question":
        users = _read_users()
        if email in users:
            users[email]["query_count"] = users[email].get("query_count", 0) + 1
            users[email]["last_active"] = int(time.time())
            _write_users(users)


# ============================================================
# Admin functions
# ============================================================
def get_all_users() -> List[Dict]:
    """Get list of all users (admin only)."""
    users = _read_users()
    return [
        {
            "email": u["email"],
            "first_seen": u.get("first_seen", 0),
            "last_login": u.get("last_login", 0),
            "login_count": u.get("login_count", 0),
            "query_count": u.get("query_count", 0),
            "last_active": u.get("last_active", 0),
        }
        for u in users.values()
    ]


def get_activity_log(limit: int = 50) -> List[Dict]:
    """Get recent activity log (admin only)."""
    activity = _read_activity()
    return activity[-limit:][::-1]  # Most recent first


def get_stats() -> Dict:
    """Get user stats for admin panel."""
    users = _read_users()
    activity = _read_activity()
    now = int(time.time())

    # Active in last 24h
    active_24h = sum(1 for u in users.values() if now - u.get("last_active", 0) < 86400)

    # Total queries
    total_queries = sum(u.get("query_count", 0) for u in users.values())

    # Total logins
    total_logins = sum(u.get("login_count", 0) for u in users.values())

    return {
        "total_users": len(users),
        "active_24h": active_24h,
        "total_queries": total_queries,
        "total_logins": total_logins,
    }
