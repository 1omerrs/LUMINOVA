"""Sales orders, order items, and status history.

Revision ID: 0007_sales
Revises: 0006_inventory
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_sales"
down_revision: Union[str, Sequence[str], None] = "0006_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("customer_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(1000)),
        sa.Column("subtotal", MONEY, nullable=False, server_default="0"),
        sa.Column("vat_total", MONEY, nullable=False, server_default="0"),
        sa.Column("total", MONEY, nullable=False, server_default="0"),
        sa.Column("stock_posted_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_orders_company_id_companies"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_orders_customer_id_customers"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_orders_created_by_users"),
        sa.UniqueConstraint("company_id", "number", name="uq_orders_company_id_number"),
        sa.CheckConstraint("status IN ('draft', 'confirmed', 'fulfilled', 'cancelled')", name="ck_orders_status"),
        sa.CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_orders_currency"),
    )
    op.create_index("ix_orders_company_id_created_at", "orders", ["company_id", "created_at"])

    op.create_table(
        "order_items",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", UUID),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", MONEY, nullable=False),
        sa.Column("unit_price", MONEY, nullable=False),
        sa.Column("vat_rate", sa.Integer(), nullable=False),
        sa.Column("line_subtotal", MONEY, nullable=False),
        sa.Column("line_vat", MONEY, nullable=False),
        sa.Column("line_total", MONEY, nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_order_items_company_id_companies"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_items_order_id_orders"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_order_items_product_id_products"),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        sa.CheckConstraint("vat_rate IN (0, 1, 10, 20)", name="ck_order_items_vat_rate"),
    )
    op.create_index("ix_order_items_order_id_position", "order_items", ["order_id", "position"])

    op.create_table(
        "order_status_events",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("actor_user_id", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_order_status_events_company_id_companies"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_status_events_order_id_orders"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_order_status_events_actor_user_id_users"),
    )
    op.create_index("ix_order_status_events_order_id_created_at", "order_status_events", ["order_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_order_status_events_order_id_created_at", table_name="order_status_events")
    op.drop_table("order_status_events")
    op.drop_index("ix_order_items_order_id_position", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_company_id_created_at", table_name="orders")
    op.drop_table("orders")
