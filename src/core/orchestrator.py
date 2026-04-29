"""
LangGraph orchestrator for complex multi-step analysis workflows.
Coordinates the execution of analysis pipelines with conditional logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from .analysis_helpers import build_evidence_payload, build_findings_summary
from ..database.repository import KnowledgeRepository
from ..database.search import SearchCriteria
from ..llm.extractor import AnalysisCoordinator, AnalysisResult, Intent, IntentExtractor
from ..llm.service import LLMService
from ..utils.config import get_config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AnalysisState(TypedDict):
    """State for the analysis workflow."""
    query: str
    intent: Intent | None
    knowledge_results: list[dict[str, Any]]
    analyses: dict[str, Any]
    synthesis: AnalysisResult | None
    current_step: str
    errors: list[str]


@dataclass
class WorkflowResult:
    """Result of the orchestrated workflow."""
    final_state: AnalysisState
    execution_path: list[str]
    success: bool
    error_message: str | None = None


class AnalysisOrchestrator:
    """Orchestrates complex analysis workflows using state-based execution."""

    def __init__(self, knowledge_repository: KnowledgeRepository):
        self.knowledge_repository = knowledge_repository
        # Note: LangGraph would be imported here in a full implementation
        # from langgraph import StateGraph, END

    @staticmethod
    def _build_intent_extractor() -> IntentExtractor:
        """Build an intent extractor backed by the configured LLM service."""
        return IntentExtractor(LLMService(get_config().llm))

    @staticmethod
    def _build_analysis_coordinator() -> AnalysisCoordinator:
        """Build an analysis coordinator backed by the configured LLM service."""
        return AnalysisCoordinator(LLMService(get_config().llm))

    def execute_analysis_workflow(self, query: str) -> WorkflowResult:
        """
        Execute the complete analysis workflow.

        Args:
            query: User query to analyze

        Returns:
            WorkflowResult with execution details
        """
        logger.info("Starting orchestrated analysis workflow")

        # Initialize state
        initial_state: AnalysisState = {
            "query": query,
            "intent": None,
            "knowledge_results": [],
            "analyses": {},
            "synthesis": None,
            "current_step": "initialize",
            "errors": []
        }

        execution_path = []

        try:
            # Step 1: Intent Extraction
            execution_path.append("intent_extraction")
            initial_state = self._extract_intent(initial_state)

            # Step 2: Knowledge Base Search
            execution_path.append("knowledge_search")
            initial_state = self._search_knowledge(initial_state)

            # Step 3: Determine Analysis Path
            execution_path.append("analysis_routing")
            initial_state = self._route_analysis(initial_state)

            # Step 4: Execute Analyses
            if initial_state["current_step"] == "perform_whys":
                execution_path.append("whys_analysis")
                initial_state = self._perform_whys_analysis(initial_state)

            if initial_state["current_step"] == "perform_ishikawa":
                execution_path.append("ishikawa_analysis")
                initial_state = self._perform_ishikawa_analysis(initial_state)

            if initial_state["current_step"] == "perform_both":
                execution_path.extend(["whys_analysis", "ishikawa_analysis"])
                initial_state = self._perform_whys_analysis(initial_state)
                initial_state = self._perform_ishikawa_analysis(initial_state)

            # Step 5: Synthesis
            execution_path.append("synthesis")
            initial_state = self._synthesize_results(initial_state)

            # Step 6: Finalize
            execution_path.append("finalize")
            initial_state["current_step"] = "completed"

            logger.info("Analysis workflow completed successfully")
            return WorkflowResult(
                final_state=initial_state,
                execution_path=execution_path,
                success=True
            )

        except Exception as e:
            error_msg = f"Workflow execution failed: {e}"
            logger.error(error_msg)
            initial_state["errors"].append(error_msg)
            initial_state["current_step"] = "failed"

            return WorkflowResult(
                final_state=initial_state,
                execution_path=execution_path,
                success=False,
                error_message=error_msg
            )

    def _extract_intent(self, state: AnalysisState) -> AnalysisState:
        """Extract intent from the query."""
        try:
            extractor = self._build_intent_extractor()
            intent = extractor.extract_intent(state["query"])
            state["intent"] = intent
            logger.info(f"Intent extracted: domains={intent.domains}")
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            state["errors"].append(f"Intent extraction: {e}")

        return state

    def _search_knowledge(self, state: AnalysisState) -> AnalysisState:
        """Search knowledge base for relevant information."""
        if not state["intent"]:
            state["errors"].append("Cannot search knowledge base: no intent extracted")
            return state

        try:
            intent = state["intent"]
            criteria = SearchCriteria(
                domains=intent.domains,
                keywords=intent.keywords,
                phases=intent.phases,
                part_numbers=intent.part_numbers,
                time_filter=intent.time_filter,
                limit=20
            )

            results = self.knowledge_repository.search_problems(criteria)
            state["knowledge_results"] = results
            logger.info(f"Knowledge search found {len(results)} results")

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            state["errors"].append(f"Knowledge search: {e}")

        return state

    def _route_analysis(self, state: AnalysisState) -> AnalysisState:
        """Determine which analyses to perform based on intent and results."""
        if not state["intent"]:
            state["current_step"] = "skip_analysis"
            return state

        intent = state["intent"]
        knowledge_count = len(state["knowledge_results"])

        # Decision logic for analysis routing
        if "D5" in intent.phases:
            # D5 = Ishikawa/root-cause analysis phase
            state["current_step"] = "perform_ishikawa"
        elif len(intent.domains) > 1 and knowledge_count < 5:
            # Multiple domains and limited knowledge - need both analyses
            state["current_step"] = "perform_both"
        elif len(intent.keywords) > 4 or len(intent.summary) > 100:
            # Complex problem - perform Ishikawa
            state["current_step"] = "perform_ishikawa"
        elif knowledge_count == 0:
            # No existing knowledge - perform 5 Whys to build understanding
            state["current_step"] = "perform_whys"
        else:
            # Default: perform targeted analysis based on available data
            state["current_step"] = "perform_whys"

        logger.info(f"Analysis routing decision: {state['current_step']}")
        return state

    def _perform_whys_analysis(self, state: AnalysisState) -> AnalysisState:
        """Perform 5 Whys analysis."""
        if not state["intent"]:
            return state

        try:
            coordinator = self._build_analysis_coordinator()
            intent = state["intent"]
            evidence = self._prepare_evidence_text(state)

            result = coordinator.perform_whys_analysis(
                problem_statement=intent.summary,
                domain=intent.domains[0] if intent.domains else "General",
                phase="D5",
                evidence=evidence
            )

            state["analyses"]["whys"] = result
            logger.info("5 Whys analysis completed")

        except Exception as e:
            logger.error(f"5 Whys analysis failed: {e}")
            state["errors"].append(f"5 Whys analysis: {e}")

        return state

    def _perform_ishikawa_analysis(self, state: AnalysisState) -> AnalysisState:
        """Perform Ishikawa diagram analysis."""
        if not state["intent"]:
            return state

        try:
            coordinator = self._build_analysis_coordinator()
            intent = state["intent"]
            evidence = self._prepare_evidence_text(state)

            result = coordinator.generate_ishikawa_diagram(
                problem_statement=intent.summary,
                evidence=evidence
            )

            state["analyses"]["ishikawa"] = result
            logger.info("Ishikawa analysis completed")

        except Exception as e:
            logger.error(f"Ishikawa analysis failed: {e}")
            state["errors"].append(f"Ishikawa analysis: {e}")

        return state

    def _synthesize_results(self, state: AnalysisState) -> AnalysisState:
        """Synthesize analysis results into final recommendations."""
        if not state["intent"] or not state["analyses"]:
            return state

        try:
            coordinator = self._build_analysis_coordinator()
            intent = state["intent"]
            findings = self._prepare_findings_summary(state)

            result = coordinator.synthesize_findings(
                problem_statement=intent.summary,
                domains=intent.domains,
                evidence_count=len(state["knowledge_results"]),
                findings=findings
            )

            state["synthesis"] = result
            logger.info("Results synthesis completed")

        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            state["errors"].append(f"Synthesis: {e}")

        return state

    def _prepare_evidence_text(self, state: AnalysisState) -> str:
        """Prepare evidence text from historical records in the knowledge base."""
        if not state["intent"]:
            return "No matching historical records found."
        return build_evidence_payload(state.get("knowledge_results", []), state["intent"])

    def _prepare_findings_summary(self, state: AnalysisState) -> str:
        """Prepare findings summary for synthesis."""
        return build_findings_summary(state.get("knowledge_results", []), state["analyses"])


# Simplified workflow execution for cases where LangGraph is not available
def execute_simple_workflow(query: str, knowledge_repo: KnowledgeRepository) -> WorkflowResult:
    """
    Execute a simplified workflow without LangGraph.

    Args:
        query: User query
        knowledge_repo: Knowledge repository instance

    Returns:
        Workflow result
    """
    orchestrator = AnalysisOrchestrator(knowledge_repo)
    return orchestrator.execute_analysis_workflow(query)
