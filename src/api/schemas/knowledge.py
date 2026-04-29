"""
Knowledge base request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .shared import KnowledgeResult


class SearchRequest(BaseModel):
    """Request model for knowledge base search."""

    domains: Optional[List[str]] = Field(None, description="Investigation domains to filter by")
    keywords: Optional[List[str]] = Field(None, description="Keywords to search for")
    phases: Optional[List[str]] = Field(None, description="Investigation phases to filter by")
    part_numbers: Optional[List[str]] = Field(None, description="Part numbers to search for")
    time_filter: Optional[str] = Field(None, description="Time-based filter")
    limit: int = Field(50, description="Maximum results to return")
    fuzzy_match: bool = Field(True, description="Whether to use fuzzy matching")


class SearchResponse(BaseModel):
    """Response model for search operations."""

    results: List[KnowledgeResult] = Field(default_factory=list, description="Search results")
    total_count: int = Field(0, description="Total number of results found")
    search_criteria: Dict[str, Any] = Field(default_factory=dict, description="Applied search criteria")


class ProblemCreateRequest(BaseModel):
    """Request model for creating a new problem."""

    title: str = Field(..., description="Problem title")
    description: str = Field(..., description="Detailed problem description")
    symptoms: str = Field(..., description="Observed symptoms")
    severity: str = Field("Medium", description="Problem severity")
    domain: str = Field(..., description="Investigation domain")
    phase: str = Field(..., description="Investigation phase")


class CauseCreateRequest(BaseModel):
    """Request model for adding a cause to a problem."""

    problem_id: str = Field(..., description="Parent problem ID")
    description: str = Field(..., description="Cause description")
    category: str = Field(..., description="Cause category")
    severity: str = Field("Medium", description="Cause severity")
    ishikawa_category: str = Field(..., description="Ishikawa diagram category")


class EvidenceCreateRequest(BaseModel):
    """Request model for adding evidence to a problem."""

    problem_id: str = Field(..., description="Parent problem ID")
    content: str = Field(..., description="Evidence content")
    source: str = Field(..., description="Evidence source")
    evidence_type: str = Field(..., description="Type of evidence")
    confidence: float = Field(0.8, description="Confidence level (0-1)")


class SolutionCreateRequest(BaseModel):
    """Request model for adding a solution to a problem."""

    problem_id: str = Field(..., description="Parent problem ID")
    description: str = Field(..., description="Solution description")
    solution_type: str = Field(..., description="Type of solution")
    priority: str = Field("Medium", description="Solution priority")
    status: str = Field("proposed", description="Solution status")
    cause_id: Optional[str] = Field(None, description="Specific cause this addresses")


class ProblemResponse(BaseModel):
    """Response model for problem details."""

    id: str = Field(..., description="Problem ID")
    title: str = Field(..., description="Problem title")
    description: Optional[str] = Field(None, description="Problem description / full text")
    symptoms: Optional[str] = Field(None, description="Problem symptoms")
    severity: Optional[str] = Field(None, description="Problem severity")
    status: Optional[str] = Field(None, description="Problem status")
    domain: Optional[str] = Field(None, description="Investigation domain")
    phase: Optional[str] = Field(None, description="Investigation phase")
    created_date: Optional[datetime] = Field(None, description="Creation date")
    updated_date: Optional[datetime] = Field(None, description="Last update date")
    causes: List[Dict[str, Any]] = Field(default_factory=list, description="Associated causes")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Associated evidence")
    analyses: List[Dict[str, Any]] = Field(default_factory=list, description="Performed analyses")
    solutions: List[Dict[str, Any]] = Field(default_factory=list, description="Proposed solutions")


class StatisticsResponse(BaseModel):
    """Response model for system statistics."""

    problemstatement_count: int = Field(0, description="Total number of problem statements")
    phase_count: int = Field(0, description="Total number of phases")
    subphase_count: int = Field(0, description="Total number of sub-phases")
    content_count: int = Field(0, description="Total number of content nodes")
    domain_count: int = Field(0, description="Number of domains")
    relationship_count: int = Field(0, description="Total relationships")
    domain_breakdown: Dict[str, int] = Field(default_factory=dict, description="PS count per domain")
