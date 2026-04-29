"""
Shared API service layer for the Ishikawa Knowledge System.
Centralizes request-to-analysis orchestration and repository access.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock
from typing import Any, Iterator

from ..schemas import (
    FiveWhysRequest,
    FiveWhysResponse,
    FrontendAnalysisRequest,
    FrontendAnalysisResponse,
    HealthResponse,
    IshikawaDiagramResponse,
    IshikawaRecreateRequest,
    IshikawaRequest,
    SearchRequest,
    SearchResponse,
)
from ...core.analysis_helpers import build_related_problem_statements
from ...core.processor import QueryProcessor
from ...database.connection import Neo4jConnection
from ...database.repository import KnowledgeRepository
from ...database.search import SearchCriteria
from ...llm.extractor import AnalysisCoordinator, Intent, IntentExtractor
from ...llm.service import LLMService
from ...utils.config import get_config
from ...utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AnalysisResources:
    """Resolved analysis dependencies for a single request."""

    repository: KnowledgeRepository
    intent_extractor: IntentExtractor
    analysis_coordinator: AnalysisCoordinator
    processor: QueryProcessor


@dataclass
class ResolvedQuery:
    """Intent, historical knowledge, and derived response metadata for a request."""

    intent: Intent
    knowledge_results: list[dict[str, Any]]
    related_ps: list[dict[str, Any]]


class APIService:
    """Service layer for API request orchestration."""

    def __init__(self) -> None:
        self._config = get_config()
        self._llm_service = LLMService(self._config.llm)
        self._analysis_db_connection = Neo4jConnection(self._config.database)
        self._analysis_connection_lock = Lock()

    def _ensure_analysis_connection(self) -> None:
        """Ensure the shared analysis connection is active."""
        if self._analysis_db_connection.is_connected():
            return

        with self._analysis_connection_lock:
            if self._analysis_db_connection.is_connected():
                return
            if not self._analysis_db_connection.connect():
                raise RuntimeError("Failed to establish database connection")

    def _build_analysis_resources(self) -> AnalysisResources:
        """Create request-scoped analysis helpers using shared long-lived dependencies."""
        repository = KnowledgeRepository(self._analysis_db_connection)
        intent_extractor = IntentExtractor(self._llm_service)
        analysis_coordinator = AnalysisCoordinator(self._llm_service)
        processor = QueryProcessor(
            intent_extractor=intent_extractor,
            analysis_coordinator=analysis_coordinator,
            knowledge_repository=repository,
        )
        return AnalysisResources(
            repository=repository,
            intent_extractor=intent_extractor,
            analysis_coordinator=analysis_coordinator,
            processor=processor,
        )

    def disconnect_analysis_connection(self) -> None:
        """Disconnect the shared analysis connection explicitly."""
        with self._analysis_connection_lock:
            if self._analysis_db_connection.is_connected():
                self._analysis_db_connection.disconnect()
                logger.info("Analysis database connection explicitly closed")

    def close(self) -> None:
        """Release shared resources held by the service."""
        self._analysis_db_connection.disconnect()

    @contextmanager
    def repository_context(self) -> Iterator[KnowledgeRepository]:
        """Yield a repository backed by a managed Neo4j connection."""
        db_connection = Neo4jConnection(self._config.database)
        if not db_connection.connect():
            raise RuntimeError("Failed to establish database connection")

        try:
            yield KnowledgeRepository(db_connection)
        finally:
            db_connection.disconnect()

    @contextmanager
    def analysis_context(self) -> Iterator[AnalysisResources]:
        """Yield all dependencies needed for an analysis request."""
        self._ensure_analysis_connection()
        yield self._build_analysis_resources()

    @staticmethod
    def build_intent_payload(intent: Intent) -> dict[str, Any]:
        """Convert internal intent objects to response payloads."""
        return {
            "domains": intent.domains,
            "keywords": intent.keywords,
            "part_numbers": intent.part_numbers,
            "phases": intent.phases,
            "time_filter": intent.time_filter,
            "summary": intent.summary,
        }

    @staticmethod
    def _append_frontend_context(evidence: str, additional_context: str | None) -> str:
        """Append extra frontend context to the evidence block."""
        if not additional_context:
            return evidence
        return f"{evidence}\n\nAdditional frontend context:\n{additional_context}"

    @staticmethod
    def _append_regeneration_context(
        evidence: str,
        previous_diagram: Any,
        recreate_reason: str | None,
    ) -> str:
        """Append prior diagram data when the frontend asks for regeneration."""
        extra_sections: list[str] = []

        if recreate_reason:
            extra_sections.append(f"Regeneration reason:\n{recreate_reason}")

        if previous_diagram is not None:
            try:
                diagram_text = json.dumps(previous_diagram, indent=2, ensure_ascii=True, default=str)
            except TypeError:
                diagram_text = str(previous_diagram)
            extra_sections.append(f"Previous Ishikawa diagram:\n{diagram_text}")

        if not extra_sections:
            return evidence

        return (
            f"{evidence}\n\n"
            "Please regenerate the Ishikawa diagram and improve the structure, clarity, and cause coverage based on the context below.\n\n"
            + "\n\n".join(extra_sections)
        )

    @staticmethod
    def search_knowledge(
        processor: QueryProcessor,
        intent: Intent,
        max_results: int,
    ) -> list[dict[str, Any]]:
        """Search the knowledge base using the caller-defined result limit."""
        return processor.search_knowledge_base(intent, max_results=max_results)

    def _resolve_query(
        self,
        services: AnalysisResources,
        *,
        query: str,
        max_results: int,
    ) -> ResolvedQuery:
        """Resolve intent plus related historical records for a query."""
        intent = services.intent_extractor.extract_intent(query)
        knowledge_results = services.processor.search_knowledge_base(intent, max_results=max_results)
        return ResolvedQuery(
            intent=intent,
            knowledge_results=knowledge_results,
            related_ps=build_related_problem_statements(knowledge_results),
        )

    def analyze_frontend_workflow(self, request: FrontendAnalysisRequest) -> FrontendAnalysisResponse:
        """Run the full analysis workflow for frontend requests."""
        if request.fast_mode:
            return self.analyze_fast_frontend_workflow(request)

        with self.analysis_context() as services:
            result = services.processor.process_query(request.query)
            response = FrontendAnalysisResponse(
                success=result.success,
                query=request.query,
                mode="full",
                processing_time=result.processing_time,
                intent=self.build_intent_payload(result.intent),
                knowledge_base_results=len(result.knowledge_results),
                related_ps=build_related_problem_statements(result.knowledge_results),
                five_whys=result.analysis_results.get("whys"),
                ishikawa=result.analysis_results.get("ishikawa"),
                synthesis=result.synthesis.__dict__ if result.synthesis else None,
                knowledge_results=result.knowledge_results if request.include_details else [],
                error_message=result.error_message,
            )

            if request.additional_context and response.ishikawa is None and response.five_whys is None:
                response.error_message = (
                    response.error_message
                    or "No analysis output was generated for the provided input"
                )

            return response

    def analyze_fast_frontend_workflow(self, request: FrontendAnalysisRequest) -> FrontendAnalysisResponse:
        """Run a lightweight frontend workflow optimized for faster responses."""
        start_time = time.perf_counter()

        with self.analysis_context() as services:
            resolved = self._resolve_query(
                services,
                query=request.query,
                max_results=request.max_results,
            )
            summary_message = (
                f"Fast response returned {len(resolved.knowledge_results)} related records "
                f"for domains: {', '.join(resolved.intent.domains) if resolved.intent.domains else 'General'}."
            )

            return FrontendAnalysisResponse(
                success=True,
                query=request.query,
                mode="fast",
                processing_time=time.perf_counter() - start_time,
                intent=self.build_intent_payload(resolved.intent),
                knowledge_base_results=len(resolved.knowledge_results),
                related_ps=resolved.related_ps,
                knowledge_results=resolved.knowledge_results if request.include_details else [],
                summary_message=summary_message,
            )

    def analyze_five_whys(self, request: FiveWhysRequest) -> FiveWhysResponse:
        """Run standalone 5 Whys analysis for frontend requests."""
        start_time = time.perf_counter()

        with self.analysis_context() as services:
            resolved = self._resolve_query(
                services,
                query=request.query,
                max_results=request.max_results,
            )
            evidence = services.processor.prepare_evidence(resolved.knowledge_results, resolved.intent)
            evidence = self._append_frontend_context(evidence, request.additional_context)

            analysis = services.analysis_coordinator.perform_whys_analysis(
                problem_statement=resolved.intent.summary or request.query,
                domain=request.domain or (resolved.intent.domains[0] if resolved.intent.domains else "General"),
                phase=request.phase,
                evidence=evidence,
            )

            return FiveWhysResponse(
                success=True,
                query=request.query,
                processing_time=time.perf_counter() - start_time,
                intent=self.build_intent_payload(resolved.intent),
                knowledge_base_results=len(resolved.knowledge_results),
                related_ps=resolved.related_ps,
                analysis=analysis,
            )

    def analyze_ishikawa(
        self,
        request: IshikawaRequest | IshikawaRecreateRequest,
        regenerated: bool = False,
    ) -> IshikawaDiagramResponse:
        """Run standalone Ishikawa generation or regeneration for frontend requests."""
        start_time = time.perf_counter()

        with self.analysis_context() as services:
            resolved = self._resolve_query(
                services,
                query=request.query,
                max_results=request.max_results,
            )
            evidence = services.processor.prepare_evidence(resolved.knowledge_results, resolved.intent)
            evidence = self._append_frontend_context(evidence, request.additional_context)

            if regenerated and isinstance(request, IshikawaRecreateRequest):
                evidence = self._append_regeneration_context(
                    evidence=evidence,
                    previous_diagram=request.previous_diagram,
                    recreate_reason=request.recreate_reason,
                )

            analysis = services.analysis_coordinator.generate_ishikawa_diagram(
                problem_statement=resolved.intent.summary or request.query,
                evidence=evidence,
            )

            return IshikawaDiagramResponse(
                success=True,
                query=request.query,
                processing_time=time.perf_counter() - start_time,
                intent=self.build_intent_payload(resolved.intent),
                knowledge_base_results=len(resolved.knowledge_results),
                related_ps=resolved.related_ps,
                analysis=analysis,
                regenerated=regenerated,
            )

    def search(self, request: SearchRequest) -> SearchResponse:
        """Run a repository search for frontend or API clients."""
        with self.repository_context() as repository:
            criteria = SearchCriteria(
                domains=request.domains or [],
                keywords=request.keywords or [],
                phases=request.phases or [],
                part_numbers=request.part_numbers or [],
                time_filter=request.time_filter,
                limit=request.limit,
                fuzzy_match=request.fuzzy_match,
            )
            results = repository.search_problems(criteria)

        search_results = [
            {
                "id": result.get("id", ""),
                "title": result.get("title"),
                "description": result.get("description") or result.get("text") or result.get("summary"),
                "symptoms": result.get("symptoms"),
                "domain": result.get("domain") or next(iter(result.get("domains", [])), None),
                "phase": result.get("phase") or next(
                    (
                        phase.get("code")
                        for phase in result.get("phases", [])
                        if isinstance(phase, dict) and phase.get("code")
                    ),
                    None,
                ),
                "score": result.get("score"),
                "causes": result.get("causes", []),
                "evidence": result.get("evidence", result.get("contents", [])),
            }
            for result in results
        ]

        return SearchResponse(
            results=search_results,
            total_count=len(search_results),
            search_criteria={
                "domains": request.domains,
                "keywords": request.keywords,
                "phases": request.phases,
                "time_filter": request.time_filter,
                "limit": request.limit,
                "fuzzy_match": request.fuzzy_match,
            },
        )

    def health(self) -> HealthResponse:
        """Run a database-backed health check for the API."""
        db_connection = Neo4jConnection(self._config.database)
        connected = db_connection.connect()

        try:
            if not connected:
                return HealthResponse(
                    status="unhealthy",
                    database_connected=False,
                    node_count=0,
                    relationship_count=0,
                )

            health_info = db_connection.health_check()
            return HealthResponse(
                status="healthy" if health_info["status"] == "healthy" else "unhealthy",
                database_connected=health_info["connected"],
                database_info=health_info.get("database_info"),
                node_count=health_info.get("node_count", 0),
                relationship_count=health_info.get("relationship_count", 0),
            )
        finally:
            db_connection.disconnect()
