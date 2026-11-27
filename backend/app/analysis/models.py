"""Computed statistics. These models are persisted as JSON and returned by the API unchanged."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _StatsModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class TrendDirection(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"
    INSUFFICIENT_DATA = "insufficient_data"


class CountBucket(_StatsModel):
    period_start: date
    commits: int


class AverageBucket(_StatsModel):
    period_start: date
    value: float


class CommitTrend(_StatsModel):
    direction: TrendDirection
    slope_per_week: float = Field(description="Least-squares slope of weekly commit counts.")
    last_4_weeks: int
    previous_4_weeks: int
    change_percent: float | None = Field(
        description="Relative change of the last 4 weeks vs. the 4 weeks before; null if the "
        "previous period had no commits."
    )


class ActiveAuthor(_StatsModel):
    name: str
    login: str | None
    is_bot: bool = False
    commits: int
    percentage: float
    first_commit_at: datetime
    last_commit_at: datetime


class RecentActivity(_StatsModel):
    last_commit_at: datetime | None
    days_since_last_commit: int | None
    commits_last_7_days: int
    commits_last_30_days: int
    active_authors_last_30_days: int


class CommitStats(_StatsModel):
    window_days: int
    since: datetime
    effective_since: datetime = Field(
        description="Start of the period actually covered. Later than `since` when the commit "
        "list was truncated by the page cap."
    )
    commits_analyzed: int
    truncated: bool
    average_weekly_commits: float
    weekly: list[CountBucket]
    monthly: list[CountBucket]
    rolling_weekly_average: list[AverageBucket]
    by_weekday: list[int] = Field(description="Commit counts Monday..Sunday (UTC).")
    trend: CommitTrend
    active_authors: list[ActiveAuthor]
    recent_activity: RecentActivity


class ContributorShare(_StatsModel):
    login: str
    is_bot: bool = False
    contributions: int
    percentage: float
    avatar_url: str | None = None
    html_url: str | None = None


class ContributorStats(_StatsModel):
    available: bool = Field(
        description="False when GitHub refuses to list contributors (very large histories)."
    )
    listed: int
    total_contributions: int
    top_contributor_share: float | None
    top_5_share: float | None
    gini_coefficient: float | None = Field(
        description="Inequality of contribution counts among listed contributors: 0 means "
        "perfectly even, values close to 1 mean work is concentrated in very few people."
    )
    bus_factor: int | None = Field(
        description="Smallest number of contributors that together made at least 50% of the "
        "listed contributions."
    )


class LanguageShare(_StatsModel):
    language: str
    bytes: int
    percentage: float


class RecentCommit(_StatsModel):
    sha: str
    message: str
    author_name: str
    author_login: str | None
    authored_at: datetime
    html_url: str | None
