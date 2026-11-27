"""Builders for realistic GitHub REST API payloads used to mock api.github.com."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

API = "https://api.github.test"
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_payload(
    owner: str = "octo-org",
    name: str = "octo-repo",
    *,
    repo_id: int = 1001,
    stars: int = 1500,
    forks: int = 120,
    open_issues: int = 42,
    language: str | None = "Python",
    created_at: datetime = datetime(2019, 3, 1, tzinfo=UTC),
    pushed_at: datetime | None = NOW - timedelta(days=1),
    size: int = 2048,
) -> dict[str, Any]:
    return {
        "id": repo_id,
        "node_id": "R_kgDOxyz",
        "name": name,
        "full_name": f"{owner}/{name}",
        "private": False,
        "owner": {
            "login": owner,
            "id": 9,
            "avatar_url": f"https://avatars.githubusercontent.com/u/9?v=4&o={owner}",
            "html_url": f"https://github.com/{owner}",
            "type": "Organization",
        },
        "html_url": f"https://github.com/{owner}/{name}",
        "description": "A repository used in tests",
        "fork": False,
        "homepage": "https://example.org",
        "size": size,
        "stargazers_count": stars,
        "watchers_count": stars,
        "subscribers_count": 37,
        "language": language,
        "forks_count": forks,
        "open_issues_count": open_issues,
        "archived": False,
        "disabled": False,
        "topics": ["analytics", "testing"],
        "license": {"key": "mit", "name": "MIT License", "spdx_id": "MIT"},
        "default_branch": "main",
        "created_at": iso(created_at),
        "updated_at": iso(NOW - timedelta(hours=3)),
        "pushed_at": iso(pushed_at) if pushed_at else None,
    }


def contributor_payload(
    login: str, contributions: int, *, user_type: str = "User"
) -> dict[str, Any]:
    return {
        "login": login,
        "id": abs(hash(login)) % 10_000_000,
        "avatar_url": f"https://avatars.githubusercontent.com/{login}",
        "html_url": f"https://github.com/{login}",
        "type": user_type,
        "contributions": contributions,
    }


def commit_payload(
    sha: str,
    authored_at: datetime,
    *,
    author_name: str = "Ada Lovelace",
    login: str | None = "ada",
    message: str = "Fix the thing\n\nLonger body explaining the fix.",
    owner: str = "octo-org",
    name: str = "octo-repo",
) -> dict[str, Any]:
    return {
        "sha": sha,
        "html_url": f"https://github.com/{owner}/{name}/commit/{sha}",
        "commit": {
            "author": {
                "name": author_name,
                "email": f"{author_name}@example.org",
                "date": iso(authored_at),
            },
            "committer": {
                "name": "GitHub",
                "email": "noreply@github.com",
                "date": iso(authored_at),
            },
            "message": message,
        },
        "author": {
            "login": login,
            "id": 1,
            "avatar_url": "",
            "html_url": f"https://github.com/{login}",
        }
        if login
        else None,
        "committer": None,
        "parents": [],
    }


def rate_limit_headers(
    remaining: int = 55, limit: int = 60, reset: datetime | None = None
) -> dict[str, str]:
    reset_at = reset or NOW + timedelta(minutes=30)
    return {
        "x-ratelimit-limit": str(limit),
        "x-ratelimit-remaining": str(remaining),
        "x-ratelimit-used": str(limit - remaining),
        "x-ratelimit-reset": str(int(reset_at.timestamp())),
        "x-ratelimit-resource": "core",
    }


def link_header(
    path: str, *, next_page: int | None = None, last_page: int | None = None, **params: str
) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    prefix = f"{API}{path}?{query + '&' if query else ''}"
    links = []
    if next_page is not None:
        links.append(f'<{prefix}page={next_page}>; rel="next"')
    if last_page is not None:
        links.append(f'<{prefix}page={last_page}>; rel="last"')
    return ", ".join(links)
