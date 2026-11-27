from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import Service
from app.schemas import (
    AnalysisDetail,
    AnalysisSummary,
    AnalyzeRequest,
    ErrorResponse,
    Page,
    to_detail,
    to_summary,
)

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post(
    "",
    response_model=AnalysisDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze a repository",
    description=(
        "Fetches the repository from GitHub, computes statistics and stores the result. "
        "If the repository was analyzed within the cache TTL, the stored analysis is returned "
        "with `200 OK` and `from_cache: true` unless `force` is set."
    ),
    responses={
        200: {"model": AnalysisDetail, "description": "Recent stored analysis reused."},
        404: {"model": ErrorResponse, "description": "Repository not found or private."},
        422: {"model": ErrorResponse, "description": "Invalid repository reference."},
        429: {"model": ErrorResponse, "description": "GitHub rate limit reached."},
        502: {"model": ErrorResponse, "description": "GitHub unavailable."},
    },
)
async def analyze_repository(
    payload: AnalyzeRequest, service: Service, response: Response
) -> AnalysisDetail:
    outcome = await service.analyze(payload.repository, force=payload.force)
    if outcome.from_cache:
        response.status_code = status.HTTP_200_OK
    return to_detail(outcome.analysis, from_cache=outcome.from_cache)


@router.get("", response_model=Page[AnalysisSummary], summary="List stored analyses")
async def list_analyses(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    repository: Annotated[
        str | None, Query(description="Filter by `owner/name` or repository URL.")
    ] = None,
) -> Page[AnalysisSummary]:
    items, total = await service.list_analyses(limit=limit, offset=offset, repository=repository)
    return Page(items=[to_summary(a) for a in items], total=total, limit=limit, offset=offset)


@router.get(
    "/{analysis_id}",
    response_model=AnalysisDetail,
    summary="Get a stored analysis",
    responses={404: {"model": ErrorResponse}},
)
async def get_analysis(analysis_id: int, service: Service) -> AnalysisDetail:
    return to_detail(await service.get(analysis_id))


@router.delete(
    "/{analysis_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a stored analysis",
    responses={404: {"model": ErrorResponse}},
)
async def delete_analysis(analysis_id: int, service: Service) -> Response:
    await service.delete(analysis_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
