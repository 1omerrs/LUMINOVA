"""Company join codes, member self sign-up with manager approval, company profile answers.

Revision ID: 0031_join_requests
Revises: 0030_member_permissions
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_join_requests"
down_revision: Union[str, Sequence[str], None] = "0030_member_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("companies", sa.Column("join_code", sa.String(16)))
    op.add_column("companies", sa.Column("sector", sa.String(40)))
    op.add_column("companies", sa.Column("team_size", sa.String(16)))
    # Eight characters without look-alikes (0/O, 1/I), shown as XXXX-XXXX.
    op.execute(
        """
        UPDATE companies SET join_code = (
            SELECT string_agg(substr('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', 1 + floor(random() * 32)::int, 1), '')
            FROM generate_series(1, 8) WHERE companies.id IS NOT NULL
        )
        """
    )
    op.execute("UPDATE companies SET join_code = substr(join_code, 1, 4) || '-' || substr(join_code, 5, 4)")
    op.alter_column("companies", "join_code", nullable=False)
    op.create_index("uq_companies_join_code", "companies", ["join_code"], unique=True)

    op.create_table(
        "join_requests",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("position", sa.String(80)),
        sa.Column("note", sa.String(300)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", UUID),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_join_requests_company_id_companies"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_join_requests_user_id_users"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], name="fk_join_requests_decided_by_users"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_join_requests_status"),
    )
    op.create_index("uq_join_requests_open_user", "join_requests", ["user_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index("ix_join_requests_company_status", "join_requests", ["company_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_join_requests_company_status", table_name="join_requests")
    op.drop_index("uq_join_requests_open_user", table_name="join_requests")
    op.drop_table("join_requests")
    op.drop_index("uq_companies_join_code", table_name="companies")
    op.drop_column("companies", "team_size")
    op.drop_column("companies", "sector")
    op.drop_column("companies", "join_code")
