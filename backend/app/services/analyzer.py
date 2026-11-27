"""Fetches everything needed for one analysis from GitHub and turns it into an ORM object."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.analysis import statistics as stats
from app.analysis.models import CommitStats, LanguageShare, RecentCommit
from app.config import Settings
from app.db.models import Analysis, AnalysisContributor, AnalysisLanguage
from app.github.client import GitHubClient
from app.github.errors import GitHubError, GitHubForbiddenError, RateLimitExceededError
from app.github.models import GitHubCommit, GitHubContributor, GitHubRepository
from app.github.url import RepositoryRef

logger = logging.getLogger(__name__)

Clock = Callable[[], datetime]


def utc_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    repository: GitHubRepository
    analysis: Analysis


@dataclass(frozen=True, slots=True)
class _ContributorData:
    items: list[GitHubContributor]
    count: int


class RepositoryAnalyzer:
    def __init__(self, client: GitHubClient, settings: Settings, clock: Clock = utc_clock) -> None:
        self._client = client
        self._settings = settings
        self._clock = clock

    async def analyze(self, ref: RepositoryRef) -> AnalyzerResult:
        # Fetch the repository first: a 404 here avoids spending ~8 more requests.
        repository = await self._client.get_repository(ref)
        canonical = RepositoryRef(owner=repository.owner.login, name=repository.name)

        now = self._clock()
        since = now - timedelta(days=self._settings.commit_window_days)

        try:
            async with asyncio.TaskGroup() as group:
                languages_task = group.create_task(self._client.get_languages(canonical))
                contributors_task = group.create_task(self._contributors(canonical))
                total_commits_task = group.create_task(self._client.count_commits(canonical))
                commits_task = group.create_task(
                    self._client.list_commits(
                        canonical, since=since, max_pages=self._settings.commits_max_pages
                    )
                )
        except ExceptionGroup as group_error:
            raise _most_relevant(group_error) from group_error

        commits_page = commits_task.result()
        commit_stats = stats.compute_commit_stats(
            [record for c in commits_page.items if (record := _commit_record(c)) is not None],
            since=since,
            now=now,
            window_days=self._settings.commit_window_days,
            truncated=commits_page.truncated,
        )

        recent = commits_page.items[: self._settings.recent_commits_limit]
        if not recent:
            # Inactive repository: nothing inside the window, but users still want to see the
            # latest commits and when the last one happened.
            recent = await self._client.list_recent_commits(
                canonical, limit=self._settings.recent_commits_limit
            )
            commit_stats = _with_last_commit(commit_stats, recent, now)

        contributor_data = contributors_task.result()
        contributor_records = (
            [
                stats.ContributorRecord(
                    login=c.login,
                    contributions=c.contributions,
                    avatar_url=c.avatar_url,
                    html_url=c.html_url,
                )
                for c in contributor_data.items
            ]
            if contributor_data is not None
            else None
        )

        analysis = _build_analysis(
            repository=repository,
            analyzed_at=now,
            languages=stats.compute_language_shares(languages_task.result()),
            contributor_records=contributor_records,
            contributors_count=contributor_data.count if contributor_data else None,
            total_commits=total_commits_task.result(),
            commit_stats=commit_stats,
            recent_commits=[item for c in recent if (item := _recent_commit(c)) is not None],
        )
        return AnalyzerResult(repository=repository, analysis=analysis)

    async def _contributors(self, ref: RepositoryRef) -> _ContributorData | None:
        """Contributors list plus exact count, spending the extra request only when needed.

        GitHub answers 403 for repositories whose history is too large to list contributors;
        that should degrade the analysis, not fail it.
        """
        try:
            page = await self._client.list_contributors(
                ref, max_pages=self._settings.contributors_max_pages
            )
            count = (
                await self._client.count_contributors(ref) if page.truncated else len(page.items)
            )
        except GitHubForbiddenError as exc:
            logger.info("Contributors unavailable for %s: %s", ref.full_name, exc.message)
            return None
        return _ContributorData(items=page.items, count=count)


def _most_relevant(group_error: ExceptionGroup[Exception]) -> Exception:
    leaves: list[Exception] = []

    def collect(error: BaseException) -> None:
        if isinstance(error, BaseExceptionGroup):
            for inner in error.exceptions:
                collect(inner)
        elif isinstance(error, Exception):
            leaves.append(error)

    collect(group_error)
    for kind in (RateLimitExceededError, GitHubError):
        for error in leaves:
            if isinstance(error, kind):
                return error
    return leaves[0] if leaves else group_error


def _commit_record(commit: GitHubCommit) -> stats.CommitRecord | None:
    authored_at = commit.authored_at
    if authored_at is None:
        return None
    return stats.CommitRecord(
        sha=commit.sha,
        authored_at=authored_at,
        author_name=commit.author_name,
        author_login=commit.author.login if commit.author else None,
    )


def _recent_commit(commit: GitHubCommit) -> RecentCommit | None:
    authored_at = commit.authored_at
    if authored_at is None:
        return None
    return RecentCommit(
        sha=commit.sha,
        message=commit.headline[:300],
        author_name=commit.author_name,
        author_login=commit.author.login if commit.author else None,
        authored_at=authored_at,
        html_url=commit.html_url,
    )


def _with_last_commit(
    commit_stats: CommitStats, recent: list[GitHubCommit], now: datetime
) -> CommitStats:
    dates = [c.authored_at for c in recent if c.authored_at is not None]
    if not dates:
        return commit_stats
    last = max(dates)
    activity = commit_stats.recent_activity.model_copy(
        update={"last_commit_at": last, "days_since_last_commit": max((now - last).days, 0)}
    )
    return commit_stats.model_copy(update={"recent_activity": activity})


def _license_label(repository: GitHubRepository) -> str | None:
    if repository.license is None:
        return None
    if repository.license.spdx_id and repository.license.spdx_id != "NOASSERTION":
        return repository.license.spdx_id
    return repository.license.name


def _build_analysis(
    *,
    repository: GitHubRepository,
    analyzed_at: datetime,
    languages: list[LanguageShare],
    contributor_records: list[stats.ContributorRecord] | None,
    contributors_count: int | None,
    total_commits: int,
    commit_stats: CommitStats,
    recent_commits: list[RecentCommit],
) -> Analysis:
    shares = stats.compute_contributor_shares(contributor_records or [])
    contributor_stats = stats.compute_contributor_stats(contributor_records)
    return Analysis(
        analyzed_at=analyzed_at,
        description=repository.description,
        homepage=repository.homepage or None,
        owner_avatar_url=repository.owner.avatar_url,
        default_branch=repository.default_branch,
        primary_language=repository.language,
        license=_license_label(repository),
        topics=list(repository.topics),
        is_fork=repository.fork,
        is_archived=repository.archived,
        stars=repository.stargazers_count,
        forks=repository.forks_count,
        open_issues=repository.open_issues_count,
        watchers=repository.subscribers_count,
        size_kb=repository.size,
        contributors_count=contributors_count,
        total_commits=total_commits,
        repo_created_at=repository.created_at,
        repo_updated_at=repository.updated_at,
        repo_pushed_at=repository.pushed_at,
        commits_analyzed=commit_stats.commits_analyzed,
        commits_last_30_days=commit_stats.recent_activity.commits_last_30_days,
        average_weekly_commits=commit_stats.average_weekly_commits,
        commit_stats=commit_stats.model_dump(mode="json"),
        contributor_stats=contributor_stats.model_dump(mode="json"),
        recent_commits=[c.model_dump(mode="json") for c in recent_commits],
        languages=[
            AnalysisLanguage(language=s.language, bytes=s.bytes, percentage=s.percentage)
            for s in languages
        ],
        contributors=[
            AnalysisContributor(
                rank=rank,
                login=s.login,
                contributions=s.contributions,
                percentage=s.percentage,
                avatar_url=s.avatar_url,
                html_url=s.html_url,
            )
            for rank, s in enumerate(shares, start=1)
        ],
    )
