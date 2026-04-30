"""
FastAPI routes for the Ishikawa Knowledge System.
Defines all API endpoints for analysis, search, and data management.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AnalysisRequest,
    AnalysisResponse,
    DetailedAnalysisResponse,
    FrontendAnalysisRequest,
    FrontendAnalysisResponse,
    FiveWhysRequest,
    FiveWhysResponse,
    IshikawaRequest,
    IshikawaRecreateRequest,
    IshikawaDiagramResponse,
    SearchRequest,
    SearchResponse,
    ProblemCreateRequest,
    ProblemResponse,
    CauseCreateRequest,
    EvidenceCreateRequest,
    SolutionCreateRequest,
    StatisticsResponse,
    HealthResponse,
    ErrorResponse,
)
from ..services import APIService
from ...core.simple_orchestrator import AnalysisOrchestrator
from ...utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ishikawa-analysis"])

service = APIService()


def _split_problem_contents(problem_data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Map the PS-centric content model back onto legacy problem detail buckets."""
    causes: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    solutions: list[dict[str, Any]] = []

    for content in problem_data.get("contents", []):
        if not isinstance(content, dict):
            continue

        phase_code = content.get("phase_code")
        if phase_code == "D4":
            causes.append(content)
        elif phase_code == "D6":
            solutions.append(content)
        else:
            evidence.append(content)

    return causes, evidence, solutions


@router.post("/analysis", response_model=FrontendAnalysisResponse)
async def analyze_workflow(request: FrontendAnalysisRequest) -> FrontendAnalysisResponse:
    """Primary frontend endpoint for full input-to-analysis-to-result flow."""
    try:
        logger.info(f"Frontend workflow request received: {request.query[:100]}...")
        return service.analyze_frontend_workflow(request)

    except Exception as e:
        logger.error(f"Frontend workflow analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analysis/fast", response_model=FrontendAnalysisResponse)
async def analyze_workflow_fast(request: FrontendAnalysisRequest) -> FrontendAnalysisResponse:
    """Fast frontend endpoint for intent extraction and related-record retrieval."""
    try:
        logger.info(f"Fast workflow request received: {request.query[:100]}...")
        fast_request = request.model_copy(update={"fast_mode": True})
        return service.analyze_fast_frontend_workflow(fast_request)

    except Exception as e:
        logger.error(f"Fast workflow analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Fast analysis failed: {str(e)}")


@router.post("/analysis/5-whys", response_model=FiveWhysResponse)
async def analyze_five_whys(request: FiveWhysRequest) -> FiveWhysResponse:
    """Generate only the 5 Whys output for a frontend request."""
    try:
        logger.info(f"5 Whys request received: {request.query[:100]}...")
        return service.analyze_five_whys(request)

    except Exception as e:
        logger.error(f"5 Whys analysis route failed: {e}")
        raise HTTPException(status_code=500, detail=f"5 Whys analysis failed: {str(e)}")


@router.post("/analysis/ishikawa", response_model=IshikawaDiagramResponse)
async def analyze_ishikawa(request: IshikawaRequest) -> IshikawaDiagramResponse:
    """Generate only the Ishikawa diagram output for a frontend request."""
    try:
        logger.info(f"Ishikawa request received: {request.query[:100]}...")
        return service.analyze_ishikawa(request, regenerated=False)

    except Exception as e:
        logger.error(f"Ishikawa analysis route failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ishikawa analysis failed: {str(e)}")


@router.post("/analysis/ishikawa/recreate", response_model=IshikawaDiagramResponse)
async def recreate_ishikawa(request: IshikawaRecreateRequest) -> IshikawaDiagramResponse:
    """Regenerate the Ishikawa diagram when the frontend explicitly asks for a fresh diagram."""
    try:
        logger.info(f"Ishikawa recreate request received: {request.query[:100]}...")
        return service.analyze_ishikawa(request, regenerated=True)

    except Exception as e:
        logger.error(f"Ishikawa recreate route failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ishikawa recreation failed: {str(e)}")


@router.post("/analyze", response_model=AnalysisResponse | DetailedAnalysisResponse)
async def analyze_problem(request: AnalysisRequest) -> AnalysisResponse:
    """
    Analyze a problem using the complete Ishikawa methodology.

    This endpoint performs intent extraction, knowledge base search,
    root cause analysis, and provides actionable recommendations.
    """
    try:
        logger.info(f"Analysis request received: {request.query[:100]}...")

        with service.analysis_context() as services:
            processor = services.processor
            orchestrator = AnalysisOrchestrator(processor)

            if request.include_details:
                result = orchestrator.get_analysis_details(request.query)

                response = DetailedAnalysisResponse(
                    intent=result["intent"],
                    knowledge_results=result["knowledge_results"],
                    analysis_results=result["analysis_results"],
                    synthesis=result["synthesis"],
                    related_ps=result.get("related_ps", []),
                    processing_time=result["processing_time"],
                    success=result["success"],
                    error_message=result.get("error_message"),
                )
                return response

            result = orchestrator.analyze_problem(request.query)
            response = AnalysisResponse(**result)
            return response

    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}",
        )


