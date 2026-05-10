"""Pydantic schemas for root cause analysis routes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from .constants import ISHIKAWA_DEFAULT_SEVERITY, ISHIKAWA_EMPTY_EVIDENCE, ISHIKAWA_EMPTY_SUBCATEGORY
from .normalize import stringify_value


class CategoryResult(BaseModel):
    sub_category: Optional[str] = None
    cause: str
    evidence: Optional[str] = None
    severity: Optional[str] = None

    @field_validator("sub_category", "evidence", "severity", mode="before")
    @classmethod
    def _coerce_optional_text_fields(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            return value
        return stringify_value(value)

    @field_validator("cause", mode="before")
    @classmethod
    def _coerce_required_text_field(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value
        return stringify_value(value) or ""


class IshikawaCategory(BaseModel):
    id: int
    category: str
    result: List[Dict[str, Any]]


class RootCauseProblemRequest(BaseModel):
    domain: str
    query: str
    past_record: Optional[int] = None


class RootCauseProblemResponse(BaseModel):
    success: bool
    ishikawa: List[IshikawaCategory]


class RootCauseRegenerateRequest(BaseModel):
    domain: str
    query: str
    past_record: Optional[int] = None
    locked_result: List[Any]


class RootCauseRegenerateResponse(BaseModel):
    success: bool
    ishikawa: List[IshikawaCategory]


class RootCauseFiveWhyRequest(BaseModel):
    domain: str
    query: str
    past_record: Optional[int] = None
    ishikawa: List[Any]


class RootCauseFiveWhyResponse(BaseModel):
    success: bool
    analysis: List[Any]


class FiveWhyStep(BaseModel):
    level: int
    question: str = ""
    answer: str = ""


class FiveWhyChainItem(BaseModel):
    problem_id: str = ""
    why_chain: List[FiveWhyStep] = Field(default_factory=list)
    root_cause: str = ""
    confidence: float = 0.0


class FiveWhyPayload(BaseModel):
    analysis: List[FiveWhyChainItem] = Field(default_factory=list)


class RootCauseRegenerateFiveWhyRequest(BaseModel):
    domain: str
    query: str
    past_record: Optional[int] = None
    ishikawa: List[Any]
    locked_analysis: List[Any]


class RootCauseFinalizeRequest(BaseModel):
    domain: str
    query: str
    ishikawa: List[Any]
    analysis: List[Any]


class RootCauseFinalizeResponse(BaseModel):
    success: bool
    summary: Dict[str, Any]


def validate_five_why_payload(parsed: Any) -> FiveWhyPayload:
    if isinstance(parsed, FiveWhyPayload):
        return parsed
    if isinstance(parsed, dict):
        try:
            return FiveWhyPayload.model_validate(parsed)
        except ValidationError:
            if isinstance(parsed.get("analysis"), list):
                return FiveWhyPayload(
                    analysis=[
                        FiveWhyChainItem.model_validate(item) if isinstance(item, dict) else FiveWhyChainItem()
                        for item in parsed["analysis"]
                    ]
                )
    if isinstance(parsed, list):
        return FiveWhyPayload(
            analysis=[
                FiveWhyChainItem.model_validate(item) if isinstance(item, dict) else FiveWhyChainItem()
                for item in parsed
            ]
        )
    raise ValueError("Invalid 5-Why payload structure")


def placeholder_category_result() -> Dict[str, Any]:
    return {
        "sub_category": ISHIKAWA_EMPTY_SUBCATEGORY,
        "cause": "Potential contributor requires deeper investigation.",
        "evidence": ISHIKAWA_EMPTY_EVIDENCE,
        "severity": ISHIKAWA_DEFAULT_SEVERITY,
    }


# ---------------------------------------------------------------------------
# Save All — persists finalized analysis to Neo4j + Supabase
# ---------------------------------------------------------------------------

class SaveAllRequest(BaseModel):
    """
    Payload for POST /api/save.

    Contains the finalized Ishikawa and 5-Whys data. Identity is resolved from
    the authenticated JWT and the body identity fields are kept only for legacy
    compatibility checks.
    """

    # Core analysis (mirrors RootCauseFinalizeRequest fields)
    domain: str
    query: str
    ishikawa: List[Any]                     # IshikawaCategory[]
    analysis: List[Any]                     # FiveWhyChainItem[]

    # Legacy-compatible identity fields. The JWT is the source of truth.
    user_id: Optional[str] = None           # users.id of the calling user
    master_user_id: Optional[str] = None    # org's master user UUID
    org_id: Optional[str] = None           # organization UUID

    # Extra metadata
    past_record: Optional[int] = None       # how many Neo4j past records were used
    session_title: Optional[str] = None     # optional user-facing label for this session
    ticket_ref: Optional[str] = None        # optional ticket/issue reference
    part_number: Optional[str] = None       # optional part number


class SaveAllResponse(BaseModel):
    """Response for POST /api/save."""

    success: bool
    message: str

    # Neo4j result
    neo4j_ps_id: Optional[str] = None          # new ProblemStatement id in Neo4j
    neo4j_content_count: int = 0               # number of Content nodes created

    # Supabase result (None when Supabase is not configured)
    supabase_session_id: Optional[str] = None
    supabase_ishikawa_id: Optional[str] = None
    supabase_five_whys_id: Optional[str] = None
    supabase_skipped: bool = False             # True when SUPABASE_URL is not set


# ---------------------------------------------------------------------------
# History — fetching saved analyses from Supabase
# ---------------------------------------------------------------------------

class HistoryRequest(BaseModel):
    """Payload to request the user's history.
    
    JWT token is verified via Bearer token in Authorization header.
    Only org_id is required in the body.
    """
    org_id: str


class HistorySessionItem(BaseModel):
    """A single saved analysis session returned in the history."""
    session_id: str
    query: str
    domain: Optional[str] = None
    title: Optional[str] = None
    created_at: str

    # Summarized stats for list view
    cause_count: int = 0
    root_causes: List[str] = Field(default_factory=list)

    # Full data snapshots
    ishikawa: List[Any] = Field(default_factory=list)
    five_whys: List[Any] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    """Response for POST /api/history."""
    success: bool
    sessions: List[HistorySessionItem]
    message: Optional[str] = None
