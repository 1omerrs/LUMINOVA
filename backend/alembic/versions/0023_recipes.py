"""Product recipes (bill of materials) and the production-on-shortage sales rule.

Revision ID: 0023_recipes
Revises: 0022_sales_rules
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_recipes"
down_revision: Union[str, Sequence[str], None] = "0022_sales_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "recipe_items",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("product_id", UUID, nullable=False),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("quantity", sa.Numeric(19, 4), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_recipe_items_company_id_companies"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_recipe_items_product_id_products"),
        sa.ForeignKeyConstraint(["material_id"], ["products.id"], name="fk_recipe_items_material_id_products"),
        sa.UniqueConstraint("product_id", "material_id", name="uq_recipe_items_product_id_material_id"),
        sa.CheckConstraint("quantity > 0", name="ck_recipe_items_quantity"),
        sa.CheckConstraint("product_id <> material_id", name="ck_recipe_items_not_self"),
    )
    op.create_index("ix_recipe_items_company_id_product_id", "recipe_items", ["company_id", "product_id"])
    op.add_column("sales_rules", sa.Column("production_on_shortage", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("sales_rules", "production_on_shortage")
    op.drop_index("ix_recipe_items_company_id_product_id", table_name="recipe_items")
    op.drop_table("recipe_items")
