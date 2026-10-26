"""Team roles and invitations.

Revision ID: 0013_team
Revises: 0012_quotes
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_team"
down_revision: Union[str, Sequence[str], None] = "0012_quotes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_company_memberships_role", "company_memberships", type_="check")
    op.create_check_constraint("ck_company_memberships_role", "company_memberships", "role IN ('owner', 'admin', 'member')")

    op.create_table(
        "company_invitations",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by", UUID),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_user_id", UUID),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_company_invitations_company_id_companies"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], name="fk_company_invitations_invited_by_users"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], name="fk_company_invitations_accepted_user_id_users"),
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_company_invitations_role"),
    )
    op.create_index("uq_company_invitations_token_hash", "company_invitations", ["token_hash"], unique=True)
    op.create_index(
        "uq_company_invitations_open_email",
        "company_invitations",
        ["company_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_company_invitations_open_email", table_name="company_invitations")
    op.drop_index("uq_company_invitations_token_hash", table_name="company_invitations")
    op.drop_table("company_invitations")
    op.drop_constraint("ck_company_memberships_role", "company_memberships", type_="check")
    op.create_check_constraint("ck_company_memberships_role", "company_memberships", "role IN ('owner')")