@router.post("/search", response_model=SearchResponse)
async def search_knowledge_base(request: SearchRequest) -> SearchResponse:
    """
    Search the knowledge base for relevant problems and solutions.

    Supports filtering by domains, keywords, phases, and other criteria.
    """
    try:
        logger.info(f"Search request: domains={request.domains}, keywords={request.keywords}")
        response = service.search(request)
        logger.info(f"Search completed: {response.total_count} results")
        return response

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


@router.post("/problems", response_model=Dict[str, str])
async def create_problem(request: ProblemCreateRequest) -> Dict[str, str]:
    """
    Create a new problem in the knowledge base.

    Returns the ID of the created problem.
    """
    try:
        logger.info(f"Creating problem: {request.title}")

        with service.repository_context() as knowledge_repo:
            problem_id = knowledge_repo.create_problem_statement(
                title=request.title,
                text=f"{request.description}\n\nSymptoms: {request.symptoms}",
                domain_names=[request.domain],
                upload_source="api",
            )

        logger.info(f"Problem created: {problem_id}")
        return {"problem_id": problem_id}

    except Exception as e:
        logger.error(f"Problem creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Problem creation failed: {str(e)}",
        )


@router.get("/problems/{problem_id}", response_model=ProblemResponse)
async def get_problem(problem_id: str) -> ProblemResponse:
    """Get detailed information about a specific problem."""
    try:
        logger.info(f"Retrieving problem: {problem_id}")

        with service.repository_context() as knowledge_repo:
            problem_data = knowledge_repo.get_ps_details(problem_id)

        if not problem_data:
            raise HTTPException(
                status_code=404,
                detail=f"Problem {problem_id} not found",
            )

        causes, evidence, solutions = _split_problem_contents(problem_data)

        response = ProblemResponse(
            id=problem_data.get("id"),
            title=problem_data.get("title", ""),
            description=problem_data.get("text", ""),
            symptoms=problem_data.get("symptoms"),
            severity=problem_data.get("severity"),
            status=problem_data.get("status"),
            domain=problem_data.get("domain") or next(iter(problem_data.get("domains", [])), None),
            phase=problem_data.get("phase") or next(
                (
                    phase.get("code")
                    for phase in problem_data.get("phases", [])
                    if isinstance(phase, dict) and phase.get("code")
                ),
                None,
            ),
            created_date=problem_data.get("created_date") or problem_data.get("created_at"),
            updated_date=problem_data.get("updated_date") or problem_data.get("updated_at"),
            causes=problem_data.get("causes", causes),
            evidence=problem_data.get("evidence", evidence),
            analyses=problem_data.get("analyses", []),
            solutions=problem_data.get("solutions", solutions),
        )
        return response

    except Exception as e:
        logger.error(f"Problem retrieval failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Problem retrieval failed: {str(e)}",
        )


@router.post("/problems/{problem_id}/causes", response_model=Dict[str, str])
async def create_cause(problem_id: str, request: CauseCreateRequest) -> Dict[str, str]:
    """Add a cause to a problem."""
    try:
        with service.repository_context() as knowledge_repo:
            cause_id = knowledge_repo.create_cause(
                problem_id=problem_id,
                description=request.description,
                category=request.category,
                severity=request.severity,
                ishikawa_category=request.ishikawa_category,
            )

        return {"cause_id": cause_id}

    except Exception as e:
        logger.error(f"Cause creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cause creation failed: {str(e)}")


@router.post("/problems/{problem_id}/evidence", response_model=Dict[str, str])
async def create_evidence(problem_id: str, request: EvidenceCreateRequest) -> Dict[str, str]:
    """Add evidence to a problem."""
    try:
        with service.repository_context() as knowledge_repo:
            evidence_id = knowledge_repo.create_evidence(
                problem_id=problem_id,
                content=request.content,
                source=request.source,
                evidence_type=request.evidence_type,
                confidence=request.confidence,
            )

        return {"evidence_id": evidence_id}

    except Exception as e:
        logger.error(f"Evidence creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evidence creation failed: {str(e)}")


@router.post("/problems/{problem_id}/solutions", response_model=Dict[str, str])
async def create_solution(problem_id: str, request: SolutionCreateRequest) -> Dict[str, str]:
    """Add solution to a problem."""
    try:
        with service.repository_context() as knowledge_repo:
            solution_id = knowledge_repo.create_solution(
                problem_id=problem_id,
                description=request.description,
                solution_type=request.solution_type,
                priority=request.priority,
                status=request.status,
                cause_id=request.cause_id,
            )

        return {"solution_id": solution_id}

    except Exception as e:
        logger.error(f"Solution creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Solution creation failed: {str(e)}")


@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics() -> StatisticsResponse:
    """Get system statistics."""
    try:
        with service.repository_context() as knowledge_repo:
            stats = knowledge_repo.get_statistics()

        return StatisticsResponse(**stats)

    except Exception as e:
        logger.error(f"Statistics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail=f"Statistics retrieval failed: {str(e)}")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Perform system health check."""
    return service.health()
