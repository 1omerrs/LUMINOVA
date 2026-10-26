"""Customer-facing quote link and quote e-mails.

Revision ID: 0029_quote_share
Revises: 0028_digest_critical
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_quote_share"
down_revision: Union[str, Sequence[str], None] = "0028_digest_critical"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = "'verify_email', 'password_reset', 'invitation', 'notification', 'digest'"


def upgrade() -> None:
    op.add_column("quotes", sa.Column("share_token_hash", sa.String(64)))
    op.add_column("quotes", sa.Column("decided_by", sa.String(16)))
    op.add_column("quotes", sa.Column("customer_note", sa.String(500)))
    op.create_index("uq_quotes_share_token_hash", "quotes", ["share_token_hash"], unique=True, postgresql_where=sa.text("share_token_hash IS NOT NULL"))
    op.create_check_constraint("ck_quotes_decided_by", "quotes", "decided_by IS NULL OR decided_by IN ('staff', 'customer')")
    op.add_column("email_messages", sa.Column("reply_to", sa.String(320)))
    op.drop_constraint("ck_email_messages_kind", "email_messages", type_="check")
    op.create_check_constraint("ck_email_messages_kind", "email_messages", f"kind IN ({KINDS}, 'quote')")


def downgrade() -> None:
    op.execute("DELETE FROM email_messages WHERE kind = 'quote'")
    op.drop_constraint("ck_email_messages_kind", "email_messages", type_="check")
    op.create_check_constraint("ck_email_messages_kind", "email_messages", f"kind IN ({KINDS})")
    op.drop_column("email_messages", "reply_to")
    op.drop_constraint("ck_quotes_decided_by", "quotes", type_="check")
    op.drop_index("uq_quotes_share_token_hash", table_name="quotes")
    op.drop_column("quotes", "customer_note")
    op.drop_column("quotes", "decided_by")
    op.drop_column("quotes", "share_token_hash")
