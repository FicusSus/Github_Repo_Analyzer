from __future__ import annotations

from datetime import timedelta

import httpx
import respx

from tests.conftest import Clock, FakeRepository, weekly_commits
from tests.factories import NOW, rate_limit_headers, repo_payload


async def analyze(api: httpx.AsyncClient, repository: str, **extra: object) -> httpx.Response:
    return await api.post("/api/analyses", json={"repository": repository, **extra})


class TestAnalyze:
    async def test_creates_analysis(
        self, api: httpx.AsyncClient, fake_repo: FakeRepository
    ) -> None:
        response = await analyze(api, "https://github.com/octo-org/octo-repo")

        assert response.status_code == 201
        body = response.json()
        assert body["from_cache"] is False
        assert body["repository"]["full_name"] == "octo-org/octo-repo"
        assert body["repository"]["license"] == "MIT"
        assert body["metrics"] == {
            "stars": 1500,
            "forks": 120,
            "open_issues": 42,
            "watchers": 37,
            "size_kb": 2048,
            "contributors_count": 4,
            "total_commits": 812,
        }
        assert body["languages"][0] == {"language": "Python", "bytes": 80000, "percentage": 80.0}
        assert body["contributors"][0]["login"] == "ada"
        assert body["contributors"][-1]["is_bot"] is True
        assert body["contributor_stats"]["bus_factor"] == 1
        stats = body["commit_stats"]
        assert stats["commits_analyzed"] == 60
        assert len(stats["by_weekday"]) == 7
        assert stats["weekly"][-1]["period_start"] == "2026-11-23"
        assert stats["trend"]["direction"] in {"increasing", "decreasing", "stable"}
        assert body["recent_commits"][0]["sha"].startswith("000")

    async def test_recent_analysis_is_served_from_cache(
        self, api: httpx.AsyncClient, fake_repo: FakeRepository, clock: Clock
    ) -> None:
        first = await analyze(api, "octo-org/octo-repo")
        clock.now = NOW + timedelta(minutes=5)
        second = await analyze(api, "OCTO-ORG/octo-repo")

        assert second.status_code == 200
        assert second.json()["from_cache"] is True
        assert second.json()["id"] == first.json()["id"]
        assert fake_repo.calls["repo"] == 1

    async def test_force_and_expired_cache_reanalyze(
        self, api: httpx.AsyncClient, fake_repo: FakeRepository, clock: Clock
    ) -> None:
        first = await analyze(api, "octo-org/octo-repo")
        forced = await analyze(api, "octo-org/octo-repo", force=True)
        clock.now = NOW + timedelta(hours=2)
        expired = await analyze(api, "octo-org/octo-repo")

        assert forced.status_code == 201
        assert expired.status_code == 201
        assert len({first.json()["id"], forced.json()["id"], expired.json()["id"]}) == 3
        assert fake_repo.calls["repo"] == 3

    async def test_invalid_reference(self, api: httpx.AsyncClient) -> None:
        response = await analyze(api, "https://gitlab.com/a/b")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_repository"

    async def test_body_validation_uses_error_envelope(self, api: httpx.AsyncClient) -> None:
        response = await api.post("/api/analyses", json={"repository": ""})
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert error["details"]["errors"][0]["location"] == "body.repository"

    async def test_repository_not_found(
        self, api: httpx.AsyncClient, github_mock: respx.MockRouter
    ) -> None:
        github_mock.get("/repos/ghost/nothing").respond(404, json={"message": "Not Found"})
        response = await analyze(api, "ghost/nothing")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "repository_not_found"

    async def test_rate_limited(
        self, api: httpx.AsyncClient, github_mock: respx.MockRouter
    ) -> None:
        github_mock.get("/repos/octo-org/octo-repo").respond(
            403,
            json={"message": "API rate limit exceeded"},
            headers=rate_limit_headers(remaining=0, reset=NOW.replace(year=2099)),
        )
        response = await analyze(api, "octo-org/octo-repo")
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0
        error = response.json()["error"]
        assert error["code"] == "github_rate_limited"
        assert error["details"]["reset_at"].startswith("2099-")

    async def test_github_outage(
        self, api: httpx.AsyncClient, github_mock: respx.MockRouter
    ) -> None:
        github_mock.get("/repos/octo-org/octo-repo").respond(500)
        response = await analyze(api, "octo-org/octo-repo")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "github_unavailable"

    async def test_failed_analysis_stores_nothing(
        self, api: httpx.AsyncClient, github_mock: respx.MockRouter
    ) -> None:
        FakeRepository(commits=weekly_commits(2, 1)).register(github_mock)
        github_mock.get("/repos/octo-org/octo-repo/languages").respond(503)
        response = await analyze(api, "octo-org/octo-repo")
        assert response.status_code == 502
        listing = await api.get("/api/analyses")
        assert listing.json()["total"] == 0


