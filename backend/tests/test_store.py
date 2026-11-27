from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Analysis, AnalysisContributor, AnalysisLanguage, Repository
from app.db.store import AnalysisStore
from app.github.models import GitHubRepository
from tests.factories import NOW, repo_payload


def github_repo(
    owner: str = "octo-org", name: str = "octo-repo", repo_id: int = 1001
) -> GitHubRepository:
    return GitHubRepository.model_validate(repo_payload(owner, name, repo_id=repo_id))


def make_analysis(repository: Repository, *, analyzed_at: datetime, stars: int = 10) -> Analysis:
    return Analysis(
        repository=repository,
        analyzed_at=analyzed_at,
        default_branch="main",
        stars=stars,
        forks=1,
        open_issues=2,
        watchers=3,
        size_kb=100,
        contributors_count=4,
        total_commits=50,
        repo_created_at=datetime(2020, 1, 1, tzinfo=UTC),
        repo_updated_at=analyzed_at,
        repo_pushed_at=None,
        commits_analyzed=5,
        commits_last_30_days=2,
        average_weekly_commits=0.5,
        commit_stats={"placeholder": True},
        contributor_stats={"available": True},
        recent_commits=[],
        topics=["a"],
        languages=[AnalysisLanguage(language="Go", bytes=10, percentage=100.0)],
        contributors=[AnalysisContributor(rank=1, login="ada", contributions=4, percentage=100.0)],
    )


async def test_upsert_creates_and_updates(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    created = await store.upsert_repository(github_repo())
    again = await store.upsert_repository(github_repo())
    await session.commit()

    assert created.id == again.id
    assert created.full_name_key == "octo-org/octo-repo"
    assert await store.get_repository_by_key("OCTO-ORG/Octo-Repo") is not None


async def test_rename_keeps_history(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    original = await store.upsert_repository(github_repo())
    await store.add_analysis(make_analysis(original, analyzed_at=NOW - timedelta(days=1)))
    await session.commit()

    renamed = await store.upsert_repository(github_repo("new-org", "renamed"))
    await session.commit()

    assert renamed.id == original.id
    assert await store.get_repository_by_key("octo-org/octo-repo") is None
    assert len(await store.history("new-org/renamed")) == 1


async def test_recreated_repository_with_same_name(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    first = await store.upsert_repository(github_repo(repo_id=1))
    await store.add_analysis(make_analysis(first, analyzed_at=NOW - timedelta(days=5)))
    await session.commit()

    second = await store.upsert_repository(github_repo(repo_id=2))
    await session.commit()

    assert second.id != first.id
    resolved = await store.get_repository_by_key("octo-org/octo-repo")
    assert resolved is not None
    assert resolved.github_id == 2


async def test_timestamps_round_trip_as_utc(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    repository = await store.upsert_repository(github_repo())
    analyzed_at = datetime(2026, 5, 4, 3, 2, 1, tzinfo=UTC)
    analysis = await store.add_analysis(make_analysis(repository, analyzed_at=analyzed_at))
    await session.commit()
    session.expunge_all()

    loaded = await store.get_analysis(analysis.id)
    assert loaded is not None
    assert loaded.analyzed_at == analyzed_at
    assert loaded.analyzed_at.tzinfo is not None
    assert loaded.languages[0].language == "Go"
    assert loaded.contributors[0].login == "ada"
    assert loaded.commit_stats == {"placeholder": True}


async def test_list_history_and_latest(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    a = await store.upsert_repository(github_repo("org", "a", repo_id=1))
    b = await store.upsert_repository(github_repo("org", "b", repo_id=2))
    for days, stars in ((3, 10), (2, 20), (1, 30)):
        await store.add_analysis(
            make_analysis(a, analyzed_at=NOW - timedelta(days=days), stars=stars)
        )
    await store.add_analysis(make_analysis(b, analyzed_at=NOW - timedelta(hours=1), stars=99))
    await session.commit()

    items, total = await store.list_analyses(limit=2, offset=0)
    assert total == 4
    assert [i.repository.full_name for i in items] == ["org/b", "org/a"]

    filtered, filtered_total = await store.list_analyses(limit=10, offset=1, repository_key="ORG/A")
    assert filtered_total == 3
    assert [i.stars for i in filtered] == [20, 10]

    history = await store.history("org/a")
    assert [h.stars for h in history] == [10, 20, 30]

    latest = await store.latest_analysis("org/a")
    assert latest is not None
    assert latest.stars == 30
    assert await store.latest_analysis("org/missing") is None


async def test_list_repositories_aggregates(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    a = await store.upsert_repository(github_repo("org", "alpha", repo_id=1))
    b = await store.upsert_repository(github_repo("org", "beta", repo_id=2))
    await store.add_analysis(make_analysis(a, analyzed_at=NOW - timedelta(days=10), stars=1))
    await store.add_analysis(make_analysis(a, analyzed_at=NOW - timedelta(days=1), stars=2))
    await store.add_analysis(make_analysis(b, analyzed_at=NOW - timedelta(days=5), stars=7))
    await session.commit()

    overviews, total = await store.list_repositories(limit=10, offset=0)
    assert total == 2
    first = overviews[0]
    assert first.repository.full_name == "org/alpha"
    assert first.analyses_count == 2
    assert first.latest.stars == 2
    assert first.first_analyzed_at == NOW - timedelta(days=10)

    searched, searched_total = await store.list_repositories(limit=10, offset=0, search="BET")
    assert searched_total == 1
    assert searched[0].repository.full_name == "org/beta"


async def test_delete_cascades_and_removes_orphan_repository(session: AsyncSession) -> None:
    store = AnalysisStore(session)
    repository = await store.upsert_repository(github_repo())
    first = await store.add_analysis(make_analysis(repository, analyzed_at=NOW - timedelta(days=2)))
    second = await store.add_analysis(
        make_analysis(repository, analyzed_at=NOW - timedelta(days=1))
    )
    await session.commit()

    assert await store.delete_analysis(first.id) is True
    await session.commit()
    assert await store.get_repository_by_key("octo-org/octo-repo") is not None

    assert await store.delete_analysis(second.id) is True
    await session.commit()
    assert await store.get_repository_by_key("octo-org/octo-repo") is None
    assert await session.scalar(select(func.count(AnalysisLanguage.id))) == 0
    assert await session.scalar(select(func.count(AnalysisContributor.id))) == 0

    assert await store.delete_analysis(12345) is False
