"""Human review (Phase 37): a lightweight review queue over generated
chat answers — see README's "review low-confidence AI outputs". Any
project member can flag an ASSISTANT message for review; only an
OWNER/EDITOR can resolve one (approve as-is, reject, or correct with a
replacement answer and a reason).

Scoped to Message rows for now, not every generated-content type
(report sections, evaluation answers) — chat is the primary place a
project's members actually see and act on a generated answer in this
app today.
"""

import uuid

from app.audit import AuditAction, AuditTargetType
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models.conversation import MessageRole
from app.models.human_review import HumanReview, HumanReviewStatus
from app.models.project import ProjectRole
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.human_review_repository import HumanReviewRepository
from app.services.project_service import ProjectService

OPEN_STATUSES = {HumanReviewStatus.NEEDS_REVIEW}


class HumanReviewService:
    def __init__(
        self,
        repository: HumanReviewRepository,
        conversation_repository: ConversationRepository,
        project_service: ProjectService,
        audit_repository: AuditEventRepository | None = None,
    ) -> None:
        self._repository = repository
        self._conversation_repository = conversation_repository
        self._project_service = project_service
        self._audit_repository = audit_repository

    async def flag_message(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, message_id: uuid.UUID
    ) -> HumanReview:
        # Any member can flag something for review — that's the whole
        # point of a review queue (catching a bad answer doesn't require
        # write access to the project).
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)

        message = await self._conversation_repository.get_message_by_id(message_id)
        if message is None or message.conversation.project_id != project_id:
            raise NotFoundError(f"Message {message_id} not found.")
        if message.role != MessageRole.ASSISTANT:
            raise ValidationError("Only generated (assistant) answers can be flagged for review.")

        existing = await self._repository.get_for_message(message_id)
        if existing is not None and existing.status in OPEN_STATUSES:
            raise ConflictError("This message already has an open review.")

        return await self._repository.create(
            project_id=project_id,
            message_id=message_id,
            flagged_by=user_id,
            original_answer=message.content,
        )

    async def list_reviews(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, status: HumanReviewStatus | None = None
    ) -> list[HumanReview]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_project(project_id, status=status)

    async def get_review(
        self, *, review_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> HumanReview:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        review = await self._repository.get_by_id(review_id)
        if review is None or review.project_id != project_id:
            raise NotFoundError(f"Review {review_id} not found.")
        return review

    async def submit_decision(
        self,
        *,
        review_id: uuid.UUID,
        project_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        status: HumanReviewStatus,
        corrected_answer: str | None,
        reason: str | None,
    ) -> HumanReview:
        # Resolving a review changes what the project treats as the
        # trustworthy answer — same owner/editor gate as everything else
        # that changes shared, project-visible state.
        await self._project_service.require_role(
            project_id=project_id,
            user_id=reviewer_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        review = await self.get_review(
            review_id=review_id, project_id=project_id, user_id=reviewer_id
        )
        if review.status not in OPEN_STATUSES:
            raise ConflictError(f"Review {review_id} has already been resolved.")
        if status == HumanReviewStatus.NEEDS_REVIEW:
            raise ValidationError("A decision must resolve the review, not leave it pending.")
        if status == HumanReviewStatus.CORRECTED and not corrected_answer:
            raise ValidationError("A corrected review requires a corrected_answer.")

        resolved = await self._repository.submit_decision(
            review,
            reviewer_id=reviewer_id,
            status=status,
            corrected_answer=corrected_answer,
            reason=reason,
        )
        if self._audit_repository is not None:
            await self._audit_repository.create(
                project_id=project_id,
                actor_user_id=reviewer_id,
                action=AuditAction.HUMAN_REVIEW_COMPLETED,
                target_type=AuditTargetType.HUMAN_REVIEW,
                target_id=review.id,
                metadata={"status": status.value, "message_id": str(review.message_id)},
            )
        return resolved
