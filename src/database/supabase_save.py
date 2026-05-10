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
                for item in cat.get("result", [])
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
                    "data": json.dumps(ishikawa),
                    "version": 1,
                    "isFinal": True,
                }
            )
            ishikawa_id = ishi.id
            logger.info("Prisma: ishikawa saved   id=%s", ishikawa_id)

            # ── 3. saved_five_whys ────────────────────────────────────
            root_causes = [
                (item.get("root_cause") or "").strip()
                for item in five_whys
                if (item.get("root_cause") or "").strip()
            ]
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
            logger.info("Prisma: five_whys saved  id=%s", five_whys_id)

        except Exception as exc:
            logger.error("Prisma save failed: %s", exc)
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
                ishikawa_records = session.savedIshikawa or []
                five_whys_records = session.savedFiveWhys or []

                ishi = ishikawa_records[0] if ishikawa_records else None
                fw = five_whys_records[0] if five_whys_records else None

                # Handle both string JSON and already-parsed objects
                if ishi:
                    if isinstance(ishi.data, str):
                        ishi_data = json.loads(ishi.data)
                    else:
                        ishi_data = ishi.data
                else:
                    ishi_data = []

                if fw:
                    if isinstance(fw.data, str):
                        fw_data = json.loads(fw.data)
                    else:
                        fw_data = fw.data
                else:
                    fw_data = []

                results.append({
                    "session_id": session.id,
                    "query": session.query,
                    "domain": session.domain,
                    "title": session.title,
                    "created_at": session.createdAt.isoformat() if session.createdAt else "",
                    "cause_count": ishi.causeCount if ishi else 0,
                    "root_causes": fw.rootCauses if fw and fw.rootCauses else [],
                    "ishikawa": ishi_data,
                    "five_whys": fw_data,
                })

            return results
            
        except Exception as exc:
            logger.error("Prisma history fetch failed: %s", exc)
            return []

