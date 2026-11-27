"""Typed views over the subset of GitHub REST API payloads the analyzer uses.

Only the fields we rely on are declared; everything else in GitHub's responses is ignored,
so additive API changes do not break parsing.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _GitHubModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class GitHubUser(_GitHubModel):
    login: str
    avatar_url: str | None = None
    html_url: str | None = None


class GitHubLicense(_GitHubModel):
    spdx_id: str | None = None
    name: str | None = None


class GitHubRepository(_GitHubModel):
    id: int
    name: str
    full_name: str
    owner: GitHubUser
    html_url: str
    description: str | None = None
    homepage: str | None = None
    language: str | None = None
    default_branch: str = "main"
    stargazers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    subscribers_count: int | None = None
    size: int = 0
    fork: bool = False
    archived: bool = False
    private: bool = False
    topics: list[str] = Field(default_factory=list)
    license: GitHubLicense | None = None
    created_at: datetime
    updated_at: datetime
    pushed_at: datetime | None = None


class GitHubContributor(_GitHubModel):
    login: str
    contributions: int
    avatar_url: str | None = None
    html_url: str | None = None
    type: str = "User"


class GitHubCommitPerson(_GitHubModel):
    name: str | None = None
    email: str | None = None
    date: datetime | None = None


class GitHubCommitDetail(_GitHubModel):
    message: str = ""
    author: GitHubCommitPerson | None = None
    committer: GitHubCommitPerson | None = None


class GitHubCommit(_GitHubModel):
    sha: str
    html_url: str | None = None
    commit: GitHubCommitDetail
    author: GitHubUser | None = None
    """GitHub account linked to the commit author email; ``None`` when no account matches."""

    @property
    def authored_at(self) -> datetime | None:
        if self.commit.author and self.commit.author.date:
            return self.commit.author.date
        if self.commit.committer and self.commit.committer.date:
            return self.commit.committer.date
        return None

    @property
    def author_name(self) -> str:
        if self.commit.author and self.commit.author.name:
            return self.commit.author.name
        if self.author:
            return self.author.login
        return "unknown"

    @property
    def headline(self) -> str:
        return self.commit.message.strip().splitlines()[0] if self.commit.message.strip() else ""


class RateLimitStatus(_GitHubModel):
    limit: int
    remaining: int
    used: int
    reset_at: datetime
    authenticated: bool
