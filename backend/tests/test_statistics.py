from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.analysis.models import TrendDirection
from app.analysis.statistics import (
    CommitRecord,
    ContributorRecord,
    compute_commit_stats,
    compute_contributor_shares,
    compute_contributor_stats,
    compute_language_shares,
    gini_coefficient,
)

# Thursday. The current week starts on Monday 2026-11-23.
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def commit(sha: str, when: datetime, name: str = "Ada", login: str | None = "ada") -> CommitRecord:
    return CommitRecord(sha=sha, authored_at=when, author_name=name, author_login=login)


def weekly_series(counts_oldest_first: list[int]) -> list[CommitRecord]:
    """One block of commits per week ending with the current (partial) week."""
    commits: list[CommitRecord] = []
    weeks = len(counts_oldest_first)
    current_week_start = datetime(2026, 11, 23, tzinfo=UTC)
    for index, count in enumerate(counts_oldest_first):
        week_start = current_week_start - timedelta(weeks=weeks - 1 - index)
        commits.extend(
            commit(f"{index}-{n}", week_start + timedelta(days=1, hours=n)) for n in range(count)
        )
    return commits


def window_for(weeks: int) -> int:
    """Window whose start (Monday 12:00) lies in the first week produced by weekly_series."""
    return 7 * (weeks - 1) + 3


def stats_for(commits: list[CommitRecord], *, window_days: int = 365, truncated: bool = False):  # type: ignore[no-untyped-def]
    return compute_commit_stats(
        commits,
        since=NOW - timedelta(days=window_days),
        now=NOW,
        window_days=window_days,
        truncated=truncated,
    )


class TestCommitBuckets:
    def test_weeks_and_months_are_zero_filled(self) -> None:
        commits = [
            commit("a", datetime(2026, 11, 24, 9, tzinfo=UTC)),
            commit("b", datetime(2026, 11, 25, 9, tzinfo=UTC)),
            commit("c", datetime(2026, 11, 3, 9, tzinfo=UTC)),
            commit("d", datetime(2026, 10, 1, 9, tzinfo=UTC)),
        ]
        stats = stats_for(commits, window_days=60)

        weeks = {b.period_start: b.commits for b in stats.weekly}
        assert weeks[date(2026, 11, 23)] == 2
        assert weeks[date(2026, 11, 2)] == 1
        assert weeks[date(2026, 11, 16)] == 0
        assert weeks[date(2026, 9, 28)] == 1
        assert all(b.period_start.weekday() == 0 for b in stats.weekly)
        assert stats.weekly[-1].period_start == date(2026, 11, 23)

        months = [(b.period_start, b.commits) for b in stats.monthly]
        assert months == [(date(2026, 9, 1), 0), (date(2026, 10, 1), 1), (date(2026, 11, 1), 3)]
        assert sum(stats.by_weekday) == 4
        assert stats.commits_analyzed == 4
        assert stats.average_weekly_commits == round(4 / len(stats.weekly), 2)

    def test_commits_outside_window_and_duplicates_are_ignored(self) -> None:
        commits = [
            commit("a", NOW - timedelta(days=2)),
            commit("a", NOW - timedelta(days=2)),
            commit("old", NOW - timedelta(days=400)),
        ]
        stats = stats_for(commits)
        assert stats.commits_analyzed == 1

    def test_future_dates_are_clamped_to_now(self) -> None:
        stats = stats_for([commit("skewed", NOW + timedelta(days=3))])
        assert stats.weekly[-1].commits == 1
        assert stats.recent_activity.days_since_last_commit == 0

    def test_weekday_distribution(self) -> None:
        monday = datetime(2026, 11, 16, 10, tzinfo=UTC)
        sunday = datetime(2026, 11, 22, 10, tzinfo=UTC)
        stats = stats_for([commit("m", monday), commit("s1", sunday), commit("s2", sunday)])
        assert stats.by_weekday == [1, 0, 0, 0, 0, 0, 2]

    def test_rolling_average(self) -> None:
        stats = stats_for(weekly_series([4, 0, 8, 4, 2]), window_days=window_for(5))
        assert [b.commits for b in stats.weekly] == [4, 0, 8, 4, 2]
        values = [b.value for b in stats.rolling_weekly_average][-3:]
        assert values == [4.0, 4.0, 3.5]

    def test_no_commits(self) -> None:
        stats = stats_for([])
        assert stats.commits_analyzed == 0
        assert all(b.commits == 0 for b in stats.weekly)
        assert stats.active_authors == []
        assert stats.recent_activity.last_commit_at is None
        assert stats.trend.direction == TrendDirection.STABLE
        assert stats.by_weekday == [0] * 7


class TestTruncation:
    def test_truncated_history_starts_at_first_complete_week(self) -> None:
        # Oldest fetched commit is on Wednesday 2026-10-14 -> its week is partial.
        commits = [
            commit("new", datetime(2026, 11, 24, tzinfo=UTC)),
            commit("old", datetime(2026, 10, 14, tzinfo=UTC)),
        ]
        stats = stats_for(commits, truncated=True)
        assert stats.truncated is True
        assert stats.effective_since == datetime(2026, 10, 19, tzinfo=UTC)
        assert stats.weekly[0].period_start == date(2026, 10, 19)
        assert stats.commits_analyzed == 1

    def test_not_truncated_keeps_requested_window(self) -> None:
        stats = stats_for([commit("x", NOW - timedelta(days=3))], window_days=30)
        assert stats.effective_since == NOW - timedelta(days=30)

    def test_truncated_within_current_week_keeps_oldest_commit(self) -> None:
        commits = [commit("a", datetime(2026, 11, 23, 8, tzinfo=UTC)), commit("b", NOW)]
        stats = stats_for(commits, truncated=True)
        assert stats.effective_since == datetime(2026, 11, 23, 8, tzinfo=UTC)
        assert stats.commits_analyzed == 2


