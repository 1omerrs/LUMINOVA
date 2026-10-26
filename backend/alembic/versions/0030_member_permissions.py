"""Per-member module permissions.

Revision ID: 0030_member_permissions
Revises: 0029_quote_share
Create Date: 2026-10-26

Existing members keep what they could do before: edit access to every module that is
enabled for their company. Owners and admins never need rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_member_permissions"
down_revision: Union[str, Sequence[str], None] = "0029_quote_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "member_permissions",
        sa.Column("company_id", UUID, primary_key=True, nullable=False),
        sa.Column("user_id", UUID, primary_key=True, nullable=False),
        sa.Column("module_key", sa.String(32), primary_key=True, nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_member_permissions_company_id_companies"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_member_permissions_user_id_users"),
        sa.CheckConstraint("level IN ('view', 'edit')", name="ck_member_permissions_level"),
    )
    op.add_column("company_invitations", sa.Column("permissions", postgresql.JSONB()))
    op.execute(
        """
        INSERT INTO member_permissions (company_id, user_id, module_key, level)
        SELECT m.company_id, m.user_id, c.module_key, 'edit'
        FROM company_memberships m
        JOIN company_modules c ON c.company_id = m.company_id AND c.status = 'enabled'
        WHERE m.role = 'member' AND m.status = 'active' AND c.module_key <> 'automation'
        """
    )


def downgrade() -> None:
    op.drop_column("company_invitations", "permissions")
    op.drop_table("member_permissions")
