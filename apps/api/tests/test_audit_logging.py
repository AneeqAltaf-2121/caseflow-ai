"""Phase 36: AuditEvent is now actually written to, for every action the
phase spec names except "human review completed" (Phase 37 doesn't exist
yet — nothing to audit until that review workflow is built)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction
from app.config import Settings
from app.errors import ConflictError, NotFoundError
from app.integrations.generation import MockGenerationProvider
from app.models.project import ProjectRole
from app.models.report import ReportType
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.user_repository import UserRepository
from app.services.document_service import DocumentService, UploadedFile
from app.services.evaluation_service import EvaluationRunService
from app.services.project_service import ProjectService
from app.services.prompt_version_service import PromptVersionService
from app.services.report_service import ReportService

pytestmark = pytest.mark.asyncio


class _InMemoryStorage:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def put(self, *, key: str, data: bytes) -> None:
        self._data[key] = data

    async def get(self, *, key: str) -> bytes:
        return self._data[key]

    async def delete(self, *, key: str) -> None:
        self._data.pop(key, None)


async def _make_user(session: AsyncSession, email: str):
    return await UserRepository(session).create(email=email, display_name=email)


async def _make_org(session: AsyncSession, slug: str):
    return await OrganizationRepository(session).create(name=slug, slug=slug)


async def test_project_created_is_audited(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "audit-owner@x.com")
    org = await _make_org(db_session, "audit-org")
    service = ProjectService(ProjectRepository(db_session), AuditEventRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Audited Project", description=None, created_by=owner.id
    )
    await db_session.commit()

    events = await AuditEventRepository(db_session).list_for_project(project.id)
    assert len(events) == 1
    assert events[0].action == AuditAction.PROJECT_CREATED
    assert events[0].actor_user_id == owner.id
    assert events[0].target_id == project.id
    assert events[0].event_metadata["name"] == "Audited Project"


async def test_member_invited_and_role_changed_and_removed_are_audited(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, "audit-owner2@x.com")
    invitee = await _make_user(db_session, "audit-invitee@x.com")
    org = await _make_org(db_session, "audit-org2")
    audit_repository = AuditEventRepository(db_session)
    service = ProjectService(ProjectRepository(db_session), audit_repository)

    project = await service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await service.invite_member(
        project_id=project.id,
        inviter_user_id=owner.id,
        invitee_user_id=invitee.id,
        role=ProjectRole.VIEWER,
    )
    await service.change_member_role(
        project_id=project.id,
        actor_user_id=owner.id,
        target_user_id=invitee.id,
        role=ProjectRole.EDITOR,
    )
    await service.remove_member(
        project_id=project.id, actor_user_id=owner.id, target_user_id=invitee.id
    )
    await db_session.commit()

    events = await audit_repository.list_for_project(project.id)
    actions = {e.action for e in events}
    assert AuditAction.MEMBER_INVITED in actions
    assert AuditAction.MEMBER_ROLE_CHANGED in actions
    assert AuditAction.MEMBER_REMOVED in actions

    role_change = next(e for e in events if e.action == AuditAction.MEMBER_ROLE_CHANGED)
    assert role_change.event_metadata == {"from_role": "viewer", "to_role": "editor"}


async def test_change_member_role_refuses_to_demote_the_last_owner(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, "audit-owner3@x.com")
    org = await _make_org(db_session, "audit-org3")
    service = ProjectService(ProjectRepository(db_session))
    project = await service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )

    with pytest.raises(ConflictError):
        await service.change_member_role(
            project_id=project.id,
            actor_user_id=owner.id,
            target_user_id=owner.id,
            role=ProjectRole.VIEWER,
        )


async def test_document_uploaded_and_deleted_are_audited(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "audit-doc@x.com")
    org = await _make_org(db_session, "audit-doc-org")
    audit_repository = AuditEventRepository(db_session)
    project_service = ProjectService(ProjectRepository(db_session))
    project = await project_service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await db_session.commit()

    service = DocumentService(
        DocumentRepository(db_session),
        project_service,
        _InMemoryStorage(),
        audit_repository,
        DocumentChunkRepository(db_session),
    )
    document = await service.upload_document(
        project_id=project.id,
        user_id=owner.id,
        file=UploadedFile(filename="a.txt", content_type="text/plain", data=b"hello"),
        settings=Settings(max_upload_size_mb=50),
    )
    await db_session.commit()

    await service.delete_document(project_id=project.id, document_id=document.id, user_id=owner.id)
    await db_session.commit()

    events = await audit_repository.list_for_project(project.id)
    actions = [e.action for e in events]
    assert AuditAction.DOCUMENT_UPLOADED in actions
    assert AuditAction.DOCUMENT_DELETED in actions

    with pytest.raises(NotFoundError):
        await service.get_document_for_user(
            project_id=project.id, document_id=document.id, user_id=owner.id
        )


async def test_report_generated_is_audited(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "audit-rep@x.com")
    org = await _make_org(db_session, "audit-rep-org")
    audit_repository = AuditEventRepository(db_session)
    project_service = ProjectService(ProjectRepository(db_session))
    project = await project_service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await db_session.commit()

    service = ReportService(ReportRepository(db_session), project_service, audit_repository)
    report = await service.create_report(
        project_id=project.id,
        user_id=owner.id,
        report_type=ReportType.EXECUTIVE_SUMMARY,
        title="Q1",
    )
    await db_session.commit()

    events = await audit_repository.list_for_project(project.id)
    assert any(
        e.action == AuditAction.REPORT_GENERATED and e.target_id == report.id for e in events
    )


async def test_evaluation_run_created_is_audited(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "audit-eval@x.com")
    org = await _make_org(db_session, "audit-eval-org")
    audit_repository = AuditEventRepository(db_session)
    project_service = ProjectService(ProjectRepository(db_session))
    project = await project_service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await db_session.commit()

    prompt_version_service = PromptVersionService(
        PromptVersionRepository(db_session), project_service
    )
    service = EvaluationRunService(
        EvaluationRunRepository(db_session),
        project_service,
        prompt_version_service,
        MockGenerationProvider(),
        Settings(),
        audit_repository,
    )
    run = await service.create_run(
        project_id=project.id, user_id=owner.id, dataset_name="sample_contract_qa"
    )
    await db_session.commit()

    events = await audit_repository.list_for_project(project.id)
    assert any(
        e.action == AuditAction.EVALUATION_RUN_CREATED and e.target_id == run.id for e in events
    )


async def test_audit_events_without_an_audit_repository_is_a_silent_no_op(
    db_session: AsyncSession,
) -> None:
    """Every service's audit_repository defaults to None — confirms
    nothing breaks (or silently double-writes) for the ~30 call sites
    that never pass one."""
    owner = await _make_user(db_session, "no-audit@x.com")
    org = await _make_org(db_session, "no-audit-org")
    service = ProjectService(ProjectRepository(db_session))  # no audit_repository

    project = await service.create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await db_session.commit()

    events = await AuditEventRepository(db_session).list_for_project(project.id)
    assert events == []
