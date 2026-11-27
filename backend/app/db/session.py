"""Async engine and session factory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    kwargs: dict[str, Any] = {}
    if database_url.startswith("postgresql"):
        kwargs.update(pool_size=10, max_overflow=10, pool_pre_ping=True)
    engine = create_async_engine(database_url, **kwargs)

    if engine.dialect.name == "sqlite":
        # SQLite (used for quick local test runs) ignores ON DELETE CASCADE unless enabled.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
