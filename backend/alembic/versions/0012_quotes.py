"""Quotes and quote items.

Revision ID: 0012_quotes
Revises: 0011_production
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_quotes"
down_revision: Union[str, Sequence[str], None] = "0011_production"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("customer_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date()),
        sa.Column("note", sa.String(1000)),
        sa.Column("subtotal", MONEY, nullable=False, server_default="0"),
        sa.Column("vat_total", MONEY, nullable=False, server_default="0"),
        sa.Column("total", MONEY, nullable=False, server_default="0"),
        sa.Column("order_id", UUID),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_quotes_company_id_companies"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_quotes_customer_id_customers"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_quotes_order_id_orders"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_quotes_created_by_users"),
        sa.UniqueConstraint("company_id", "number", name="uq_quotes_company_id_number"),
        sa.UniqueConstraint("order_id", name="uq_quotes_order_id"),
        sa.CheckConstraint("status IN ('draft', 'sent', 'accepted', 'rejected')", name="ck_quotes_status"),
        sa.CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_quotes_currency"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= quote_date", name="ck_quotes_valid_until"),
        sa.CheckConstraint("order_id IS NULL OR status = 'accepted'", name="ck_quotes_order_accepted"),
    )
    op.create_index("ix_quotes_company_id_created_at", "quotes", ["company_id", "created_at"])

    op.create_table(
        "quote_items",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("quote_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", UUID),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("unit_price", MONEY, nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("line_subtotal", MONEY, nullable=False),
        sa.Column("line_vat", MONEY, nullable=False),
        sa.Column("line_total", MONEY, nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_quote_items_company_id_companies"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], name="fk_quote_items_quote_id_quotes"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_quote_items_product_id_products"),
        sa.CheckConstraint("quantity > 0", name="ck_quote_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_quote_items_unit_price"),
        sa.CheckConstraint("vat_rate IN (0, 1, 10, 20)", name="ck_quote_items_vat_rate"),
    )
    op.create_index("ix_quote_items_quote_id_position", "quote_items", ["quote_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_quote_items_quote_id_position", table_name="quote_items")
    op.drop_table("quote_items")
    op.drop_index("ix_quotes_company_id_created_at", table_name="quotes")
    op.drop_table("quotes")
