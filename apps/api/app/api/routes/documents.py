"""Document upload/download routes, nested under a project.

routes -> DocumentService -> DocumentRepository + StorageBackend. Membership
and role checks happen inside DocumentService (via ProjectService), never
here — see docs/domain-model.md.
"""

import uuid

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.dependencies import CurrentUserIdDep, DbSessionDep, SettingsDep, StorageDep
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.document import DocumentRead
from app.services.document_service import DocumentService, UploadedFile
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/documents", tags=["documents"])


def _service(db: DbSessionDep, storage: StorageDep) -> DocumentService:
    return DocumentService(DocumentRepository(db), ProjectService(ProjectRepository(db)), storage)


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
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )
