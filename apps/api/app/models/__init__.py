"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
what Alembic's `env.py` targets for autogenerate/offline SQL rendering.
"""

from app.models.audit_event import AuditEvent
from app.models.chunk import EMBEDDING_DIMENSIONS, DocumentChunk
from app.models.citation import Citation
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.job import Job, JobStatus
from app.models.model_run import ModelRun, ModelRunStatus
from app.models.organization import Organization
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.prompt_version import PromptVersion
from app.models.user import User

__all__ = [
    "AuditEvent",
    "Citation",
    "Conversation",
    "Message",
    "MessageRole",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "DocumentVersion",
    "EMBEDDING_DIMENSIONS",
    "Job",
    "JobStatus",
    "ModelRun",
    "ModelRunStatus",
    "Organization",
    "Project",
    "ProjectMember",
    "ProjectRole",
    "PromptVersion",
    "User",
]
