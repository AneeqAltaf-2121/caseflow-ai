"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
what Alembic's `env.py` targets for autogenerate/offline SQL rendering.
"""

from app.models.audit_event import AuditEvent
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.job import Job, JobStatus
from app.models.organization import Organization
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Conversation",
    "Message",
    "MessageRole",
    "Document",
    "DocumentStatus",
    "DocumentVersion",
    "Job",
    "JobStatus",
    "Organization",
    "Project",
    "ProjectMember",
    "ProjectRole",
    "User",
]
