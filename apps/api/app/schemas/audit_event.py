import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    actor_user_id: uuid.UUID
    action: str
    target_type: str
    target_id: uuid.UUID
    event_metadata: dict
    created_at: datetime
