"""Normalization helpers for root cause payloads."""

import re
from typing import Any, Optional

from .constants import BONE_ALIASES


def normalize_bone_name(name: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", str(name).strip().lower())
    return BONE_ALIASES.get(normalized, str(name).strip())


def stringify_value(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [stringify_value(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "description", "cause", "title", "name", "value"):
            if key in value and value[key] not in (None, ""):
                stringified = stringify_value(value[key])
                if stringified:
                    return stringified
        return ", ".join(
            f"{key}: {stringify_value(val)}"
            for key, val in value.items()
            if stringify_value(val)
        ) or str(value)
    return str(value)
