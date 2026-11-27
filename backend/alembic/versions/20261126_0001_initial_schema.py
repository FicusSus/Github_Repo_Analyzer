"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-26 23:50:32.736590

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("full_name", sa.String(length=140), nullable=False),
        sa.Column("full_name_key", sa.String(length=140), nullable=False),
        sa.Column("owner", sa.String(length=39), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("html_url", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repositories")),
        sa.UniqueConstraint("full_name_key", name=op.f("uq_repositories_full_name_key")),
        sa.UniqueConstraint("github_id", name=op.f("uq_repositories_github_id")),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage", sa.String(length=500), nullable=True),
        sa.Column("owner_avatar_url", sa.String(length=500), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("primary_language", sa.String(length=100), nullable=True),
        sa.Column("license", sa.String(length=100), nullable=True),
        sa.Column(
            "topics",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("is_fork", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("forks", sa.Integer(), nullable=False),
        sa.Column("open_issues", sa.Integer(), nullable=False),
        sa.Column("watchers", sa.Integer(), nullable=True),
        sa.Column("size_kb", sa.Integer(), nullable=False),
        sa.Column("contributors_count", sa.Integer(), nullable=True),
        sa.Column("total_commits", sa.Integer(), nullable=True),
        sa.Column("repo_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("repo_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("repo_pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commits_analyzed", sa.Integer(), nullable=False),
        sa.Column("commits_last_30_days", sa.Integer(), nullable=False),
        sa.Column("average_weekly_commits", sa.Float(), nullable=False),
        sa.Column(
            "commit_stats",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "contributor_stats",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "recent_commits",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repositories.id"],
            name=op.f("fk_analyses_repository_id_repositories"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_index(op.f("ix_analyses_analyzed_at"), "analyses", ["analyzed_at"], unique=False)
    op.create_index(
        "ix_analyses_repository_id_analyzed_at",
        "analyses",
        ["repository_id", "analyzed_at"],
        unique=False,
    )
    op.create_table(
        "analysis_contributors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("contributions", sa.Integer(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("html_url", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_analysis_contributors_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_contributors")),
        sa.UniqueConstraint(
            "analysis_id", "login", name=op.f("uq_analysis_contributors_analysis_id_login")
        ),
    )
    op.create_table(
        "analysis_languages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=100), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_analysis_languages_analysis_id_analyses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_languages")),
        sa.UniqueConstraint(
            "analysis_id", "language", name=op.f("uq_analysis_languages_analysis_id_language")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("analysis_languages")
    op.drop_table("analysis_contributors")
    op.drop_index("ix_analyses_repository_id_analyzed_at", table_name="analyses")
    op.drop_index(op.f("ix_analyses_analyzed_at"), table_name="analyses")
    op.drop_table("analyses")
    op.drop_table("repositories")
