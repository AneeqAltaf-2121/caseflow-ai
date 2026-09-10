import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.document import Document, DocumentVersion

# Must match the `vector(...)` column width in the migration that created
# document_chunks, and Settings.embedding_dimensions (see config.py's
# comment on that field). Changing the embedding model's output size means
# a new migration to ALTER the column — not just changing this constant.
EMBEDDING_DIMENSIONS = 384


class DocumentChunk(Base):
    """A retrievable unit of text extracted from a document (see
    app/ingestion/chunker.py), with enough positional metadata to support
    citations back to the exact page/passage it came from.

    `embedding` starts NULL: a chunk exists as soon as it's chunked
    (Phase 10), and is populated once the embedding pipeline (Phase 13)
    processes it — the two are separate steps so partial embedding
    failures don't lose chunking work.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    # "metadata" is reserved on declarative models (Base.metadata) — the
    # column is still named `metadata` in the database (see the
    # migration); only the Python attribute is renamed, same pattern as
    # AuditEvent.event_metadata.
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_column()

    document: Mapped["Document"] = relationship()
    document_version: Mapped["DocumentVersion"] = relationship()

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} document={self.document_id} page={self.page_number}>"
