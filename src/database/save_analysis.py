"""
Neo4j persistence layer for user-saved Ishikawa + 5-Whys analyses.

When a user clicks "Save All" the finalized analysis is written back into the
organization's Neo4j instance as a first-class ProblemStatement node with
fully-scaffolded D1-D7 phases. This enriches the shared knowledge base and
improves future search / LLM context quality.

Mapping
-------
Ishikawa result items (status = confirmed / immediate_action = True)
    → D4 / root_cause          Content nodes
Ishikawa result items (status = possible, not immediate)
    → D4 / contributing_factors Content nodes
Full Ishikawa JSON summary
    → D5 / ishikawa_analysis   Content node
5-Whys chain items
    → D5 / five_whys           Content nodes  (one per chain item)
Root causes extracted from 5-Whys
    → D7 / lesson_learned      Content nodes
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Severity text → numeric scale used by the repository
_SEVERITY_MAP: dict[str, int] = {
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


def _severity_int(value: str | None, default: int = 3) -> int:
    if not value:
        return default
    return _SEVERITY_MAP.get(value.strip().lower(), default)


def _is_meaningful(item: dict[str, Any]) -> bool:
    """Return True if the result item has at least a cause string."""
    cause = (item.get("cause") or "").strip()
    sub = (item.get("sub_category") or "").strip()
    return bool(cause or sub)


def _is_confirmed(item: dict[str, Any]) -> bool:
    status = (item.get("status") or "").strip().lower()
    immediate = item.get("immediate_action", False)
    severity = (item.get("severity") or "").strip().lower()
    return (
        status == "confirmed"
        or immediate is True
        or severity in ("high", "critical")
    )


def _format_why_chain(steps: list[dict[str, Any]]) -> str:
    lines = []
    for step in sorted(steps, key=lambda s: s.get("level", 0)):
        lvl = step.get("level", "?")
        q = step.get("question", "")
        a = step.get("answer", "")
        lines.append(f"Why #{lvl}: {q}\nAnswer: {a}")
    return "\n".join(lines)


class AnalysisSaver:
    """
    Persists a finalized Ishikawa + 5-Whys analysis into Neo4j.

    Uses the KnowledgeRepository's existing write methods so that saved
    analyses are indistinguishable from data ingested via any other path.
    """

    def __init__(self, repository: Any) -> None:
        """
        Args:
            repository: A KnowledgeRepository instance (already connected).
        """
        self.repo = repository

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def save_analysis(
        self,
        query: str,
        domain: str,
        ishikawa: list[dict[str, Any]],
        five_whys: list[dict[str, Any]],
        *,
        ticket_ref: str = "",
        part_number: str = "",
        source: str = "user_save",
    ) -> dict[str, Any]:
        """
        Write the full analysis into Neo4j and return a summary dict.

        Returns
        -------
        {
            "ps_id": str,
            "content_count": int,
            "domain": str,
        }
        """
        ps_id = str(uuid.uuid4())
        logger.info(
            "Saving analysis to Neo4j: ps_id=%s  domain=%r  query=%r...",
            ps_id,
            domain,
            query[:80],
        )

        # ── 1. Build title + keyword lists from Ishikawa data ─────────
        all_keywords = self._extract_keywords(ishikawa)
        title = self._build_title(query)
        summary = self._build_summary(query, five_whys)
        quality_score = self._estimate_quality(ishikawa, five_whys)

        # ── 2. Create the ProblemStatement node (scaffolds D1-D7) ─────
        created_ps_id = self.repo.create_problem_statement(
            ps_id=ps_id,
            title=title,
            text=query,
            domain_names=[domain] if domain else ["General"],
            keywords=all_keywords[:20],
            ticket_ref=ticket_ref,
            part_number=part_number,
            scaffold_phases=True,
            summary=summary,
            keywords_extracted=all_keywords[:15],
            quality_score=quality_score,
            domain_tags=[domain] if domain else [],
            upload_source=source,
            ollama_processed=True,
        )

        content_ids: list[str] = []

        # ── 3. Persist Ishikawa causes ─────────────────────────────────
        content_ids.extend(self._save_ishikawa_content(created_ps_id, ishikawa))

        # ── 4. Persist full Ishikawa JSON summary under D5 ────────────
        ishikawa_summary_id = self._save_ishikawa_summary(created_ps_id, query, ishikawa)
        if ishikawa_summary_id:
            content_ids.append(ishikawa_summary_id)

        # ── 5. Persist 5-Whys chains ──────────────────────────────────
        content_ids.extend(self._save_five_whys_content(created_ps_id, five_whys))

        # ── 6. Persist root-cause lessons under D7 ────────────────────
        content_ids.extend(self._save_lessons(created_ps_id, five_whys))

        # ── 7. Refresh domain aggregated stats ────────────────────────
        try:
            self.repo.refresh_domain_stats(domain or "General")
        except Exception as exc:
            logger.warning("Domain stats refresh skipped: %s", exc)

        logger.info(
            "Analysis saved to Neo4j: ps_id=%s  content_nodes=%d",
            created_ps_id,
            len(content_ids),
        )
        return {
            "ps_id": created_ps_id,
            "content_count": len(content_ids),
            "domain": domain,
        }

    # ------------------------------------------------------------------
    # Ishikawa → D4 (causes) + D5 (ishikawa_analysis summary)
    # ------------------------------------------------------------------

    def _save_ishikawa_content(
        self,
        ps_id: str,
        ishikawa: list[dict[str, Any]],
    ) -> list[str]:
        """Write each meaningful Ishikawa result item to D4."""
        ids: list[str] = []
        for category in ishikawa:
            bone = category.get("category", "Unknown")
            results: list[dict[str, Any]] = category.get("result", [])
            for item in results:
                if not _is_meaningful(item):
                    continue
                status = (item.get("status") or "possible").strip().lower()
                if status in ("excluded", "na"):
                    continue

                cause_text = (item.get("cause") or "").strip()
                sub_cat = (item.get("sub_category") or "").strip()
                evidence = (item.get("evidence") or "").strip()
                severity_str = item.get("severity") or "Medium"
                severity_num = _severity_int(severity_str)

                full_text = f"[{bone}] {sub_cat}: {cause_text}" if sub_cat else f"[{bone}] {cause_text}"
                summary_text = full_text[:180]
                keywords = [bone, sub_cat, status][:5]

                # Confirmed / high-severity → D4/root_cause
                # Possible → D4/contributing_factors
                sub_phase = "root_cause" if _is_confirmed(item) else "contributing_factors"

                try:
                    cid = self.repo.create_content(
                        ps_id=ps_id,
                        phase_code="D4",
                        sub_phase=sub_phase,
                        text=full_text,
                        summary=summary_text,
                        keywords=[k for k in keywords if k],
                        category=bone,
                        severity=severity_num,
                        root_cause=cause_text,
                        corrective_action=evidence,
                        model="user_save",
                        confidence=1.0 if _is_confirmed(item) else 0.6,
                    )
                    ids.append(cid)
                except Exception as exc:
                    logger.warning("Ishikawa content save failed at D4/%s: %s", sub_phase, exc)

        return ids

    def _save_ishikawa_summary(
        self,
        ps_id: str,
        query: str,
        ishikawa: list[dict[str, Any]],
    ) -> str | None:
        """Write a compact JSON of the full Ishikawa diagram under D5/ishikawa_analysis."""
        # Strip status + immediate_action for a clean stored copy
        compact = []
        for cat in ishikawa:
            bone = cat.get("category", "")
            results = [
                {
                    "sub_category": item.get("sub_category", ""),
                    "cause": item.get("cause", ""),
                    "evidence": item.get("evidence", ""),
                    "severity": item.get("severity", ""),
                }
                for item in cat.get("result", [])
                if _is_meaningful(item)
            ]
            if results:
                compact.append({"category": bone, "result": results})

        if not compact:
            return None

        try:
            text = json.dumps(compact, ensure_ascii=False)
            summary = f"Ishikawa diagram for: {query[:120]}"
            return self.repo.create_content(
                ps_id=ps_id,
                phase_code="D5",
                sub_phase="ishikawa_analysis",
                text=text,
                summary=summary,
                keywords=["ishikawa", "root_cause_analysis"],
                category="IshikawaDigram",
                severity=3,
                model="user_save",
                confidence=1.0,
            )
        except Exception as exc:
            logger.warning("Ishikawa D5 summary save failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 5-Whys → D5 (five_whys) + D7 (lesson_learned)
    # ------------------------------------------------------------------

    def _save_five_whys_content(
        self,
        ps_id: str,
        five_whys: list[dict[str, Any]],
    ) -> list[str]:
        """Write each FiveWhyChainItem as a Content node under D5/five_whys."""
        ids: list[str] = []
        for item in five_whys:
            chain: list[dict[str, Any]] = item.get("why_chain", [])
            root_cause = (item.get("root_cause") or "").strip()
            confidence = float(item.get("confidence") or 0.0)
            problem_id = item.get("problem_id", "")

            if not chain and not root_cause:
                continue

            chain_text = _format_why_chain(chain)
            full_text = (
                f"Problem ID: {problem_id}\n\n"
                f"{chain_text}\n\n"
                f"Root Cause: {root_cause}"
            ).strip()

            summary = root_cause[:180] if root_cause else chain_text[:180]

            try:
                cid = self.repo.create_content(
                    ps_id=ps_id,
                    phase_code="D5",
                    sub_phase="five_whys",
                    text=full_text,
                    summary=summary,
                    keywords=["5-whys", "root_cause"],
                    category="FiveWhys",
                    severity=4,
                    root_cause=root_cause,
                    model="user_save",
                    confidence=min(1.0, max(0.0, confidence)),
                )
                ids.append(cid)
            except Exception as exc:
                logger.warning("5-Whys content save failed for problem_id=%r: %s", problem_id, exc)

        return ids

    def _save_lessons(
        self,
        ps_id: str,
        five_whys: list[dict[str, Any]],
    ) -> list[str]:
        """Extract root causes from 5-Whys and write them under D7/lesson_learned."""
        ids: list[str] = []
        seen: set[str] = set()
        for item in five_whys:
            root_cause = (item.get("root_cause") or "").strip()
            if not root_cause or root_cause in seen:
                continue
            seen.add(root_cause)
            try:
                cid = self.repo.create_content(
                    ps_id=ps_id,
                    phase_code="D7",
                    sub_phase="lesson_learned",
                    text=root_cause,
                    summary=root_cause[:180],
                    keywords=["lesson_learned", "root_cause"],
                    category="LessonLearned",
                    severity=3,
                    root_cause=root_cause,
                    model="user_save",
                    confidence=1.0,
                )
                ids.append(cid)
            except Exception as exc:
                logger.warning("Lesson learned save failed: %s", exc)
        return ids

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_keywords(self, ishikawa: list[dict[str, Any]]) -> list[str]:
        """Pull sub-categories and cause keywords from Ishikawa data."""
        kws: list[str] = []
        for cat in ishikawa:
            bone = cat.get("category", "")
            if bone:
                kws.append(bone)
            for item in cat.get("result", []):
                sub = (item.get("sub_category") or "").strip()
                if sub and sub not in kws:
                    kws.append(sub)
        return kws

    def _build_title(self, query: str) -> str:
        words = query.strip().split()
        short = " ".join(words[:12])
        return short if len(short) <= 120 else short[:117] + "..."

    def _build_summary(self, query: str, five_whys: list[dict[str, Any]]) -> str:
        root_causes = [
            (fw.get("root_cause") or "").strip()
            for fw in five_whys
            if (fw.get("root_cause") or "").strip()
        ]
        if root_causes:
            causes_text = "; ".join(root_causes[:3])
            return f"Root causes identified: {causes_text}. Problem: {query[:100]}"
        return query[:180]

    def _estimate_quality(
        self,
        ishikawa: list[dict[str, Any]],
        five_whys: list[dict[str, Any]],
    ) -> float:
        """
        Simple heuristic: more causes + confident 5-Whys = higher quality.
        Range 0.0-1.0.
        """
        cause_count = sum(
            1
            for cat in ishikawa
            for item in cat.get("result", [])
            if _is_meaningful(item)
        )
        why_count = len(five_whys)
        avg_confidence = (
            sum(float(w.get("confidence") or 0) for w in five_whys) / why_count
            if why_count
            else 0.0
        )
        score = min(1.0, (cause_count / 20) * 0.5 + avg_confidence * 0.5)
        return round(score, 2)
