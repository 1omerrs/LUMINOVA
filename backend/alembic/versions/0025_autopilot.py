"""Automatic tasks generated from business signals.

Revision ID: 0025_autopilot
Revises: 0024_payments
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_autopilot"
down_revision: Union[str, Sequence[str], None] = "0024_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("tasks", sa.Column("source_key", sa.String(120)))
    op.create_index(
        "uq_tasks_open_source_key",
        "tasks",
        ["company_id", "source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL AND status <> 'done' AND deleted_at IS NULL"),
    )
    op.create_table(
        "autopilot_settings",
        sa.Column("company_id", UUID, primary_key=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("kinds", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("default_assignee_id", UUID),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_autopilot_settings_company_id_companies"),
        sa.ForeignKeyConstraint(["default_assignee_id"], ["users.id"], name="fk_autopilot_settings_default_assignee_id_users"),
    )


def downgrade() -> None:
    op.drop_table("autopilot_settings")
    op.drop_index("uq_tasks_open_source_key", table_name="tasks")
    op.drop_column("tasks", "source_key")
