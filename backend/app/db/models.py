"""SQLAlchemy ORM models.

Scalars that are filtered, sorted or charted over time (stars, forks, contributor counts…) are
real columns; languages and contributors are normalised child tables so they can be compared
across analyses; derived time series are stored as JSON documents validated by Pydantic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONDocument = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime that always round-trips as UTC (also on SQLite)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use timezone-aware UTC values.")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    full_name: Mapped[str] = mapped_column(String(140))
    full_name_key: Mapped[str] = mapped_column(String(140), unique=True)
    owner: Mapped[str] = mapped_column(String(39))
    name: Mapped[str] = mapped_column(String(100))
    html_url: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Analysis.analyzed_at",
    )


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("ix_analyses_repository_id_analyzed_at", "repository_id", "analyzed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    analyzed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

    description: Mapped[str | None] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(String(500))
    owner_avatar_url: Mapped[str | None] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(255))
    primary_language: Mapped[str | None] = mapped_column(String(100))
    license: Mapped[str | None] = mapped_column(String(100))
    topics: Mapped[list[str]] = mapped_column(JSONDocument, default=list)
    is_fork: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    stars: Mapped[int] = mapped_column(Integer)
    forks: Mapped[int] = mapped_column(Integer)
    open_issues: Mapped[int] = mapped_column(Integer)
    watchers: Mapped[int | None] = mapped_column(Integer)
    size_kb: Mapped[int] = mapped_column(Integer)
    contributors_count: Mapped[int | None] = mapped_column(Integer)
    total_commits: Mapped[int | None] = mapped_column(Integer)

    repo_created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    repo_updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    repo_pushed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    commits_analyzed: Mapped[int] = mapped_column(Integer)
    commits_last_30_days: Mapped[int] = mapped_column(Integer)
    average_weekly_commits: Mapped[float] = mapped_column(Float)
    commit_stats: Mapped[dict[str, Any]] = mapped_column(JSONDocument)
    contributor_stats: Mapped[dict[str, Any]] = mapped_column(JSONDocument)
    recent_commits: Mapped[list[dict[str, Any]]] = mapped_column(JSONDocument, default=list)

    repository: Mapped[Repository] = relationship(back_populates="analyses")
    languages: Mapped[list[AnalysisLanguage]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnalysisLanguage.bytes.desc()",
    )
    contributors: Mapped[list[AnalysisContributor]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnalysisContributor.rank",
    )


class AnalysisLanguage(Base):
    __tablename__ = "analysis_languages"
    __table_args__ = (UniqueConstraint("analysis_id", "language"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(100))
    bytes: Mapped[int] = mapped_column(BigInteger)
    percentage: Mapped[float] = mapped_column(Float)

    analysis: Mapped[Analysis] = relationship(back_populates="languages")


class AnalysisContributor(Base):
    __tablename__ = "analysis_contributors"
    __table_args__ = (UniqueConstraint("analysis_id", "login"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    login: Mapped[str] = mapped_column(String(100))
    contributions: Mapped[int] = mapped_column(Integer)
    percentage: Mapped[float] = mapped_column(Float)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    html_url: Mapped[str | None] = mapped_column(String(500))

    analysis: Mapped[Analysis] = relationship(back_populates="contributors")


__all__ = [
    "Analysis",
    "AnalysisContributor",
    "AnalysisLanguage",
    "Base",
    "Repository",
]
