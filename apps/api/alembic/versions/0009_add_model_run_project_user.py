"""Add model_runs.project_id and model_runs.user_id

Revision ID: 0009_add_model_run_project_user
Revises: 0008_add_evaluation_runs
Create Date: 2026-09-10 09:00:00.000000

Phase 32 cost tracking: aggregating spend by project/user needs these
columns directly on model_runs rather than joined through Message or
EvaluationResult (see app/models/model_run.py's comment). No existing
ModelRun rows in any environment this project runs in (no live
deployment — IaC only, see docs/decisions), so adding them NOT NULL
needs no backfill/default.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_add_model_run_project_user"
down_revision: str | None = "0008_add_evaluation_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table: SQLite can't ALTER TABLE ADD a foreign key
    # directly (see migration 0005's comment).
    with op.batch_alter_table("model_runs") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Uuid(), nullable=False))
        batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=False))
        batch_op.create_foreign_key(
            "fk_model_runs_project_id", "projects", ["project_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_foreign_key(
            "fk_model_runs_user_id", "users", ["user_id"], ["id"], ondelete="RESTRICT"
        )
    op.create_index(op.f("ix_model_runs_project_id"), "model_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_model_runs_user_id"), "model_runs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_runs_user_id"), table_name="model_runs")
    op.drop_index(op.f("ix_model_runs_project_id"), table_name="model_runs")
    with op.batch_alter_table("model_runs") as batch_op:
        batch_op.drop_constraint("fk_model_runs_user_id", type_="foreignkey")
        batch_op.drop_constraint("fk_model_runs_project_id", type_="foreignkey")
        batch_op.drop_column("user_id")
        batch_op.drop_column("project_id")