class TestTrend:
    @pytest.mark.parametrize(
        ("counts", "direction"),
        [
            ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 0], TrendDirection.INCREASING),
            ([10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0], TrendDirection.DECREASING),
            ([5, 5, 6, 5, 4, 5, 5, 6, 5, 5, 0], TrendDirection.STABLE),
            ([3, 3, 0], TrendDirection.INSUFFICIENT_DATA),
            # Sparse, bursty activity: too few commits for the slope to mean anything.
            ([0, 1, 0, 0, 0, 5, 0, 0, 4, 0, 0, 0, 0], TrendDirection.INSUFFICIENT_DATA),
        ],
    )
    def test_direction(self, counts: list[int], direction: TrendDirection) -> None:
        stats = stats_for(weekly_series(counts), window_days=window_for(len(counts)))
        assert stats.trend.direction == direction

    def test_current_partial_week_is_excluded(self) -> None:
        # A steady 5/week followed by a nearly empty current week must not look like decline.
        stats = stats_for(weekly_series([5] * 10 + [1]), window_days=window_for(11))
        assert stats.trend.direction == TrendDirection.STABLE
        assert stats.trend.last_4_weeks == 20
        assert stats.trend.previous_4_weeks == 20
        assert stats.trend.change_percent == 0.0

    def test_change_percent_is_null_without_previous_activity(self) -> None:
        stats = stats_for(weekly_series([0, 0, 0, 0, 1, 2, 3, 4, 0]), window_days=window_for(9))
        assert stats.trend.previous_4_weeks == 0
        assert stats.trend.change_percent is None


class TestAuthors:
    def test_groups_by_login_and_falls_back_to_name(self) -> None:
        commits = [
            commit("1", NOW - timedelta(days=1), name="Ada L.", login="ada"),
            commit("2", NOW - timedelta(days=2), name="Ada Lovelace", login="ada"),
            commit("3", NOW - timedelta(days=3), name="Ada Lovelace", login="ada"),
            commit("4", NOW - timedelta(days=40), name="Anon Dev", login=None),
            commit("5", NOW - timedelta(days=41), name="anon dev ", login=None),
            commit("6", NOW - timedelta(days=5), name="dependabot[bot]", login="dependabot[bot]"),
        ]
        authors = stats_for(commits).active_authors

        assert [(a.login, a.commits) for a in authors] == [
            ("ada", 3),
            (None, 2),
            ("dependabot[bot]", 1),
        ]
        assert authors[0].name == "Ada Lovelace"
        assert authors[0].percentage == 50.0
        assert authors[0].last_commit_at == NOW - timedelta(days=1)
        assert authors[2].is_bot is True
        assert authors[0].is_bot is False

    def test_recent_activity(self) -> None:
        commits = [
            commit("1", NOW - timedelta(days=1), login="ada"),
            commit("2", NOW - timedelta(days=6), login="grace", name="Grace"),
            commit("3", NOW - timedelta(days=20), login="linus", name="Linus"),
            commit("4", NOW - timedelta(days=45), login="ken", name="Ken"),
        ]
        activity = stats_for(commits).recent_activity
        assert activity.commits_last_7_days == 2
        assert activity.commits_last_30_days == 3
        assert activity.active_authors_last_30_days == 3
        assert activity.days_since_last_commit == 1


class TestContributors:
    def test_shares_are_sorted_and_flag_bots(self) -> None:
        shares = compute_contributor_shares(
            [
                ContributorRecord("bob", 25),
                ContributorRecord("alice", 75),
                ContributorRecord("renovate[bot]", 0),
            ]
        )
        assert [(s.login, s.percentage) for s in shares] == [
            ("alice", 75.0),
            ("bob", 25.0),
            ("renovate[bot]", 0.0),
        ]
        assert shares[-1].is_bot is True

    def test_stats(self) -> None:
        stats = compute_contributor_stats(
            [ContributorRecord(f"u{i}", c) for i, c in enumerate([40, 30, 10, 10, 5, 5])]
        )
        assert stats.available is True
        assert stats.total_contributions == 100
        assert stats.top_contributor_share == 40.0
        assert stats.top_5_share == 95.0
        assert stats.bus_factor == 2
        assert stats.gini_coefficient is not None
        assert 0 < stats.gini_coefficient < 1

    def test_single_dominant_contributor(self) -> None:
        stats = compute_contributor_stats(
            [ContributorRecord("solo", 900), ContributorRecord("drive-by", 1)]
        )
        assert stats.bus_factor == 1

    def test_unavailable(self) -> None:
        stats = compute_contributor_stats(None)
        assert stats.available is False
        assert stats.bus_factor is None

    def test_empty_list(self) -> None:
        stats = compute_contributor_stats([])
        assert stats.available is True
        assert stats.total_contributions == 0
        assert stats.gini_coefficient is None


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], 0.0),
        ([7], 0.0),
        ([5, 5, 5, 5], 0.0),
        ([0, 0, 0, 10], 0.75),
        ([1, 2, 3, 4], 0.25),
    ],
)
def test_gini_coefficient(values: list[float], expected: float) -> None:
    assert gini_coefficient(values) == pytest.approx(expected)


def test_language_shares() -> None:
    shares = compute_language_shares({"Shell": 250, "Python": 700, "Makefile": 50, "Empty": 0})
    assert [(s.language, s.percentage) for s in shares] == [
        ("Python", 70.0),
        ("Shell", 25.0),
        ("Makefile", 5.0),
    ]
    assert compute_language_shares({}) == []
