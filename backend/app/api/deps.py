"""FastAPI dependencies.

Long-lived objects live on ``app.state`` and are created in the application lifespan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.github.client import GitHubClient
from app.services.analysis_service import AnalysisService, KeyedLocks
from app.services.analyzer import Clock, RepositoryAnalyzer


@dataclass
class AppResources:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    github: GitHubClient
    locks: KeyedLocks
    clock: Clock


def get_resources(request: Request) -> AppResources:
    resources: AppResources = request.app.state.resources
    return resources


Resources = Annotated[AppResources, Depends(get_resources)]


async def get_session(resources: Resources) -> AsyncIterator[AsyncSession]:
    async with resources.session_factory() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def get_analysis_service(resources: Resources, session: Session) -> AnalysisService:
    analyzer = RepositoryAnalyzer(resources.github, resources.settings, clock=resources.clock)
    return AnalysisService(
        session=session,
        analyzer=analyzer,
        settings=resources.settings,
        locks=resources.locks,
        clock=resources.clock,
    )


Service = Annotated[AnalysisService, Depends(get_analysis_service)]
