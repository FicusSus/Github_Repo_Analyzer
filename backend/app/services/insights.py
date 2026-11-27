"""Cross-analysis views: history of one repository and side-by-side comparison."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from app.analysis.models import CommitStats, ContributorStats
from app.db.models import Analysis
from app.schemas import (
    ComparedRepository,
    Comparison,
    LanguageComparisonRow,
    MetricChange,
    RepositoryHistory,
    WeeklyComparison,
    to_history_point,
)

HISTORY_METRICS = (
    "stars",
    "forks",
    "open_issues",
    "watchers",
    "contributors_count",
    "total_commits",
    "commits_last_30_days",
    "average_weekly_commits",
)
COMPARISON_WEEKS = 52


def build_history(analyses: Sequence[Analysis]) -> RepositoryHistory:
    if not analyses:
        raise ValueError("History requires at least one analysis.")
    points = [to_history_point(a) for a in analyses]
    frame = pd.DataFrame([p.model_dump() for p in points])

    changes: dict[str, MetricChange] = {}
    for metric in HISTORY_METRICS:
        values = frame[metric].dropna()
        if values.empty:
            changes[metric] = MetricChange(first=None, last=None, absolute=None, percent=None)
            continue
        first, last = float(values.iloc[0]), float(values.iloc[-1])
        changes[metric] = MetricChange(
            first=first,
            last=last,
            absolute=round(last - first, 2),
            percent=round((last - first) / first * 100, 2) if first else None,
        )

    latest = analyses[-1].repository
    return RepositoryHistory(
        full_name=latest.full_name, html_url=latest.html_url, points=points, changes=changes
    )


def build_comparison(analyses: Sequence[Analysis]) -> Comparison:
    repositories: list[ComparedRepository] = []
    language_shares: dict[str, dict[str, float]] = {}
    weekly_series: dict[str, pd.Series] = {}

    for analysis in analyses:
        name = analysis.repository.full_name
        commit_stats = CommitStats.model_validate(analysis.commit_stats)
        contributor_stats = ContributorStats.model_validate(analysis.contributor_stats)
        repositories.append(
            ComparedRepository(
                analysis_id=analysis.id,
                full_name=name,
                html_url=analysis.repository.html_url,
                analyzed_at=analysis.analyzed_at,
                primary_language=analysis.primary_language,
                stars=analysis.stars,
                forks=analysis.forks,
                open_issues=analysis.open_issues,
                contributors_count=analysis.contributors_count,
                total_commits=analysis.total_commits,
                commits_analyzed=analysis.commits_analyzed,
                average_weekly_commits=analysis.average_weekly_commits,
                commits_last_30_days=analysis.commits_last_30_days,
                days_since_last_commit=commit_stats.recent_activity.days_since_last_commit,
                bus_factor=contributor_stats.bus_factor,
                trend=commit_stats.trend.direction,
                repo_created_at=analysis.repo_created_at,
            )
        )
        for language in analysis.languages:
            language_shares.setdefault(language.language, {})[name] = language.percentage
        weekly_series[name] = pd.Series(
            {pd.Timestamp(b.period_start): b.commits for b in commit_stats.weekly},
            dtype="int64",
        )

    rows = [
        LanguageComparisonRow(
            language=language,
            shares={r.full_name: shares.get(r.full_name, 0.0) for r in repositories},
        )
        for language, shares in sorted(
            language_shares.items(), key=lambda item: (-max(item[1].values()), item[0])
        )
    ]

    return Comparison(
        repositories=repositories,
        languages=rows,
        weekly_activity=_align_weeks(weekly_series),
    )


def _align_weeks(series: dict[str, pd.Series]) -> WeeklyComparison:
    non_empty = {name: s for name, s in series.items() if not s.empty}
    if not non_empty:
        return WeeklyComparison(weeks=[], series={name: [] for name in series})
    frame = pd.concat(non_empty, axis=1).sort_index().tail(COMPARISON_WEEKS)
    aligned: dict[str, list[int | None]] = {}
    for name in series:
        if name not in frame:
            aligned[name] = [None] * len(frame)
            continue
        column = frame[name]
        aligned[name] = [None if pd.isna(v) else int(v) for v in column.tolist()]
    return WeeklyComparison(weeks=[ts.date() for ts in frame.index], series=aligned)
