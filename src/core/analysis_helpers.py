"""Shared helpers for analysis pipelines and response shaping."""

from __future__ import annotations

from typing import Any

from ..llm.extractor import Intent


def build_related_problem_statements(
    knowledge_results: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Build the list of historical problem statements to surface in responses."""
    related: list[dict[str, Any]] = []
    for record in knowledge_results[:limit]:
        ps_id = record.get("id", "")
        if not ps_id:
            continue

        root_causes: list[str] = []
        corrections: list[str] = []
        for content in record.get("contents") or []:
            if not isinstance(content, dict):
                continue
            if content.get("root_cause"):
                root_causes.append(content["root_cause"])
            if content.get("corrective_action"):
                corrections.append(content["corrective_action"])

        related.append(
            {
                "id": ps_id,
                "title": record.get("title", ""),
                "summary": record.get("summary", ""),
                "domains": record.get("domain_tags") or record.get("domains") or [],
                "ticket_ref": record.get("ticket_ref"),
                "quality_score": record.get("quality_score"),
                "key_root_causes": list(dict.fromkeys(root_causes))[:3],
                "key_corrective_actions": list(dict.fromkeys(corrections))[:3],
            }
        )
    return related


def build_evidence_payload(
    knowledge_results: list[dict[str, Any]],
    intent: Intent,
    *,
    limit: int = 10,
) -> str:
    """
    Prepare evidence text from historical records and the extracted intent.

    The payload emphasizes past root causes, corrective actions, and Ishikawa
    categories so the LLM can ground the current analysis in existing data.
    """
    evidence_parts: list[str] = []

    if intent.keywords:
        evidence_parts.append(f"Current query keywords: {', '.join(intent.keywords)}")
    if intent.domains:
        evidence_parts.append(f"Domains under investigation: {', '.join(intent.domains)}")
    if intent.part_numbers:
        evidence_parts.append(f"Part Numbers: {', '.join(intent.part_numbers)}")

    if not knowledge_results:
        evidence_parts.append("No matching historical records found.")
        return "\n".join(evidence_parts)

    evidence_parts.append(f"\n--- {len(knowledge_results)} MATCHING HISTORICAL RECORDS ---")

    for index, record in enumerate(knowledge_results[:limit], start=1):
        title = record.get("title", "Untitled")
        summary = record.get("summary", record.get("text", ""))[:300]
        keywords = record.get("keywords_extracted") or record.get("keywords") or []
        domains = record.get("domain_tags") or record.get("domains") or []

        block = [f"\n[Record {index}] {title}"]
        if domains:
            block.append(f"  Domains: {', '.join(domains)}")
        if keywords:
            block.append(f"  Keywords: {', '.join(keywords[:10])}")
        if summary:
            block.append(f"  Summary: {summary}")

        root_causes: list[str] = []
        corrections: list[str] = []
        categories: dict[str, int] = {}
        for content in record.get("contents") or []:
            if not isinstance(content, dict):
                continue
            root_cause = content.get("root_cause", "")
            corrective_action = content.get("corrective_action", "")
            category = content.get("category", "")
            phase = content.get("phase_code", "")
            if root_cause:
                root_causes.append(f"[{phase}] {root_cause}")
            if corrective_action:
                corrections.append(f"[{phase}] {corrective_action}")
            if category:
                categories[category] = categories.get(category, 0) + 1

        if root_causes:
            block.append(f"  Root Causes: {'; '.join(root_causes[:5])}")
        if corrections:
            block.append(f"  Corrective Actions: {'; '.join(corrections[:5])}")
        if categories:
            block.append(
                "  Ishikawa categories: "
                + ", ".join(f"{category}({count})" for category, count in categories.items())
            )

        evidence_parts.append("\n".join(block))

    evidence_parts.append(
        "\nUse the above historical root causes, corrective actions, and "
        "Ishikawa categories as the primary basis for reorganising the "
        "current query's analysis. Supplement with engineering reasoning "
        "only where historical data has gaps."
    )

    return "\n".join(evidence_parts)


def build_findings_summary(
    knowledge_results: list[dict[str, Any]],
    analysis_results: dict[str, Any],
    *,
    limit: int = 10,
) -> str:
    """Prepare a compact findings summary for synthesis."""
    findings: list[str] = []

    if knowledge_results:
        findings.append(f"Found {len(knowledge_results)} related historical cases.")
        all_root_causes: list[str] = []
        all_corrections: list[str] = []

        for record in knowledge_results[:limit]:
            for content in record.get("contents") or []:
                if not isinstance(content, dict):
                    continue
                if content.get("root_cause"):
                    all_root_causes.append(content["root_cause"])
                if content.get("corrective_action"):
                    all_corrections.append(content["corrective_action"])

        if all_root_causes:
            findings.append(f"Historical root causes: {'; '.join(list(dict.fromkeys(all_root_causes))[:5])}")
        if all_corrections:
            findings.append(
                f"Historical corrective actions: {'; '.join(list(dict.fromkeys(all_corrections))[:5])}"
            )
    else:
        findings.append("No directly related cases found in knowledge base.")

    whys_data = analysis_results.get("whys") or {}
    if "root_cause" in whys_data:
        findings.append(f"5 Whys root cause (current query): {whys_data['root_cause']}")
    chain = whys_data.get("analysis_chain", [])
    if chain:
        findings.append(f"5 Whys depth: {len(chain)} levels")

    ishikawa_data = analysis_results.get("ishikawa") or {}
    bones = ishikawa_data.get("bones", {})
    if bones:
        total = sum(len(entries) for entries in bones.values())
        findings.append(f"Ishikawa identified {total} causes across {len(bones)} categories")
    key_findings = ishikawa_data.get("key_findings", [])
    if key_findings:
        findings.append(f"Ishikawa key findings: {'; '.join(key_findings[:3])}")

    return "\n".join(findings)


def should_perform_whys(intent: Intent) -> bool:
    """Determine whether 5 Whys analysis should run."""
    return "D5" in intent.phases or len(intent.keywords) > 3 or len(intent.summary) > 100


def should_perform_ishikawa(intent: Intent, knowledge_results: list[dict[str, Any]]) -> bool:
    """Determine whether Ishikawa analysis should run."""
    return (
        len(intent.domains) > 1
        or len(intent.keywords) > 5
        or (len(knowledge_results) < 3 and len(intent.keywords) > 2)
    )
