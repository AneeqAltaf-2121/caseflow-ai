import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus


class JobRepository:
    """Data access for Job — the durable, queryable record of a unit of
    background work (see ADR 003). The Redis/Dramatiq queue is just the
    delivery mechanism; this row is what the app and its users can query
    ("did my upload finish processing?") independent of the broker.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, type: str, payload: dict, max_attempts: int = 3) -> Job:
        job = Job(type=type, payload=payload, max_attempts=max_attempts)
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        return await self._session.get(Job, job_id)

    async def mark_running(self, job: Job) -> Job:
        job.status = JobStatus.RUNNING
        job.attempt += 1
        job.started_at = datetime.now(UTC)
        await self._session.flush()
        return job

    async def mark_succeeded(self, job: Job) -> Job:
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC)
        job.error = None
        await self._session.flush()
        return job

    async def record_failure(self, job: Job, error: str) -> Job:
        """Record a failed attempt without deciding whether to retry —
        that's the caller's call based on `job.attempt` vs
        `job.max_attempts` (see app/jobs/ingestion.py)."""
        job.error = error
        await self._session.flush()
        return job

    async def mark_failed(self, job: Job) -> Job:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        await self._session.flush()
        return job
