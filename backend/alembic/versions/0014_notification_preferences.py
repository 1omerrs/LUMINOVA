"""Notification preferences per user and category.

Revision ID: 0014_notification_preferences
Revises: 0013_team
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_notification_preferences"
down_revision: Union[str, Sequence[str], None] = "0013_team"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_notification_preferences_company_id_companies"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_notification_preferences_user_id_users"),
        sa.UniqueConstraint("user_id", "company_id", "category", name="uq_notification_preferences_user_company_category"),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
