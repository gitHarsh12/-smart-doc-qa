"""
=============================================================
🛡️ FIX F-16: Structured JSON Logging + Sentry Integration
=============================================================
Previous logging was basic INFO-level stdout. Plain text logs
made debugging hard on Streamlit Cloud.

Yeh module:
1. Emits logs as JSON (easy to parse, supports structured fields)
2. Optional Sentry integration for error tracking
3. Filters API keys from log messages (defense in depth)

Usage:
    # app.py top me:
    from modules.logging_setup import setup_logging
    setup_logging()

    # Then use as normal:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("API call", extra={"user_id": "harsh@x.com", "tokens": 432})
=============================================================
"""

import os
import sys
import json
import re
import logging
from datetime import datetime, timezone
from typing import Optional


# Patterns to scrub from log messages
_KEY_PATTERNS = [
    (re.compile(r'nvapi-[A-Za-z0-9_-]{10,}'), 'nvapi-****'),
    # Groq keys use gsk_ (underscore) prefix
    (re.compile(r'gsk_[A-Za-z0-9_-]{10,}'), 'gsk_****'),
    (re.compile(r'gsk-[A-Za-z0-9_-]{10,}'), 'gsk-****'),
    (re.compile(r'sk-or-[A-Za-z0-9_-]{10,}'), 'sk-or-****'),
    (re.compile(r'Bearer\s+[A-Za-z0-9_.-]{10,}'), 'Bearer ****'),
]


def _scrub_secrets(text: str) -> str:
    """Remove API keys / Bearer tokens from a string."""
    if not text:
        return text
    for pattern, replacement in _KEY_PATTERNS:
        text = pattern.sub(replacement, text)
    # Also scrub actual env-var values
    for env_key in ["NVIDIA_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"]:
        val = os.getenv(env_key, "")
        if val and val in text:
            text = text.replace(val, f"{env_key}=****")
    return text


class JSONFormatter(logging.Formatter):
    """Emit logs as JSON for easier parsing in Streamlit Cloud log viewer.

    Each log line is a JSON object with:
    - timestamp (ISO 8601 UTC)
    - level
    - logger name
    - message (scrubbed of secrets)
    - module + line
    - optional fields from extra={...}
    - exception (if any, with traceback)
    """

    # Standard fields to extract from record
    _EXTRA_FIELDS = (
        "user_id", "request_id", "provider", "tokens",
        "latency_ms", "model", "document_id", "cache_hit",
    )

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub_secrets(record.getMessage()),
            "module": record.module,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        for key in self._EXTRA_FIELDS:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # Sanitize any non-JSON-serializable values
        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO", enable_sentry: bool = True) -> logging.Logger:
    """Initialize structured JSON logging + optional Sentry.

    Args:
        level: Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
        enable_sentry: Try to init Sentry if SENTRY_DSN env var is set

    Returns:
        Root logger
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)

    # Sentry integration (optional)
    if enable_sentry:
        sentry_dsn = os.getenv("SENTRY_DSN")
        if sentry_dsn:
            try:
                import sentry_sdk
                sentry_sdk.init(
                    dsn=sentry_dsn,
                    traces_sample_rate=0.1,  # 10% of requests traced
                    environment=os.getenv("SENTRY_ENV", "production"),
                    before_send=_sentry_before_send,
                )
                logging.info("Sentry initialized", extra={"sentry": True})
            except ImportError:
                logging.warning("sentry-sdk not installed — skipping Sentry init")
            except Exception as e:
                logging.warning(f"Sentry init failed: {e}")

    return root_logger


def _sentry_before_send(event: dict, hint: dict) -> Optional[dict]:
    """Filter Sentry events — scrub secrets, drop noisy events."""
    # Drop info-level events (we only want warnings+)
    if event.get("level") == "info":
        return None
    # Scrub API keys from exception messages
    if "exception" in event:
        for exc in event["exception"].get("values", []):
            if "value" in exc:
                exc["value"] = _scrub_secrets(exc["value"])
    return event
