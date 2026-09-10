import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PromptVersionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    template: str = Field(min_length=1)
    activate: bool = True


class PromptVersionRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    version: int
    template: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
