import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.report import ReportStatus, ReportType


class ReportCreate(BaseModel):
    report_type: ReportType
    title: str = Field(min_length=1, max_length=300)


class ReportRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    report_type: ReportType
    title: str
    status: ReportStatus
    error: str | None
    created_by: uuid.UUID
    created_at: datetime


class ReportCitationRead(BaseModel):
    id: uuid.UUID
    source_number: int
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID
    document_filename: str
    page_number: int
    quote: str


class ReportSectionRead(BaseModel):
    id: uuid.UUID
    heading: str
    content: str
    position: int
    citations: list[ReportCitationRead] = Field(default_factory=list)


class ReportDetailRead(ReportRead):
    sections: list[ReportSectionRead]
