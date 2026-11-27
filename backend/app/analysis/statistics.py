"""Pure statistics functions built on pandas.

Everything here is deterministic given its inputs (``now`` is always passed in), which keeps
the calculations easy to unit-test without touching the network or the database.

Conventions:
* all timestamps are converted to naive UTC internally and returned as aware UTC;
* weeks start on Monday 00:00 UTC, months on the 1st;
* the current week/month is partial and is excluded from trend detection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from app.analysis.models import (
    ActiveAuthor,
    AverageBucket,
    CommitStats,
    CommitTrend,
    ContributorShare,
    ContributorStats,
    CountBucket,
    LanguageShare,
    RecentActivity,
    TrendDirection,
)

TREND_WINDOW_WEEKS = 12
TREND_MIN_WEEKS = 4
TREND_MIN_COMMITS = 20
"""Below this many commits in the trend window, week-to-week noise dominates any slope."""
TREND_RELATIVE_THRESHOLD = 0.2
ROLLING_WINDOW_WEEKS = 4
TOP_AUTHORS = 10


@dataclass(frozen=True, slots=True)
class CommitRecord:
    sha: str
    authored_at: datetime
    author_name: str
    author_login: str | None


@dataclass(frozen=True, slots=True)
class ContributorRecord:
    login: str
    contributions: int
    avatar_url: str | None = None
    html_url: str | None = None


def is_bot(login: str | None) -> bool:
    return bool(login) and str(login).lower().endswith("[bot]")


# --------------------------------------------------------------------------- commits


def compute_commit_stats(
    commits: Sequence[CommitRecord],
    *,
    since: datetime,
    now: datetime,
    window_days: int,
    truncated: bool,
) -> CommitStats:
    now_ts = _to_naive_utc(now)
    since_ts = _to_naive_utc(since)
    frame = _commits_frame(commits, upper_bound=now_ts)

    effective_since_ts = _effective_since(frame, since_ts, now_ts, truncated=truncated)
    frame = frame[frame["authored_at"] >= effective_since_ts]

    weekly = _weekly_counts(frame, effective_since_ts, now_ts)
    monthly = _monthly_counts(frame, effective_since_ts, now_ts)
    rolling = weekly.rolling(ROLLING_WINDOW_WEEKS, min_periods=1).mean().round(2)

    by_weekday = (
        frame["authored_at"].dt.day_of_week.value_counts().reindex(range(7), fill_value=0)
        if not frame.empty
        else pd.Series([0] * 7)
    )

    return CommitStats(
        window_days=window_days,
        since=_to_aware(since_ts),
        effective_since=_to_aware(effective_since_ts),
        commits_analyzed=len(frame),
        truncated=truncated,
        average_weekly_commits=round(float(weekly.mean()), 2) if len(weekly) else 0.0,
        weekly=[CountBucket(period_start=d, commits=int(v)) for d, v in _dated(weekly)],
        monthly=[CountBucket(period_start=d, commits=int(v)) for d, v in _dated(monthly)],
        rolling_weekly_average=[
            AverageBucket(period_start=d, value=float(v)) for d, v in _dated(rolling)
        ],
        by_weekday=[int(v) for v in by_weekday.tolist()],
        trend=_trend(weekly.iloc[:-1]),  # last bucket is the current, incomplete week
        active_authors=_active_authors(frame),
        recent_activity=_recent_activity(frame, now_ts),
    )


def _commits_frame(commits: Sequence[CommitRecord], *, upper_bound: pd.Timestamp) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "sha": pd.Series([c.sha for c in commits], dtype="str"),
            "authored_at": pd.to_datetime([c.authored_at for c in commits], utc=True),
            "author_name": pd.Series([c.author_name for c in commits], dtype="str"),
            "author_login": pd.Series([c.author_login for c in commits], dtype="object"),
        }
    )
    frame["authored_at"] = frame["authored_at"].dt.tz_convert(None)
    # Commits with clock-skewed future dates are counted as "now" rather than dropped.
    frame["authored_at"] = frame["authored_at"].where(
        frame["authored_at"] <= upper_bound, upper_bound
    )
    frame = frame.drop_duplicates(subset="sha")
    identity = frame["author_login"].where(
        frame["author_login"].notna(), "name:" + frame["author_name"].str.strip().str.lower()
    )
    frame["identity"] = identity
    return frame


def _effective_since(
    frame: pd.DataFrame, since: pd.Timestamp, now: pd.Timestamp, *, truncated: bool
) -> pd.Timestamp:
    """When the commit list was cut by the page cap, older weeks would look artificially empty.

    In that case analysis starts at the first *complete* week we have data for.
    """
    if not truncated or frame.empty:
        return since
    oldest = frame["authored_at"].min()
    next_week = _week_start(oldest) + pd.Timedelta(days=7)
    candidate = next_week if next_week <= _week_start(now) else oldest
    return max(since, candidate)


def _week_start(ts: pd.Timestamp) -> pd.Timestamp:
    return (ts - pd.Timedelta(days=ts.day_of_week)).normalize()


def _weekly_counts(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    index = pd.date_range(_week_start(start), _week_start(end), freq="7D")
    if frame.empty:
        return pd.Series(0, index=index, dtype="int64")
    weeks = frame["authored_at"].dt.normalize() - pd.to_timedelta(
        frame["authored_at"].dt.day_of_week, unit="D"
    )
    counts: pd.Series = weeks.value_counts().reindex(index, fill_value=0).astype("int64")
    return counts.sort_index()


def _monthly_counts(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    index = pd.date_range(start.to_period("M").start_time, end.to_period("M").start_time, freq="MS")
    if frame.empty:
        return pd.Series(0, index=index, dtype="int64")
    months = frame["authored_at"].dt.to_period("M").dt.start_time
    counts: pd.Series = months.value_counts().reindex(index, fill_value=0).astype("int64")
    return counts.sort_index()


def _trend(weekly_complete: pd.Series) -> CommitTrend:
    values = weekly_complete.to_numpy(dtype=float)
    last_4 = int(values[-4:].sum()) if len(values) else 0
    previous_4 = int(values[-8:-4].sum()) if len(values) > 4 else 0
    change = round((last_4 - previous_4) / previous_4 * 100, 2) if previous_4 else None

    window = values[-TREND_WINDOW_WEEKS:]
    if len(window) < TREND_MIN_WEEKS or 0 < window.sum() < TREND_MIN_COMMITS:
        return CommitTrend(
            direction=TrendDirection.INSUFFICIENT_DATA,
            slope_per_week=0.0,
            last_4_weeks=last_4,
            previous_4_weeks=previous_4,
            change_percent=change,
        )

    slope = float(np.polyfit(np.arange(len(window)), window, 1)[0])
    mean = float(window.mean())
    if mean == 0:
        direction = TrendDirection.STABLE
    else:
        relative_change = slope * (len(window) - 1) / mean
        if relative_change > TREND_RELATIVE_THRESHOLD:
            direction = TrendDirection.INCREASING
        elif relative_change < -TREND_RELATIVE_THRESHOLD:
            direction = TrendDirection.DECREASING
        else:
            direction = TrendDirection.STABLE

    return CommitTrend(
        direction=direction,
        slope_per_week=round(slope, 3),
        last_4_weeks=last_4,
        previous_4_weeks=previous_4,
        change_percent=change,
    )


def _active_authors(frame: pd.DataFrame) -> list[ActiveAuthor]:
    if frame.empty:
        return []
    total = len(frame)
    grouped = (
        frame.groupby("identity")
        .agg(
            commits=("sha", "size"),
            first=("authored_at", "min"),
            last=("authored_at", "max"),
            login=("author_login", "first"),
            name=("author_name", lambda names: names.mode().iat[0]),
        )
        .sort_values(["commits", "last"], ascending=[False, False])
        .head(TOP_AUTHORS)
    )
    authors: list[ActiveAuthor] = []
    for name, login, commits, first, last in zip(
        grouped["name"].tolist(),
        grouped["login"].tolist(),
        grouped["commits"].tolist(),
        grouped["first"].tolist(),
        grouped["last"].tolist(),
        strict=True,
    ):
        login_value = login if isinstance(login, str) else None
        authors.append(
            ActiveAuthor(
                name=str(name),
                login=login_value,
                is_bot=is_bot(login_value),
                commits=int(commits),
                percentage=round(int(commits) / total * 100, 2),
                first_commit_at=_to_aware(first),
                last_commit_at=_to_aware(last),
            )
        )
    return authors


def _recent_activity(frame: pd.DataFrame, now: pd.Timestamp) -> RecentActivity:
    if frame.empty:
        return RecentActivity(
            last_commit_at=None,
            days_since_last_commit=None,
            commits_last_7_days=0,
            commits_last_30_days=0,
            active_authors_last_30_days=0,
        )
    last = frame["authored_at"].max()
    last_30 = frame[frame["authored_at"] > now - pd.Timedelta(days=30)]
    last_7 = frame[frame["authored_at"] > now - pd.Timedelta(days=7)]
    return RecentActivity(
        last_commit_at=_to_aware(last),
        days_since_last_commit=int((now - last).days),
        commits_last_7_days=len(last_7),
        commits_last_30_days=len(last_30),
        active_authors_last_30_days=int(last_30["identity"].nunique()),
    )


# --------------------------------------------------------------------------- contributors


def compute_contributor_shares(contributors: Sequence[ContributorRecord]) -> list[ContributorShare]:
    total = sum(c.contributions for c in contributors)
    ordered = sorted(contributors, key=lambda c: (-c.contributions, c.login.lower()))
    return [
        ContributorShare(
            login=c.login,
            is_bot=is_bot(c.login),
            contributions=c.contributions,
            percentage=round(c.contributions / total * 100, 2) if total else 0.0,
            avatar_url=c.avatar_url,
            html_url=c.html_url,
        )
        for c in ordered
    ]


def compute_contributor_stats(contributors: Sequence[ContributorRecord] | None) -> ContributorStats:
    if contributors is None:
        return ContributorStats(
            available=False,
            listed=0,
            total_contributions=0,
            top_contributor_share=None,
            top_5_share=None,
            gini_coefficient=None,
            bus_factor=None,
        )
    counts = pd.Series([c.contributions for c in contributors], dtype="int64")
    counts = counts[counts > 0].sort_values(ascending=False, ignore_index=True)
    total = int(counts.sum())
    if total == 0:
        return ContributorStats(
            available=True,
            listed=len(contributors),
            total_contributions=0,
            top_contributor_share=None,
            top_5_share=None,
            gini_coefficient=None,
            bus_factor=None,
        )
    shares = counts / total
    cumulative = shares.cumsum()
    bus_factor = int((cumulative < 0.5).sum()) + 1
    return ContributorStats(
        available=True,
        listed=len(contributors),
        total_contributions=total,
        top_contributor_share=round(float(shares.iloc[0]) * 100, 2),
        top_5_share=round(float(shares.head(5).sum()) * 100, 2),
        gini_coefficient=round(gini_coefficient(counts.to_numpy()), 4),
        bus_factor=bus_factor,
    )


def gini_coefficient(values: Sequence[float] | np.ndarray) -> float:
    """Gini coefficient of non-negative values (0 for empty input or a single value)."""
    array = np.sort(np.asarray(values, dtype=float))
    n = array.size
    total = array.sum()
    if n <= 1 or total == 0:
        return 0.0
    ranks = np.arange(1, n + 1)
    return float((2 * np.sum(ranks * array)) / (n * total) - (n + 1) / n)


# --------------------------------------------------------------------------- languages


def compute_language_shares(languages: Mapping[str, int]) -> list[LanguageShare]:
    series = pd.Series(languages, dtype="int64")
    series = series[series > 0]
    total = int(series.sum())
    if total == 0:
        return []
    ordered = series.sort_values(ascending=False, kind="stable")
    return [
        LanguageShare(language=str(name), bytes=int(size), percentage=round(size / total * 100, 2))
        for name, size in ordered.items()
    ]


# --------------------------------------------------------------------------- helpers


def _dated(series: pd.Series) -> list[tuple[date, float]]:
    return [
        (ts.date(), float(value))
        for ts, value in zip(pd.DatetimeIndex(series.index), series.tolist(), strict=True)
    ]


def _to_naive_utc(value: datetime | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _to_aware(value: pd.Timestamp | datetime) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    result: datetime = ts.to_pydatetime()
    return result


def window_start(now: datetime, window_days: int) -> datetime:
    return now.astimezone(UTC) - timedelta(days=window_days)
