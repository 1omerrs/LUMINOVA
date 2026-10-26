"""Project milestones.

Revision ID: 0016_project_milestones
Revises: 0015_support
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_project_milestones"
down_revision: Union[str, Sequence[str], None] = "0015_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "project_milestones",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_project_milestones_company_id_companies"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_milestones_project_id_projects"),
    )
    op.create_index("ix_project_milestones_project_id_position", "project_milestones", ["project_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_project_milestones_project_id_position", table_name="project_milestones")
    op.drop_table("project_milestones")
