"""Six-digit e-mail verification codes next to the link token.

Revision ID: 0033_verification_codes
Revises: 0032_support_kinds
Create Date: 2026-10-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_verification_codes"
down_revision: Union[str, Sequence[str], None] = "0032_support_kinds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_verification_tokens", sa.Column("code_hash", sa.String(64)))
    op.add_column("email_verification_tokens", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_column("email_verification_tokens", "attempts")
    op.drop_column("email_verification_tokens", "code_hash")
