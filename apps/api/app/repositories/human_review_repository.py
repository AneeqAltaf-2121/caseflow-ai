import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.human_review import HumanReview, HumanReviewStatus


class HumanReviewRepository:
    """Data access for HumanReview. No authorization here — see
    app/services/human_review_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        message_id: uuid.UUID,
        flagged_by: uuid.UUID,
        original_answer: str,
    ) -> HumanReview:
        review = HumanReview(
            project_id=project_id,
            message_id=message_id,
            flagged_by=flagged_by,
            original_answer=original_answer,
            status=HumanReviewStatus.NEEDS_REVIEW,
        )
        self._session.add(review)
        await self._session.flush()
        return review

    async def get_by_id(self, review_id: uuid.UUID) -> HumanReview | None:
        result = await self._session.execute(
            select(HumanReview)
            .where(HumanReview.id == review_id)
            .options(selectinload(HumanReview.message))
        )
        return result.scalar_one_or_none()

    async def get_for_message(self, message_id: uuid.UUID) -> HumanReview | None:
        """The most recent review flagged for a message — used to refuse
        flagging the same message twice while a review is still open."""
        result = await self._session.execute(
            select(HumanReview)
            .where(HumanReview.message_id == message_id)
            .order_by(HumanReview.created_at.desc())
        )
        return result.scalars().first()

    async def list_for_project(
        self, project_id: uuid.UUID, *, status: HumanReviewStatus | None = None
    ) -> list[HumanReview]:
        query = select(HumanReview).where(HumanReview.project_id == project_id)
        if status is not None:
            query = query.where(HumanReview.status == status)
        result = await self._session.execute(
            query.order_by(HumanReview.created_at.desc()).options(selectinload(HumanReview.message))
        )
        return list(result.scalars().all())

    async def submit_decision(
        self,
        review: HumanReview,
        *,
        reviewer_id: uuid.UUID,
        status: HumanReviewStatus,
        corrected_answer: str | None,
        reason: str | None,
    ) -> HumanReview:
        review.status = status
        review.reviewer_id = reviewer_id
        review.reviewed_at = datetime.now(UTC)
        review.corrected_answer = corrected_answer
        review.reason = reason
        await self._session.flush()
        return review
