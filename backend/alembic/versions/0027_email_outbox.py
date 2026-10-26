"""Outgoing e-mail queue handed to n8n.

Revision ID: 0027_email_outbox
Revises: 0026_workdays_cash
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_email_outbox"
down_revision: Union[str, Sequence[str], None] = "0026_workdays_cash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "email_messages",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID),
        sa.Column("user_id", UUID),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("ref", sa.String(80)),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body_text", sa.Text()),
        sa.Column("body_html", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(400)),
        sa.Column("provider_message_id", sa.String(200)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("handed_off_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_email_messages_company_id_companies"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_email_messages_user_id_users"),
        sa.CheckConstraint("kind IN ('verify_email', 'password_reset', 'invitation', 'notification')", name="ck_email_messages_kind"),
        sa.CheckConstraint("status IN ('queued', 'handed_off', 'sent', 'failed')", name="ck_email_messages_status"),
    )
    op.create_index("ix_email_messages_due", "email_messages", ["status", "next_attempt_at"])
    op.create_index("ix_email_messages_created_at", "email_messages", ["created_at"])
    op.create_index("ix_email_messages_ref", "email_messages", ["ref"])


def downgrade() -> None:
    op.drop_index("ix_email_messages_ref", table_name="email_messages")
    op.drop_index("ix_email_messages_created_at", table_name="email_messages")
    op.drop_index("ix_email_messages_due", table_name="email_messages")
    op.drop_table("email_messages")
