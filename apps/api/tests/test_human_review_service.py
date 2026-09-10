import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.conversation import MessageRole
from app.models.human_review import HumanReviewStatus
from app.models.project import ProjectRole
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.human_review_repository import HumanReviewRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.human_review_service import HumanReviewService
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="hr-owner@x.com", display_name="Owner")
    viewer = await UserRepository(db_session).create(email="hr-viewer@x.com", display_name="Viewer")
    org = await OrganizationRepository(db_session).create(name="Co", slug="hr-co")
    project_repository = ProjectRepository(db_session)
    project_service = ProjectService(project_repository)
    project = await project_service.create_project(
        organization_id=org.id, name="Legal", description=None, created_by=owner.id
    )
    await project_repository.add_member(
        project_id=project.id, user_id=viewer.id, role=ProjectRole.VIEWER, invited_by=owner.id
    )

    conversation_repository = ConversationRepository(db_session)
    conversation = await conversation_repository.create(
        project_id=project.id, title="Chat", created_by=owner.id
    )
    user_message = await conversation_repository.add_message(
        conversation_id=conversation.id, role=MessageRole.USER, content="What is the term?"
    )
    assistant_message = await conversation_repository.add_message(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content="The term is 90 days [1].",
    )
    await db_session.commit()
    return owner, viewer, project, user_message, assistant_message


def _service(db_session: AsyncSession) -> HumanReviewService:
    return HumanReviewService(
        HumanReviewRepository(db_session),
        ConversationRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        AuditEventRepository(db_session),
    )


async def test_any_member_can_flag_an_assistant_message(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)

    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )

    assert review.status == HumanReviewStatus.NEEDS_REVIEW
    assert review.flagged_by == viewer.id
    assert review.original_answer == "The term is 90 days [1]."
    assert review.reviewer_id is None


async def test_cannot_flag_a_user_message(db_session: AsyncSession) -> None:
    owner, _viewer, project, user_message, _assistant_message = await _seed(db_session)
    service = _service(db_session)

    with pytest.raises(ValidationError):
        await service.flag_message(
            project_id=project.id, user_id=owner.id, message_id=user_message.id
        )


async def test_cannot_flag_the_same_message_twice_while_open(db_session: AsyncSession) -> None:
    owner, _viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)

    await service.flag_message(
        project_id=project.id, user_id=owner.id, message_id=assistant_message.id
    )
    with pytest.raises(ConflictError):
        await service.flag_message(
            project_id=project.id, user_id=owner.id, message_id=assistant_message.id
        )


async def test_flagging_a_message_from_another_project_is_not_found(
    db_session: AsyncSession,
) -> None:
    owner, _viewer, _project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)

    org2 = await OrganizationRepository(db_session).create(name="Other", slug="hr-other")
    other_project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org2.id, name="Other", description=None, created_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(NotFoundError):
        await service.flag_message(
            project_id=other_project.id, user_id=owner.id, message_id=assistant_message.id
        )


async def test_viewer_cannot_resolve_a_review(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)
    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )

    with pytest.raises(ForbiddenError):
        await service.submit_decision(
            review_id=review.id,
            project_id=project.id,
            reviewer_id=viewer.id,
            status=HumanReviewStatus.APPROVED,
            corrected_answer=None,
            reason=None,
        )


async def test_owner_can_approve_a_review(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)
    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )

    resolved = await service.submit_decision(
        review_id=review.id,
        project_id=project.id,
        reviewer_id=owner.id,
        status=HumanReviewStatus.APPROVED,
        corrected_answer=None,
        reason="Looks right.",
    )

    assert resolved.status == HumanReviewStatus.APPROVED
    assert resolved.reviewer_id == owner.id
    assert resolved.reviewed_at is not None
    assert resolved.reason == "Looks right."

    events = await AuditEventRepository(db_session).list_for_project(project.id)
    assert any(e.action == "human_review.completed" for e in events)


async def test_correcting_a_review_requires_a_corrected_answer(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)
    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )

    with pytest.raises(ValidationError):
        await service.submit_decision(
            review_id=review.id,
            project_id=project.id,
            reviewer_id=owner.id,
            status=HumanReviewStatus.CORRECTED,
            corrected_answer=None,
            reason=None,
        )

    resolved = await service.submit_decision(
        review_id=review.id,
        project_id=project.id,
        reviewer_id=owner.id,
        status=HumanReviewStatus.CORRECTED,
        corrected_answer="The term is actually 60 days.",
        reason="Misread the clause.",
    )
    assert resolved.status == HumanReviewStatus.CORRECTED
    assert resolved.corrected_answer == "The term is actually 60 days."


async def test_cannot_resolve_an_already_resolved_review(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)
    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )
    await service.submit_decision(
        review_id=review.id,
        project_id=project.id,
        reviewer_id=owner.id,
        status=HumanReviewStatus.REJECTED,
        corrected_answer=None,
        reason="Wrong.",
    )

    with pytest.raises(ConflictError):
        await service.submit_decision(
            review_id=review.id,
            project_id=project.id,
            reviewer_id=owner.id,
            status=HumanReviewStatus.APPROVED,
            corrected_answer=None,
            reason=None,
        )


async def test_list_reviews_can_filter_by_status(db_session: AsyncSession) -> None:
    owner, viewer, project, _user_message, assistant_message = await _seed(db_session)
    service = _service(db_session)
    review = await service.flag_message(
        project_id=project.id, user_id=viewer.id, message_id=assistant_message.id
    )

    needs_review = await service.list_reviews(
        project_id=project.id, user_id=owner.id, status=HumanReviewStatus.NEEDS_REVIEW
    )
    assert [r.id for r in needs_review] == [review.id]

    approved = await service.list_reviews(
        project_id=project.id, user_id=owner.id, status=HumanReviewStatus.APPROVED
    )
    assert approved == []
