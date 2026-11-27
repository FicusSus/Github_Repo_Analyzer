from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.github.client import GitHubClient
from app.github.errors import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubForbiddenError,
    GitHubUnavailableError,
    RateLimitExceededError,
    RepositoryNotFoundError,
)
from app.github.url import RepositoryRef
from tests.factories import (
    API,
    NOW,
    commit_payload,
    contributor_payload,
    link_header,
    rate_limit_headers,
    repo_payload,
)

REF = RepositoryRef("octo-org", "octo-repo")
BASE = "/repos/octo-org/octo-repo"


async def test_get_repository_parses_payload(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(
        200, json=repo_payload(), headers=rate_limit_headers(remaining=59)
    )

    repo = await github_client.get_repository(REF)

    assert repo.full_name == "octo-org/octo-repo"
    assert repo.stargazers_count == 1500
    assert repo.license is not None
    assert repo.license.spdx_id == "MIT"
    assert repo.created_at.tzinfo is not None
    request = github_mock.calls.last.request
    assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert request.headers["Accept"] == "application/vnd.github+json"
    assert "Authorization" not in request.headers
    assert github_client.last_rate_limit is not None
    assert github_client.last_rate_limit.remaining == 59


async def test_token_is_sent_as_bearer(github_mock: respx.MockRouter) -> None:
    github_mock.get(BASE).respond(200, json=repo_payload())
    async with GitHubClient(base_url=API, token="ghp_secret") as client:
        await client.get_repository(REF)
        assert client.authenticated
    assert github_mock.calls.last.request.headers["Authorization"] == "Bearer ghp_secret"


async def test_not_found(github_mock: respx.MockRouter, github_client: GitHubClient) -> None:
    github_mock.get(BASE).respond(404, json={"message": "Not Found"})
    with pytest.raises(RepositoryNotFoundError):
        await github_client.get_repository(REF)


async def test_bad_token(github_mock: respx.MockRouter, github_client: GitHubClient) -> None:
    github_mock.get(BASE).respond(401, json={"message": "Bad credentials"})
    with pytest.raises(GitHubAuthenticationError):
        await github_client.get_repository(REF)


async def test_primary_rate_limit_then_fail_fast(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    reset = datetime.now(UTC) + timedelta(minutes=20)
    route = github_mock.get(BASE).respond(
        403,
        json={"message": "API rate limit exceeded for 1.2.3.4."},
        headers=rate_limit_headers(remaining=0, reset=reset),
    )

    with pytest.raises(RateLimitExceededError) as first:
        await github_client.get_repository(REF)
    assert first.value.reset_at == reset.replace(microsecond=0)

    # The client now knows the budget is spent and does not call GitHub again.
    with pytest.raises(RateLimitExceededError):
        await github_client.get_languages(REF)
    assert route.call_count == 1


async def test_secondary_rate_limit_uses_retry_after(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(
        429,
        json={"message": "You have exceeded a secondary rate limit."},
        headers={"retry-after": "42"},
    )
    with pytest.raises(RateLimitExceededError) as error:
        await github_client.get_repository(REF)
    assert error.value.retry_after_seconds == 42


async def test_secondary_rate_limit_without_headers_waits_a_minute(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(403, json={"message": "You have exceeded a secondary rate limit"})
    with pytest.raises(RateLimitExceededError) as error:
        await github_client.get_repository(REF)
    assert error.value.retry_after_seconds == 60


async def test_other_forbidden_is_not_a_rate_limit(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(403, json={"message": "Repository access blocked"})
    with pytest.raises(GitHubForbiddenError):
        await github_client.get_repository(REF)


async def test_server_errors_are_retried(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    route = github_mock.get(BASE).mock(
        side_effect=[
            httpx.Response(502),
            httpx.ConnectTimeout("timeout"),
            httpx.Response(200, json=repo_payload()),
        ]
    )
    repo = await github_client.get_repository(REF)
    assert repo.name == "octo-repo"
    assert route.call_count == 3


async def test_gives_up_after_max_retries(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    route = github_mock.get(BASE).respond(503)
    with pytest.raises(GitHubUnavailableError):
        await github_client.get_repository(REF)
    assert route.call_count == 3  # first attempt + max_retries=2


async def test_network_failure_maps_to_unavailable(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).mock(side_effect=httpx.ConnectError("dns failure"))
    with pytest.raises(GitHubUnavailableError, match="Could not reach GitHub"):
        await github_client.get_repository(REF)


async def test_unexpected_payload_raises_github_error(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(200, json={"unexpected": True})
    with pytest.raises(GitHubError, match="Unexpected repository payload"):
        await github_client.get_repository(REF)


async def test_invalid_json_raises_github_error(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(BASE).respond(200, text="<html>oops</html>")
    with pytest.raises(GitHubError, match="not valid JSON"):
        await github_client.get_repository(REF)


async def test_conditional_requests_reuse_cached_body(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    route = github_mock.get(f"{BASE}/languages").mock(
        side_effect=[
            httpx.Response(200, json={"Go": 100}, headers={"etag": 'W/"abc"'}),
            httpx.Response(304),
        ]
    )

    assert await github_client.get_languages(REF) == {"Go": 100}
    assert await github_client.get_languages(REF) == {"Go": 100}

    assert route.calls[0].request.headers.get("If-None-Match") is None
    assert route.calls[1].request.headers["If-None-Match"] == 'W/"abc"'


async def test_pagination_follows_link_header_until_cap(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    path = f"{BASE}/contributors"

    def page(request: httpx.Request) -> httpx.Response:
        number = int(request.url.params.get("page", "1"))
        items = [contributor_payload(f"user{number}-{i}", 100 - i) for i in range(2)]
        return httpx.Response(
            200,
            json=items,
            headers={"link": link_header(path, next_page=number + 1, last_page=5, per_page="100")},
        )

    route = github_mock.get(path).mock(side_effect=page)

    result = await github_client.list_contributors(REF, max_pages=3)

    assert [c.login for c in result.items][:3] == ["user1-0", "user1-1", "user2-0"]
    assert len(result.items) == 6
    assert result.truncated is True
    assert route.call_count == 3
    assert route.calls[0].request.url.params["per_page"] == "100"
    assert route.calls[2].request.url.params["page"] == "3"


async def test_pagination_reports_complete_result(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(f"{BASE}/contributors").respond(200, json=[contributor_payload("solo", 3)])
    result = await github_client.list_contributors(REF, max_pages=3)
    assert result.truncated is False
    assert len(result.items) == 1


async def test_count_uses_last_page_number(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    path = f"{BASE}/commits"
    github_mock.get(path).respond(
        200,
        json=[commit_payload("a" * 40, NOW)],
        headers={"link": link_header(path, next_page=2, last_page=4321, per_page="1")},
    )
    assert await github_client.count_commits(REF) == 4321
    assert github_mock.calls.last.request.url.params["per_page"] == "1"


async def test_count_without_link_header(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(f"{BASE}/contributors").respond(200, json=[contributor_payload("solo", 3)])
    assert await github_client.count_contributors(REF) == 1


async def test_empty_repository_has_no_commits(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(f"{BASE}/commits").respond(409, json={"message": "Git Repository is empty."})
    result = await github_client.list_commits(REF, since=NOW - timedelta(days=30), max_pages=2)
    assert result.items == []
    assert result.truncated is False
    assert await github_client.count_commits(REF) == 0
    assert await github_client.list_recent_commits(REF, limit=5) == []


async def test_contributors_no_content(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get(f"{BASE}/contributors").respond(204)
    result = await github_client.list_contributors(REF)
    assert result.items == []


async def test_list_commits_sends_since_in_utc(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    route = github_mock.get(f"{BASE}/commits").respond(200, json=[])
    since = datetime(2026, 1, 15, 3, 4, 5, tzinfo=UTC)
    await github_client.list_commits(REF, since=since, max_pages=1)
    assert route.calls.last.request.url.params["since"] == "2026-01-15T03:04:05Z"


async def test_get_rate_limit(github_mock: respx.MockRouter, github_client: GitHubClient) -> None:
    reset = int((NOW + timedelta(minutes=10)).timestamp())
    github_mock.get("/rate_limit").respond(
        200,
        json={"resources": {"core": {"limit": 60, "remaining": 12, "used": 48, "reset": reset}}},
    )
    status = await github_client.get_rate_limit()
    assert (status.limit, status.remaining, status.used) == (60, 12, 48)
    assert status.reset_at == datetime.fromtimestamp(reset, tz=UTC)
    assert status.authenticated is False


async def test_get_rate_limit_rejects_malformed_payload(
    github_mock: respx.MockRouter, github_client: GitHubClient
) -> None:
    github_mock.get("/rate_limit").respond(200, json={"resources": {}})
    with pytest.raises(GitHubError):
        await github_client.get_rate_limit()
