from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import respx

from app.config import Settings
from app.github.client import GitHubClient
from app.github.errors import RateLimitExceededError, RepositoryNotFoundError
from app.github.url import RepositoryRef
from app.services.analyzer import RepositoryAnalyzer
from tests.conftest import Clock, FakeRepository, weekly_commits
from tests.factories import NOW, commit_payload, contributor_payload, repo_payload

REF = RepositoryRef("octo-org", "octo-repo")


def analyzer(client: GitHubClient, settings: Settings, clock: Clock) -> RepositoryAnalyzer:
    return RepositoryAnalyzer(client, settings, clock=clock)


async def test_full_analysis(
    fake_repo: FakeRepository, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    result = await analyzer(github_client, settings, clock).analyze(REF)
    analysis = result.analysis

    assert result.repository.full_name == "octo-org/octo-repo"
    assert analysis.stars == 1500
    assert analysis.forks == 120
    assert analysis.open_issues == 42
    assert analysis.watchers == 37
    assert analysis.license == "MIT"
    assert analysis.topics == ["analytics", "testing"]
    assert analysis.total_commits == 812
    assert analysis.contributors_count == 4
    assert analysis.commits_analyzed == 60
    assert analysis.analyzed_at == NOW

    assert [(lang.language, lang.percentage) for lang in analysis.languages] == [
        ("Python", 80.0),
        ("Shell", 15.0),
        ("Dockerfile", 5.0),
    ]
    assert [(c.rank, c.login) for c in analysis.contributors][:2] == [(1, "ada"), (2, "grace")]
    assert analysis.contributor_stats["bus_factor"] == 1
    assert analysis.commit_stats["recent_activity"]["commits_last_30_days"] == 15
    assert len(analysis.recent_commits) == settings.recent_commits_limit
    assert analysis.recent_commits[0]["message"] == "Fix the thing"

    # Small repository: the contributor list was complete, so no extra count request.
    assert fake_repo.calls.get("contributors_count") is None
    assert fake_repo.calls["commits"] == 1


async def test_large_contributor_list_uses_count_request(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    fake = FakeRepository(
        contributors=[contributor_payload(f"user{i}", 1000 - i) for i in range(250)],
        commits=weekly_commits(2, 1),
    ).register(github_mock)

    analysis = (await analyzer(github_client, settings, clock).analyze(REF)).analysis

    assert analysis.contributors_count == 250
    assert len(analysis.contributors) == 100  # contributors_max_pages=1
    assert fake.calls["contributors_count"] == 1


async def test_contributors_unavailable_degrades_gracefully(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    FakeRepository(contributors_status=403, commits=weekly_commits(3, 2)).register(github_mock)

    analysis = (await analyzer(github_client, settings, clock).analyze(REF)).analysis

    assert analysis.contributors_count is None
    assert analysis.contributors == []
    assert analysis.contributor_stats["available"] is False
    assert analysis.commits_analyzed == 6


async def test_inactive_repository_still_reports_last_commit(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    old = [commit_payload("f" * 40, NOW - timedelta(days=800))]
    fake = FakeRepository(commits=old, total_commits=1).register(github_mock)

    analysis = (await analyzer(github_client, settings, clock).analyze(REF)).analysis

    assert analysis.commits_analyzed == 0
    assert fake.calls["recent_commits"] == 1
    assert len(analysis.recent_commits) == 1
    assert analysis.commit_stats["recent_activity"]["days_since_last_commit"] == 800
    assert analysis.total_commits == 1


async def test_truncated_commit_history(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    # 50 weeks * 10 commits = 500 commits, but only 3 pages (300) may be fetched.
    FakeRepository(commits=weekly_commits(50, 10)).register(github_mock)

    analysis = (await analyzer(github_client, settings, clock).analyze(REF)).analysis

    assert analysis.commit_stats["truncated"] is True
    assert analysis.commits_analyzed < 300
    weekly = analysis.commit_stats["weekly"]
    # No artificial empty weeks at the start of the truncated range.
    assert all(bucket["commits"] > 0 for bucket in weekly[:-1])


async def test_renamed_repository_uses_canonical_name(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    fake = FakeRepository(
        owner="new-owner",
        name="new-name",
        repo=repo_payload("new-owner", "new-name"),
        commits=weekly_commits(2, 1),
    ).register(github_mock)
    # GitHub redirects the old name to the new one.
    github_mock.get("/repos/old-owner/old-name").respond(
        301, headers={"location": "https://api.github.test/repos/new-owner/new-name"}
    )

    result = await analyzer(github_client, settings, clock).analyze(
        RepositoryRef("old-owner", "old-name")
    )

    assert result.repository.full_name == "new-owner/new-name"
    assert fake.calls["languages"] == 1


async def test_not_found_stops_early(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    github_mock.get("/repos/octo-org/octo-repo").respond(404, json={"message": "Not Found"})
    with pytest.raises(RepositoryNotFoundError):
        await analyzer(github_client, settings, clock).analyze(REF)
    assert len(github_mock.calls) == 1


async def test_rate_limit_during_parallel_fetch_is_unwrapped(
    github_mock: respx.MockRouter, github_client: GitHubClient, settings: Settings, clock: Clock
) -> None:
    FakeRepository(commits=weekly_commits(2, 1)).register(github_mock)
    github_mock.get("/repos/octo-org/octo-repo/languages").mock(
        return_value=httpx.Response(
            403, json={"message": "secondary rate limit"}, headers={"retry-after": "30"}
        )
    )
    with pytest.raises(RateLimitExceededError) as error:
        await analyzer(github_client, settings, clock).analyze(REF)
    assert error.value.retry_after_seconds == 30
