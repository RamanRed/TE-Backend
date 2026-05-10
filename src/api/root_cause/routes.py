"""Root cause analysis routes and handlers."""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from ..services import APIService
from ...database.save_analysis import AnalysisSaver
from ...database.supabase_save import SupabaseSaver
from ...utils.auth import get_token_claims_from_bearer
from ...database.prisma_client import get_prisma
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
    SaveAllRequest,
    SaveAllResponse,
    HistoryRequest,
    HistoryResponse,
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


# ---------------------------------------------------------------------------
# POST /api/save — Save All (Neo4j + Supabase)
# ---------------------------------------------------------------------------

@router.post("/save", response_model=SaveAllResponse)
async def save_all(
    request: SaveAllRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Save a finalized Ishikawa + 5-Whys analysis.

    Writes to **two stores** in sequence:

    1. **Neo4j** (always) — creates a new ProblemStatement node with fully-
       scaffolded D1-D7 phases and populates:
         • D4/root_cause          — confirmed Ishikawa causes
         • D4/contributing_factors — possible Ishikawa causes
         • D5/ishikawa_analysis   — full Ishikawa JSON snapshot
         • D5/five_whys           — each 5-Whys chain item
         • D7/lesson_learned      — extracted root causes

    2. **Supabase** (when SUPABASE_URL + SUPABASE_SERVICE_KEY are set) — inserts:
         • analysis_sessions  (parent row)
         • saved_ishikawa     (full IshikawaCategory[] as JSONB)
         • saved_five_whys    (full FiveWhyChainItem[] as JSONB)
       All three rows carry (user_id, master_user_id, org_id) for RLS.

    If Supabase is not configured the Neo4j write still succeeds and
    ``supabase_skipped=true`` is returned.
    """
    logger.info(
        "Save All request: domain=%r  query=%r...",
        request.domain,
        request.query[:80],
    )

    payload = get_token_claims_from_bearer(authorization)
    if not payload:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_id = payload.get("sub")
    org_id = payload.get("org_id")
    master_user_id = payload.get("master_user_id")

    if not user_id or not org_id or not master_user_id:
        raise HTTPException(status_code=401, detail="Invalid JWT token: missing required claims")

    body_identity = {
        "user_id": request.user_id,
        "org_id": request.org_id,
        "master_user_id": request.master_user_id,
    }
    token_identity = {
        "user_id": user_id,
        "org_id": org_id,
        "master_user_id": master_user_id,
    }
    for field_name, body_value in body_identity.items():
        token_value = token_identity[field_name]
        if body_value and body_value != token_value:
            logger.warning(
                "Save All request %s mismatch: body=%s token=%s",
                field_name,
                body_value,
                token_value,
            )
            # Legacy clients may still send stale identity values; ignore them
            # and continue using the verified JWT claims.

    try:
        db = get_prisma()
        user = db.user.find_unique(where={"id": user_id})
        if not user:
            logger.warning("Save All JWT references non-existent user: %s", user_id)
            raise HTTPException(status_code=401, detail="User not found")

        if user.orgId != org_id:
            logger.warning(
                "Save All user %s belongs to org %s but token requested org %s",
                user_id,
                user.orgId,
                org_id,
            )
            raise HTTPException(status_code=403, detail="User does not belong to this organization")

        org = db.organization.find_unique(where={"id": org_id})
        if not org:
            logger.warning("Save All organization not found: %s", org_id)
            raise HTTPException(status_code=404, detail="Organization not found")

        resolved_master_user_id = org.masterUserId or user_id
        if master_user_id != resolved_master_user_id:
            logger.warning(
                "Save All master_user_id %s replaced with current org master %s",
                master_user_id,
                resolved_master_user_id,
            )
            master_user_id = resolved_master_user_id
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Save All identity verification failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to verify identity: {exc}")

    # ── 1. Neo4j write ─────────────────────────────────────────────────
    neo4j_result: dict = {}
    try:
        with service.repository_context() as repo:
            saver = AnalysisSaver(repo)
            neo4j_result = saver.save_analysis(
                query=request.query,
                domain=request.domain,
                ishikawa=request.ishikawa,
                five_whys=request.analysis,
                ticket_ref=request.ticket_ref or "",
                part_number=request.part_number or "",
                source="user_save",
            )
        logger.info(
            "Neo4j save complete: ps_id=%s  content_nodes=%d",
            neo4j_result.get("ps_id"),
            neo4j_result.get("content_count", 0),
        )
    except Exception as exc:
        logger.error("Neo4j save failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Neo4j save failed: {exc}",
        )

    # ── 2. Supabase write ───────────────────────────────────────────────
    # Supabase identity is optional — if not provided we skip gracefully.
    supabase_result: dict = {
        "session_id": None,
        "ishikawa_id": None,
        "five_whys_id": None,
        "skipped": True,
    }

    try:
        sb_saver = SupabaseSaver()
        supabase_result = sb_saver.save_analysis(
            user_id=user_id,
            master_user_id=master_user_id,
            org_id=org_id,
            query=request.query,
            domain=request.domain,
            past_record=request.past_record,
            session_title=request.session_title,
            ishikawa=request.ishikawa,
            five_whys=request.analysis,
        )
    except Exception as exc:
        # Non-fatal — Neo4j data is already saved.
        logger.error("Supabase save failed (non-fatal): %s", exc)
        supabase_result["skipped"] = True

    # ── 3. Build response ───────────────────────────────────────────────
    sb_skipped = supabase_result.get("skipped", True)
    message_parts = [
        f"Analysis saved to Neo4j (ps_id={neo4j_result.get('ps_id')}, "
        f"content_nodes={neo4j_result.get('content_count', 0)})."
    ]
    if sb_skipped:
        message_parts.append("Supabase save skipped (not configured or identity missing).")
    else:
        message_parts.append(
            f"Saved to Supabase (session={supabase_result.get('session_id')})."
        )

    return SaveAllResponse(
        success=True,
        message=" ".join(message_parts),
        neo4j_ps_id=neo4j_result.get("ps_id"),
        neo4j_content_count=neo4j_result.get("content_count", 0),
        supabase_session_id=supabase_result.get("session_id"),
        supabase_ishikawa_id=supabase_result.get("ishikawa_id"),
        supabase_five_whys_id=supabase_result.get("five_whys_id"),
        supabase_skipped=sb_skipped,
    )


# ---------------------------------------------------------------------------
# POST /api/history — Fetch History from Supabase
# ---------------------------------------------------------------------------

@router.post("/history", response_model=HistoryResponse)
async def get_history(
    request = None,
    authorization: Optional[str] = Header(None),
):
    """
    Fetch saved analysis history from Supabase for the given user.
    
    JWT token verification:
    - Extracts Bearer token from Authorization header
    - Verifies token and extracts user_id, org_id, and master_user_id
    - Uses the JWT claims as the source of truth for history visibility

    The optional request body is kept only for backward compatibility.
    """
    # ── 1. Verify JWT token ────────────────────────────────────────────
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("History request missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    payload = get_token_claims_from_bearer(authorization)
    
    if not payload:
        logger.warning("History request with invalid/expired JWT token")
        raise HTTPException(status_code=401, detail="Invalid or expired JWT token")
    
    user_id = payload.get("sub")
    if not user_id:
        logger.warning("JWT token missing 'sub' claim")
        raise HTTPException(status_code=401, detail="Invalid JWT token: missing user info")
    
    org_id = payload.get("org_id")
    master_user_id = payload.get("master_user_id")

    if not org_id or not master_user_id:
        logger.warning("JWT token missing required org claims")
        raise HTTPException(status_code=401, detail="Invalid JWT token: missing organization info")

    if request and request.org_id and request.org_id != org_id:
        logger.warning(
            "History request body org_id %s does not match JWT org_id %s",
            request.org_id,
            org_id,
        )
        raise HTTPException(status_code=403, detail="Request does not match authenticated organization")

    # ── 2. Query database for user info ─────────────────────────────────
    try:
        db = get_prisma()
        user = db.user.find_unique(where={"id": user_id})
        
        if not user:
            logger.warning(f"JWT token references non-existent user: {user_id}")
            raise HTTPException(status_code=401, detail="User not found")
        
        # Verify user belongs to the organization from the JWT
        if user.orgId != org_id:
            logger.warning(f"User {user_id} attempted to access org {org_id} but belongs to {user.orgId}")
            raise HTTPException(status_code=403, detail="User does not belong to this organization")
        # Keep token claims aligned with current database state
        org = db.organization.find_unique(where={"id": org_id})
        if not org:
            logger.warning(f"Organization not found: {org_id}")
            raise HTTPException(status_code=404, detail="Organization not found")

        if org.masterUserId != master_user_id:
            logger.warning(
                "JWT master_user_id %s does not match current org master %s",
                master_user_id,
                org.masterUserId,
            )
            raise HTTPException(status_code=401, detail="Invalid JWT token: organization access changed")
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Database lookup failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to verify user information")

    # ── 3. Fetch history with verified credentials ─────────────────────
    logger.info(
        "History fetch requested for user=%s, org=%s (JWT verified)",
        user_id,
        org_id,
    )

    try:
        sb_saver = SupabaseSaver()
        history_data = sb_saver.get_history(
            user_id=user_id,
            master_user_id=master_user_id,
            org_id=org_id,
        )

        return HistoryResponse(
            success=True,
            sessions=history_data,
        )
    except Exception as exc:
        logger.error("Failed to fetch history: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch history: {exc}",
        )


