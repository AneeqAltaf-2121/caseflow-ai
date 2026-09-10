import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentStatus, DocumentVersion


class DocumentRepository:
    """Data access for Document and DocumentVersion. No authorization or
    storage-backend calls here — see app/services/document_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
        checksum_sha256: str,
        storage_key: str,
        uploaded_by: uuid.UUID,
    ) -> Document:
        document = Document(
            project_id=project_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            status=DocumentStatus.UPLOADED,
        )
        self._session.add(document)
        await self._session.flush()

        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
        )
        self._session.add(version)
        await self._session.flush()
        return document

    async def add_version(
        self, *, document: Document, storage_key: str, checksum_sha256: str
    ) -> DocumentVersion:
        """Record a re-upload as a new version and point the document at it."""
        next_version_number = len(document.versions) + 1
        version = DocumentVersion(
            document_id=document.id,
            version_number=next_version_number,
            storage_key=storage_key,
            checksum_sha256=checksum_sha256,
        )
        self._session.add(version)
        document.storage_key = storage_key
        document.checksum_sha256 = checksum_sha256
        document.status = DocumentStatus.UPLOADED
        await self._session.flush()
        return version

    async def get_by_checksum(
        self, *, project_id: uuid.UUID, checksum_sha256: str
    ) -> Document | None:
        """Phase 35 duplicate-upload detection: is a document with this
        exact content (by its *current* version's checksum) already in
        this project? Used to reject an accidental double-submit before
        it spends a storage write and a duplicate ingestion job."""
        result = await self._session.execute(
            select(Document).where(
                Document.project_id == project_id, Document.checksum_sha256 == checksum_sha256
            )
        )
        return result.scalars().first()

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        result = await self._session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.versions))
        )
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[Document]:
        result = await self._session.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(self, document: Document, status: DocumentStatus) -> Document:
        document.status = status
        await self._session.flush()
        return document
