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
    past_record: int


class RootCauseProblemResponse(BaseModel):
    success: bool
    ishikawa: List[IshikawaCategory]


class RootCauseRegenerateRequest(BaseModel):
    domain: str
    query: str
    past_record: int
    locked_result: List[Any]


class RootCauseRegenerateResponse(BaseModel):
    success: bool
    ishikawa: List[IshikawaCategory]


class RootCauseFiveWhyRequest(BaseModel):
    domain: str
    query: str
    past_record: int
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
    past_record: int
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
