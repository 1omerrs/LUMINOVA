"""Workspace closure requests.

Revision ID: 0018_closure_requests
Revises: 0017_automation
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_closure_requests"
down_revision: Union[str, Sequence[str], None] = "0017_automation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "closure_requests",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("requested_by", UUID, nullable=False),
        sa.Column("reason", sa.String(1000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_closure_requests_company_id_companies"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], name="fk_closure_requests_requested_by_users"),
        sa.ForeignKeyConstraint(["completed_by"], ["users.id"], name="fk_closure_requests_completed_by_users"),
        sa.CheckConstraint("status IN ('pending', 'cancelled', 'completed')", name="ck_closure_requests_status"),
    )
    op.create_index("uq_closure_requests_pending_company", "closure_requests", ["company_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index("uq_closure_requests_pending_company", table_name="closure_requests")
    op.drop_table("closure_requests")
