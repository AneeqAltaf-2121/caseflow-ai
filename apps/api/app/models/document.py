import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.project import Project


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    """A logical document within a project.

    Only metadata + a pointer to its current version live here — file bytes
    live in object storage (see app/integrations/storage.py), and each
    upload/re-upload gets its own immutable DocumentVersion so history isn't
    destroyed. DocumentChunk is added in Phase 8 once ingestion exists.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SqlEnum(DocumentStatus, native_enum=False, length=20),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    project: Mapped["Project"] = relationship()
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename!r} status={self.status}>"


class DocumentVersion(Base):
    """An immutable version of a document's underlying file.

    Re-uploading a document creates a new version rather than overwriting
    the old one, so ingestion/citations can keep pointing at the exact
    bytes they were computed from.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    document: Mapped["Document"] = relationship(back_populates="versions")

    def __repr__(self) -> str:
        return f"<DocumentVersion document={self.document_id} version={self.version_number}>"