class TestStoredAnalyses:
    async def test_list_get_delete(self, api: httpx.AsyncClient, fake_repo: FakeRepository) -> None:
        created = (await analyze(api, "octo-org/octo-repo")).json()

        listing = await api.get("/api/analyses", params={"repository": "octo-org/octo-repo"})
        assert listing.status_code == 200
        page = listing.json()
        assert page["total"] == 1
        assert page["items"][0]["full_name"] == "octo-org/octo-repo"
        assert page["items"][0]["commits_last_30_days"] == 15

        detail = await api.get(f"/api/analyses/{created['id']}")
        assert detail.status_code == 200
        assert detail.json()["commit_stats"] == created["commit_stats"]

        latest = await api.get("/api/repositories/octo-org/octo-repo/latest")
        assert latest.json()["id"] == created["id"]

        deleted = await api.delete(f"/api/analyses/{created['id']}")
        assert deleted.status_code == 204
        missing = await api.get(f"/api/analyses/{created['id']}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "analysis_not_found"
        assert (await api.delete(f"/api/analyses/{created['id']}")).status_code == 404

    async def test_pagination_validation(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/analyses", params={"limit": 0})
        assert response.status_code == 422

    async def test_unknown_route_uses_envelope(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestHistoryAndComparison:
    async def test_history_tracks_changes(
        self, api: httpx.AsyncClient, fake_repo: FakeRepository, clock: Clock
    ) -> None:
        await analyze(api, "octo-org/octo-repo")
        fake_repo.repo = repo_payload(stars=1800, forks=150)
        clock.now = NOW + timedelta(days=7)
        await analyze(api, "octo-org/octo-repo")

        response = await api.get("/api/repositories/octo-org/octo-repo/history")
        assert response.status_code == 200
        history = response.json()
        assert [p["stars"] for p in history["points"]] == [1500, 1800]
        assert history["changes"]["stars"] == {
            "first": 1500.0,
            "last": 1800.0,
            "absolute": 300.0,
            "percent": 20.0,
        }

        repositories = (await api.get("/api/repositories")).json()
        assert repositories["total"] == 1
        assert repositories["items"][0]["analyses_count"] == 2
        assert repositories["items"][0]["latest"]["stars"] == 1800

    async def test_history_of_unknown_repository(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/repositories/nobody/nothing/history")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "repository_not_tracked"

    async def test_compare(self, api: httpx.AsyncClient, github_mock: respx.MockRouter) -> None:
        FakeRepository(commits=weekly_commits(10, 2)).register(github_mock)
        FakeRepository(
            owner="other",
            name="lib",
            repo=repo_payload("other", "lib", repo_id=2002, stars=10, language="Rust"),
            languages={"Rust": 900, "Python": 100},
            commits=weekly_commits(3, 5, login="grace", author_name="Grace"),
        ).register(github_mock)
        await analyze(api, "octo-org/octo-repo")
        await analyze(api, "other/lib")

        response = await api.get(
            "/api/compare",
            params=[("repositories", "octo-org/octo-repo"), ("repositories", "other/lib")],
        )

        assert response.status_code == 200
        comparison = response.json()
        names = [r["full_name"] for r in comparison["repositories"]]
        assert names == ["octo-org/octo-repo", "other/lib"]
        languages = {row["language"]: row["shares"] for row in comparison["languages"]}
        assert languages["Rust"] == {"octo-org/octo-repo": 0.0, "other/lib": 90.0}
        assert languages["Python"] == {"octo-org/octo-repo": 80.0, "other/lib": 10.0}
        weekly = comparison["weekly_activity"]
        assert len(weekly["weeks"]) == len(weekly["series"]["octo-org/octo-repo"])
        assert weekly["series"]["octo-org/octo-repo"][-2] == 2
        assert weekly["series"]["other/lib"][-2] == 5

    async def test_compare_requires_analyzed_repositories(
        self, api: httpx.AsyncClient, fake_repo: FakeRepository
    ) -> None:
        await analyze(api, "octo-org/octo-repo")
        response = await api.get(
            "/api/compare", params=[("repositories", "octo-org/octo-repo"), ("repositories", "x/y")]
        )
        assert response.status_code == 404
        assert response.json()["error"]["details"]["missing"] == ["x/y"]

    async def test_compare_rejects_duplicates(self, api: httpx.AsyncClient) -> None:
        response = await api.get(
            "/api/compare", params=[("repositories", "a/b"), ("repositories", "A/B")]
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_comparison"

    async def test_compare_requires_two(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/compare", params={"repositories": "a/b"})
        assert response.status_code == 422


class TestMeta:
    async def test_health(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    async def test_rate_limit(self, api: httpx.AsyncClient, github_mock: respx.MockRouter) -> None:
        github_mock.get("/rate_limit").respond(
            200,
            json={
                "resources": {
                    "core": {"limit": 60, "remaining": 59, "used": 1, "reset": 1900000000}
                }
            },
        )
        response = await api.get("/api/github/rate-limit")
        assert response.status_code == 200
        assert response.json()["remaining"] == 59

    async def test_openapi_is_served(self, api: httpx.AsyncClient) -> None:
        response = await api.get("/api/openapi.json")
        assert response.status_code == 200
        assert "/api/analyses" in response.json()["paths"]
