"""Human review (Phase 37), nested under a project — a review queue over
generated chat answers. Any member may flag a message; resolving a
review (approve/reject/correct) is owner/editor-gated, same as any other
write to shared project state."""

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUserIdDep, DbSessionDep
from app.models.human_review import HumanReview, HumanReviewStatus
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.human_review_repository import HumanReviewRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.human_review import HumanReviewDecision, HumanReviewFlag, HumanReviewRead
from app.services.human_review_service import HumanReviewService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/reviews", tags=["human-review"])


def _service(db: DbSessionDep) -> HumanReviewService:
    return HumanReviewService(
        HumanReviewRepository(db),
        ConversationRepository(db),
        ProjectService(ProjectRepository(db)),
        AuditEventRepository(db),
    )


def _read(review: HumanReview) -> HumanReviewRead:
    return HumanReviewRead(
        id=review.id,
        project_id=review.project_id,
        message_id=review.message_id,
        status=review.status,
        flagged_by=review.flagged_by,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
        original_answer=review.original_answer,
        corrected_answer=review.corrected_answer,
        reason=review.reason,
        created_at=review.created_at,
    )


@router.post("", response_model=HumanReviewRead, status_code=201)
async def flag_message(
    project_id: uuid.UUID,
    payload: HumanReviewFlag,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> HumanReviewRead:
    review = await _service(db).flag_message(
        project_id=project_id, user_id=current_user_id, message_id=payload.message_id
    )
    return _read(review)


@router.get("", response_model=list[HumanReviewRead])
async def list_reviews(
    project_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    status: HumanReviewStatus | None = None,
) -> list[HumanReviewRead]:
    reviews = await _service(db).list_reviews(
        project_id=project_id, user_id=current_user_id, status=status
    )
    return [_read(r) for r in reviews]


@router.get("/{review_id}", response_model=HumanReviewRead)
async def get_review(
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> HumanReviewRead:
    review = await _service(db).get_review(
        review_id=review_id, project_id=project_id, user_id=current_user_id
    )
    return _read(review)


@router.patch("/{review_id}", response_model=HumanReviewRead)
async def submit_decision(
    project_id: uuid.UUID,
    review_id: uuid.UUID,
    payload: HumanReviewDecision,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> HumanReviewRead:
    review = await _service(db).submit_decision(
        review_id=review_id,
        project_id=project_id,
        reviewer_id=current_user_id,
        status=payload.status,
        corrected_answer=payload.corrected_answer,
        reason=payload.reason,
    )
    return _read(review)
