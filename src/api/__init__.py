"""
API package for the Ishikawa Knowledge System.
Provides lazy exports to avoid importing the FastAPI app during internal module loads.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_SCHEMA_EXPORTS = {
    "AnalysisRequest",
    "AnalysisResponse",
    "DetailedAnalysisResponse",
    "SearchRequest",
    "SearchResponse",
    "ProblemCreateRequest",
    "ProblemResponse",
    "CauseCreateRequest",
    "EvidenceCreateRequest",
    "SolutionCreateRequest",
    "StatisticsResponse",
    "HealthResponse",
    "ErrorResponse",
}

__all__ = [
    "create_application",
    "app",
    *_SCHEMA_EXPORTS,
    "router",
]


def __getattr__(name: str) -> Any:
    """Load API exports lazily to keep package imports lightweight."""
    if name in {"create_application", "app"}:
        module = import_module(".app", __name__)
        return getattr(module, name)

    if name == "router":
        module = import_module(".routers.v1", __name__)
        return module.router

    if name in _SCHEMA_EXPORTS:
        module = import_module(".schemas", __name__)
        return getattr(module, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
