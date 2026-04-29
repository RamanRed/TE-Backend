"""
Analysis request/response schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .shared import IntentResponse, RelatedPS, SynthesisResponse, KnowledgeResult


class AnalysisRequest(BaseModel):
    """Request model for problem analysis."""

    query: str = Field(..., description="User query describing the problem to analyze")
    include_details: bool = Field(False, description="Whether to include detailed analysis steps")
    max_results: int = Field(20, description="Maximum number of knowledge base results to return")


class AnalysisResponse(BaseModel):
    """Complete response model for problem analysis."""

    success: bool = Field(True, description="Whether the analysis was successful")
    processing_time: float = Field(0.0, description="Total processing time in seconds")
    intent: IntentResponse = Field(..., description="Extracted intent")
    knowledge_base_results: int = Field(0, description="Number of knowledge base results found")
    analyses_performed: List[str] = Field(default_factory=list, description="Types of analyses performed")
    root_cause: Optional[str] = Field(None, description="Identified root cause")
    recommendations: List[str] = Field(default_factory=list, description="Final recommendations")
    confidence: Optional[float] = Field(None, description="Overall confidence level")
    related_ps: List[RelatedPS] = Field(default_factory=list, description="Most related historical Problem Statements")
    error: Optional[str] = Field(None, description="Error message if analysis failed")


class DetailedAnalysisResponse(BaseModel):
    """Detailed response model with all analysis steps."""

    intent: IntentResponse = Field(..., description="Extracted intent")
    knowledge_results: List[KnowledgeResult] = Field(default_factory=list, description="Detailed knowledge base results")
    analysis_results: Dict[str, Any] = Field(default_factory=dict, description="Detailed analysis results")
    synthesis: Optional[SynthesisResponse] = Field(None, description="Synthesis results")
    related_ps: List[RelatedPS] = Field(default_factory=list, description="Most related historical Problem Statements")
    processing_time: float = Field(0.0, description="Total processing time")
    success: bool = Field(True, description="Analysis success status")
    error_message: Optional[str] = Field(None, description="Error details")
