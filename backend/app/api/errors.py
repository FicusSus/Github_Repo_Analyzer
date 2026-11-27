"""Translate domain exceptions into a single JSON error envelope:

{"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError
from app.github.errors import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubForbiddenError,
    GitHubUnavailableError,
    InvalidRepositoryURLError,
    RateLimitExceededError,
    RepositoryNotFoundError,
)

logger = logging.getLogger(__name__)


def _error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(
        status_code=status_code, content=jsonable_encoder({"error": body}), headers=headers
    )


async def _app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return _error(exc.status_code, exc.code, exc.message, exc.details)


_SIMPLE_GITHUB_ERRORS: tuple[tuple[type[GitHubError], int, str], ...] = (
    (InvalidRepositoryURLError, status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_repository"),
    (RepositoryNotFoundError, status.HTTP_404_NOT_FOUND, "repository_not_found"),
    (GitHubForbiddenError, status.HTTP_403_FORBIDDEN, "github_forbidden"),
    (GitHubUnavailableError, status.HTTP_502_BAD_GATEWAY, "github_unavailable"),
)


async def _github_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GitHubError)
    for error_type, status_code, code in _SIMPLE_GITHUB_ERRORS:
        if isinstance(exc, error_type):
            return _error(status_code, code, exc.message)
    if isinstance(exc, RateLimitExceededError):
        retry_after = _retry_after_seconds(exc)
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "github_rate_limited",
            "GitHub API rate limit reached. Try again later"
            + (f" (in about {math.ceil(retry_after / 60)} min)." if retry_after else "."),
            details={"reset_at": exc.reset_at, "retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )
    if isinstance(exc, GitHubAuthenticationError):
        logger.error("GitHub token rejected: %s", exc.message)
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            "github_auth_failed",
            "The server's GitHub credentials are invalid. Contact the administrator.",
        )
    logger.warning("Unexpected GitHub error: %s", exc.message)
    return _error(status.HTTP_502_BAD_GATEWAY, "github_error", exc.message)


def _retry_after_seconds(exc: RateLimitExceededError) -> int | None:
    if exc.retry_after_seconds is not None:
        return exc.retry_after_seconds
    if exc.reset_at is not None:
        return max(1, math.ceil((exc.reset_at - datetime.now(UTC)).total_seconds()))
    return None


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"location": ".".join(str(p) for p in err.get("loc", ())), "message": err.get("msg")}
        for err in exc.errors()
    ]
    return _error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "Request validation failed.",
        details={"errors": errors},
    )


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = "not_found" if exc.status_code == status.HTTP_404_NOT_FOUND else "http_error"
    headers = dict(exc.headers) if exc.headers else None
    return _error(exc.status_code, code, str(exc.detail), headers=headers)


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return _error(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An unexpected error occurred."
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(GitHubError, _github_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
