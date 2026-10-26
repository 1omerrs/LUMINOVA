"""Complaint and LUMINOVA-initiated support conversations.

Revision ID: 0032_support_kinds
Revises: 0031_join_requests
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_support_kinds"
down_revision: Union[str, Sequence[str], None] = "0031_join_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_support_tickets_category", "support_tickets", type_="check")
    op.create_check_constraint(
        "ck_support_tickets_category", "support_tickets", "category IN ('question', 'bug', 'request', 'account', 'complaint', 'notice')"
    )
    op.add_column("support_tickets", sa.Column("opened_by_staff", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("support_tickets", "opened_by_staff")
    op.execute("UPDATE support_tickets SET category = 'question' WHERE category IN ('complaint', 'notice')")
    op.drop_constraint("ck_support_tickets_category", "support_tickets", type_="check")
    op.create_check_constraint("ck_support_tickets_category", "support_tickets", "category IN ('question', 'bug', 'request', 'account')")
