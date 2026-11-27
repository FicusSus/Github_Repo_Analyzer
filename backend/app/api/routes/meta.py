from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.deps import Resources, Session
from app.schemas import ErrorResponse, HealthStatus, RateLimitInfo

router = APIRouter(tags=["meta"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthStatus, summary="Liveness and database check")
async def health(session: Session, response: Response) -> HealthStatus:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthStatus(status="degraded", database="unavailable", version=__version__)
    return HealthStatus(status="ok", database="ok", version=__version__)


@router.get(
    "/github/rate-limit",
    response_model=RateLimitInfo,
    summary="Current GitHub API budget of this server",
    description="Calls GitHub's `/rate_limit`, which does not consume the budget itself.",
    responses={502: {"model": ErrorResponse}},
)
async def github_rate_limit(resources: Resources) -> RateLimitInfo:
    status_ = await resources.github.get_rate_limit()
    return RateLimitInfo.model_validate(status_.model_dump())
