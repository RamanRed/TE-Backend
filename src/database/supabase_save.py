"""
Supabase persistence layer — powered by Prisma.

Inserts the three-row transaction:
  1. analysis_sessions
  2. saved_ishikawa
  3. saved_five_whys
All rows carry the (user_id, master_user_id, org_id) security triplet.
"""

from __future__ import annotations

from typing import Any
import json

from ..utils.logging import get_logger
from .prisma_client import get_prisma

logger = get_logger(__name__)


class SupabaseSaver:
    """Persists a finalized analysis to Supabase via Prisma."""

    def save_analysis(
        self,
        *,
        user_id: str,
        master_user_id: str,
        org_id: str,
        query: str,
        domain: str,
        past_record: int | None,
        session_title: str | None,
        ishikawa: list[dict[str, Any]],
        five_whys: list[dict[str, Any]],
        main_cause: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Insert session + ishikawa + five_whys rows.
        Returns dict with session_id, ishikawa_id, five_whys_id, skipped.
        """
        try:
            db = get_prisma()
        except Exception as exc:
            logger.error("Prisma connection failed: %s", exc)
            return {"session_id": None, "ishikawa_id": None, "five_whys_id": None, "skipped": True}

        # ── Defensive coercions ──────────────────────────────────────────
        if not isinstance(ishikawa, list):
            ishikawa = []
        if not isinstance(five_whys, list):
            five_whys = []
        if not isinstance(main_cause, list):
            main_cause = []

        session_id = ishikawa_id = five_whys_id = None

        try:
            # ── 1. analysis_sessions ──────────────────────────────────
            session = db.analysissession.create(
                data={
                    "userId": user_id,
                    "masterUserId": master_user_id,
                    "orgId": org_id,
                    "query": query,
                    "domain": domain or None,
                    "pastRecord": past_record,
                    "title": session_title or None,
                    "isFinalized": True,
                }
            )
            session_id = session.id
            logger.info("Prisma: session created  id=%s", session_id)

            # ── 2. saved_ishikawa ─────────────────────────────────────
            cause_count = sum(
                1 for cat in ishikawa
                for item in (cat.get("result", []) if isinstance(cat, dict) else [])
                if (item.get("cause") or item.get("sub_category") or "").strip()
            )
            ishi = db.savedishikawa.create(
                data={
                    "sessionId": session_id,
                    "userId": user_id,
                    "masterUserId": master_user_id,
                    "orgId": org_id,
                    "problemQuery": query,
                    "domain": domain or None,
                    "categoryCount": len(ishikawa),
                    "causeCount": cause_count,
                    "mainCause": main_cause,
                    "data": json.dumps(ishikawa),
                    "version": 1,
                    "isFinal": True,
                }
            )
            ishikawa_id = ishi.id
            logger.info("Prisma: ishikawa saved   id=%s  chains=%d  main_causes=%d",
                        ishikawa_id, cause_count, len(main_cause))

            # ── 3. saved_five_whys ────────────────────────────────────
            # Extract root_causes from each chain safely (handles dict or object)
            root_causes = []
            for item in five_whys:
                if isinstance(item, dict):
                    rc = (item.get("root_cause") or "").strip()
                else:
                    rc = (getattr(item, "root_cause", None) or "").strip()
                if rc:
                    root_causes.append(rc)

            fw = db.savedfivewhys.create(
                data={
                    "sessionId": session_id,
                    "ishikawaId": ishikawa_id,
                    "userId": user_id,
                    "masterUserId": master_user_id,
                    "orgId": org_id,
                    "problemQuery": query,
                    "domain": domain or None,
                    "chainCount": len(five_whys),
                    "data": json.dumps(five_whys),
                    "rootCauses": root_causes,
                    "version": 1,
                }
            )
            five_whys_id = fw.id
            logger.info("Prisma: five_whys saved  id=%s  chains=%d  root_causes=%d",
                        five_whys_id, len(five_whys), len(root_causes))

        except Exception as exc:
            logger.error("Prisma save failed: %s", exc, exc_info=True)
            return {
                "session_id": session_id,
                "ishikawa_id": ishikawa_id,
                "five_whys_id": five_whys_id,
                "skipped": True,
            }

        return {
            "session_id": session_id,
            "ishikawa_id": ishikawa_id,
            "five_whys_id": five_whys_id,
            "skipped": False,
        }

    def get_history(
        self,
        *,
        user_id: str,
        master_user_id: str,
        org_id: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch the user's history from Prisma.
        If user_id == master_user_id, they are the master user and see all org history.
        Otherwise, they only see their own history.
        """
        try:
            db = get_prisma()
        except Exception as exc:
            logger.error("Prisma connection failed: %s", exc)
            return []

        # Determine filter: master user sees all in org, regular user sees own
        is_master = (user_id == master_user_id)
        
        where_clause = {
            "orgId": org_id,
        }
        if not is_master:
            where_clause["userId"] = user_id

        try:
            sessions = db.analysissession.find_many(
                where=where_clause,
                order={"createdAt": "desc"},
                include={
                    "savedIshikawa":True,
                    "savedFiveWhys":True
                }
            )
            
            results = []

            for session in sessions:
                try:
                    ishikawa_records = session.savedIshikawa or []
                    five_whys_records = session.savedFiveWhys or []

                    ishi = ishikawa_records[0] if ishikawa_records else None
                    fw = five_whys_records[0] if five_whys_records else None

                    # Safely parse JSON — handles str, dict, list, and None
                    def safe_json(val, fallback):
                        if val is None:
                            return fallback
                        if isinstance(val, (list, dict)):
                            return val
                        if isinstance(val, str):
                            try:
                                return json.loads(val)
                            except Exception:
                                return fallback
                        return fallback

                    ishi_data = safe_json(ishi.data if ishi else None, [])
                    fw_data   = safe_json(fw.data if fw else None, [])

                    # Ensure fw_data is always a list (handles single-chain objects)
                    if isinstance(fw_data, dict):
                        fw_data = [fw_data]

                    results.append({
                        "session_id":  session.id,
                        "query":       session.query,
                        "domain":      session.domain,
                        "title":       session.title,
                        "created_at":  session.createdAt.isoformat() if session.createdAt else "",
                        "cause_count": ishi.causeCount if ishi else 0,
                        "root_causes": (fw.rootCauses or []) if fw else [],
                        "main_cause":  (ishi.mainCause or []) if ishi else [],
                        "ishikawa":    ishi_data,
                        "five_whys":   fw_data,
                    })
                except Exception as row_exc:
                    logger.warning("Skipping malformed history session %s: %s", session.id, row_exc)
                    continue

            return results
            
        except Exception as exc:
            logger.error("Prisma history fetch failed: %s", exc)
            return []

