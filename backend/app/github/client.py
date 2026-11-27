"""Async client for the GitHub REST API.

Responsibilities:

* consistent headers (API version, media type, optional server-side token);
* ``Link``-header pagination with a hard page cap;
* conditional requests with an in-memory ETag cache;
* rate-limit bookkeeping and fail-fast behaviour when the limit is exhausted;
* retries with exponential backoff for transport errors and 5xx responses;
* translation of HTTP failures into the domain exceptions in :mod:`app.github.errors`.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from pydantic import TypeAdapter, ValidationError

from app.config import Settings
from app.github.errors import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubForbiddenError,
    GitHubUnavailableError,
    RateLimitExceededError,
    RepositoryEmptyError,
    RepositoryNotFoundError,
)
from app.github.models import (
    GitHubCommit,
    GitHubContributor,
    GitHubRepository,
    RateLimitStatus,
)
from app.github.url import RepositoryRef

logger = logging.getLogger(__name__)

API_VERSION = "2022-11-28"
PER_PAGE = 100
_SECONDARY_LIMIT_FALLBACK_SECONDS = 60

_contributors_adapter = TypeAdapter(list[GitHubContributor])
_commits_adapter = TypeAdapter(list[GitHubCommit])
_languages_adapter = TypeAdapter(dict[str, int])


@dataclass(frozen=True, slots=True)
class PageResult[T]:
    items: list[T]
    truncated: bool
    """``True`` when more pages existed than the configured page cap allowed us to fetch."""


@dataclass(frozen=True, slots=True)
class _Response:
    status_code: int
    data: Any
    links: dict[str, dict[str, str]]
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    etag: str
    data: Any
    links: dict[str, dict[str, str]]


class _ETagCache:
    """Small LRU cache of ``url -> (etag, body)`` used for conditional requests."""

    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()

    def get(self, key: str) -> _CacheEntry | None:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry

    def put(self, key: str, entry: _CacheEntry) -> None:
        if self._max_size <= 0:
            return
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_size:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


class GitHubClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.github.com",
        token: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        etag_cache_size: int = 512,
        backoff_base_seconds: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "github-repo-analyzer/1.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._authenticated = bool(token)
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=True,
            transport=transport,
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._etags = _ETagCache(etag_cache_size)
        self._rate_limit: RateLimitStatus | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> GitHubClient:
        return cls(
            base_url=settings.github_api_url,
            token=settings.github_token.get_secret_value() if settings.github_token else None,
            timeout_seconds=settings.github_timeout_seconds,
            max_retries=settings.github_max_retries,
            etag_cache_size=settings.github_etag_cache_size,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def last_rate_limit(self) -> RateLimitStatus | None:
        """Rate-limit state observed on the most recent ``core`` API response."""
        return self._rate_limit

    # ------------------------------------------------------------------ public API

    async def get_repository(self, ref: RepositoryRef) -> GitHubRepository:
        response = await self._get(f"/repos/{ref.owner}/{ref.name}")
        return _parse(GitHubRepository.model_validate, response.data, "repository")

    async def get_languages(self, ref: RepositoryRef) -> dict[str, int]:
        response = await self._get(f"/repos/{ref.owner}/{ref.name}/languages")
        return _parse(_languages_adapter.validate_python, response.data or {}, "languages")

    async def list_contributors(
        self, ref: RepositoryRef, *, max_pages: int = 1
    ) -> PageResult[GitHubContributor]:
        """Contributors sorted by contribution count (descending), as GitHub returns them."""
        raw = await self._paginate(
            f"/repos/{ref.owner}/{ref.name}/contributors", {}, max_pages=max_pages
        )
        items = _parse(_contributors_adapter.validate_python, raw.items, "contributors")
        return PageResult(items=items, truncated=raw.truncated)

    async def count_contributors(self, ref: RepositoryRef) -> int:
        return await self._count(f"/repos/{ref.owner}/{ref.name}/contributors", {})

    async def count_commits(self, ref: RepositoryRef) -> int:
        """Total number of commits on the default branch."""
        try:
            return await self._count(f"/repos/{ref.owner}/{ref.name}/commits", {})
        except RepositoryEmptyError:
            return 0

    async def list_commits(
        self, ref: RepositoryRef, *, since: datetime, max_pages: int
    ) -> PageResult[GitHubCommit]:
        """Commits on the default branch authored after ``since``, newest first."""
        params = {"since": since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            raw = await self._paginate(
                f"/repos/{ref.owner}/{ref.name}/commits", params, max_pages=max_pages
            )
        except RepositoryEmptyError:
            return PageResult(items=[], truncated=False)
        items = _parse(_commits_adapter.validate_python, raw.items, "commits")
        return PageResult(items=items, truncated=raw.truncated)

    async def list_recent_commits(self, ref: RepositoryRef, *, limit: int) -> list[GitHubCommit]:
        """The newest ``limit`` commits on the default branch, regardless of date (one request)."""
        try:
            response = await self._get(
                f"/repos/{ref.owner}/{ref.name}/commits", {"per_page": str(min(limit, PER_PAGE))}
            )
        except RepositoryEmptyError:
            return []
        return _parse(_commits_adapter.validate_python, response.data or [], "commits")

    async def get_rate_limit(self) -> RateLimitStatus:
        """Query ``/rate_limit``; GitHub does not count this call against the limit."""
        response = await self._get("/rate_limit", check_budget=False)
        core = (response.data or {}).get("resources", {}).get("core")
        if not isinstance(core, dict):
            raise GitHubError("Unexpected /rate_limit response from GitHub.")
        status = RateLimitStatus(
            limit=int(core["limit"]),
            remaining=int(core["remaining"]),
            used=int(core.get("used", int(core["limit"]) - int(core["remaining"]))),
            reset_at=datetime.fromtimestamp(int(core["reset"]), tz=UTC),
            authenticated=self._authenticated,
        )
        self._rate_limit = status
        return status

    # ------------------------------------------------------------------ internals

    async def _paginate(
        self, path: str, params: dict[str, str], *, max_pages: int
    ) -> PageResult[Any]:
        items: list[Any] = []
        url: str | None = path
        query: dict[str, str] | None = {**params, "per_page": str(PER_PAGE)}
        pages = 0
        while url is not None and pages < max_pages:
            response = await self._get(url, query)
            pages += 1
            if response.data is None:  # 204 No Content (e.g. contributors of an empty repo)
                break
            if not isinstance(response.data, list):
                raise GitHubError(f"Expected a list from {path}, got {type(response.data)}.")
            items.extend(response.data)
            url = response.links.get("next", {}).get("url")
            query = None  # the "next" URL already carries every query parameter
        return PageResult(items=items, truncated=url is not None)

    async def _count(self, path: str, params: dict[str, str]) -> int:
        """Count a collection with one request: ask for 1 item/page and read the last page no."""
        response = await self._get(path, {**params, "per_page": "1"})
        last_url = response.links.get("last", {}).get("url")
        if last_url:
            page = parse_qs(urlsplit(last_url).query).get("page", ["0"])[0]
            if page.isdigit():
                return int(page)
        return len(response.data) if isinstance(response.data, list) else 0

    async def _get(
        self, url: str, params: dict[str, str] | None = None, *, check_budget: bool = True
    ) -> _Response:
        if check_budget:
            self._fail_fast_if_exhausted()

        cache_key = _cache_key(url, params)
        cached = self._etags.get(cache_key)
        headers = {"If-None-Match": cached.etag} if cached else {}

        response = await self._send_with_retries(url, params, headers)

        if response.status_code == httpx.codes.NOT_MODIFIED and cached is not None:
            logger.debug("ETag hit for %s", cache_key)
            return _Response(200, cached.data, cached.links, from_cache=True)

        _raise_for_status(response)

        data: Any = None
        if response.status_code != httpx.codes.NO_CONTENT and response.content:
            try:
                data = response.json()
            except ValueError as exc:
                raise GitHubError("GitHub returned a response that is not valid JSON.") from exc

        links = {str(rel): {"url": str(link["url"])} for rel, link in response.links.items() if rel}
        etag = response.headers.get("etag")
        if etag and response.status_code == httpx.codes.OK:
            self._etags.put(cache_key, _CacheEntry(etag=etag, data=data, links=links))
        return _Response(response.status_code, data, links)

    async def _send_with_retries(
        self, url: str, params: dict[str, str] | None, headers: dict[str, str]
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._http.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise GitHubUnavailableError(f"Could not reach GitHub: {exc}") from exc
                logger.warning("GitHub transport error (%s), retrying", exc.__class__.__name__)
            else:
                self._record_rate_limit(response.headers)
                if response.status_code < 500:
                    return response
                if attempt >= self._max_retries:
                    raise GitHubUnavailableError(
                        f"GitHub kept failing with HTTP {response.status_code}.",
                        status_code=response.status_code,
                    )
                logger.warning("GitHub returned %s, retrying", response.status_code)
            await asyncio.sleep(self._backoff_delay(attempt))
            attempt += 1

    def _backoff_delay(self, attempt: int) -> float:
        if self._backoff_base <= 0:
            return 0.0
        return float(self._backoff_base * (2**attempt) + random.uniform(0, self._backoff_base))

    def _record_rate_limit(self, headers: httpx.Headers) -> None:
        resource = headers.get("x-ratelimit-resource", "core")
        if resource != "core":
            return
        try:
            limit = int(headers["x-ratelimit-limit"])
            remaining = int(headers["x-ratelimit-remaining"])
            reset = int(headers["x-ratelimit-reset"])
        except (KeyError, ValueError):
            return
        used = int(headers.get("x-ratelimit-used", limit - remaining))
        self._rate_limit = RateLimitStatus(
            limit=limit,
            remaining=remaining,
            used=used,
            reset_at=datetime.fromtimestamp(reset, tz=UTC),
            authenticated=self._authenticated,
        )

    def _fail_fast_if_exhausted(self) -> None:
        """Avoid hammering GitHub once we know the primary limit is spent (GitHub's guidance)."""
        status = self._rate_limit
        if status is None or status.remaining > 0:
            return
        if status.reset_at > datetime.now(UTC):
            raise RateLimitExceededError(
                "GitHub API rate limit exhausted.", status_code=403, reset_at=status.reset_at
            )


def _cache_key(url: str, params: dict[str, str] | None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(sorted(params.items()))}"


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return str(body["message"])
    return response.reason_phrase


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    message = _error_message(response)

    if status == httpx.codes.UNAUTHORIZED:
        raise GitHubAuthenticationError(
            "GitHub rejected the configured token. Check GITHUB_TOKEN.", status_code=status
        )
    if status in {httpx.codes.FORBIDDEN, httpx.codes.TOO_MANY_REQUESTS}:
        retry_after = response.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            raise RateLimitExceededError(
                f"GitHub secondary rate limit: {message}",
                status_code=status,
                retry_after_seconds=int(retry_after),
            )
        if response.headers.get("x-ratelimit-remaining") == "0":
            reset = response.headers.get("x-ratelimit-reset", "")
            reset_at = datetime.fromtimestamp(int(reset), tz=UTC) if reset.isdigit() else None
            raise RateLimitExceededError(
                "GitHub API rate limit exhausted.", status_code=status, reset_at=reset_at
            )
        if "rate limit" in message.lower():
            raise RateLimitExceededError(
                f"GitHub rate limit: {message}",
                status_code=status,
                retry_after_seconds=_SECONDARY_LIMIT_FALLBACK_SECONDS,
            )
        raise GitHubForbiddenError(message, status_code=status)
    if status == httpx.codes.NOT_FOUND:
        raise RepositoryNotFoundError(
            "Repository not found. It may be private, renamed or deleted.", status_code=status
        )
    if status == httpx.codes.CONFLICT:
        raise RepositoryEmptyError(message, status_code=status)
    if status == httpx.codes.UNAVAILABLE_FOR_LEGAL_REASONS:
        raise GitHubForbiddenError(message, status_code=status)
    raise GitHubError(f"GitHub API error {status}: {message}", status_code=status)


def _parse[T](validator: Callable[[Any], T], payload: Any, what: str) -> T:
    try:
        return validator(payload)
    except ValidationError as exc:
        raise GitHubError(
            f"Unexpected {what} payload from GitHub ({exc.error_count()} validation errors)."
        ) from exc
