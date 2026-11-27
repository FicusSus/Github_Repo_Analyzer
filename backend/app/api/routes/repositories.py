from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import Service
from app.schemas import (
    AnalysisDetail,
    Comparison,
    ErrorResponse,
    Page,
    RepositoryHistory,
    TrackedRepository,
    to_detail,
    to_summary,
)

router = APIRouter(tags=["repositories"])


@router.get(
    "/repositories",
    response_model=Page[TrackedRepository],
    summary="List analyzed repositories with their latest snapshot",
)
async def list_repositories(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=140)] = None,
) -> Page[TrackedRepository]:
    overviews, total = await service.repositories(limit=limit, offset=offset, search=search)
    items = [
        TrackedRepository(
            full_name=o.repository.full_name,
            html_url=o.repository.html_url,
            analyses_count=o.analyses_count,
            first_analyzed_at=o.first_analyzed_at,
            last_analyzed_at=o.last_analyzed_at,
            latest=to_summary(o.latest),
        )
        for o in overviews
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/repositories/{owner}/{name}/latest",
    response_model=AnalysisDetail,
    summary="Latest stored analysis of a repository",
    responses={404: {"model": ErrorResponse}},
)
async def latest_analysis(owner: str, name: str, service: Service) -> AnalysisDetail:
    return to_detail(await service.latest(owner, name))


@router.get(
    "/repositories/{owner}/{name}/history",
    response_model=RepositoryHistory,
    summary="Statistics of every stored analysis of a repository, oldest first",
    responses={404: {"model": ErrorResponse}},
)
async def repository_history(owner: str, name: str, service: Service) -> RepositoryHistory:
    return await service.history(owner, name)


@router.get(
    "/compare",
    response_model=Comparison,
    summary="Compare the latest analyses of 2-5 repositories",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def compare_repositories(
    service: Service,
    repositories: Annotated[
        list[str],
        Query(
            min_length=2,
            max_length=5,
            description="Repeat the parameter: `?repositories=a/b&repositories=c/d`.",
        ),
    ],
) -> Comparison:
    return await service.compare(repositories)
