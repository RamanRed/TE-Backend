"""
Frontend-oriented request/response schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .shared import IntentResponse, RelatedPS, KnowledgeResult, SynthesisResponse


class FrontendAnalysisRequest(BaseModel):
    """Frontend request model for full workflow analysis."""

    query: str = Field(..., description="Problem statement submitted from the frontend form")
    include_details: bool = Field(False, description="Whether to return detailed knowledge results")
    max_results: int = Field(20, description="Maximum number of related records to search")
    fast_mode: bool = Field(False, description="Return a faster lightweight response without full RCA generation")
    additional_context: Optional[str] = Field(
        None,
        description="Optional extra context from the frontend form or user session",
    )


class FiveWhysRequest(BaseModel):
    """Frontend request model for standalone 5 Whys analysis."""

    query: str = Field(..., description="Problem statement submitted from the frontend form")
    max_results: int = Field(20, description="Maximum number of related records to search")
    domain: Optional[str] = Field(None, description="Optional domain override for the 5 Whys analysis")
    phase: str = Field("D5", description="Investigation phase for the 5 Whys analysis")
    additional_context: Optional[str] = Field(
        None,
        description="Optional extra context from the frontend form or user session",
    )


class IshikawaRequest(BaseModel):
    """Frontend request model for standalone Ishikawa generation."""

    query: str = Field(..., description="Problem statement submitted from the frontend form")
    max_results: int = Field(20, description="Maximum number of related records to search")
    additional_context: Optional[str] = Field(
        None,
        description="Optional extra context from the frontend form or user session",
    )


class IshikawaRecreateRequest(IshikawaRequest):
    """Frontend request model for regenerating an Ishikawa diagram."""

    recreate_reason: Optional[str] = Field(
        None,
        description="Why the frontend is requesting a new Ishikawa diagram",
    )
    previous_diagram: Optional[Any] = Field(
        None,
        description="Existing Ishikawa diagram payload that should be improved or regenerated",
    )


class FrontendAnalysisResponse(BaseModel):
    """Frontend-oriented workflow response with all major outputs in one payload."""

    success: bool = Field(True, description="Whether the workflow completed successfully")
    query: str = Field(..., description="Original query received from the frontend")
    mode: str = Field("full", description="Response mode used for the workflow")
    processing_time: float = Field(0.0, description="Total processing time in seconds")
    intent: IntentResponse = Field(..., description="Extracted intent")
    knowledge_base_results: int = Field(0, description="Number of related knowledge base records found")
    related_ps: List[RelatedPS] = Field(default_factory=list, description="Most related historical Problem Statements")
    five_whys: Optional[Dict[str, Any]] = Field(None, description="5 Whys output for the current query")
    ishikawa: Optional[Dict[str, Any]] = Field(None, description="Ishikawa diagram output for the current query")
    synthesis: Optional[SynthesisResponse] = Field(None, description="Combined RCA synthesis for the query")
    knowledge_results: List[KnowledgeResult] = Field(
        default_factory=list,
        description="Detailed knowledge base results when requested",
    )
    summary_message: Optional[str] = Field(None, description="Short summary for lightweight fast responses")
    error_message: Optional[str] = Field(None, description="Error details if the workflow failed")


class FiveWhysResponse(BaseModel):
    """Response model for standalone 5 Whys analysis."""

    success: bool = Field(True, description="Whether the analysis completed successfully")
    query: str = Field(..., description="Original query received from the frontend")
    processing_time: float = Field(0.0, description="Total processing time in seconds")
    intent: IntentResponse = Field(..., description="Extracted intent")
    knowledge_base_results: int = Field(0, description="Number of related knowledge base records found")
    related_ps: List[RelatedPS] = Field(default_factory=list, description="Most related historical Problem Statements")
    analysis: Dict[str, Any] = Field(default_factory=dict, description="5 Whys analysis payload")
    error_message: Optional[str] = Field(None, description="Error details if analysis failed")


class IshikawaDiagramResponse(BaseModel):
    """Response model for standalone Ishikawa generation or regeneration."""

    success: bool = Field(True, description="Whether the analysis completed successfully")
    query: str = Field(..., description="Original query received from the frontend")
    processing_time: float = Field(0.0, description="Total processing time in seconds")
    intent: IntentResponse = Field(..., description="Extracted intent")
    knowledge_base_results: int = Field(0, description="Number of related knowledge base records found")
    related_ps: List[RelatedPS] = Field(default_factory=list, description="Most related historical Problem Statements")
    analysis: Dict[str, Any] = Field(default_factory=dict, description="Ishikawa diagram payload")
    regenerated: bool = Field(False, description="Whether this payload was generated through the regenerate route")
    error_message: Optional[str] = Field(None, description="Error details if analysis failed")
