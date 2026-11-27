"""Request and response models of the public HTTP API, plus ORM -> schema mappers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.models import (
    CommitStats,
    ContributorShare,
    ContributorStats,
    LanguageShare,
    RecentCommit,
    TrendDirection,
)
from app.db.models import Analysis


class _Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- requests


class AnalyzeRequest(BaseModel):
    repository: str = Field(
        min_length=1,
        max_length=500,
        description="Repository URL or `owner/name` shorthand.",
        examples=["https://github.com/fastapi/fastapi", "pallets/flask"],
    )
    force: bool = Field(
        default=False,
        description="Analyze again even if a recent stored analysis exists.",
    )


# ----------------------------------------------------------------------------- analyses


class RepositoryInfo(_Schema):
    full_name: str
    owner: str
    name: str
    html_url: str
    owner_avatar_url: str | None
    description: str | None
    homepage: str | None
    default_branch: str
    primary_language: str | None
    license: str | None
    topics: list[str]
    is_fork: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    pushed_at: datetime | None


class RepositoryMetrics(_Schema):
    stars: int
    forks: int
    open_issues: int = Field(description="Open issues *and* pull requests, as GitHub counts them.")
    watchers: int | None
    size_kb: int
    contributors_count: int | None
    total_commits: int | None = Field(description="Commits on the default branch.")


class AnalysisDetail(_Schema):
    id: int
    analyzed_at: datetime
    from_cache: bool = False
    repository: RepositoryInfo
    metrics: RepositoryMetrics
    languages: list[LanguageShare]
    contributors: list[ContributorShare]
    contributor_stats: ContributorStats
    commit_stats: CommitStats
    recent_commits: list[RecentCommit]


class AnalysisSummary(_Schema):
    id: int
    analyzed_at: datetime
    full_name: str
    html_url: str
    description: str | None
    primary_language: str | None
    stars: int
    forks: int
    open_issues: int
    contributors_count: int | None
    commits_last_30_days: int
    average_weekly_commits: float


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


# ----------------------------------------------------------------------------- repositories


class TrackedRepository(BaseModel):
    full_name: str
    html_url: str
    analyses_count: int
    first_analyzed_at: datetime
    last_analyzed_at: datetime
    latest: AnalysisSummary


class HistoryPoint(BaseModel):
    analysis_id: int
    analyzed_at: datetime
    stars: int
    forks: int
    open_issues: int
    watchers: int | None
    contributors_count: int | None
    total_commits: int | None
    commits_last_30_days: int
    average_weekly_commits: float


class MetricChange(BaseModel):
    first: float | None
    last: float | None
    absolute: float | None
    percent: float | None


class RepositoryHistory(BaseModel):
    full_name: str
    html_url: str
    points: list[HistoryPoint]
    changes: dict[str, MetricChange]


# ----------------------------------------------------------------------------- comparison


class ComparedRepository(BaseModel):
    analysis_id: int
    full_name: str
    html_url: str
    analyzed_at: datetime
    primary_language: str | None
    stars: int
    forks: int
    open_issues: int
    contributors_count: int | None
    total_commits: int | None
    commits_analyzed: int
    average_weekly_commits: float
    commits_last_30_days: int
    days_since_last_commit: int | None
    bus_factor: int | None
    trend: TrendDirection
    repo_created_at: datetime


class LanguageComparisonRow(BaseModel):
    language: str
    shares: dict[str, float] = Field(description="Percentage per repository full name.")


class WeeklyComparison(BaseModel):
    weeks: list[date]
    series: dict[str, list[int | None]] = Field(
        description="Commits per week per repository; null where a week lies outside that "
        "repository's analysed window."
    )


class Comparison(BaseModel):
    repositories: list[ComparedRepository]
    languages: list[LanguageComparisonRow]
    weekly_activity: WeeklyComparison


# ----------------------------------------------------------------------------- misc


class RateLimitInfo(BaseModel):
    limit: int
    remaining: int
    used: int
    reset_at: datetime
    authenticated: bool


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ----------------------------------------------------------------------------- mappers


def to_detail(analysis: Analysis, *, from_cache: bool = False) -> AnalysisDetail:
    repo = analysis.repository
    return AnalysisDetail(
        id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        from_cache=from_cache,
        repository=RepositoryInfo(
            full_name=repo.full_name,
            owner=repo.owner,
            name=repo.name,
            html_url=repo.html_url,
            owner_avatar_url=analysis.owner_avatar_url,
            description=analysis.description,
            homepage=analysis.homepage,
            default_branch=analysis.default_branch,
            primary_language=analysis.primary_language,
            license=analysis.license,
            topics=list(analysis.topics or []),
            is_fork=analysis.is_fork,
            is_archived=analysis.is_archived,
            created_at=analysis.repo_created_at,
            updated_at=analysis.repo_updated_at,
            pushed_at=analysis.repo_pushed_at,
        ),
        metrics=RepositoryMetrics(
            stars=analysis.stars,
            forks=analysis.forks,
            open_issues=analysis.open_issues,
            watchers=analysis.watchers,
            size_kb=analysis.size_kb,
            contributors_count=analysis.contributors_count,
            total_commits=analysis.total_commits,
        ),
        languages=[
            LanguageShare(language=lang.language, bytes=lang.bytes, percentage=lang.percentage)
            for lang in analysis.languages
        ],
        contributors=[
            ContributorShare(
                login=c.login,
                is_bot=c.login.lower().endswith("[bot]"),
                contributions=c.contributions,
                percentage=c.percentage,
                avatar_url=c.avatar_url,
                html_url=c.html_url,
            )
            for c in analysis.contributors
        ],
        contributor_stats=ContributorStats.model_validate(analysis.contributor_stats),
        commit_stats=CommitStats.model_validate(analysis.commit_stats),
        recent_commits=[RecentCommit.model_validate(c) for c in analysis.recent_commits or []],
    )


def to_summary(analysis: Analysis) -> AnalysisSummary:
    return AnalysisSummary(
        id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        full_name=analysis.repository.full_name,
        html_url=analysis.repository.html_url,
        description=analysis.description,
        primary_language=analysis.primary_language,
        stars=analysis.stars,
        forks=analysis.forks,
        open_issues=analysis.open_issues,
        contributors_count=analysis.contributors_count,
        commits_last_30_days=analysis.commits_last_30_days,
        average_weekly_commits=analysis.average_weekly_commits,
    )


def to_history_point(analysis: Analysis) -> HistoryPoint:
    return HistoryPoint(
        analysis_id=analysis.id,
        analyzed_at=analysis.analyzed_at,
        stars=analysis.stars,
        forks=analysis.forks,
        open_issues=analysis.open_issues,
        watchers=analysis.watchers,
        contributors_count=analysis.contributors_count,
        total_commits=analysis.total_commits,
        commits_last_30_days=analysis.commits_last_30_days,
        average_weekly_commits=analysis.average_weekly_commits,
    )
