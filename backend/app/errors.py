"""Application-level (non-GitHub) errors that map onto HTTP responses."""

from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class AnalysisNotFoundError(AppError):
    status_code = 404
    code = "analysis_not_found"


class RepositoryNotTrackedError(AppError):
    status_code = 404
    code = "repository_not_tracked"


class InvalidComparisonError(AppError):
    status_code = 422
    code = "invalid_comparison"
