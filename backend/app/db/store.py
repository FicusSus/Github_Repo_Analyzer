"""Data-access layer: every SQL query the application runs lives here."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from app.db.models import Analysis, Repository
from app.github.models import GitHubRepository


@dataclass(frozen=True, slots=True)
class RepositoryOverview:
    repository: Repository
    analyses_count: int
    first_analyzed_at: datetime
    last_analyzed_at: datetime
    latest: Analysis


def _with_children() -> tuple[ExecutableOption, ...]:
    return (
        selectinload(Analysis.repository),
        selectinload(Analysis.languages),
        selectinload(Analysis.contributors),
    )


class AnalysisStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- repositories

    async def get_repository_by_key(self, key: str) -> Repository | None:
        result = await self._session.execute(
            select(Repository).where(Repository.full_name_key == key.lower())
        )
        return result.scalar_one_or_none()

    async def upsert_repository(self, payload: GitHubRepository) -> Repository:
        """Insert or update a repository, matching on GitHub's immutable numeric id.

        Matching on the id (not the name) keeps history intact when a repository is renamed or
        transferred to another owner.
        """
        result = await self._session.execute(
            select(Repository).where(Repository.github_id == payload.id)
        )
        repository = result.scalar_one_or_none()
        key = payload.full_name.lower()

        if repository is None:
            # A *different* GitHub repository may have previously used this name (deleted and
            # recreated). Free the name so the unique constraint is not violated.
            stale = await self.get_repository_by_key(key)
            if stale is not None:
                stale.full_name_key = f"{key}#replaced-{stale.github_id}"
                await self._session.flush()
            repository = Repository(github_id=payload.id)
            self._session.add(repository)

        repository.full_name = payload.full_name
        repository.full_name_key = key
        repository.owner = payload.owner.login
        repository.name = payload.name
        repository.html_url = payload.html_url
        await self._session.flush()
        return repository

    async def list_repositories(
        self, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[RepositoryOverview], int]:
        stats = (
            select(
                Analysis.repository_id.label("repository_id"),
                func.count(Analysis.id).label("analyses_count"),
                func.min(Analysis.analyzed_at).label("first_analyzed_at"),
                func.max(Analysis.analyzed_at).label("last_analyzed_at"),
                func.max(Analysis.id).label("latest_id"),
            )
            .group_by(Analysis.repository_id)
            .subquery()
        )
        base = select(Repository, stats).join(stats, stats.c.repository_id == Repository.id)
        if search:
            base = base.where(Repository.full_name_key.contains(search.lower().strip()))

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            await self._session.execute(
                base.order_by(stats.c.last_analyzed_at.desc()).limit(limit).offset(offset)
            )
        ).all()

        latest_ids = [row.latest_id for row in rows]
        latest_by_id = {a.id: a for a in await self._get_many(latest_ids)}
        overviews = [
            RepositoryOverview(
                repository=row.Repository,
                analyses_count=int(row.analyses_count),
                first_analyzed_at=row.first_analyzed_at,
                last_analyzed_at=row.last_analyzed_at,
                latest=latest_by_id[row.latest_id],
            )
            for row in rows
        ]
        return overviews, int(total or 0)

    # ----------------------------------------------------------------- analyses

    async def add_analysis(self, analysis: Analysis) -> Analysis:
        self._session.add(analysis)
        await self._session.flush()
        return analysis

    async def get_analysis(self, analysis_id: int) -> Analysis | None:
        result = await self._session.execute(
            select(Analysis).where(Analysis.id == analysis_id).options(*_with_children())
        )
        return result.scalar_one_or_none()

    async def latest_analysis(self, repository_key: str) -> Analysis | None:
        result = await self._session.execute(
            select(Analysis)
            .join(Analysis.repository)
            .where(Repository.full_name_key == repository_key.lower())
            .order_by(Analysis.analyzed_at.desc(), Analysis.id.desc())
            .limit(1)
            .options(*_with_children())
        )
        return result.scalar_one_or_none()

    async def list_analyses(
        self, *, limit: int, offset: int, repository_key: str | None = None
    ) -> tuple[list[Analysis], int]:
        query = select(Analysis).join(Analysis.repository)
        if repository_key:
            query = query.where(Repository.full_name_key == repository_key.lower())
        total = await self._session.scalar(select(func.count()).select_from(query.subquery()))
        result = await self._session.execute(
            query.order_by(Analysis.analyzed_at.desc(), Analysis.id.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Analysis.repository))
        )
        return list(result.scalars().all()), int(total or 0)

    async def history(self, repository_key: str) -> list[Analysis]:
        result = await self._session.execute(
            select(Analysis)
            .join(Analysis.repository)
            .where(Repository.full_name_key == repository_key.lower())
            .order_by(Analysis.analyzed_at.asc(), Analysis.id.asc())
            .options(selectinload(Analysis.repository))
        )
        return list(result.scalars().all())

    async def delete_analysis(self, analysis_id: int) -> bool:
        analysis = await self._session.get(Analysis, analysis_id)
        if analysis is None:
            return False
        repository_id = analysis.repository_id
        await self._session.delete(analysis)
        await self._session.flush()
        remaining = await self._session.scalar(
            select(func.count(Analysis.id)).where(Analysis.repository_id == repository_id)
        )
        if not remaining:
            await self._session.execute(delete(Repository).where(Repository.id == repository_id))
        return True

    async def _get_many(self, ids: Sequence[int]) -> list[Analysis]:
        if not ids:
            return []
        result = await self._session.execute(
            select(Analysis).where(Analysis.id.in_(ids)).options(selectinload(Analysis.repository))
        )
        return list(result.scalars().all())
