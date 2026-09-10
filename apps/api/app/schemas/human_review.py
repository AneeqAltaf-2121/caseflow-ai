import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.human_review import HumanReviewStatus


class HumanReviewFlag(BaseModel):
    message_id: uuid.UUID


class HumanReviewDecision(BaseModel):
    status: HumanReviewStatus
    corrected_answer: str | None = Field(default=None, max_length=20_000)
    reason: str | None = Field(default=None, max_length=2_000)


class HumanReviewRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    message_id: uuid.UUID
    status: HumanReviewStatus
    flagged_by: uuid.UUID
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    original_answer: str
    corrected_answer: str | None
    reason: str | None
    created_at: datetime
