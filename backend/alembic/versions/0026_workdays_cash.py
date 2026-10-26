"""Working-day project scheduling and opening cash balances.

Revision ID: 0026_workdays_cash
Revises: 0025_autopilot
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026_workdays_cash"
down_revision: Union[str, Sequence[str], None] = "0025_autopilot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("projects", sa.Column("working_days_only", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "cash_balances",
        sa.Column("company_id", UUID, primary_key=True, nullable=False),
        sa.Column("currency", sa.String(3), primary_key=True, nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("updated_by", UUID),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_cash_balances_company_id_companies"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_cash_balances_updated_by_users"),
        sa.CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_cash_balances_currency"),
    )


def downgrade() -> None:
    op.drop_table("cash_balances")
    op.drop_column("projects", "working_days_only")
