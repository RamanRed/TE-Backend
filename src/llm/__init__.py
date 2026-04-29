"""
LLM package for the Ishikawa Knowledge System.
Provides intent extraction, analysis coordination, and LLM client functionality.
"""

from .client import LLMResponse, OllamaClient
from .extractor import IntentExtractor, AnalysisCoordinator, AnalysisPipeline, Intent, AnalysisResult
from .service import LLMService
from .prompts import (
    get_intent_extraction_prompt,
    get_whys_analysis_prompt,
    get_ishikawa_diagram_prompt,
    get_synthesis_prompt
)

__all__ = [
    # Client classes
    "LLMService",
    "OllamaClient",
    "LLMResponse",

    # Analysis classes
    "IntentExtractor",
    "AnalysisCoordinator",
    "AnalysisPipeline",
    "Intent",
    "AnalysisResult",

    # Prompt functions
    "get_intent_extraction_prompt",
    "get_whys_analysis_prompt",
    "get_ishikawa_diagram_prompt",
    "get_synthesis_prompt"
]
