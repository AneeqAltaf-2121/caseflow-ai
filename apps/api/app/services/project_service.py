"""Project business logic.

Authorization note: every read here is scoped to a `requesting_user_id`,
derived from the authenticated session (see app/dependencies.py's
CurrentUserIdDep) rather than trusted from client input.
"""

import uuid

from app.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.project import Project, ProjectMember, ProjectRole
from app.repositories.project_repository import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    async def create_project(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        created_by: uuid.UUID,
    ) -> Project:
        """Create a project and add its creator as the owning member.

        These two writes happen in the same DB transaction (the caller's
        session commits once, at the request boundary — see get_db) so a
        project is never left without an owner.
        """
        project = await self._repository.create(
            organization_id=organization_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        await self._repository.add_member(
            project_id=project.id,
            user_id=created_by,
            role=ProjectRole.OWNER,
            invited_by=None,
        )
        return project

    async def list_projects_for_user(self, user_id: uuid.UUID) -> list[Project]:
        return await self._repository.list_for_user(user_id)

    async def get_project_for_user(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
        project = await self._repository.get_by_id(project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found.")

        member = await self._repository.get_member(project_id=project_id, user_id=user_id)
        if member is None:
            # Deliberately the same error a nonexistent project would raise
            # in shape (404, not 403) so membership isn't leaked — a
            # non-member can't distinguish "doesn't exist" from "not yours".
            raise NotFoundError(f"Project {project_id} not found.")

        return project

    async def require_role(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, allowed: set[ProjectRole]
    ) -> ProjectMember:
        """Raise ForbiddenError unless the user's role in the project is
        one of `allowed`. Used by every write operation that isn't plain
        project creation (invite, upload, delete, ...)."""
        member = await self._repository.get_member(project_id=project_id, user_id=user_id)
        if member is None:
            raise NotFoundError(f"Project {project_id} not found.")
        if member.role not in allowed:
            raise ForbiddenError(
                f"Role '{member.role.value}' is not permitted to perform this action."
            )
        return member

    async def list_members(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[ProjectMember]:
        # Confirms the requester is themself a member before revealing the roster.
        await self.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_members(project_id)

    async def invite_member(
        self,
        *,
        project_id: uuid.UUID,
        inviter_user_id: uuid.UUID,
        invitee_user_id: uuid.UUID,
        role: ProjectRole,
    ) -> ProjectMember:
        """Add `invitee_user_id` to the project. Only owners can invite."""
        await self.require_role(
            project_id=project_id, user_id=inviter_user_id, allowed={ProjectRole.OWNER}
        )

        existing = await self._repository.get_member(project_id=project_id, user_id=invitee_user_id)
        if existing is not None:
            raise ConflictError("User is already a member of this project.")

        return await self._repository.add_member(
            project_id=project_id,
            user_id=invitee_user_id,
            role=role,
            invited_by=inviter_user_id,
        )

    async def update_project(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        description: str | None,
        description_set: bool,
    ) -> Project:
        """Rename/redescribe a project. Owners and editors may do this."""
        await self.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        project = await self._repository.get_by_id(project_id)
        assert project is not None  # require_role already proved it exists
        return await self._repository.update(
            project, name=name, description=description, has_description=description_set
        )

    async def delete_project(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Permanently delete a project and everything scoped to it
        (members, documents, conversations, ... via ON DELETE CASCADE).
        Owner-only — this is irreversible."""
        await self.require_role(project_id=project_id, user_id=user_id, allowed={ProjectRole.OWNER})
        project = await self._repository.get_by_id(project_id)
        assert project is not None
        await self._repository.delete(project)

    async def remove_member(
        self, *, project_id: uuid.UUID, actor_user_id: uuid.UUID, target_user_id: uuid.UUID
    ) -> None:
        """Remove a member from a project. Owner-only; the last remaining
        owner can't be removed, so a project can never end up ownerless."""
        await self.require_role(
            project_id=project_id, user_id=actor_user_id, allowed={ProjectRole.OWNER}
        )
        target = await self._repository.get_member(project_id=project_id, user_id=target_user_id)
        if target is None:
            raise NotFoundError("That user is not a member of this project.")

        if target.role == ProjectRole.OWNER:
            members = await self._repository.list_members(project_id)
            remaining_owners = [m for m in members if m.role == ProjectRole.OWNER]
            if len(remaining_owners) <= 1:
                raise ConflictError("Cannot remove the last owner of a project.")

        await self._repository.remove_member(target)
