"""Phase 34: confirms each job function binds a trace context
(job_id + its own resource id) via structlog.contextvars before doing
anything else, so *every* log line emitted during that job — including
ones from code this test never calls directly — automatically carries
it. structlog.testing.capture_logs() can't be used here: it replaces the
whole processor pipeline (including merge_contextvars), which would
silently hide the exact thing being tested. Instead this reconfigures
structlog with merge_contextvars + a capturing processor, the same way
capture_logs() works internally, then restores the real config after.
"""

import uuid
from contextlib import contextmanager

import pytest
import structlog
from structlog.testing import LogCapture

from app.jobs.evaluations import run_evaluation
from app.jobs.ingestion import process_document
from app.jobs.reports import generate_report

pytestmark = pytest.mark.asyncio


@contextmanager
def capture_logs_with_contextvars():
    cap = LogCapture()
    processors = structlog.get_config()["processors"]
    old_processors = processors.copy()
    processors.clear()
    processors.append(structlog.contextvars.merge_contextvars)
    processors.append(cap)
    structlog.configure(processors=processors)
    try:
        yield cap.entries
    finally:
        processors.clear()
        processors.extend(old_processors)
        structlog.configure(processors=processors)


async def test_process_document_binds_job_and_document_id(db_session_factory) -> None:
    job_id = uuid.uuid4()
    document_id = uuid.uuid4()

    with capture_logs_with_contextvars() as entries:
        await process_document(
            job_id=job_id,
            document_id=document_id,
            session_factory=db_session_factory,
            storage=None,  # never reached: the job returns at the missing-job check
            embedding_provider=None,  # type: ignore[arg-type]
        )

    assert entries, "expected at least one log line"
    for entry in entries:
        assert entry["job_id"] == str(job_id)
        assert entry["document_id"] == str(document_id)


async def test_generate_report_binds_job_and_report_id(db_session_factory) -> None:
    job_id = uuid.uuid4()
    report_id = uuid.uuid4()

    with capture_logs_with_contextvars() as entries:
        await generate_report(
            job_id=job_id,
            report_id=report_id,
            session_factory=db_session_factory,
            embedding_provider=None,  # type: ignore[arg-type]
            reranker=None,  # type: ignore[arg-type]
            generation_provider=None,  # type: ignore[arg-type]
        )

    assert entries
    for entry in entries:
        assert entry["job_id"] == str(job_id)
        assert entry["report_id"] == str(report_id)


async def test_run_evaluation_binds_job_and_evaluation_run_id(db_session_factory) -> None:
    job_id = uuid.uuid4()
    evaluation_run_id = uuid.uuid4()

    with capture_logs_with_contextvars() as entries:
        await run_evaluation(
            job_id=job_id,
            evaluation_run_id=evaluation_run_id,
            session_factory=db_session_factory,
            embedding_provider=None,  # type: ignore[arg-type]
            reranker=None,  # type: ignore[arg-type]
            generation_provider=None,  # type: ignore[arg-type]
            judge_provider=None,  # type: ignore[arg-type]
        )

    assert entries
    for entry in entries:
        assert entry["job_id"] == str(job_id)
        assert entry["evaluation_run_id"] == str(evaluation_run_id)


async def test_trace_context_does_not_leak_between_jobs(db_session_factory) -> None:
    """A worker thread runs many jobs in sequence — the second job's log
    lines must not carry the first job's id (contextvars are thread-local,
    not per-call, so this only holds if each job clears before binding)."""
    first_job_id = uuid.uuid4()
    second_job_id = uuid.uuid4()

    with capture_logs_with_contextvars() as entries:
        await run_evaluation(
            job_id=first_job_id,
            evaluation_run_id=uuid.uuid4(),
            session_factory=db_session_factory,
            embedding_provider=None,  # type: ignore[arg-type]
            reranker=None,  # type: ignore[arg-type]
            generation_provider=None,  # type: ignore[arg-type]
            judge_provider=None,  # type: ignore[arg-type]
        )
        await process_document(
            job_id=second_job_id,
            document_id=uuid.uuid4(),
            session_factory=db_session_factory,
            storage=None,  # type: ignore[arg-type]
            embedding_provider=None,  # type: ignore[arg-type]
        )

    first_job_entries = [e for e in entries if "evaluation_run_id" in e]
    second_job_entries = [e for e in entries if "document_id" in e]
    assert first_job_entries and second_job_entries
    assert all(e["job_id"] == str(first_job_id) for e in first_job_entries)
    assert all(e["job_id"] == str(second_job_id) for e in second_job_entries)
