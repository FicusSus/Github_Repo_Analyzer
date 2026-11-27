"""Shared fixtures.

Database tests run against PostgreSQL when ``TEST_DATABASE_URL`` is set (CI does this) and
fall back to a throw-away SQLite file otherwise, so the suite also runs without Docker.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import Analysis, AnalysisContributor, AnalysisLanguage, Base, Repository
from app.db.session import create_engine, create_session_factory
from app.github.client import GitHubClient
from app.main import create_app
from tests.factories import (
    API,
    NOW,
    commit_payload,
    contributor_payload,
    link_header,
    rate_limit_headers,
    repo_payload,
)


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    path: Path = tmp_path_factory.mktemp("db") / "test.sqlite3"
    return f"sqlite+aiosqlite:///{path}"


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield create_session_factory(engine)
    async with engine.begin() as connection:
        for model in (AnalysisContributor, AnalysisLanguage, Analysis, Repository):
            await connection.execute(delete(model))


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        github_api_url=API,
        github_token=None,
        github_max_retries=2,
        commit_window_days=365,
        commits_max_pages=3,
        contributors_max_pages=1,
        analysis_cache_ttl_seconds=600,
        cors_origins=["http://localhost:5173"],
    )


@pytest.fixture
def github_mock() -> respx.MockRouter:
    with respx.mock(base_url=API, assert_all_called=False) as router:
        yield router


@pytest.fixture
async def github_client() -> AsyncIterator[GitHubClient]:
    client = GitHubClient(base_url=API, max_retries=2, backoff_base_seconds=0)
    yield client
    await client.aclose()


@dataclass
class Clock:
    now: datetime = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
async def api(
    settings: Settings,
    github_client: GitHubClient,
    clock: Clock,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, github=github_client, clock=clock)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


# ----------------------------------------------------------------------------- GitHub fakes

TOO_LARGE_MESSAGE = (
    "The history or contributor list is too large to list contributors for this repository "
    "via the API."
)


@dataclass
class FakeRepository:
    """Registers respx routes that behave like GitHub for one repository."""

    owner: str = "octo-org"
    name: str = "octo-repo"
    repo: dict[str, Any] = field(default_factory=repo_payload)
    languages: dict[str, int] = field(
        default_factory=lambda: {"Python": 80_000, "Shell": 15_000, "Dockerfile": 5_000}
    )
    contributors: list[dict[str, Any]] = field(
        default_factory=lambda: [
            contributor_payload("ada", 120),
            contributor_payload("grace", 60),
            contributor_payload("linus", 15),
            contributor_payload("dependabot[bot]", 5, user_type="Bot"),
        ]
    )
    commits: list[dict[str, Any]] = field(default_factory=list)
    total_commits: int = 812
    contributors_status: int = 200
    remaining: int = 50
    calls: dict[str, int] = field(default_factory=dict)

    def register(self, router: respx.MockRouter) -> FakeRepository:
        base = f"/repos/{self.owner}/{self.name}"
        router.get(base).mock(side_effect=self._handler("repo", lambda r: self.repo))
        router.get(f"{base}/languages").mock(
            side_effect=self._handler("languages", lambda r: self.languages)
        )
        router.get(f"{base}/contributors").mock(side_effect=self._contributors)
        router.get(f"{base}/commits").mock(side_effect=self._commits)
        return self

    def _count(self, key: str) -> None:
        self.calls[key] = self.calls.get(key, 0) + 1

    def _response(
        self, status: int, json: Any = None, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        all_headers = {**rate_limit_headers(remaining=self.remaining), **(headers or {})}
        return httpx.Response(status, json=json, headers=all_headers)

    def _handler(
        self, key: str, body: Callable[[httpx.Request], Any]
    ) -> Callable[[httpx.Request], httpx.Response]:
        def handle(request: httpx.Request) -> httpx.Response:
            self._count(key)
            return self._response(200, body(request))

        return handle

    def _contributors(self, request: httpx.Request) -> httpx.Response:
        per_page = int(request.url.params.get("per_page", "30"))
        key = "contributors_count" if per_page == 1 else "contributors"
        self._count(key)
        if self.contributors_status != 200:
            return self._response(
                self.contributors_status,
                {"message": TOO_LARGE_MESSAGE},
            )
        return self._paged(request, self.contributors, per_page)

    def _commits(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        per_page = int(params.get("per_page", "30"))
        if "since" in params:
            self._count("commits")
            since = datetime.fromisoformat(params["since"].replace("Z", "+00:00"))
            items = [
                c
                for c in self.commits
                if datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00"))
                >= since
            ]
            return self._paged(request, items, per_page)
        if per_page == 1:
            self._count("commits_count")
            headers = (
                {"link": link_header(request.url.path, last_page=self.total_commits, per_page="1")}
                if self.total_commits > 1
                else {}
            )
            return self._response(200, self.commits[:1], headers)
        self._count("recent_commits")
        return self._response(200, self.commits[:per_page])

    def _paged(self, request: httpx.Request, items: list[Any], per_page: int) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        start = (page - 1) * per_page
        chunk = items[start : start + per_page]
        pages = max(1, -(-len(items) // per_page))
        extra = {k: v for k, v in request.url.params.items() if k != "page"}
        headers: dict[str, str] = {}
        if page < pages:
            headers["link"] = link_header(
                request.url.path, next_page=page + 1, last_page=pages, **extra
            )
        return self._response(200, chunk, headers)


def weekly_commits(
    weeks: int,
    per_week: int | Callable[[int], int],
    *,
    login: str | None = "ada",
    author_name: str = "Ada",
) -> list[dict[str, Any]]:
    """Commits spread over the last ``weeks`` weeks (newest first, like GitHub returns them)."""
    commits: list[dict[str, Any]] = []
    for week in range(weeks):
        count = per_week(week) if callable(per_week) else per_week
        for i in range(count):
            when = NOW - timedelta(days=7 * week + 1, hours=i)
            commits.append(
                commit_payload(
                    f"{week:03d}{i:04d}".ljust(40, "a"), when, login=login, author_name=author_name
                )
            )
    commits.sort(key=lambda c: c["commit"]["author"]["date"], reverse=True)
    return commits


@pytest.fixture
def fake_repo(github_mock: respx.MockRouter) -> FakeRepository:
    fake = FakeRepository(commits=weekly_commits(20, 3))
    return fake.register(github_mock)
