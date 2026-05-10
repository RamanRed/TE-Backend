"""
Sync Prisma client singleton.
Connect once on first use, reuse across requests.
"""

from __future__ import annotations

from prisma import Prisma
from ..utils.logging import get_logger

logger = get_logger(__name__)

_client: Prisma | None = None


def get_prisma() -> Prisma:
    """Return a connected sync Prisma client (creates connection on first call)."""
    global _client
    if _client is None:
        _client = Prisma()
        _client.connect()
        logger.info("Prisma client connected to Supabase")
    return _client


def disconnect_prisma() -> None:
    global _client
    if _client is not None:
        try:
            _client.disconnect()
            logger.info("Prisma client disconnected")
        except Exception as exc:
            logger.warning("Prisma disconnect error: %s", exc)
        finally:
            _client = None
