"""5-Why generation helpers."""

from typing import Any, Dict, List

from ..root_cause.constants import (
    FIVE_WHY_MAX_NUM_PREDICT,
    FIVE_WHY_MIN_NUM_PREDICT,
    FIVE_WHY_REQUEST_TIMEOUT,
    FIVE_WHY_TOKENS_PER_CAUSE,
)
from ..root_cause.schemas import FiveWhyPayload, validate_five_why_payload
from ..root_cause.normalize import stringify_value


def compute_five_why_num_predict(cause_total: int) -> int:
    estimated = max(FIVE_WHY_MIN_NUM_PREDICT, cause_total * FIVE_WHY_TOKENS_PER_CAUSE)
    return min(FIVE_WHY_MAX_NUM_PREDICT, estimated)


def extract_cause_text(item: Any) -> str:
    if isinstance(item, dict):
        return (
            stringify_value(item.get("cause"))
            or stringify_value(item.get("description"))
            or stringify_value(item.get("title"))
            or stringify_value(item.get("text"))
            or ""
        )
    return stringify_value(item) or ""


def compact_ishikawa_for_five_why(ishikawa: List[Any], max_causes: int) -> List[Dict[str, Any]]:
    """Shrink Ishikawa payload for faster 5-Why generation without losing core cause context."""
    compact: List[Dict[str, Any]] = []
    cause_count = 0

    for category_index, category in enumerate(ishikawa, start=1):
        if cause_count >= max_causes:
            break

        if not isinstance(category, dict):
            continue

        category_id = category.get("id", category_index)
        category_name = stringify_value(category.get("category")) or f"Category {category_index}"
        raw_results = category.get("result") or category.get("results") or []
        if not isinstance(raw_results, list):
            raw_results = [raw_results]

        simplified_results: List[Dict[str, str]] = []
        for result_index, item in enumerate(raw_results, start=1):
            if cause_count >= max_causes:
                break

            cause = extract_cause_text(item).strip()
            if not cause:
                continue

            raw_problem_id = item.get("problem_id") if isinstance(item, dict) else None
            problem_id = str(raw_problem_id).strip() if raw_problem_id not in (None, "") else f"{category_id}-{result_index}"

            simplified_results.append(
                {
                    "problem_id": problem_id,
                    "cause": cause,
                }
            )
            cause_count += 1

        if simplified_results:
            compact.append(
                {
                    "id": category_id,
                    "category": category_name,
                    "result": simplified_results,
                }
            )

    return compact


def generate_structured_five_why(
    llm_service,
    prompt: str,
    output_name: str,
    num_predict: int,
) -> FiveWhyPayload:
    response = llm_service.client.generate(
        prompt,
        temperature=0.2,
        format="json",
        request_timeout=FIVE_WHY_REQUEST_TIMEOUT,
        options={"num_predict": num_predict},
    )
    if not response.success:
        raise RuntimeError(response.error_message)

    try:
        parsed = llm_service._parse_json_response(response.content, output_name)
        return validate_five_why_payload(parsed)
    except Exception as first_error:
        strict_prompt = (
            prompt
            + "\n\nIMPORTANT: Return ONLY strict valid JSON matching the provided schema."
            + " No markdown fences, no prose, no trailing commas."
            + " Ensure double quotes on all keys/strings."
        )
        retry = llm_service.client.generate(
            strict_prompt,
            temperature=0.0,
            format="json",
            request_timeout=FIVE_WHY_REQUEST_TIMEOUT,
            options={"num_predict": num_predict},
        )
        if not retry.success:
            raise RuntimeError(retry.error_message)

        parsed_retry = llm_service._parse_json_response(retry.content, f"{output_name} Retry")
        return validate_five_why_payload(parsed_retry)
