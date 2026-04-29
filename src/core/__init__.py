"""
Core package for the Ishikawa Knowledge System.
Contains the main processing logic and workflow orchestration.
"""

from .processor import ProcessingResult, QueryProcessor
from .orchestrator import AnalysisOrchestrator as LangGraphOrchestrator, execute_simple_workflow, WorkflowResult
from .simple_orchestrator import AnalysisOrchestrator

__all__ = [
    # Processing components
    "QueryProcessor",
    "AnalysisOrchestrator",
    "ProcessingResult",

    # Orchestration components
    "LangGraphOrchestrator",
    "execute_simple_workflow",
    "WorkflowResult"
]
