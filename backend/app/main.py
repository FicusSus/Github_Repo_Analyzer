"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.deps import AppResources
from app.api.errors import register_error_handlers
from app.api.routes import analyses, meta, repositories
from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory
from app.github.client import GitHubClient
from app.services.analysis_service import KeyedLocks
from app.services.analyzer import Clock, utc_clock

API_PREFIX = "/api"


def create_app(
    settings: Settings | None = None,
    *,
    github: GitHubClient | None = None,
    clock: Clock = utc_clock,
) -> FastAPI:
    """Build the application.

    ``github`` and ``clock`` can be injected by tests; production code relies on settings.
    """
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url)
        client = github or GitHubClient.from_settings(settings)
        app.state.resources = AppResources(
            settings=settings,
            session_factory=create_session_factory(engine),
            github=client,
            locks=KeyedLocks(),
            clock=clock,
        )
        if not client.authenticated:
            logging.getLogger(__name__).info(
                "No GITHUB_TOKEN configured: using the anonymous limit of 60 requests/hour."
            )
        try:
            yield
        finally:
            if github is None:
                await client.aclose()
            await engine.dispose()

    app = FastAPI(
        title="GitHub Repository Analyzer",
        version=__version__,
        description=(
            "Analyze public GitHub repositories: commit activity, languages, contributors and "
            "how these statistics change over time."
        ),
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    for router in (analyses.router, repositories.router, meta.router):
        app.include_router(router, prefix=API_PREFIX)
    return app
