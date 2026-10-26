"""Inventory products and stock movements.

Revision ID: 0006_inventory
Revises: 0005_customers
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_inventory"
down_revision: Union[str, Sequence[str], None] = "0005_customers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UNITS = "'adet', 'kg', 'g', 'lt', 'ml', 'm', 'm2', 'paket', 'kutu'"


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("min_stock", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("stock_quantity", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_products_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_products_created_by_users"),
        sa.CheckConstraint(f"unit IN ({UNITS})", name="ck_products_unit"),
        sa.CheckConstraint("min_stock >= 0", name="ck_products_min_stock"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_products_stock_quantity"),
    )
    op.create_index("ix_products_company_id_created_at", "products", ["company_id", "created_at"])
    op.create_index(
        "uq_products_company_id_sku",
        "products",
        ["company_id", sa.text("lower(sku)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(19, 4), nullable=False),
        sa.Column("note", sa.String(300)),
        sa.Column("reference_type", sa.String(40)),
        sa.Column("reference_id", sa.String(64)),
        sa.Column("idempotency_key", sa.String(80)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_stock_movements_company_id_companies"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_stock_movements_product_id_products"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_stock_movements_created_by_users"),
        sa.CheckConstraint("kind IN ('in', 'out', 'adjustment')", name="ck_stock_movements_kind"),
        sa.CheckConstraint("balance_after >= 0", name="ck_stock_movements_balance_after"),
    )
    op.create_index("ix_stock_movements_product_id_created_at", "stock_movements", ["product_id", "created_at"])
    op.create_index(
        "uq_stock_movements_company_id_idempotency_key",
        "stock_movements",
        ["company_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_stock_movements_company_id_idempotency_key", table_name="stock_movements")
    op.drop_index("ix_stock_movements_product_id_created_at", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("uq_products_company_id_sku", table_name="products")
    op.drop_index("ix_products_company_id_created_at", table_name="products")
    op.drop_table("products")
