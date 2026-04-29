"""Root cause analysis routes and handlers."""

import json

from fastapi import APIRouter, HTTPException

from ..services import APIService
from ...llm.prompts import (
    get_finalize_analysis_prompt,
    get_generate_five_why_prompt,
    get_ishikawa_diagram_prompt,
    get_regenerate_five_why_prompt,
    get_regenerate_ishikawa_prompt,
)
from ...utils.logging import get_logger
from .constants import (
    FIVE_WHY_MAX_CAUSES,
    FIVE_WHY_MAX_NUM_PREDICT,
    FIVE_WHY_TOKENS_PER_CAUSE,
    ISHIKAWA_MIN_RESULTS_PER_BONE,
    ISHIKAWA_NUM_PREDICT,
    ISHIKAWA_REQUEST_TIMEOUT,
)
from .five_whys import (
    compact_ishikawa_for_five_why,
    compute_five_why_num_predict,
    generate_structured_five_why,
)
from .ishikawa import build_ishikawa_response, merge_ishikawa_categories, pad_bone_results
from .schemas import (
    RootCauseFinalizeRequest,
    RootCauseFinalizeResponse,
    RootCauseFiveWhyRequest,
    RootCauseFiveWhyResponse,
    RootCauseProblemRequest,
    RootCauseProblemResponse,
    RootCauseRegenerateFiveWhyRequest,
    RootCauseRegenerateRequest,
    RootCauseRegenerateResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["root-cause-analysis"])
service = APIService()


@router.post("/problem", response_model=RootCauseProblemResponse)
async def generate_problem(request: RootCauseProblemRequest):
    """Generate Problem (Ishikawa)."""
    try:
        logger.info(
            "Problem analysis request received: domain=%s, past_record=%s, query=%s...",
            request.domain,
            request.past_record,
            request.query[:100],
        )

        with service.analysis_context() as services:
            intent = services.intent_extractor.extract_intent(request.query)

            if request.domain:
                domain = request.domain.strip()
                intent.domains = [domain] + [item for item in intent.domains if item.lower() != domain.lower()]

            if request.past_record is not None and not intent.time_filter:
                intent.time_filter = str(request.past_record)

            knowledge_results = APIService.search_knowledge(services.processor, intent, max_results=20)
            evidence = services.processor.prepare_evidence(knowledge_results, intent)

            context_parts = []
            if request.domain:
                context_parts.append(f"Requested domain: {request.domain}")
            if request.past_record is not None:
                context_parts.append(f"Historical reference year: {request.past_record}")

            if context_parts:
                evidence = APIService._append_frontend_context(evidence, "\n".join(context_parts))

            prompt = get_ishikawa_diagram_prompt(
                problem_statement=intent.summary or request.query,
                evidence=evidence,
            )
            llm_service = services.analysis_coordinator.llm_service
            raw_response = llm_service.client.generate(
                prompt,
                temperature=0.2,
                format="json",
                request_timeout=ISHIKAWA_REQUEST_TIMEOUT,
                options={"num_predict": ISHIKAWA_NUM_PREDICT},
            )
            if not raw_response.success:
                raise RuntimeError(f"Ishikawa LLM call failed: {raw_response.error_message}")
            analysis = llm_service._parse_json_response(raw_response.content, "Ishikawa")

        ishikawa_categories = build_ishikawa_response(analysis)
        padded_categories = pad_bone_results(ishikawa_categories, ISHIKAWA_MIN_RESULTS_PER_BONE)

        return RootCauseProblemResponse(
            success=True,
            ishikawa=padded_categories,
        )
    except Exception as e:
        logger.error(f"Error in /api/problem: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate", response_model=RootCauseRegenerateResponse)
async def regenerate_ishikawa(request: RootCauseRegenerateRequest):
    """Regenerate Ishikawa (with Locked Data)."""
    try:
        logger.info("Regenerate Ishikawa request received.")

        with service.analysis_context() as services:
            intent = services.intent_extractor.extract_intent(request.query)
            if request.domain:
                intent.domains = [request.domain]
            if request.past_record is not None and not intent.time_filter:
                intent.time_filter = str(request.past_record)

            knowledge_results = APIService.search_knowledge(services.processor, intent, max_results=20)
            evidence = services.processor.prepare_evidence(knowledge_results, intent)

            locked_json = json.dumps(request.locked_result, indent=2)
            prompt = get_regenerate_ishikawa_prompt(request.query, evidence, locked_json)

            llm_service = services.analysis_coordinator.llm_service
            response = llm_service.client.generate(
                prompt,
                temperature=0.2,
                format="json",
                request_timeout=ISHIKAWA_REQUEST_TIMEOUT,
                options={"num_predict": ISHIKAWA_NUM_PREDICT},
            )

            if not response.success:
                raise RuntimeError(response.error_message)

            parsed = llm_service._parse_json_response(response.content, "Ishikawa Regeneration")

            generated_categories = build_ishikawa_response(parsed)
            locked_categories = build_ishikawa_response({"ishikawa": request.locked_result})
            merged_categories = merge_ishikawa_categories(locked_categories, generated_categories)
            padded_categories = pad_bone_results(merged_categories, ISHIKAWA_MIN_RESULTS_PER_BONE)

        return RootCauseRegenerateResponse(
            success=True,
            ishikawa=padded_categories,
        )
    except Exception as e:
        logger.error(f"Error in /api/regenerate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/gen-five-why", response_model=RootCauseFiveWhyResponse)
