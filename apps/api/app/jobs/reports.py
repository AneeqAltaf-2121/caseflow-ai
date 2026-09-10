"""Report generation job.

Runs every section of a report (app/reports/templates.py) through
RagService and persists the results, with the same retry/backoff and
durable Job record pattern as document ingestion (app/jobs/ingestion.py).
Unlike ingestion, any failure here is treated as transient (retried) —
there's no equivalent of "this file will never parse" for a report; a
failure is a generation-provider hiccup until proven otherwise by
exhausting retries.

`generate_report` is a plain async function so tests can call it directly
against a test session factory and injected providers, without a running
broker/worker. `generate_report_job` is the thin, untested-in-CI Dramatiq
actor that wires it to real Postgres/Redis/LLM APIs in production.
"""

import asyncio
import uuid

import dramatiq
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache import get_cache
from app.config import get_settings
from app.database import create_engine, create_session_factory
from app.integrations.embeddings import EmbeddingProvider, get_embedding_provider
from app.integrations.generation import GenerationProvider, get_generation_provider
from app.models.report import ReportCitation, ReportStatus
from app.rag.service import RagService
from app.reports.generator import generate_sections
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.report_repository import ReportRepository
from app.retrieval.reranker import CrossEncoderReranker, Reranker
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

logger = structlog.get_logger("caseflow.jobs.reports")


async def generate_report(
    *,
    job_id: uuid.UUID,
    report_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    embedding_provider: EmbeddingProvider,
    reranker: Reranker,
    generation_provider: GenerationProvider,
) -> None:
    # Phase 34: bind a trace context every log line for this job picks up
    # automatically — see the matching comment in process_document.
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(job_id=str(job_id), report_id=str(report_id))

    async with session_factory() as session:
        job_repo = JobRepository(session)
        report_repo = ReportRepository(session)

        job = await job_repo.get_by_id(job_id)
        if job is None:
            logger.warning("report_job_missing", job_id=str(job_id))
            return

        report = await report_repo.get_by_id(report_id)
        if report is None:
            await job_repo.record_failure(job, "Report no longer exists.")
            await job_repo.mark_failed(job)
            await session.commit()
            return

        await job_repo.mark_running(job)
        await report_repo.update_status(report, ReportStatus.PROCESSING)
        await session.commit()

        hybrid_service = HybridSearchService(
            DocumentChunkRepository(session),
            ProjectService(ProjectRepository(session)),
            embedding_provider,
            get_cache(),
        )
        rag_service = RagService(RetrievalService(hybrid_service, reranker), generation_provider)

        try:
            generated_sections = await generate_sections(
                rag_service=rag_service,
                project_id=report.project_id,
                user_id=report.created_by,
                report_type=report.report_type,
            )
        except Exception as exc:  # noqa: BLE001 - any failure here is treated as transient
            await job_repo.record_failure(job, str(exc))
            exhausted = job.attempt >= job.max_attempts
            if exhausted:
                await job_repo.mark_failed(job)
                await report_repo.update_status(report, ReportStatus.FAILED, error=str(exc))
            await session.commit()
            if exhausted:
                logger.error(
                    "report_job_failed_permanently",
                    job_id=str(job_id),
                    report_id=str(report_id),
                    error=str(exc),
                )
                return
            logger.warning(
                "report_job_attempt_failed",
                job_id=str(job_id),
                report_id=str(report_id),
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                error=str(exc),
            )
            raise  # let Dramatiq's Retries middleware redeliver with backoff

        # Idempotent under retry: drop any sections a previous, partially
        # failed attempt already wrote before writing the fresh set.
        report.sections.clear()
        await session.flush()

        for position, section in enumerate(generated_sections, start=1):
            citation_rows = [
                ReportCitation(
                    document_id=c.document_id,
                    document_chunk_id=c.document_chunk_id,
                    source_number=c.source_number,
                    page_number=c.page_number,
                    quote=c.quote,
                )
                for c in section.citations
            ]
            await report_repo.add_section(
                report_id=report.id,
                heading=section.heading,
                content=section.content,
                position=position,
                citations=citation_rows,
            )

        await report_repo.update_status(report, ReportStatus.READY)
        await job_repo.mark_succeeded(job)
        await session.commit()
        logger.info(
            "report_job_succeeded",
            job_id=str(job_id),
            report_id=str(report_id),
            section_count=len(generated_sections),
        )


@dramatiq.actor(max_retries=3, min_backoff=2_000, max_backoff=60_000, queue_name="reports")
def generate_report_job(job_id: str, report_id: str) -> None:
    """The actual Dramatiq entrypoint — not exercised in CI (needs a real
    Postgres + Redis + LLM provider), kept intentionally thin so all the
    logic worth testing lives in `generate_report` above."""
    settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    embedding_provider = get_embedding_provider(settings)
    generation_provider = get_generation_provider(settings)
    reranker = CrossEncoderReranker()
    try:
        asyncio.run(
            generate_report(
                job_id=uuid.UUID(job_id),
                report_id=uuid.UUID(report_id),
                session_factory=session_factory,
                embedding_provider=embedding_provider,
                reranker=reranker,
                generation_provider=generation_provider,
            )
        )
    finally:
        asyncio.run(engine.dispose())
