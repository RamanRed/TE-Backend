"""Utilities for extracting and normalizing JSON-like model output."""

from __future__ import annotations

import re


def extract_json_candidate(content: str) -> str:
    """Extract the most likely JSON object or array from model output."""
    text = content.strip()

    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            return text[start:end].strip()

    if "```" in text:
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
        if blocks:
            return blocks[0].strip()

    object_start = text.find("{")
    array_start = text.find("[")
    starts = [index for index in (object_start, array_start) if index != -1]
    if not starts:
        return text

    first = min(starts)
    stack: list[str] = []
    in_string = False
    escaped = False

    for idx in range(first, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch in "[{":
            stack.append(ch)
            continue

        if ch in "]}":
            if not stack:
                continue
            opening = stack[-1]
            is_match = (opening == "[" and ch == "]") or (opening == "{" and ch == "}")
            if not is_match:
                continue
            stack.pop()
            if not stack:
                return text[first : idx + 1].strip()

    return text[first:].strip()


def cleanup_json_candidate(candidate: str) -> str:
    """Apply conservative cleanup rules to JSON-like text."""
    cleaned = candidate.strip()
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\ufeff", "")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned
