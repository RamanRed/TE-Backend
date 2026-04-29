"""
Shared Pydantic models used across API responses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentResponse(BaseModel):
    """Response model for extracted intent."""

    domains: List[str] = Field(default_factory=list, description="Identified investigation domains")
    keywords: List[str] = Field(default_factory=list, description="Extracted technical keywords")
    part_numbers: List[str] = Field(default_factory=list, description="Identified part numbers")
    phases: List[str] = Field(default_factory=list, description="Relevant investigation phases")
    time_filter: Optional[str] = Field(None, description="Time-based filter")
    summary: str = Field("", description="Problem summary")


class RelatedPS(BaseModel):
    """A historical Problem Statement most related to the current query."""

    id: str = Field(..., description="Problem Statement ID")
    title: str = Field("", description="PS title")
    summary: str = Field("", description="PS executive summary")
    domains: List[str] = Field(default_factory=list, description="Ishikawa domains")
    ticket_ref: Optional[str] = Field(None, description="Ticket / JIRA reference")
    quality_score: Optional[float] = Field(None, description="Documentation quality 0-1")
    key_root_causes: List[str] = Field(default_factory=list, description="Root causes from historical content")
    key_corrective_actions: List[str] = Field(default_factory=list, description="Corrective actions from historical content")


class KnowledgeResult(BaseModel):
    """Response model for knowledge base search results."""

    id: str = Field(..., description="Result ID")
    title: Optional[str] = Field(None, description="Result title")
    description: Optional[str] = Field(None, description="Result description")
    symptoms: Optional[str] = Field(None, description="Associated symptoms")
    domain: Optional[str] = Field(None, description="Investigation domain")
    phase: Optional[str] = Field(None, description="Investigation phase")
    score: Optional[float] = Field(None, description="Relevance score")
    causes: List[Dict[str, Any]] = Field(default_factory=list, description="Associated causes")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Associated evidence")


class AnalysisResultResponse(BaseModel):
    """Response model for analysis results."""

    type: str = Field(..., description="Type of analysis performed")
    result: Dict[str, Any] = Field(..., description="Analysis result data")
    confidence: float = Field(0.0, description="Analysis confidence level")


class SynthesisResponse(BaseModel):
    """Response model for result synthesis."""

    root_cause: str = Field("", description="Identified root cause")
    contributing_factors: List[str] = Field(default_factory=list, description="Contributing factors")
    systemic_issues: List[str] = Field(default_factory=list, description="Systemic issues identified")
    immediate_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Immediate corrective actions")
    preventive_measures: List[Dict[str, Any]] = Field(default_factory=list, description="Preventive measures")
    confidence_level: float = Field(0.0, description="Overall confidence level")
    recommendations: List[str] = Field(default_factory=list, description="Final recommendations")


class HealthResponse(BaseModel):
    """Response model for system health check."""

    status: str = Field(..., description="Overall system status")
    database_connected: bool = Field(False, description="Database connection status")
    database_info: Optional[Dict[str, Any]] = Field(None, description="Database information")
    node_count: int = Field(0, description="Total nodes in database")
    relationship_count: int = Field(0, description="Total relationships in database")
    last_check: datetime = Field(default_factory=datetime.now, description="Time of last health check")


class ErrorResponse(BaseModel):
    """Response model for API errors."""

    error: str = Field(..., description="Error message")
    error_code: str = Field(..., description="Error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")
