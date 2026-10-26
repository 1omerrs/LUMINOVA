"""Projects and the task to project link.

Revision ID: 0009_projects
Revises: 0008_tasks
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_projects"
down_revision: Union[str, Sequence[str], None] = "0008_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("customer_id", UUID),
        sa.Column("start_date", sa.Date()),
        sa.Column("due_date", sa.Date()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_projects_company_id_companies"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_projects_customer_id_customers"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_projects_created_by_users"),
        sa.CheckConstraint("status IN ('planned', 'active', 'on_hold', 'completed')", name="ck_projects_status"),
        sa.CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="ck_projects_completed_at"),
        sa.CheckConstraint("start_date IS NULL OR due_date IS NULL OR start_date <= due_date", name="ck_projects_dates"),
    )
    op.create_index("ix_projects_company_id_status", "projects", ["company_id", "status"], postgresql_where=sa.text("deleted_at IS NULL"))

    op.add_column("tasks", sa.Column("project_id", UUID))
    op.create_foreign_key("fk_tasks_project_id_projects", "tasks", "projects", ["project_id"], ["id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"], postgresql_where=sa.text("deleted_at IS NULL AND project_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_constraint("fk_tasks_project_id_projects", "tasks", type_="foreignkey")
    op.drop_column("tasks", "project_id")
    op.drop_index("ix_projects_company_id_status", table_name="projects")
    op.drop_table("projects")
