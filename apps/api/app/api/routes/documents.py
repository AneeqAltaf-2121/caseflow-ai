"""Document upload/download routes, nested under a project.

routes -> DocumentService -> DocumentRepository + StorageBackend. Membership
and role checks happen inside DocumentService (via ProjectService), never
here — see docs/domain-model.md.
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserIdDep, DbSessionDep, SettingsDep, StorageDep
from app.jobs.ingestion import process_document_job
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService, UploadedFile
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


def _content_disposition(filename: str) -> str:
    """RFC 6266 encoding for the download filename (Phase 38 defense in
    depth — DocumentService.sanitize_filename already strips characters
    that would let this header be malformed or injected into, but a
    header value should never trust untrusted text at all if avoidable).
    A plain ASCII fallback (quotes/backslashes escaped) covers older
    clients that don't understand filename*; UTF-8 percent-encoding in
    filename* covers everything else correctly."""
    ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
    ascii_fallback = ascii_fallback.replace("\\", "\\\\").replace('"', '\\"')
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _service(db: DbSessionDep, storage: StorageDep) -> DocumentService:
    return DocumentService(
        DocumentRepository(db),
        ProjectService(ProjectRepository(db)),
        storage,
        AuditEventRepository(db),
        DocumentChunkRepository(db),
    )


async def _enqueue_ingestion(db: AsyncSession, document_id: uuid.UUID) -> None:
    """Create the durable Job record and publish the message. Commits
    explicitly (rather than relying on get_db's commit-on-request-exit)
    so the row is visible to a worker before it can possibly pick the
    message up — enqueueing before committing is a real race in
    production, even if it never shows up in single-process tests."""
    job = await JobRepository(db).create(
        type="document_ingestion", payload={"document_id": str(document_id)}
    )
    await db.commit()
    process_document_job.send(str(job.id), str(document_id))


@router.post("", response_model=DocumentRead, status_code=201)
async def upload_document(
    project_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> DocumentRead:
    data = await file.read()
    document = await _service(db, storage).upload_document(
        project_id=project_id,
        user_id=current_user_id,
        file=UploadedFile(
            filename=file.filename or "untitled",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        ),
        settings=settings,
    )
    await _enqueue_ingestion(db, document.id)
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/versions", response_model=DocumentRead, status_code=201)
async def upload_new_version(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
) -> DocumentRead:
    data = await file.read()
    document = await _service(db, storage).replace_document(
        project_id=project_id,
        document_id=document_id,
        user_id=current_user_id,
        file=UploadedFile(
            filename=file.filename or "untitled",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        ),
        settings=settings,
    )
    await _enqueue_ingestion(db, document.id)
    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep, storage: StorageDep
) -> list[DocumentRead]:
    documents = await _service(db, storage).list_documents(
        project_id=project_id, user_id=current_user_id
    )
    return [DocumentRead.model_validate(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    storage: StorageDep,
) -> DocumentRead:
    document = await _service(db, storage).get_document_for_user(
        project_id=project_id, document_id=document_id, user_id=current_user_id
    )
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    storage: StorageDep,
) -> None:
    await _service(db, storage).delete_document(
        project_id=project_id, document_id=document_id, user_id=current_user_id
    )


@router.get("/{document_id}/download")
async def download_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    storage: StorageDep,
) -> Response:
    document, data = await _service(db, storage).download_document(
        project_id=project_id, document_id=document_id, user_id=current_user_id
    )
    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": _content_disposition(document.filename)},
    )
