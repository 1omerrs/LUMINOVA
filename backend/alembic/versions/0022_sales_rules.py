"""Line discounts on quotes and orders, and per-company sales workflow rules.

Revision ID: 0022_sales_rules
Revises: 0021_project_planning
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_sales_rules"
down_revision: Union[str, Sequence[str], None] = "0021_project_planning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(19, 4)


def upgrade() -> None:
    for items, header in (("order_items", "orders"), ("quote_items", "quotes")):
        op.add_column(items, sa.Column("discount_rate", sa.Numeric(5, 2), nullable=False, server_default="0"))
        op.add_column(items, sa.Column("line_discount", MONEY, nullable=False, server_default="0"))
        op.create_check_constraint(f"ck_{items}_discount_rate", items, "discount_rate >= 0 AND discount_rate <= 100")
        op.add_column(header, sa.Column("discount_total", MONEY, nullable=False, server_default="0"))
    op.create_table(
        "sales_rules",
        sa.Column("company_id", UUID, primary_key=True, nullable=False),
        sa.Column("income_on", sa.String(16), nullable=False, server_default="off"),
        sa.Column("income_due_days", sa.Integer()),
        sa.Column("confirm_template_id", UUID),
        sa.Column("updated_by", UUID),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_sales_rules_company_id_companies"),
        sa.ForeignKeyConstraint(["confirm_template_id"], ["task_templates.id"], name="fk_sales_rules_confirm_template_id_task_templates"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_sales_rules_updated_by_users"),
        sa.CheckConstraint("income_on IN ('off', 'confirmed', 'fulfilled')", name="ck_sales_rules_income_on"),
        sa.CheckConstraint("income_due_days IS NULL OR income_due_days BETWEEN 0 AND 365", name="ck_sales_rules_income_due_days"),
    )


def downgrade() -> None:
    op.drop_table("sales_rules")
    for items, header in (("order_items", "orders"), ("quote_items", "quotes")):
        op.drop_column(header, "discount_total")
        op.drop_constraint(f"ck_{items}_discount_rate", items, type_="check")
        op.drop_column(items, "line_discount")
        op.drop_column(items, "discount_rate")
