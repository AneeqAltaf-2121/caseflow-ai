"""Report generation (Phase 24), nested under a project. Generation runs
as a background job (see app/jobs/reports.py) — creating a report returns
immediately with status=QUEUED; poll GET .../{report_id} for progress."""

import uuid

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserIdDep, DbSessionDep
from app.jobs.reports import generate_report_job
from app.models.report import Report, ReportSection
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.report_repository import ReportRepository
from app.schemas.report import (
    ReportCitationRead,
    ReportCreate,
    ReportDetailRead,
    ReportRead,
    ReportSectionRead,
)
from app.services.project_service import ProjectService
from app.services.report_service import ReportService

router = APIRouter(prefix="/projects/{project_id}/reports", tags=["reports"])


def _service(db: DbSessionDep) -> ReportService:
    return ReportService(ReportRepository(db), ProjectService(ProjectRepository(db)))


async def _enqueue_report(db: AsyncSession, report_id: uuid.UUID) -> None:
    """Same commit-before-send reasoning as documents.py's
    _enqueue_ingestion — a worker must never be able to pick up a message
    before the row it references is actually visible to it."""
    job = await JobRepository(db).create(
        type="report_generation", payload={"report_id": str(report_id)}
    )
    await db.commit()
    generate_report_job.send(str(job.id), str(report_id))


def _report_read(report: Report) -> ReportRead:
    return ReportRead(
        id=report.id,
        project_id=report.project_id,
        report_type=report.report_type,
        title=report.title,
        status=report.status,
        error=report.error,
        created_by=report.created_by,
        created_at=report.created_at,
    )


def _section_read(section: ReportSection) -> ReportSectionRead:
    return ReportSectionRead(
        id=section.id,
        heading=section.heading,
        content=section.content,
        position=section.position,
        citations=[
            ReportCitationRead(
                id=c.id,
                source_number=c.source_number,
                document_id=c.document_id,
                document_chunk_id=c.document_chunk_id,
                document_filename=c.document.filename,
                page_number=c.page_number,
                quote=c.quote,
            )
            for c in section.citations
        ],
    )


@router.post("", response_model=ReportRead, status_code=201)
async def create_report(
    project_id: uuid.UUID,
    payload: ReportCreate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> ReportRead:
    report = await _service(db).create_report(
        project_id=project_id,
        user_id=current_user_id,
        report_type=payload.report_type,
        title=payload.title,
    )
    await _enqueue_report(db, report.id)
    return _report_read(report)


@router.get("", response_model=list[ReportRead])
async def list_reports(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> list[ReportRead]:
    reports = await _service(db).list_reports(project_id=project_id, user_id=current_user_id)
    return [_report_read(r) for r in reports]


@router.get("/{report_id}", response_model=ReportDetailRead)
async def get_report(
    project_id: uuid.UUID, report_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> ReportDetailRead:
    report = await _service(db).get_report(
        report_id=report_id, project_id=project_id, user_id=current_user_id
    )
    return ReportDetailRead(
        **_report_read(report).model_dump(),
        sections=[_section_read(s) for s in report.sections],
    )
