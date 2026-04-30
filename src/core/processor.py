"""
Core processing logic for the Ishikawa Knowledge System.
Handles intent processing, analysis coordination, and result synthesis.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .analysis_helpers import (
    build_evidence_payload,
    build_findings_summary,
    should_perform_ishikawa,
    should_perform_whys,
)
from ..database.repository import KnowledgeRepository
from ..database.search import SearchCriteria
from ..llm.extractor import AnalysisCoordinator, AnalysisResult, Intent, IntentExtractor
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a user query."""

    intent: Intent
    knowledge_results: list[dict[str, Any]]
    analysis_results: dict[str, Any]
    synthesis: AnalysisResult | None
    processing_time: float
    success: bool
    error_message: str | None = None


def _unwrap_search_rows(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalise rows returned by advanced_search or fulltext_search.

    Both methods now return rows shaped as:
        {"problem_statement": {...ps fields...}, "relevance_score": float}

    This helper flattens the wrapper and injects ``relevance_score`` into the
    PS dict so downstream evidence builders can use it without knowing the
    original row shape.
    """
    results: list[dict[str, Any]] = []
    for row in raw:
        if "problem_statement" in row:
            ps = dict(row["problem_statement"])
            ps["relevance_score"] = float(row.get("relevance_score", 0.0))
            results.append(ps)
        else:
            # Already flat (structured search path) — pass through unchanged
            results.append(row)
    return results


class QueryProcessor:
    """Main processor for handling user queries and coordinating analysis."""

    def __init__(
        self,
        intent_extractor: IntentExtractor,
        analysis_coordinator: AnalysisCoordinator,
        knowledge_repository: KnowledgeRepository,
        *,
        default_max_results: int = 20,
    ) -> None:
        self.intent_extractor = intent_extractor
        self.analysis_coordinator = analysis_coordinator
        self.knowledge_repository = knowledge_repository
        self.default_max_results = default_max_results

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def process_query(self, query: str) -> ProcessingResult:
        """Process a user query through the complete analysis pipeline."""
        start_time = time.perf_counter()

        try:
            logger.info("Processing query: %s...", query[:100])
            intent = self.intent_extractor.extract_intent(query)
            knowledge_results = self.search_knowledge_base(intent)
            analysis_results = self._perform_analyses(query, intent, knowledge_results)
            synthesis = self._synthesize_results(query, intent, knowledge_results, analysis_results)

            processing_time = time.perf_counter() - start_time
            logger.info(
                "Query processing completed in %.2fs | results=%d",
                processing_time, len(knowledge_results),
            )
            return ProcessingResult(
                intent=intent,
                knowledge_results=knowledge_results,
                analysis_results=analysis_results,
                synthesis=synthesis,
                processing_time=processing_time,
                success=True,
            )
        except Exception as exc:
            processing_time = time.perf_counter() - start_time
            logger.error("Query processing failed after %.2fs: %s", processing_time, exc)
            return ProcessingResult(
                intent=Intent([], [], [], [], None, ""),
                knowledge_results=[],
                analysis_results={},
                synthesis=None,
                processing_time=processing_time,
                success=False,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Knowledge-base search (tiered strategy)
    # ------------------------------------------------------------------

    def search_knowledge_base(
        self,
        intent: Intent,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search the knowledge base using a three-tier relevance strategy.

        Tier 1 — advanced_search (keywords present)
            Lucene full-text scoring + structured domain/phase/date filters.
            Returns relevance-ranked PS objects.

        Tier 2 — fulltext_search (Tier 1 empty or failed)
            Broader Lucene search, no structured filters.
            Also returns relevance-ranked PS objects (same shape as Tier 1).

        Tier 3 — search_problems (no keywords at all)
            Structured property-filter only, ordered by created_at DESC.

        All tiers go through ``_unwrap_search_rows`` so the caller always
        receives a flat list of PS dicts, each optionally carrying a
        ``relevance_score`` key.
        """
        result_limit = max_results or self.default_max_results

        criteria = SearchCriteria(
            domains=intent.domains,
            keywords=intent.keywords,
            phases=intent.phases,
            part_numbers=intent.part_numbers,
            time_filter=intent.time_filter,
            limit=result_limit,
        )

        results: list[dict[str, Any]] = []

        if intent.keywords:
            search_text = " ".join(intent.keywords)

            # ── Tier 1: advanced scored + structured search ───────────────────
            try:
                raw = self.knowledge_repository.advanced_search(search_text, criteria)
                results = _unwrap_search_rows(raw)
                logger.info(
                    "Tier-1 advanced search %r → %d results",
                    search_text, len(results),
                )
            except Exception as adv_exc:
                logger.warning(
                    "Tier-1 advanced search failed (%s), falling back to Tier-2 fulltext",
                    adv_exc,
                )

            # ── Tier 2: broader fulltext (no structured filters) ──────────────
            if not results:
                try:
                    raw = self.knowledge_repository.fulltext_search(
                        search_text, limit=result_limit
                    )
                    results = _unwrap_search_rows(raw)
                    logger.info(
                        "Tier-2 fulltext search %r → %d results",
                        search_text, len(results),
                    )
                except Exception as ft_exc:
                    logger.warning(
                        "Tier-2 fulltext search failed (%s), falling back to Tier-3 structured",
                        ft_exc,
                    )

            # ── Tier 2b: if both indexed searches failed, drop to structured ──
            if not results:
                try:
                    raw = self.knowledge_repository.search_problems(criteria)
                    results = _unwrap_search_rows(raw)
                    logger.info(
                        "Tier-2b structured fallback (keywords present but indexes failed) → %d results",
                        len(results),
                    )
                except Exception as struct_exc:
                    logger.error("All search tiers failed: %s", struct_exc)

        else:
            # ── Tier 3: structured filter only (no free-text keywords) ─────────
            try:
                raw = self.knowledge_repository.search_problems(criteria)
                results = _unwrap_search_rows(raw)
                logger.info("Tier-3 structured search → %d results", len(results))
            except Exception as exc:
                logger.error("Tier-3 structured search failed: %s", exc)

        logger.info(
            "Knowledge base search complete: %d results returned (limit=%d)",
            len(results), result_limit,
        )
        return results

    # ------------------------------------------------------------------
    # Evidence preparation
    # ------------------------------------------------------------------

    def prepare_evidence(self, knowledge_results: list[dict[str, Any]], intent: Intent) -> str:
        """Build the evidence block passed into analysis prompts."""
        return build_evidence_payload(knowledge_results, intent)

    # ------------------------------------------------------------------
    # Analysis pipeline
    # ------------------------------------------------------------------

    def _perform_analyses(
        self,
        query: str,
        intent: Intent,
        knowledge_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform the analyses relevant to the query."""
        analyses: dict[str, Any] = {}

        try:
            evidence = self.prepare_evidence(knowledge_results, intent)
            problem_statement = intent.summary or query
            primary_domain = intent.domains[0] if intent.domains else "General"

            if should_perform_whys(intent):
                try:
                    analyses["whys"] = self.analysis_coordinator.perform_whys_analysis(
                        problem_statement=problem_statement,
                        domain=primary_domain,
                        phase="D5",
                        evidence=evidence,
                    )
                    logger.info("5 Whys analysis completed")
                except Exception as exc:
                    logger.error("5 Whys analysis failed: %s", exc)
                    analyses["whys_error"] = str(exc)

            if should_perform_ishikawa(intent, knowledge_results):
                try:
                    analyses["ishikawa"] = self.analysis_coordinator.generate_ishikawa_diagram(
                        problem_statement=problem_statement,
                        evidence=evidence,
                    )
                    logger.info("Ishikawa diagram analysis completed")
                except Exception as exc:
                    logger.error("Ishikawa analysis failed: %s", exc)
                    analyses["ishikawa_error"] = str(exc)

        except Exception as exc:
            logger.error("Analysis execution failed: %s", exc)

        return analyses

    def _synthesize_results(
        self,
        query: str,
        intent: Intent,
        knowledge_results: list[dict[str, Any]],
        analysis_results: dict[str, Any],
    ) -> AnalysisResult | None:
        """Synthesize all findings into final recommendations."""
        try:
            if not analysis_results:
                logger.info("No analyses performed — skipping synthesis")
                return None

            findings = build_findings_summary(knowledge_results, analysis_results)
            synthesis = self.analysis_coordinator.synthesize_findings(
                problem_statement=intent.summary or query,
                domains=intent.domains,
                evidence_count=len(knowledge_results),
                findings=findings,
            )
            logger.info("Results synthesis completed")
            return synthesis
        except Exception as exc:
            logger.error("Results synthesis failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Deprecated compatibility wrappers
    # ------------------------------------------------------------------

    def _search_knowledge_base(self, intent: Intent) -> list[dict[str, Any]]:
        return self.search_knowledge_base(intent)

    def _prepare_evidence(self, knowledge_results: list[dict[str, Any]], intent: Intent) -> str:
        return self.prepare_evidence(knowledge_results, intent)

    def _should_perform_whys(self, intent: Intent) -> bool:
        return should_perform_whys(intent)

    def _should_perform_ishikawa(self, intent: Intent, knowledge_results: list[dict[str, Any]]) -> bool:
        return should_perform_ishikawa(intent, knowledge_results)

    def _prepare_findings_summary(
        self,
        knowledge_results: list[dict[str, Any]],
        analysis_results: dict[str, Any],
    ) -> str:
        return build_findings_summary(knowledge_results, analysis_results)
