import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditEventRepository:
    """Data access for AuditEvent — append-only, no update/delete methods
    on purpose (see the model's own docstring). No authorization here —
    callers write from whatever service already proved the actor has
    permission to perform the action being audited."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        action: str,
        target_type: str,
        target_id: uuid.UUID,
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            project_id=project_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            event_metadata=metadata or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_for_project(
        self, project_id: uuid.UUID, *, limit: int = 200
    ) -> list[AuditEvent]:
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
