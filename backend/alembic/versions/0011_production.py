"""Production orders and their materials.

Revision ID: 0011_production
Revises: 0010_finance
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_production"
down_revision: Union[str, Sequence[str], None] = "0010_finance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
QUANTITY = sa.Numeric(19, 4)


def upgrade() -> None:
    op.create_table(
        "production_orders",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("planned_date", sa.Date()),
        sa.Column("note", sa.String(1000)),
        sa.Column("cancel_reason", sa.String(300)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("stock_posted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_production_orders_company_id_companies"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_production_orders_product_id_products"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_production_orders_created_by_users"),
        sa.UniqueConstraint("company_id", "number", name="uq_production_orders_company_id_number"),
        sa.CheckConstraint("status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_production_orders_status"),
        sa.CheckConstraint("quantity > 0", name="ck_production_orders_quantity"),
        sa.CheckConstraint("(status = 'completed') = (stock_posted_at IS NOT NULL)", name="ck_production_orders_posted"),
    )
    op.create_index("ix_production_orders_company_id_created_at", "production_orders", ["company_id", "created_at"])

    op.create_table(
        "production_materials",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("order_id", UUID, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("quantity", QUANTITY, nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_production_materials_company_id_companies"),
        sa.ForeignKeyConstraint(["order_id"], ["production_orders.id"], name="fk_production_materials_order_id_production_orders"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_production_materials_product_id_products"),
        sa.UniqueConstraint("order_id", "product_id", name="uq_production_materials_order_id_product_id"),
        sa.CheckConstraint("quantity > 0", name="ck_production_materials_quantity"),
    )


def downgrade() -> None:
    op.drop_table("production_materials")
    op.drop_index("ix_production_orders_company_id_created_at", table_name="production_orders")
    op.drop_table("production_orders")