async def gen_five_why(request: RootCauseFiveWhyRequest):
    """Generate 5-Why Analysis."""
    try:
        logger.info("Generate 5-Why request received.")

        with service.analysis_context() as services:
            compact_ishikawa = compact_ishikawa_for_five_why(request.ishikawa, FIVE_WHY_MAX_CAUSES)
            if not compact_ishikawa:
                raise HTTPException(status_code=400, detail="No valid Ishikawa causes found for 5-Why generation")

            cause_total = sum(len(category.get("result", [])) for category in compact_ishikawa)
            logger.info(
                "5-Why generation using %s causes (cap=%s)",
                cause_total,
                FIVE_WHY_MAX_CAUSES,
            )

            num_predict = compute_five_why_num_predict(cause_total)
            logger.info("5-Why generation num_predict=%s", num_predict)

            ishikawa_json = json.dumps(compact_ishikawa, indent=2)
            prompt = get_generate_five_why_prompt(request.query, request.domain, ishikawa_json)

            llm_service = services.analysis_coordinator.llm_service
            payload = generate_structured_five_why(
                llm_service,
                prompt,
                "5-Why Generation",
                num_predict=num_predict,
            )

            if not payload.analysis and cause_total > 0 and num_predict < FIVE_WHY_MAX_NUM_PREDICT:
                expanded_num_predict = min(
                    FIVE_WHY_MAX_NUM_PREDICT,
                    num_predict + max(FIVE_WHY_TOKENS_PER_CAUSE * 2, cause_total * 120),
                )
                logger.warning(
                    "5-Why generation returned empty analysis; retrying once with num_predict=%s",
                    expanded_num_predict,
                )
                payload = generate_structured_five_why(
                    llm_service,
                    prompt,
                    "5-Why Generation Expanded",
                    num_predict=expanded_num_predict,
                )

        return RootCauseFiveWhyResponse(
            success=True,
            analysis=payload.model_dump().get("analysis", []),
        )
    except Exception as e:
        logger.error(f"Error in /api/gen-five-why: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate-five-why", response_model=RootCauseFiveWhyResponse)
async def regenerate_five_why(request: RootCauseRegenerateFiveWhyRequest):
    """Regenerate 5-Why (Using Ishikawa + Locked Data)."""
    try:
        logger.info("Regenerate 5-Why request received.")

        with service.analysis_context() as services:
            compact_ishikawa = compact_ishikawa_for_five_why(request.ishikawa, FIVE_WHY_MAX_CAUSES)
            if not compact_ishikawa:
                raise HTTPException(status_code=400, detail="No valid Ishikawa causes found for 5-Why regeneration")

            cause_total = sum(len(category.get("result", [])) for category in compact_ishikawa)
            logger.info(
                "5-Why regeneration using %s causes (cap=%s)",
                cause_total,
                FIVE_WHY_MAX_CAUSES,
            )

            num_predict = compute_five_why_num_predict(cause_total)
            logger.info("5-Why regeneration num_predict=%s", num_predict)

            ishikawa_json = json.dumps(compact_ishikawa, indent=2)
            locked_analysis_json = json.dumps(request.locked_analysis, indent=2)

            prompt = get_regenerate_five_why_prompt(request.query, request.domain, ishikawa_json, locked_analysis_json)

            llm_service = services.analysis_coordinator.llm_service
            payload = generate_structured_five_why(
                llm_service,
                prompt,
                "5-Why Regeneration",
                num_predict=num_predict,
            )

            if not payload.analysis and cause_total > 0 and num_predict < FIVE_WHY_MAX_NUM_PREDICT:
                expanded_num_predict = min(
                    FIVE_WHY_MAX_NUM_PREDICT,
                    num_predict + max(FIVE_WHY_TOKENS_PER_CAUSE * 2, cause_total * 120),
                )
                logger.warning(
                    "5-Why regeneration returned empty analysis; retrying once with num_predict=%s",
                    expanded_num_predict,
                )
                payload = generate_structured_five_why(
                    llm_service,
                    prompt,
                    "5-Why Regeneration Expanded",
                    num_predict=expanded_num_predict,
                )

        return RootCauseFiveWhyResponse(
            success=True,
            analysis=payload.model_dump().get("analysis", []),
        )
    except Exception as e:
        logger.error(f"Error in /api/regenerate-five-why: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/finalize", response_model=RootCauseFinalizeResponse)
async def finalize_analysis(request: RootCauseFinalizeRequest):
    """Finalize Analysis."""
    try:
        logger.info("Finalize analysis request received.")

        with service.analysis_context() as services:
            ishikawa_json = json.dumps(request.ishikawa, indent=2)
            analysis_json = json.dumps(request.analysis, indent=2)

            prompt = get_finalize_analysis_prompt(request.query, request.domain, ishikawa_json, analysis_json)

            llm_service = services.analysis_coordinator.llm_service
            response = llm_service.client.generate(
                prompt,
                temperature=0.2,
                format="json",
                request_timeout=900,
            )

            if not response.success:
                raise RuntimeError(response.error_message)

            parsed = llm_service._parse_json_response(response.content, "Finalize Analysis")

        service.disconnect_analysis_connection()

        return RootCauseFinalizeResponse(
            success=True,
            summary=parsed.get("summary", {}),
        )
    except Exception as e:
        logger.error(f"Error in /api/finalize: {e}")
        service.disconnect_analysis_connection()
        raise HTTPException(status_code=500, detail=str(e))
