"""Exceptions raised by the GitHub integration layer."""

from __future__ import annotations

from datetime import datetime


class GitHubError(Exception):
    """Base class for all GitHub integration errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InvalidRepositoryURLError(GitHubError):
    """The supplied string is not a recognisable GitHub repository reference."""


class RepositoryNotFoundError(GitHubError):
    """The repository does not exist or is private."""


class RateLimitExceededError(GitHubError):
    """GitHub refused the request because a primary or secondary rate limit was hit."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reset_at: datetime | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.reset_at = reset_at
        self.retry_after_seconds = retry_after_seconds


class GitHubAuthenticationError(GitHubError):
    """The configured server-side token was rejected."""


class GitHubForbiddenError(GitHubError):
    """GitHub returned 403/451 for a reason other than rate limiting."""


class RepositoryEmptyError(GitHubError):
    """The repository exists but has no commits (GitHub answers 409 on history endpoints)."""


class GitHubUnavailableError(GitHubError):
    """GitHub could not be reached or kept failing with server errors."""
