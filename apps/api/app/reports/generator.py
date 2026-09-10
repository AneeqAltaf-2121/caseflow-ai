"""Runs a report's sections through RagService — the pure orchestration
logic, deliberately separate from persistence (app/repositories/
report_repository.py builds the ORM rows) and from the job wiring
(app/jobs/reports.py), matching the split already used for document
ingestion (extract/chunk/embed vs. the job that calls them).
"""

import uuid
from dataclasses import dataclass

from app.models.report import ReportType
from app.rag.service import Citation as RagCitation
from app.rag.service import RagService
from app.reports.templates import sections_for


@dataclass(frozen=True)
class GeneratedSection:
    heading: str
    content: str
    citations: list[RagCitation]


async def generate_sections(
    *,
    rag_service: RagService,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    report_type: ReportType,
) -> list[GeneratedSection]:
    sections = []
    for spec in sections_for(report_type):
        answer = await rag_service.answer_question(
            project_id=project_id, user_id=user_id, query=spec.question
        )
        sections.append(
            GeneratedSection(
                heading=spec.heading, content=answer.answer, citations=answer.citations
            )
        )
    return sections
