"""Add document_chunks with pgvector embedding column

Revision ID: 0003_add_document_chunks_pgvector
Revises: 0002_add_document_versions
Create Date: 2026-09-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_document_chunks_pgvector"
down_revision: str | None = "0002_add_document_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match app.models.chunk.EMBEDDING_DIMENSIONS.
EMBEDDING_DIMENSIONS = 384


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # The vector extension and HNSW index are PostgreSQL-only (see ADR
    # 002) — SQLite runs this same migration for fast repository/
    # migration tests (tests/test_migrations.py) but obviously has no
    # pgvector extension, and doesn't need one: pgvector-python's Vector
    # type stores/reads a plain list of floats on any dialect, which is
    # all schema/CRUD tests need. Only similarity-ranked search needs a
    # real Postgres+pgvector database, and is tested against one directly.
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_chunks_document_version_id"),
        "document_chunks",
        ["document_version_id"],
        unique=False,
    )

    if _is_postgres():
        # HNSW over cosine distance — matches the `cosine_distance()`
        # comparator used by the retrieval repository (Phase 14). IVFFlat
        # was the other option considered (see ADR 002); HNSW needs no
        # training step and performs well at the corpus sizes this project
        # targets.
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_index(op.f("ix_document_chunks_document_version_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    # Deliberately not dropping the vector extension — other objects in
    # the database may depend on it, and CREATE EXTENSION IF NOT EXISTS
    # makes re-running upgrade() safe regardless.
