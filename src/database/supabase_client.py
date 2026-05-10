"""
Supabase client wrapper for the Ishikawa Knowledge System backend.

Reads SUPABASE_URL and SUPABASE_SERVICE_KEY from environment. If neither
is set the client is disabled and all save calls are silently skipped —
this lets the Neo4j path work independently during development.
"""

from __future__ import annotations

import os
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Lazily loaded so the import itself never fails even if supabase-py
# is not installed (the feature degrades gracefully).
_supabase_module: Any = None
_client: Any = None


def _load_supabase() -> Any:
    global _supabase_module
    if _supabase_module is None:
        try:
            import supabase as _sb  # noqa: PLC0415
            _supabase_module = _sb
        except ImportError:
            logger.warning(
                "supabase-py is not installed. "
                "Run `pip install supabase` to enable Supabase saves."
            )
            _supabase_module = False  # sentinel — don't retry
    return _supabase_module


def get_supabase_client() -> Any | None:
    """
    Return a connected Supabase client, or None if not configured.

    Uses the service-role key so the backend can write rows on behalf of
    any user while still populating user_id / org_id for RLS queries.
    """
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "").strip()
    # Prefer the service-role key (bypasses RLS); fall back to anon/publishable key.
    key = (
        os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
    )

    if not url or not key:
        logger.debug(
            "SUPABASE_URL / SUPABASE_SERVICE_KEY not set — "
            "Supabase saves are disabled."
        )
        return None

    sb = _load_supabase()
    if not sb:
        return None

    try:
        _client = sb.create_client(url, key)
        logger.info("Supabase client initialised (url=%s...)", url[:40])
        return _client
    except Exception as exc:
        logger.error("Supabase client creation failed: %s", exc)
        return None


def is_supabase_enabled() -> bool:
    """Quick check — True only if both env vars are present AND supabase-py is installed."""
    return get_supabase_client() is not None
