"""Partial payments for financial records.

Existing paid records get a single payment for their full amount on their paid date,
so balances and cash flow stay correct after the upgrade.

Revision ID: 0024_payments
Revises: 0023_recipes
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_payments"
down_revision: Union[str, Sequence[str], None] = "0023_recipes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "financial_payments",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("record_id", UUID, nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False, server_default="transfer"),
        sa.Column("note", sa.String(300)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_financial_payments_company_id_companies"),
        sa.ForeignKeyConstraint(["record_id"], ["financial_records.id"], name="fk_financial_payments_record_id_financial_records"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_financial_payments_created_by_users"),
        sa.CheckConstraint("amount > 0", name="ck_financial_payments_amount"),
        sa.CheckConstraint("method IN ('cash', 'transfer', 'card', 'check', 'other')", name="ck_financial_payments_method"),
    )
    op.create_index("ix_financial_payments_record_id", "financial_payments", ["record_id"])
    op.create_index("ix_financial_payments_company_id_paid_on", "financial_payments", ["company_id", "paid_on"])
    op.add_column("financial_records", sa.Column("paid_amount", sa.Numeric(19, 4), nullable=False, server_default="0"))
    op.execute(
        """
        INSERT INTO financial_payments (id, company_id, record_id, amount, paid_on, method, note, created_by, created_at)
        SELECT gen_random_uuid(), company_id, id, amount, paid_on, 'transfer', 'Önceki tam ödeme kaydından aktarıldı.', created_by, updated_at
        FROM financial_records WHERE status = 'paid' AND paid_on IS NOT NULL
        """
    )
    op.execute("UPDATE financial_records SET paid_amount = amount WHERE status = 'paid'")
    op.drop_constraint("ck_financial_records_status", "financial_records", type_="check")
    op.create_check_constraint("ck_financial_records_status", "financial_records", "status IN ('pending', 'partial', 'paid', 'cancelled')")
    op.create_check_constraint("ck_financial_records_paid_amount", "financial_records", "paid_amount >= 0 AND paid_amount <= amount")


def downgrade() -> None:
    op.drop_constraint("ck_financial_records_paid_amount", "financial_records", type_="check")
    op.execute("UPDATE financial_records SET status = 'pending' WHERE status = 'partial'")
    op.drop_constraint("ck_financial_records_status", "financial_records", type_="check")
    op.create_check_constraint("ck_financial_records_status", "financial_records", "status IN ('pending', 'paid', 'cancelled')")
    op.drop_column("financial_records", "paid_amount")
    op.drop_index("ix_financial_payments_company_id_paid_on", table_name="financial_payments")
    op.drop_index("ix_financial_payments_record_id", table_name="financial_payments")
    op.drop_table("financial_payments")
