"""Project templates and planned task scheduling (start date and duration).

Revision ID: 0021_project_planning
Revises: 0020_task_workflow
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_project_planning"
down_revision: Union[str, Sequence[str], None] = "0020_task_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("tasks", sa.Column("start_date", sa.Date()))
    op.add_column("tasks", sa.Column("duration_days", sa.Integer()))
    op.add_column("tasks", sa.Column("milestone_id", UUID))
    op.create_foreign_key("fk_tasks_milestone_id_project_milestones", "tasks", "project_milestones", ["milestone_id"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_tasks_duration_days", "tasks", "duration_days IS NULL OR duration_days BETWEEN 1 AND 365")
    op.create_table(
        "project_templates",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("items", JSONB, nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_project_templates_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_project_templates_created_by_users"),
    )
    op.create_index("ix_project_templates_company_id", "project_templates", ["company_id"], postgresql_where=sa.text("deleted_at IS NULL"))
    op.add_column("projects", sa.Column("template_id", UUID))
    op.create_foreign_key("fk_projects_template_id_project_templates", "projects", "project_templates", ["template_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_projects_template_id_project_templates", "projects", type_="foreignkey")
    op.drop_column("projects", "template_id")
    op.drop_index("ix_project_templates_company_id", table_name="project_templates")
    op.drop_table("project_templates")
    op.drop_constraint("ck_tasks_duration_days", "tasks", type_="check")
    op.drop_constraint("fk_tasks_milestone_id_project_milestones", "tasks", type_="foreignkey")
    op.drop_column("tasks", "milestone_id")
    op.drop_column("tasks", "duration_days")
    op.drop_column("tasks", "start_date")
