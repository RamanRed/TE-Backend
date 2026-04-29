"""Lightweight response-oriented orchestrator built on QueryProcessor."""

from __future__ import annotations

from typing import Any

from .analysis_helpers import build_related_problem_statements
from .processor import ProcessingResult, QueryProcessor
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AnalysisOrchestrator:
    """High-level orchestrator for the complete analysis workflow."""

    def __init__(self, processor: QueryProcessor):
        self.processor = processor

    @staticmethod
    def _build_related_ps(knowledge_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Backward-compatible related-PS builder."""
        return build_related_problem_statements(knowledge_results)

    @staticmethod
    def _serialize_intent(result: ProcessingResult) -> dict[str, Any]:
        """Convert intent objects into response-safe dictionaries."""
        return {
            "domains": result.intent.domains,
            "keywords": result.intent.keywords,
            "part_numbers": result.intent.part_numbers,
            "phases": result.intent.phases,
            "time_filter": result.intent.time_filter,
            "summary": result.intent.summary,
        }

    def analyze_problem(self, query: str) -> dict[str, Any]:
        """Perform complete problem analysis and return a compact API payload."""
        logger.info("Starting complete problem analysis")
        result = self.processor.process_query(query)

        response = {
            "success": result.success,
            "processing_time": result.processing_time,
            "intent": self._serialize_intent(result),
            "knowledge_base_results": len(result.knowledge_results),
            "analyses_performed": list(result.analysis_results.keys()),
            "related_ps": self._build_related_ps(result.knowledge_results),
        }

        if result.synthesis:
            response["root_cause"] = result.synthesis.root_cause
            response["recommendations"] = result.synthesis.recommendations
            response["confidence"] = result.synthesis.confidence_level

        if result.error_message:
            response["error"] = result.error_message

        logger.info("Analysis completed: success=%s", result.success)
        return response

    def get_analysis_details(self, query: str) -> dict[str, Any]:
        """Return the full intermediate analysis payload for debugging or UI details."""
        result = self.processor.process_query(query)
        return {
            "intent": self._serialize_intent(result),
            "knowledge_results": result.knowledge_results,
            "analysis_results": result.analysis_results,
            "synthesis": result.synthesis.__dict__ if result.synthesis else None,
            "related_ps": self._build_related_ps(result.knowledge_results),
            "processing_time": result.processing_time,
            "success": result.success,
            "error_message": result.error_message,
        }
