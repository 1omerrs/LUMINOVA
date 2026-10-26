"""Tasks.

Revision ID: 0008_tasks
Revises: 0007_sales
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_tasks"
down_revision: Union[str, Sequence[str], None] = "0007_sales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(4000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("due_date", sa.Date()),
        sa.Column("assignee_user_id", UUID),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_tasks_company_id_companies"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], name="fk_tasks_assignee_user_id_users"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_tasks_created_by_users"),
        sa.CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="ck_tasks_status"),
        sa.CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_tasks_priority"),
        sa.CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_tasks_completed_at"),
    )
    op.create_index(
        "ix_tasks_company_id_status_due_date",
        "tasks",
        ["company_id", "status", "due_date"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_company_id_status_due_date", table_name="tasks")
    op.drop_table("tasks")
