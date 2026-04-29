"""Helpers for Ishikawa response shaping and merging."""

from typing import Any, Dict, List

from .constants import (
    CANONICAL_BONES,
    ISHIKAWA_DEFAULT_SEVERITY,
    ISHIKAWA_EMPTY_EVIDENCE,
    ISHIKAWA_EMPTY_SUBCATEGORY,
    ISHIKAWA_FILL_EMPTY_CATEGORIES,
)
from .normalize import normalize_bone_name, stringify_value
from .schemas import IshikawaCategory


def build_category_result(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        sub_category = stringify_value(
            item.get("sub_category")
            or item.get("subcategory")
            or item.get("group")
            or item.get("type")
        )
        cause = stringify_value(
            item.get("cause")
            or item.get("description")
            or item.get("title")
            or item.get("text")
            or item.get("reason")
            or item.get("issue")
        )
        evidence = stringify_value(item.get("evidence") or item.get("reasoning") or item.get("support") or item.get("rationale"))
        severity = stringify_value(item.get("severity") or item.get("impact") or item.get("priority"))

        return {
            "sub_category": sub_category or ISHIKAWA_EMPTY_SUBCATEGORY,
            "cause": cause or "Potential contributor requires deeper investigation.",
            "evidence": evidence or ISHIKAWA_EMPTY_EVIDENCE,
            "severity": severity or ISHIKAWA_DEFAULT_SEVERITY,
        }

    return {
        "sub_category": ISHIKAWA_EMPTY_SUBCATEGORY,
        "cause": stringify_value(item) or "Potential contributor requires deeper investigation.",
        "evidence": ISHIKAWA_EMPTY_EVIDENCE,
        "severity": ISHIKAWA_DEFAULT_SEVERITY,
    }


def extract_result_items(category: Dict[str, Any]) -> List[Any]:
    for key in ("result", "results", "causes", "items", "entries"):
        raw = category.get(key)
        if raw in (None, ""):
            continue
        return raw if isinstance(raw, list) else [raw]
    return []


def placeholder_result_for_bone(bone: str) -> Dict[str, str]:
    return {
        "sub_category": ISHIKAWA_EMPTY_SUBCATEGORY,
        "cause": f"No strong {bone.lower()} cause was extracted from current evidence.",
        "evidence": ISHIKAWA_EMPTY_EVIDENCE,
        "severity": ISHIKAWA_DEFAULT_SEVERITY,
    }


def build_ishikawa_response(analysis: Dict[str, Any]) -> List[IshikawaCategory]:
    ishikawa_payload = analysis.get("ishikawa")
    if isinstance(ishikawa_payload, list):
        grouped: Dict[str, List[Dict[str, Any]]] = {bone: [] for bone in CANONICAL_BONES}
        for category in ishikawa_payload:
            if not isinstance(category, dict):
                continue

            raw_results = extract_result_items(category)
            normalized_name = normalize_bone_name(
                category.get("category") or category.get("bone") or category.get("name")
            )
            if normalized_name not in grouped:
                continue

            grouped[normalized_name].extend(
                build_category_result(item)
                for item in raw_results
                if item not in (None, "")
            )

        if ISHIKAWA_FILL_EMPTY_CATEGORIES:
            for bone in CANONICAL_BONES:
                if not grouped[bone]:
                    grouped[bone].append(placeholder_result_for_bone(bone))

        return [
            IshikawaCategory(id=index, category=bone, result=grouped[bone])
            for index, bone in enumerate(CANONICAL_BONES, start=1)
        ]

    bones = analysis.get("bones") or analysis.get("categories") or {}
    if not isinstance(bones, dict):
        return []

    grouped = {bone: [] for bone in CANONICAL_BONES}

    for bone_name, items in bones.items():
        normalized_name = normalize_bone_name(bone_name)
        if normalized_name not in grouped:
            continue

        if isinstance(items, list):
            grouped[normalized_name].extend(
                build_category_result(item)
                for item in items
                if item not in (None, "")
            )
        elif items not in (None, ""):
            grouped[normalized_name].append(build_category_result(items))

    if ISHIKAWA_FILL_EMPTY_CATEGORIES:
        for bone in CANONICAL_BONES:
            if not grouped[bone]:
                grouped[bone].append(placeholder_result_for_bone(bone))

    return [
        IshikawaCategory(id=index, category=bone, result=grouped[bone])
        for index, bone in enumerate(CANONICAL_BONES, start=1)
    ]


def category_signature(item: Dict[str, Any]) -> tuple:
    return (
        item.get("sub_category") or "",
        item.get("cause") or "",
        item.get("evidence") or "",
        item.get("severity") or "",
    )


def merge_ishikawa_categories(
    locked: List[IshikawaCategory],
    generated: List[IshikawaCategory],
) -> List[IshikawaCategory]:
    merged_map: Dict[str, List[Dict[str, Any]]] = {bone: [] for bone in CANONICAL_BONES}

    for category in locked:
        if category.category not in merged_map:
            continue
        merged_map[category.category].extend(category.result or [])

    for category in generated:
        if category.category not in merged_map:
            continue
        existing_signatures = {category_signature(item) for item in merged_map[category.category]}
        for item in (category.result or []):
            signature = category_signature(item)
            if signature in existing_signatures:
                continue
            merged_map[category.category].append(item)
            existing_signatures.add(signature)

    return [
        IshikawaCategory(id=index, category=bone, result=merged_map[bone])
        for index, bone in enumerate(CANONICAL_BONES, start=1)
    ]


def pad_bone_results(ishikawa: List[IshikawaCategory], min_per_bone: int) -> List[IshikawaCategory]:
    """Ensure every bone has at least min_per_bone result items by adding placeholders."""
    padded = []
    for category in ishikawa:
        result = list(category.result) if category.result else []
        while len(result) < min_per_bone:
            result.append(placeholder_result_for_bone(category.category))
        padded.append(IshikawaCategory(id=category.id, category=category.category, result=result))
    return padded
