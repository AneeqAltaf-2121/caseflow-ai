"""Report authorization/orchestration (Phase 24) — the request-time half;
the actual generation runs in a background job (app/jobs/reports.py).
"""

import uuid

from app.errors import NotFoundError
from app.models.project import ProjectRole
from app.models.report import Report, ReportType
from app.repositories.report_repository import ReportRepository
from app.services.project_service import ProjectService


class ReportService:
    def __init__(self, repository: ReportRepository, project_service: ProjectService) -> None:
        self._repository = repository
        self._project_service = project_service

    async def create_report(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, report_type: ReportType, title: str
    ) -> Report:
        # Generating a report spends real retrieval + LLM calls across
        # every section — same owner/editor gate as uploading a document.
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        return await self._repository.create(
            project_id=project_id, report_type=report_type, title=title, created_by=user_id
        )

    async def list_reports(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Report]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_project(project_id)

    async def get_report(
        self, *, report_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Report:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        report = await self._repository.get_by_id(report_id)
        if report is None or report.project_id != project_id:
            raise NotFoundError(f"Report {report_id} not found.")
        return report
