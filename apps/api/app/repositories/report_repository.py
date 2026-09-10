import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.report import Report, ReportCitation, ReportSection, ReportStatus, ReportType


class ReportRepository:
    """Data access for Report/ReportSection/ReportCitation. No
    authorization here — see app/services/report_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, project_id: uuid.UUID, report_type: ReportType, title: str, created_by: uuid.UUID
    ) -> Report:
        report = Report(
            project_id=project_id, report_type=report_type, title=title, created_by=created_by
        )
        self._session.add(report)
        await self._session.flush()
        return report

    async def get_by_id(self, report_id: uuid.UUID) -> Report | None:
        result = await self._session.execute(
            select(Report)
            .where(Report.id == report_id)
            .options(
                selectinload(Report.sections)
                .selectinload(ReportSection.citations)
                .selectinload(ReportCitation.document)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[Report]:
        result = await self._session.execute(
            select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self, report: Report, status: ReportStatus, *, error: str | None = None
    ) -> Report:
        report.status = status
        report.error = error
        await self._session.flush()
        return report

    async def add_section(
        self,
        *,
        report_id: uuid.UUID,
        heading: str,
        content: str,
        position: int,
        citations: list[ReportCitation] | None = None,
    ) -> ReportSection:
        section = ReportSection(
            report_id=report_id, heading=heading, content=content, position=position
        )
        self._session.add(section)
        # Appending via the relationship (not setting section_id directly)
        # populates section.citations in memory too — same reasoning as
        # ConversationRepository.add_message's citation handling.
        for citation in citations or []:
            section.citations.append(citation)
        await self._session.flush()
        return section
