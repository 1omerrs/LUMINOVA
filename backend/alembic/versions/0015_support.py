"""Support tickets and messages.

Revision ID: 0015_support
Revises: 0014_notification_preferences
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_support"
down_revision: Union[str, Sequence[str], None] = "0014_notification_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("created_by", UUID, nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_support_tickets_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_support_tickets_created_by_users"),
        sa.UniqueConstraint("company_id", "number", name="uq_support_tickets_company_number"),
        sa.CheckConstraint("status IN ('open', 'answered', 'closed')", name="ck_support_tickets_status"),
        sa.CheckConstraint("category IN ('question', 'bug', 'request', 'account')", name="ck_support_tickets_category"),
    )
    op.create_index("ix_support_tickets_status_updated_at", "support_tickets", ["status", "updated_at"])
    op.create_table(
        "support_messages",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("ticket_id", UUID, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("author_user_id", UUID, nullable=False),
        sa.Column("author_kind", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], name="fk_support_messages_ticket_id_support_tickets"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_support_messages_company_id_companies"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], name="fk_support_messages_author_user_id_users"),
        sa.CheckConstraint("author_kind IN ('customer', 'staff')", name="ck_support_messages_author_kind"),
    )
    op.create_index("ix_support_messages_ticket_id_created_at", "support_messages", ["ticket_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_support_messages_ticket_id_created_at", table_name="support_messages")
    op.drop_table("support_messages")
    op.drop_index("ix_support_tickets_status_updated_at", table_name="support_tickets")
    op.drop_table("support_tickets")
