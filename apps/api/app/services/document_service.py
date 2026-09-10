"""Document upload/retrieval business logic.

Uploaded files are untrusted input: size and content-type are validated
before anything touches storage or the database (see docs/architecture.md's
"documents are untrusted evidence" principle, which starts here). Access is
scoped through ProjectService so a project's membership rules stay the
single source of truth for "who can see/write this document".
"""

import hashlib
import uuid
from dataclasses import dataclass

from app.config import Settings
from app.errors import NotFoundError, ValidationError
from app.integrations.storage import StorageBackend
from app.models.document import Document
from app.models.project import ProjectRole
from app.repositories.document_repository import DocumentRepository
from app.services.project_service import ProjectService

# Content types accepted for ingestion (Phase 8 extracts text from these).
# Anything else is rejected at upload time rather than silently accepted
# and failing later in the pipeline.
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        project_service: ProjectService,
        storage: StorageBackend,
    ) -> None:
        self._repository = repository
        self._project_service = project_service
        self._storage = storage

    def _validate(self, file: UploadedFile, *, settings: Settings) -> None:
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f"Unsupported content type {file.content_type!r}. "
                f"Allowed: {sorted(ALLOWED_CONTENT_TYPES)}."
            )
        max_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(file.data) > max_bytes:
            raise ValidationError(f"File exceeds the {settings.max_upload_size_mb}MB upload limit.")
        if len(file.data) == 0:
            raise ValidationError("Uploaded file is empty.")

    async def upload_document(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        file: UploadedFile,
        settings: Settings,
    ) -> Document:
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        self._validate(file, settings=settings)

        checksum = hashlib.sha256(file.data).hexdigest()
        storage_key = f"projects/{project_id}/{uuid.uuid4().hex}/{file.filename}"

        await self._storage.put(key=storage_key, data=file.data)
        try:
            return await self._repository.create(
                project_id=project_id,
                filename=file.filename,
                content_type=file.content_type,
                size_bytes=len(file.data),
                checksum_sha256=checksum,
                storage_key=storage_key,
                uploaded_by=user_id,
            )
        except Exception:
            await self._storage.delete(key=storage_key)
            raise

    async def replace_document(
        self,
        *,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        file: UploadedFile,
        settings: Settings,
    ) -> Document:
        """Upload a new version of an existing document."""
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        self._validate(file, settings=settings)

        document = await self.get_document_for_user(
            project_id=project_id, document_id=document_id, user_id=user_id
        )

        checksum = hashlib.sha256(file.data).hexdigest()
        storage_key = f"projects/{project_id}/{uuid.uuid4().hex}/{file.filename}"

        await self._storage.put(key=storage_key, data=file.data)
        try:
            await self._repository.add_version(
                document=document, storage_key=storage_key, checksum_sha256=checksum
            )
        except Exception:
            await self._storage.delete(key=storage_key)
            raise
        return document

    async def list_documents(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Document]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_project(project_id)

    async def get_document_for_user(
        self, *, project_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> Document:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        document = await self._repository.get_by_id(document_id)
        if document is None or document.project_id != project_id:
            raise NotFoundError(f"Document {document_id} not found.")
        return document

    async def download_document(
        self, *, project_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Document, bytes]:
        document = await self.get_document_for_user(
            project_id=project_id, document_id=document_id, user_id=user_id
        )
        data = await self._storage.get(key=document.storage_key)
        return document, data
