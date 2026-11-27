"""Use cases exposed by the HTTP API: analyze, list, inspect, compare, track history."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Analysis
from app.db.store import AnalysisStore, RepositoryOverview
from app.errors import AnalysisNotFoundError, InvalidComparisonError, RepositoryNotTrackedError
from app.github.url import RepositoryRef, parse_repository_ref
from app.schemas import Comparison, RepositoryHistory
from app.services.analyzer import Clock, RepositoryAnalyzer, utc_clock
from app.services.insights import build_comparison, build_history

logger = logging.getLogger(__name__)

MIN_COMPARED = 2
MAX_COMPARED = 5


@dataclass
class KeyedLocks:
    """One asyncio lock per repository so concurrent requests for the same repo do the
    GitHub work once and the second request is served from the fresh stored result."""

    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _waiters: dict[str, int] = field(default_factory=dict)

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._waiters[key] = self._waiters.get(key, 0) + 1
        try:
            async with lock:
                yield
        finally:
            self._waiters[key] -= 1
            if self._waiters[key] == 0:
                del self._waiters[key]
                del self._locks[key]


@dataclass(frozen=True, slots=True)
class AnalyzeOutcome:
    analysis: Analysis
    from_cache: bool


class AnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        analyzer: RepositoryAnalyzer,
        settings: Settings,
        locks: KeyedLocks,
        clock: Clock = utc_clock,
    ) -> None:
        self._session = session
        self._store = AnalysisStore(session)
        self._analyzer = analyzer
        self._settings = settings
        self._locks = locks
        self._clock = clock

    async def analyze(self, raw_reference: str, *, force: bool = False) -> AnalyzeOutcome:
        ref = parse_repository_ref(raw_reference)
        async with self._locks.hold(ref.key):
            if not force:
                cached = await self._fresh_analysis(ref)
                if cached is not None:
                    return AnalyzeOutcome(analysis=cached, from_cache=True)
            # Do not keep a database transaction open while waiting on GitHub.
            await self._session.commit()

            result = await self._analyzer.analyze(ref)

            repository = await self._store.upsert_repository(result.repository)
            result.analysis.repository = repository
            await self._store.add_analysis(result.analysis)
            await self._session.commit()
            logger.info(
                "Analyzed %s: %d commits, %d languages",
                repository.full_name,
                result.analysis.commits_analyzed,
                len(result.analysis.languages),
            )

        stored = await self._store.get_analysis(result.analysis.id)
        if stored is None:  # pragma: no cover - deleted concurrently right after commit
            raise AnalysisNotFoundError(f"Analysis {result.analysis.id} disappeared.")
        return AnalyzeOutcome(analysis=stored, from_cache=False)

    async def get(self, analysis_id: int) -> Analysis:
        analysis = await self._store.get_analysis(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"Analysis {analysis_id} does not exist.")
        return analysis

    async def latest(self, owner: str, name: str) -> Analysis:
        ref = parse_repository_ref(f"{owner}/{name}")
        analysis = await self._store.latest_analysis(ref.key)
        if analysis is None:
            raise RepositoryNotTrackedError(
                f"{ref.full_name} has not been analyzed yet.", details={"repository": ref.full_name}
            )
        return analysis

    async def list_analyses(
        self, *, limit: int, offset: int, repository: str | None = None
    ) -> tuple[list[Analysis], int]:
        key = parse_repository_ref(repository).key if repository else None
        return await self._store.list_analyses(limit=limit, offset=offset, repository_key=key)

    async def delete(self, analysis_id: int) -> None:
        if not await self._store.delete_analysis(analysis_id):
            raise AnalysisNotFoundError(f"Analysis {analysis_id} does not exist.")
        await self._session.commit()

    async def repositories(
        self, *, limit: int, offset: int, search: str | None = None
    ) -> tuple[list[RepositoryOverview], int]:
        return await self._store.list_repositories(limit=limit, offset=offset, search=search)

    async def history(self, owner: str, name: str) -> RepositoryHistory:
        ref = parse_repository_ref(f"{owner}/{name}")
        analyses = await self._store.history(ref.key)
        if not analyses:
            raise RepositoryNotTrackedError(
                f"{ref.full_name} has not been analyzed yet.", details={"repository": ref.full_name}
            )
        return build_history(analyses)

    async def compare(self, references: Sequence[str]) -> Comparison:
        refs: dict[str, RepositoryRef] = {}
        for raw in references:
            ref = parse_repository_ref(raw)
            refs.setdefault(ref.key, ref)
        if not MIN_COMPARED <= len(refs) <= MAX_COMPARED:
            raise InvalidComparisonError(
                f"Select between {MIN_COMPARED} and {MAX_COMPARED} different repositories.",
                details={"received": len(refs)},
            )

        analyses: list[Analysis] = []
        missing: list[str] = []
        for key, ref in refs.items():
            latest = await self._store.latest_analysis(key)
            if latest is None:
                missing.append(ref.full_name)
            else:
                analyses.append(latest)
        if missing:
            raise RepositoryNotTrackedError(
                "Some repositories have not been analyzed yet: " + ", ".join(missing),
                details={"missing": missing},
            )
        return build_comparison(analyses)

    async def _fresh_analysis(self, ref: RepositoryRef) -> Analysis | None:
        ttl = self._settings.analysis_cache_ttl_seconds
        if ttl <= 0:
            return None
        latest = await self._store.latest_analysis(ref.key)
        if latest is None:
            return None
        if self._clock() - latest.analyzed_at <= timedelta(seconds=ttl):
            return latest
        return None
