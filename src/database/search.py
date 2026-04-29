"""Shared search models for database queries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchCriteria:
    """Search criteria for knowledge base queries."""

    domains: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    part_numbers: list[str] = field(default_factory=list)
    time_filter: str | None = None
    limit: int = 50
    fuzzy_match: bool = True
    date_from: str | None = None
    date_to: str | None = None
    severity_min: int | None = None
    category: str | None = None
