"""Document processing job.

Reads the file back out of storage and runs it through the full pipeline:
extract (app/ingestion/pipeline.py) -> chunk (app/ingestion/chunker.py) ->
embed (app/integrations/embeddings.py) -> persist DocumentChunk rows with
their vectors -> mark the document READY. Real retry/backoff and a
durable Job record throughout.

`process_document` is a plain async function so tests can call it directly
against the test session factory/storage/embedding provider, without a
running broker or worker process. `process_document_job` is the thin,
untested-in-CI Dramatiq actor that wires it to real Postgres/Redis/S3/
embedding-API in production.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import dramatiq
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.errors import ValidationError
from app.ingestion.chunker import chunk_document
from app.ingestion.pipeline import extract_document
from app.integrations.embeddings import EmbeddingProvider, get_embedding_provider
from app.integrations.storage import StorageBackend, get_storage_backend
from app.models.chunk import DocumentChunk
from app.models.document import DocumentStatus
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository

logger = structlog.get_logger("caseflow.jobs.ingestion")

# How many chunk texts go into one embed() call — bounds request size for
# real API-backed providers (OpenAI) on very large documents. Irrelevant
# to in-process providers (mock/local) beyond a little extra looping.
EMBEDDING_BATCH_SIZE = 64


async def process_document(
    *,
    job_id: uuid.UUID,
    document_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    storage: StorageBackend,
    embedding_provider: EmbeddingProvider,
) -> None:
    # Phase 34: bind a trace context that every log line for this job
    # picks up automatically, including ones emitted from deep inside the
    # ingestion pipeline — not just the explicit job_id=... kwargs already
    # threaded through this function's own logger calls below. Cleared
    # (not just overwritten) first since a worker thread runs many jobs
    # in sequence and contextvars are thread-local, not per-job.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(job_id=str(job_id), document_id=str(document_id))

    async with session_factory() as session:
        job_repo = JobRepository(session)
        doc_repo = DocumentRepository(session)
        chunk_repo = DocumentChunkRepository(session)

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
            data = await storage.get(key=document.storage_key)
            extracted = extract_document(
                content_type=document.content_type, data=data, filename=document.filename
            )
            chunks = chunk_document(extracted)

            embeddings: list[list[float]] = []
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
                batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
                embeddings.extend(await embedding_provider.embed([c.text for c in batch]))
        except ValidationError as exc:
            # Not transient (corrupt/unreadable file, unsupported content
            # type) — retrying the same bytes would just fail the same way,
            # so this fails permanently on the first attempt rather than
            # burning through max_attempts with backoff.
            await job_repo.record_failure(job, str(exc))
            await job_repo.mark_failed(job)
            await doc_repo.update_status(document, DocumentStatus.FAILED)
            await session.commit()
            logger.error(
                "ingestion_job_failed_permanently",
                job_id=str(job_id),
                document_id=str(document_id),
                error=str(exc),
            )
            return
        except Exception as exc:  # noqa: BLE001 - any other failure is treated as transient
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

        # Idempotent under retry: a previous attempt may have already
        # persisted chunks for this document before failing partway
        # through (e.g. mid-embedding-batch on a transient API error).
        # Clearing first means a retried run never leaves duplicates.
        await chunk_repo.delete_for_document(document.id)

        # `document.versions` is eager-loaded (selectinload) and ordered
        # by version_number (see Document.versions) — the last entry is
        # always the current version, matching document.storage_key.
        current_version = document.versions[-1]
        embedded_at = datetime.now(UTC).isoformat()
        embedding_version = f"{type(embedding_provider).__name__}:{embedding_provider.dimensions}"

        rows = [
            DocumentChunk(
                document_id=document.id,
                document_version_id=current_version.id,
                page_number=chunk.page_number,
                section=None,
                text=chunk.text,
                token_count=chunk.token_count,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                embedding=embedding,
                chunk_metadata={
                    "embedding_version": embedding_version,
                    "embedded_at": embedded_at,
                },
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        if rows:
            await chunk_repo.bulk_create(rows)

        await doc_repo.update_status(document, DocumentStatus.READY)
        await job_repo.mark_succeeded(job)
        await session.commit()
        logger.info(
            "ingestion_job_succeeded",
            job_id=str(job_id),
            document_id=str(document_id),
            page_count=extracted.page_count,
            char_count=len(extracted.full_text),
            chunk_count=len(chunks),
            embedding_version=embedding_version,
        )


@dramatiq.actor(max_retries=3, min_backoff=1_000, max_backoff=30_000, queue_name="ingestion")
def process_document_job(job_id: str, document_id: str) -> None:
    """The actual Dramatiq entrypoint — not exercised in CI (needs a real
    Postgres + Redis + embedding provider), kept intentionally thin so all
    the logic worth testing lives in `process_document` above."""
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    storage = get_storage_backend(settings)
    embedding_provider = get_embedding_provider(settings)
    try:
        asyncio.run(
            process_document(
                job_id=uuid.UUID(job_id),
                document_id=uuid.UUID(document_id),
                session_factory=session_factory,
                storage=storage,
                embedding_provider=embedding_provider,
            )
        )
    finally:
        asyncio.run(engine.dispose())
