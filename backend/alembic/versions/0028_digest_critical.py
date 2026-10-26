"""Critical stock level per product and weekly digest e-mails.

Revision ID: 0028_digest_critical
Revises: 0027_email_outbox
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_digest_critical"
down_revision: Union[str, Sequence[str], None] = "0027_email_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("critical_stock", sa.Numeric(19, 4)))
    op.create_check_constraint("ck_products_critical_stock", "products", "critical_stock IS NULL OR critical_stock >= 0")
    op.drop_constraint("ck_email_messages_kind", "email_messages", type_="check")
    op.create_check_constraint(
        "ck_email_messages_kind", "email_messages", "kind IN ('verify_email', 'password_reset', 'invitation', 'notification', 'digest')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM email_messages WHERE kind = 'digest'")
    op.drop_constraint("ck_email_messages_kind", "email_messages", type_="check")
    op.create_check_constraint("ck_email_messages_kind", "email_messages", "kind IN ('verify_email', 'password_reset', 'invitation', 'notification')")
    op.drop_constraint("ck_products_critical_stock", "products", type_="check")
    op.drop_column("products", "critical_stock")
