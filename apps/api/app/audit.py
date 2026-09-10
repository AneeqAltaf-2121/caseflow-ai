"""Audit action name constants (Phase 36) — shared between every service
that writes an AuditEvent, so an action string is never hand-typed (and
never drifts) at more than one call site.

Written at the point a user-attributable action happens in the service
layer, not when a background job later finishes it — a report/evaluation
run is audited when a user *requests* it (the human-attributable action),
not when the job completes (no human actor at that point, and
AuditEvent.actor_user_id is required).
"""

import enum


class AuditAction(enum.StrEnum):
    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    MEMBER_INVITED = "member.invited"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    REPORT_GENERATED = "report.generated"
    EVALUATION_RUN_CREATED = "evaluation_run.created"
    # Wired in Phase 37 — HumanReviewService.submit_decision.
    HUMAN_REVIEW_COMPLETED = "human_review.completed"


class AuditTargetType(enum.StrEnum):
    PROJECT = "project"
    PROJECT_MEMBER = "project_member"
    DOCUMENT = "document"
    REPORT = "report"
    EVALUATION_RUN = "evaluation_run"
    HUMAN_REVIEW = "human_review"
