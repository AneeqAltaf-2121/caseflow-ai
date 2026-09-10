"""Document processing job.

Phase 8 scope only: prove the async pipeline end-to-end (upload returns
immediately; a worker picks the job up, reads the file back out of
storage, and transitions the document to READY/FAILED) with real
retry/backoff and a durable Job record. Actual text extraction is Phase 9
(app/ingestion/) — there's nowhere to put extracted text yet (DocumentChunk
doesn't exist until Phase 9-11 per docs/domain-model.md).

`process_document` is a plain async function so tests can call it directly
against the test session factory/storage backend, without a running broker
or worker process. `process_document_job` is the thin, untested-in-CI
Dramatiq actor that wires it to real Postgres/Redis/S3 in production.
"""

import asyncio
import uuid

import dramatiq
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.integrations.storage import StorageBackend, get_storage_backend
from app.models.document import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository

logger = structlog.get_logger("caseflow.jobs.ingestion")


async def process_document(
    *,
    job_id: uuid.UUID,
    document_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    storage: StorageBackend,
) -> None:
    async with session_factory() as session:
        job_repo = JobRepository(session)
        doc_repo = DocumentRepository(session)

        job = await job_repo.get_by_id(job_id)
        if job is None:
            logger.warning("ingestion_job_missing", job_id=str(job_id))
            return

        document = await doc_repo.get_by_id(document_id)
        if document is None:
            await job_repo.record_failure(job, "Document no longer exists.")
            await job_repo.mark_failed(job)
            await session.commit()
            return

        await job_repo.mark_running(job)
        await doc_repo.update_status(document, DocumentStatus.PROCESSING)
        await session.commit()

        try:
            # Phase 9 replaces this with real extraction (PDF/DOCX/TXT) and
            # chunking. For now, just prove storage is reachable and the
            # bytes round-trip correctly.
            await storage.get(key=document.storage_key)
        except Exception as exc:  # noqa: BLE001 - any failure means retry/fail, not crash the worker
            await job_repo.record_failure(job, str(exc))
            exhausted = job.attempt >= job.max_attempts
            if exhausted:
                await job_repo.mark_failed(job)
                await doc_repo.update_status(document, DocumentStatus.FAILED)
            await session.commit()
            if exhausted:
                logger.error(
                    "ingestion_job_failed_permanently",
                    job_id=str(job_id),
                    document_id=str(document_id),
                    error=str(exc),
                )
                return
            logger.warning(
                "ingestion_job_attempt_failed",
                job_id=str(job_id),
                document_id=str(document_id),
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                error=str(exc),
            )
            raise  # let Dramatiq's Retries middleware redeliver with backoff

        await doc_repo.update_status(document, DocumentStatus.READY)
        await job_repo.mark_succeeded(job)
        await session.commit()
        logger.info("ingestion_job_succeeded", job_id=str(job_id), document_id=str(document_id))


@dramatiq.actor(max_retries=3, min_backoff=1_000, max_backoff=30_000, queue_name="ingestion")
def process_document_job(job_id: str, document_id: str) -> None:
    """The actual Dramatiq entrypoint — not exercised in CI (needs a real
    Postgres + Redis), kept intentionally thin so all the logic worth
    testing lives in `process_document` above."""
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    storage = get_storage_backend(settings)
    try:
        asyncio.run(
            process_document(
                job_id=uuid.UUID(job_id),
                document_id=uuid.UUID(document_id),
                session_factory=session_factory,
                storage=storage,
            )
        )
    finally:
        asyncio.run(engine.dispose())
