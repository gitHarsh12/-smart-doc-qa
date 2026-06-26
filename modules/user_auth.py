"""
=============================================================
🔐 Simple User Auth + Tracking (for public demo apps)
=============================================================
Bhai ke requirement ke according:
- Users enter email + password to use the app
- Data saved (so admin knows WHO used the app)
- Simple — no OAuth, no email verification
- Admin panel to view user list

Security notes:
- Passwords are HASHED (SHA256 + salt) — never stored in plain text
- Email stored as-is (for admin to see who used)
- Login state stored in st.session_state (per browser session)
- User log saved to JSON file (persists across app restarts)

Usage:
    from modules.user_auth import is_logged_in, show_login_form, get_current_user, log_user_activity

    if not is_logged_in():
        show_login_form()
        st.stop()

    # User is logged in — show app
    user = get_current_user()
    st.write(f"Welcome, {user['email']}")

    # Log activity
    log_user_activity(user['email'], "asked question", "What is RAG?")
=============================================================
"""

import os
import json
import hashlib
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================
USERS_FILE = Path(".users.json")  # Stores all registered users + activity log
SALT = "rag_app_2026_fixed_salt"  # Fixed salt for password hashing (demo only)

# Admin credentials (set in secrets.toml or env)
# Default: admin@rag.app / admin123 (CHANGE THIS in production!)
DEFAULT_ADMIN_EMAIL = "admin@rag.app"
DEFAULT_ADMIN_PASSWORD = "admin123"


def _hash_password(password: str) -> str:
    """Hash password with SHA256 + salt. Never store plain text."""
    return hashlib.sha256((password + SALT).encode()).hexdigest()


def _verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    return _hash_password(password) == hashed


def _read_users() -> Dict:
    """Read user database from JSON file."""
    if not USERS_FILE.exists():
        return {"users": {}, "activity_log": []}
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not read users file: {e}")
        return {"users": {}, "activity_log": []}


def _write_users(data: Dict) -> None:
    """Write user database to JSON file (atomic)."""
    try:
        tmp = USERS_FILE.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(USERS_FILE)
    except OSError as e:
        logger.error(f"Could not write users file: {e}")


# ============================================================
# Session State Helpers
# ============================================================
def is_logged_in() -> bool:
    """Check if current user is logged in."""
    try:
        import streamlit as st
        return st.session_state.get("user_email") is not None
    except Exception:
        return False


def is_admin() -> bool:
    """Check if current user is admin."""
    try:
        import streamlit as st
        return st.session_state.get("is_admin", False)
    except Exception:
        return False


def get_current_user() -> Optional[Dict]:
    """Get current logged-in user info."""
    try:
        import streamlit as st
        email = st.session_state.get("user_email")
        if not email:
            return None
        return {
            "email": email,
            "is_admin": st.session_state.get("is_admin", False),
            "login_time": st.session_state.get("login_time"),
        }
    except Exception:
        return None


def logout() -> None:
    """Log out current user."""
    try:
        import streamlit as st
        keys_to_remove = ["user_email", "is_admin", "login_time", "user_id"]
        for key in keys_to_remove:
            if key in st.session_state:
                del st.session_state[key]
    except Exception:
        pass


# ============================================================
# Login / Registration
# ============================================================
def register_or_login(email: str, password: str) -> tuple:
    """Register new user OR login existing user.

    Returns:
        (success: bool, message: str)
    """
    email = email.strip().lower()
    if not email or not password:
        return False, "Email aur password dono chahiye."

    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Sahi email address daalo (e.g., naam@gmail.com)."

    if len(password) < 4:
        return False, "Password kam se kam 4 character ka hona chahiye."

    data = _read_users()
    users = data.get("users", {})

    # Check admin login
    admin_email = os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    admin_pass = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)

    if email == admin_email.lower():
        if password == admin_pass:
            try:
                import streamlit as st
                st.session_state.user_email = email
                st.session_state.is_admin = True
                st.session_state.login_time = time.time()
                st.session_state.user_id = f"admin_{email}"
            except Exception:
                pass
            logger.info(f"👑 Admin login: {email}")
            return True, "Admin login successful!"
        else:
            return False, "Galat admin password."

    # Check if user exists
    if email in users:
        # Login existing user
        if not _verify_password(password, users[email]["password_hash"]):
            return False, "Galat password. Dobara try karo."
        users[email]["last_login"] = time.time()
        users[email]["login_count"] = users[email].get("login_count", 0) + 1
        data["users"] = users
        _write_users(data)
        logger.info(f"👋 User login: {email}")
    else:
        # Register new user
        users[email] = {
            "password_hash": _hash_password(password),
            "first_seen": time.time(),
            "last_login": time.time(),
            "login_count": 1,
            "queries_made": 0,
        }
        data["users"] = users
        _write_users(data)
        logger.info(f"🆕 New user registered: {email}")

    # Set session state
    try:
        import streamlit as st
        st.session_state.user_email = email
        st.session_state.is_admin = False
        st.session_state.login_time = time.time()
        st.session_state.user_id = f"user_{email}"
    except Exception:
        pass

    return True, "Login successful!"


def log_user_activity(email: str, action: str, details: str = "") -> None:
    """Log user activity (for admin panel)."""
    try:
        data = _read_users()
        entry = {
            "email": email,
            "action": action,
            "details": details[:200] if details else "",
            "timestamp": time.time(),
            "datetime": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        data.setdefault("activity_log", []).append(entry)

        # Keep only last 1000 entries (prevent file from growing forever)
        if len(data["activity_log"]) > 1000:
            data["activity_log"] = data["activity_log"][-1000:]

        # Increment user's query count
        if action == "asked_question" and email in data.get("users", {}):
            data["users"][email]["queries_made"] = data["users"][email].get("queries_made", 0) + 1
            data["users"][email]["last_active"] = time.time()

        _write_users(data)
    except Exception as e:
        logger.warning(f"Could not log activity: {e}")


# ============================================================
# Admin Panel Data
# ============================================================
def get_all_users() -> List[Dict]:
    """Get all registered users (admin only)."""
    data = _read_users()
    users = data.get("users", {})
    result = []
    for email, info in users.items():
        result.append({
            "email": email,
            "first_seen": info.get("first_seen", 0),
            "last_login": info.get("last_login", 0),
            "login_count": info.get("login_count", 0),
            "queries_made": info.get("queries_made", 0),
            "last_active": info.get("last_active", 0),
        })
    # Sort by last_active (most recent first)
    result.sort(key=lambda x: x.get("last_active", 0), reverse=True)
    return result


def get_activity_log(limit: int = 50) -> List[Dict]:
    """Get recent activity log (admin only)."""
    data = _read_users()
    log = data.get("activity_log", [])
    return log[-limit:][::-1]  # Last N entries, most recent first


def get_stats() -> Dict:
    """Get user statistics (admin only)."""
    data = _read_users()
    users = data.get("users", {})
    log = data.get("activity_log", [])

    # Active users (last 24 hours)
    now = time.time()
    active_24h = sum(1 for u in users.values()
                     if now - u.get("last_active", 0) < 86400)

    return {
        "total_users": len(users),
        "active_24h": active_24h,
        "total_queries": sum(u.get("queries_made", 0) for u in users.values()),
        "total_logins": sum(u.get("login_count", 0) for u in users.values()),
        "log_entries": len(log),
    }
