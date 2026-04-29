"""Write and compatibility operations for the knowledge repository."""

from __future__ import annotations

import uuid
from typing import Any

from ..utils.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_MAP = {
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}


class KnowledgeRepositoryWriteMixin:
    """Mutation-oriented repository operations."""

    @staticmethod
    def _coerce_severity(value: int | str | None, default: int = 3) -> int:
        """Normalize mixed severity input into the repository's 1-5 scale."""
        if isinstance(value, int):
            return max(1, min(value, 5))
        if isinstance(value, str):
            return _SEVERITY_MAP.get(value.strip().lower(), default)
        return default

    @staticmethod
    def _summarize_text(text: str, limit: int = 180) -> str:
        """Create a compact summary without extra dependencies."""
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 3].rstrip()}..."

    def create_problem_statement(
        self,
        title: str,
        text: str,
        domain_names: list[str],
        keywords: list[str] | None = None,
        ticket_ref: str | None = None,
        part_number: str | None = None,
        ps_id: str | None = None,
        scaffold_phases: bool = True,
        summary: str = "",
        keywords_extracted: list[str] | None = None,
        quality_score: float = 0.0,
        domain_tags: list[str] | None = None,
        upload_source: str = "manual",
        ollama_processed: bool = False,
    ) -> str:
        """Create a ProblemStatement node and optionally scaffold D1-D7 phases."""
        created_ps_id = ps_id or str(uuid.uuid4())

        try:
            query = self.query_builder.build_ps_creation_query()
            params = {
                "ps_id": created_ps_id,
                "title": title,
                "text": text,
                "keywords": keywords or [],
                "ticket_ref": ticket_ref or "",
                "part_number": part_number or "",
                "domain_names": domain_names,
                "summary": summary,
                "keywords_extracted": keywords_extracted or [],
                "quality_score": quality_score,
                "domain_tags": domain_tags or [],
                "upload_source": upload_source,
                "ollama_processed": ollama_processed,
            }
            result = self.connection.execute_write_query(query, params)
            created_id = result[0]["ps_id"] if result else created_ps_id

            if scaffold_phases:
                scaffold_query = self.query_builder.build_ps_phase_scaffold_query()
                self.connection.execute_write_query(scaffold_query, {"ps_id": created_id})

            logger.info("Created PS %r in domains %s", created_id, domain_names)
            return created_id
        except Exception as exc:
            logger.error("PS creation failed: %s", exc)
            raise RuntimeError(f"PS creation failed: {exc}") from exc

    def create_problem(self, *args: Any, **kwargs: Any) -> str:
        """Deprecated alias kept for backward compatibility."""
        return self.create_problem_statement(*args, **kwargs)

    def create_content(
        self,
        ps_id: str,
        phase_code: str,
        sub_phase: str,
        text: str,
        summary: str,
        keywords: list[str] | None = None,
        category: str | None = None,
        severity: int = 3,
        root_cause: str | None = None,
        corrective_action: str | None = None,
        model: str = "ollama",
        confidence: float = 0.0,
        content_id: str | None = None,
    ) -> str:
        """Create a content node under a specific sub-phase."""
        created_content_id = content_id or str(uuid.uuid4())

        try:
            query = self.query_builder.build_content_creation_query()
            params = {
                "content_id": created_content_id,
                "ps_id": ps_id,
                "phase_code": phase_code,
                "sub_phase": sub_phase,
                "text": text,
                "summary": summary,
                "keywords": keywords or [],
                "category": category or "Unknown",
                "severity": self._coerce_severity(severity),
                "root_cause": root_cause or "",
                "corrective_action": corrective_action or "",
                "model": model,
                "confidence": confidence,
            }
            result = self.connection.execute_write_query(query, params)
            created_id = result[0]["content_id"] if result else created_content_id
            logger.info(
                "Created content %r for PS %r at %s/%s (model=%s, confidence=%.2f)",
                created_id,
                ps_id,
                phase_code,
                sub_phase,
                model,
                confidence,
            )
            return created_id
        except Exception as exc:
            logger.error("Content creation failed: %s", exc)
            raise RuntimeError(f"Content creation failed: {exc}") from exc

    def create_cause(
        self,
        problem_id: str,
        description: str,
        category: str,
        severity: int | str | None = None,
        ishikawa_category: str | None = None,
    ) -> str:
        """Compatibility writer for legacy cause routes."""
        cause_category = ishikawa_category or category or "Unknown"
        return self.create_content(
            ps_id=problem_id,
            phase_code="D4",
            sub_phase="root_cause",
            text=description,
            summary=self._summarize_text(description),
            keywords=[category] if category else [],
            category=cause_category,
            severity=self._coerce_severity(severity),
            root_cause=description,
            model="api",
            confidence=1.0,
        )

    def create_evidence(
        self,
        problem_id: str,
        content: str,
        source: str,
        evidence_type: str,
        confidence: float = 0.8,
    ) -> str:
        """Compatibility writer for legacy evidence routes."""
        evidence_text = f"[{evidence_type}] {content}\nSource: {source}"
        return self.create_content(
            ps_id=problem_id,
            phase_code="D3",
            sub_phase="verification",
            text=evidence_text,
            summary=self._summarize_text(content),
            keywords=[evidence_type, source],
            category="Evidence",
            severity=3,
            model="api",
            confidence=confidence,
        )

    def create_solution(
        self,
        problem_id: str,
        description: str,
        solution_type: str,
        priority: str = "Medium",
        status: str = "proposed",
        cause_id: str | None = None,
    ) -> str:
        """Compatibility writer for legacy solution routes."""
        metadata_parts = [f"Type: {solution_type}", f"Priority: {priority}", f"Status: {status}"]
        if cause_id:
            metadata_parts.append(f"Cause ID: {cause_id}")
        text = f"{description}\n" + " | ".join(metadata_parts)
        return self.create_content(
            ps_id=problem_id,
            phase_code="D6",
            sub_phase="corrective_action",
            text=text,
            summary=self._summarize_text(description),
            keywords=[solution_type, priority, status],
            category="CorrectiveAction",
            severity=self._coerce_severity(priority),
            corrective_action=description,
            model="api",
            confidence=1.0,
        )

    def update_ps_summary(
        self,
        ps_id: str,
        summary: str,
        keywords_extracted: list[str] | None = None,
        quality_score: float = 0.0,
        domain_tags: list[str] | None = None,
        ollama_processed: bool = True,
    ) -> dict[str, Any] | None:
        """Persist PS-level extraction results onto an existing ProblemStatement."""
        try:
            query = self.query_builder.build_ps_summary_update_query()
            params = {
                "ps_id": ps_id,
                "summary": summary,
                "keywords_extracted": keywords_extracted or [],
                "quality_score": quality_score,
                "domain_tags": domain_tags or [],
                "ollama_processed": ollama_processed,
            }
            result = self.connection.execute_write_query(query, params)
            logger.info("Updated PS summary for %r (quality=%.2f)", ps_id, quality_score)
            return result[0] if result else None
        except Exception as exc:
            logger.error("PS summary update failed for %r: %s", ps_id, exc)
            raise RuntimeError(f"PS summary update failed: {exc}") from exc

    def refresh_domain_stats(self, domain_name: str) -> dict[str, Any] | None:
        """Re-aggregate and persist summary stats onto a domain node."""
        try:
            query = self.query_builder.build_domain_stats_update_query()
            result = self.connection.execute_write_query(query, {"domain_name": domain_name})
            logger.info("Refreshed stats for domain %r", domain_name)
            return result[0] if result else None
        except Exception as exc:
            logger.error("Domain stats refresh failed for %r: %s", domain_name, exc)
            raise RuntimeError(f"Domain stats refresh failed: {exc}") from exc

    def upload_full_ps_json(
        self,
        json_data: dict[str, Any],
        llm_service: Any = None,
    ) -> dict[str, Any]:
        """Bulk-upload a fully structured PS document that includes D1-D7 content."""
        phase_sub_phases = {
            "D1": ["organise", "plan"],
            "D2": ["problem_statement", "symptoms"],
            "D3": ["immediate_action", "verification"],
            "D4": ["root_cause", "contributing_factors"],
            "D5": ["ishikawa_analysis", "five_whys"],
            "D6": ["corrective_action", "owner", "deadline"],
            "D7": ["prevention", "lesson_learned"],
        }

        ps_id = self.create_problem_statement(
            title=json_data.get("title", ""),
            text=json_data.get("text", ""),
            domain_names=json_data.get("domain_names", []),
            keywords=json_data.get("keywords", []),
            ticket_ref=json_data.get("ticket_ref"),
            part_number=json_data.get("part_number"),
            ps_id=json_data.get("ps_id"),
            scaffold_phases=True,
            upload_source="structured_json",
            ollama_processed=False,
        )

        all_content_texts: list[str] = []
        content_ids: list[str] = []

        for phase_code, sub_phases in phase_sub_phases.items():
            phase_data = json_data.get(phase_code, {})
            for sub_phase in sub_phases:
                raw = phase_data.get(sub_phase, [])
                texts = [raw] if isinstance(raw, str) else list(raw)
                for text in texts:
                    if not text or not text.strip():
                        continue
                    try:
                        created_id = self.create_content(
                            ps_id=ps_id,
                            phase_code=phase_code,
                            sub_phase=sub_phase,
                            text=text.strip(),
                            summary="",
                            model="upload",
                            confidence=0.0,
                        )
                        content_ids.append(created_id)
                        all_content_texts.append(f"[{phase_code}/{sub_phase}] {text.strip()}")
                    except Exception as exc:
                        logger.warning("Skipped content at %s/%s: %s", phase_code, sub_phase, exc)

        ollama_ok = False
        if llm_service is not None and all_content_texts:
            try:
                full_doc = "\n".join(all_content_texts)
                llm_result = llm_service.summarize_problem_statement(
                    title=json_data.get("title", ""),
                    problem_text=json_data.get("text", ""),
                    content_text=full_doc,
                )
                self.update_ps_summary(
                    ps_id=ps_id,
                    summary=llm_result.get("summary", ""),
                    keywords_extracted=llm_result.get("keywords_extracted", []),
                    quality_score=float(llm_result.get("quality_score", 0.0)),
                    domain_tags=llm_result.get("domain_tags", []),
                    ollama_processed=True,
                )
                ollama_ok = True
            except Exception as exc:
                logger.warning("Ollama PS-level summarisation skipped for %r: %s", ps_id, exc)

        for domain_name in json_data.get("domain_names", []):
            try:
                self.refresh_domain_stats(domain_name)
            except Exception as exc:
                logger.warning("Domain stats refresh skipped for %r: %s", domain_name, exc)

        logger.info(
            "Uploaded PS %r: %s content nodes, ollama_processed=%s",
            ps_id,
            len(content_ids),
            ollama_ok,
        )
        return {
            "ps_id": ps_id,
            "content_count": len(content_ids),
            "ollama_processed": ollama_ok,
        }
