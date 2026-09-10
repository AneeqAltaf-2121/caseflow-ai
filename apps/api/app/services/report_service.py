"""Report authorization/orchestration (Phase 24) — the request-time half;
the actual generation runs in a background job (app/jobs/reports.py).
"""

import uuid

from app.audit import AuditAction, AuditTargetType
from app.errors import NotFoundError
from app.models.project import ProjectRole
from app.models.report import Report, ReportType
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.report_repository import ReportRepository
from app.services.project_service import ProjectService


class ReportService:
    def __init__(
        self,
        repository: ReportRepository,
        project_service: ProjectService,
        audit_repository: AuditEventRepository | None = None,
    ) -> None:
        self._repository = repository
        self._project_service = project_service
        self._audit_repository = audit_repository

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
        report = await self._repository.create(
            project_id=project_id, report_type=report_type, title=title, created_by=user_id
        )
        if self._audit_repository is not None:
            # Audited at request time, not once the background job
            # finishes — see app/audit.py's module docstring for why.
            await self._audit_repository.create(
                project_id=project_id,
                actor_user_id=user_id,
                action=AuditAction.REPORT_GENERATED,
                target_type=AuditTargetType.REPORT,
                target_id=report.id,
                metadata={"report_type": report_type.value, "title": title},
            )
        return report

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
