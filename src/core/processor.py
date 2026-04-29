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
            logger.info("Query processing completed in %.2fs", processing_time)
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
            logger.error("Query processing failed: %s", exc)
            return ProcessingResult(
                intent=Intent([], [], [], [], None, ""),
                knowledge_results=[],
                analysis_results={},
                synthesis=None,
                processing_time=processing_time,
                success=False,
                error_message=str(exc),
            )

    def search_knowledge_base(
        self,
        intent: Intent,
        *,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search the knowledge base for relevant historical records."""
        result_limit = max_results or self.default_max_results

        try:
            criteria = SearchCriteria(
                domains=intent.domains,
                keywords=intent.keywords,
                phases=intent.phases,
                part_numbers=intent.part_numbers,
                time_filter=intent.time_filter,
                limit=result_limit,
            )

            results = self.knowledge_repository.search_problems(criteria)
            if not results and intent.keywords:
                results = self.knowledge_repository.fulltext_search(" ".join(intent.keywords), limit=result_limit)

            logger.info("Knowledge base search returned %s results", len(results))
            return results
        except Exception as exc:
            logger.error("Knowledge base search failed: %s", exc)
            return []

    def prepare_evidence(self, knowledge_results: list[dict[str, Any]], intent: Intent) -> str:
        """Build the evidence block passed into analysis prompts."""
        return build_evidence_payload(knowledge_results, intent)

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
                logger.info("No analyses performed, skipping synthesis")
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

    def _search_knowledge_base(self, intent: Intent) -> list[dict[str, Any]]:
        """Deprecated compatibility wrapper."""
        return self.search_knowledge_base(intent)

    def _prepare_evidence(self, knowledge_results: list[dict[str, Any]], intent: Intent) -> str:
        """Deprecated compatibility wrapper."""
        return self.prepare_evidence(knowledge_results, intent)

    def _should_perform_whys(self, intent: Intent) -> bool:
        """Deprecated compatibility wrapper."""
        return should_perform_whys(intent)

    def _should_perform_ishikawa(self, intent: Intent, knowledge_results: list[dict[str, Any]]) -> bool:
        """Deprecated compatibility wrapper."""
        return should_perform_ishikawa(intent, knowledge_results)

    def _prepare_findings_summary(
        self,
        knowledge_results: list[dict[str, Any]],
        analysis_results: dict[str, Any],
    ) -> str:
        """Deprecated compatibility wrapper."""
        return build_findings_summary(knowledge_results, analysis_results)
