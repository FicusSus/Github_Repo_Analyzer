from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.analysis.statistics import CommitRecord, compute_commit_stats, compute_contributor_stats
from app.db.models import Analysis, AnalysisLanguage, Repository
from app.services.insights import build_comparison, build_history
from tests.factories import NOW


def analysis(
    full_name: str,
    *,
    weeks_back: int,
    analyzed_at: datetime = NOW,
    stars: int = 10,
    contributors: int | None = 3,
    languages: dict[str, float] | None = None,
) -> Analysis:
    commits = [
        CommitRecord(
            sha=f"{full_name}{w}",
            authored_at=analyzed_at - timedelta(weeks=w, hours=1),
            author_name="Ada",
            author_login="ada",
        )
        for w in range(weeks_back)
    ]
    stats = compute_commit_stats(
        commits,
        since=analyzed_at - timedelta(weeks=weeks_back),
        now=analyzed_at,
        window_days=7 * weeks_back,
        truncated=False,
    )
    owner, name = full_name.split("/")
    return Analysis(
        id=hash(full_name + str(analyzed_at)) % 10_000,
        repository=Repository(
            full_name=full_name, owner=owner, name=name, html_url=f"https://github.com/{full_name}"
        ),
        analyzed_at=analyzed_at,
        primary_language="Python",
        stars=stars,
        forks=1,
        open_issues=0,
        watchers=None,
        contributors_count=contributors,
        total_commits=100,
        commits_analyzed=stats.commits_analyzed,
        commits_last_30_days=stats.recent_activity.commits_last_30_days,
        average_weekly_commits=stats.average_weekly_commits,
        repo_created_at=datetime(2020, 1, 1, tzinfo=UTC),
        commit_stats=stats.model_dump(mode="json"),
        contributor_stats=compute_contributor_stats(None).model_dump(mode="json"),
        languages=[
            AnalysisLanguage(language=lang, bytes=1, percentage=pct)
            for lang, pct in (languages or {"Python": 100.0}).items()
        ],
    )


def test_comparison_aligns_weeks_with_gaps() -> None:
    long = analysis("org/long", weeks_back=8)
    short = analysis("org/short", weeks_back=3, languages={"Go": 60.0, "Python": 40.0})

    comparison = build_comparison([long, short])

    weeks = comparison.weekly_activity.weeks
    assert weeks == sorted(weeks)
    assert weeks[-1] == date(2026, 11, 23)
    long_series = comparison.weekly_activity.series["org/long"]
    short_series = comparison.weekly_activity.series["org/short"]
    assert len(long_series) == len(short_series) == len(weeks)
    assert short_series[0] is None  # before the short repository's window
    assert short_series[-1] is not None
    assert all(value is not None for value in long_series)

    rows = {row.language: row.shares for row in comparison.languages}
    assert list(rows) == ["Python", "Go"]  # ordered by highest share
    assert rows["Go"] == {"org/long": 0.0, "org/short": 60.0}
    assert comparison.repositories[1].bus_factor is None


def test_history_changes_handle_missing_values() -> None:
    first = analysis(
        "org/repo", weeks_back=4, analyzed_at=NOW - timedelta(days=30), stars=0, contributors=None
    )
    second = analysis("org/repo", weeks_back=4, stars=50, contributors=None)

    history = build_history([first, second])

    assert [p.stars for p in history.points] == [0, 50]
    assert history.changes["stars"].absolute == 50.0
    assert history.changes["stars"].percent is None  # growth from zero has no percentage
    assert history.changes["contributors_count"].first is None
    assert history.changes["watchers"].last is None


def test_history_requires_points() -> None:
    with pytest.raises(ValueError, match="at least one"):
        build_history([])
