import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.integrations.storage import LocalStorageBackend
from app.jobs.ingestion import process_document
from app.models.document import DocumentStatus
from app.models.job import JobStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed_document(db_session: AsyncSession, *, storage_key: str | None = None):
    user = await UserRepository(db_session).create(email="ingest@x.com", display_name="Ingest")
    org = await OrganizationRepository(db_session).create(name="IngestCo", slug="ingestco")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Ingestion", description=None, created_by=user.id
    )
    document = await DocumentRepository(db_session).create(
        project_id=project.id,
        filename="notes.txt",
        content_type="text/plain",
        size_bytes=5,
        checksum_sha256="abc",
        storage_key=storage_key or "missing/key.txt",
        uploaded_by=user.id,
    )
    await db_session.commit()
    return document


async def test_process_document_succeeds_and_marks_ready(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))
    await storage.put(key="docs/notes.txt", data=b"hello")

    async with db_session_factory() as session:
        document = await _seed_document(session, storage_key="docs/notes.txt")
        job = await JobRepository(session).create(
            type="document_ingestion", payload={"document_id": str(document.id)}
        )
        await session.commit()
        job_id, document_id = job.id, document.id

    await process_document(
        job_id=job_id, document_id=document_id, session_factory=db_session_factory, storage=storage
    )

    async with db_session_factory() as session:
        refreshed_document = await DocumentRepository(session).get_by_id(document_id)
        refreshed_job = await JobRepository(session).get_by_id(job_id)
        assert refreshed_document is not None and refreshed_job is not None
        assert refreshed_document.status == DocumentStatus.READY
        assert refreshed_job.status == JobStatus.SUCCEEDED
        assert refreshed_job.attempt == 1


async def test_process_document_retries_then_fails_permanently(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))
    # storage_key is never written, so storage.get() always raises.

    async with db_session_factory() as session:
        document = await _seed_document(session)
        job = await JobRepository(session).create(
            type="document_ingestion", payload={"document_id": str(document.id)}, max_attempts=2
        )
        await session.commit()
        job_id, document_id = job.id, document.id

    # Attempt 1: transient failure, re-raises for the caller (Dramatiq, in
    # production) to redeliver.
    with pytest.raises(FileNotFoundError):
        await process_document(
            job_id=job_id,
            document_id=document_id,
            session_factory=db_session_factory,
            storage=storage,
        )

    async with db_session_factory() as session:
        job_after_first = await JobRepository(session).get_by_id(job_id)
        assert job_after_first is not None
        assert job_after_first.status == JobStatus.RUNNING
        assert job_after_first.attempt == 1
        assert job_after_first.error is not None

    # Attempt 2 (== max_attempts): fails permanently, does not re-raise.
    await process_document(
        job_id=job_id, document_id=document_id, session_factory=db_session_factory, storage=storage
    )

    async with db_session_factory() as session:
        final_document = await DocumentRepository(session).get_by_id(document_id)
        final_job = await JobRepository(session).get_by_id(job_id)
        assert final_document is not None and final_job is not None
        assert final_document.status == DocumentStatus.FAILED
        assert final_job.status == JobStatus.FAILED
        assert final_job.attempt == 2


async def test_process_document_handles_missing_job(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))
    # Should return quietly rather than raise when the job row doesn't exist.
    await process_document(
        job_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        session_factory=db_session_factory,
        storage=storage,
    )
