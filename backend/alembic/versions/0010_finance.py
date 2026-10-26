"""Financial records and their revision history.

Revision ID: 0010_finance
Revises: 0009_projects
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_finance"
down_revision: Union[str, Sequence[str], None] = "0009_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "financial_records",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("counterparty", sa.String(160)),
        sa.Column("customer_id", UUID),
        sa.Column("order_id", UUID),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("paid_on", sa.Date()),
        sa.Column("note", sa.String(1000)),
        sa.Column("cancel_reason", sa.String(300)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_financial_records_company_id_companies"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_financial_records_customer_id_customers"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_financial_records_order_id_orders"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_financial_records_created_by_users"),
        sa.CheckConstraint("kind IN ('income', 'expense')", name="ck_financial_records_kind"),
        sa.CheckConstraint("status IN ('pending', 'paid', 'cancelled')", name="ck_financial_records_status"),
        sa.CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_financial_records_currency"),
        sa.CheckConstraint("amount > 0", name="ck_financial_records_amount"),
        sa.CheckConstraint("(status = 'paid') = (paid_on IS NOT NULL)", name="ck_financial_records_paid_on"),
        sa.CheckConstraint("order_id IS NULL OR kind = 'income'", name="ck_financial_records_order_income"),
    )
    op.create_index("ix_financial_records_company_id_record_date", "financial_records", ["company_id", "record_date"])
    op.create_index(
        "uq_financial_records_order_id",
        "financial_records",
        ["company_id", "order_id"],
        unique=True,
        postgresql_where=sa.text("order_id IS NOT NULL AND status <> 'cancelled'"),
    )

    op.create_table(
        "financial_record_revisions",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("record_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason", sa.String(300)),
        sa.Column("actor_user_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_financial_record_revisions_company_id_companies"),
        sa.ForeignKeyConstraint(["record_id"], ["financial_records.id"], name="fk_financial_record_revisions_record_id_financial_records"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_financial_record_revisions_actor_user_id_users"),
    )
    op.create_index("ix_financial_record_revisions_record_id_revision", "financial_record_revisions", ["record_id", "revision"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_financial_record_revisions_record_id_revision", table_name="financial_record_revisions")
    op.drop_table("financial_record_revisions")
    op.drop_index("uq_financial_records_order_id", table_name="financial_records")
    op.drop_index("ix_financial_records_company_id_record_date", table_name="financial_records")
    op.drop_table("financial_records")
