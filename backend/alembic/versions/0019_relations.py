"""Cross-module links: tasks to customers and orders, projects to quotes and orders,
production orders to sales orders and projects. All columns are nullable, so existing
rows stay valid.

Revision ID: 0019_relations
Revises: 0018_closure_requests
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_relations"
down_revision: Union[str, Sequence[str], None] = "0018_closure_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
LINKS = (
    ("tasks", "customer_id", "customers"),
    ("tasks", "order_id", "orders"),
    ("projects", "quote_id", "quotes"),
    ("projects", "order_id", "orders"),
    ("production_orders", "sales_order_id", "orders"),
    ("production_orders", "project_id", "projects"),
)


def upgrade() -> None:
    for table, column, target in LINKS:
        op.add_column(table, sa.Column(column, UUID))
        op.create_foreign_key(f"fk_{table}_{column}_{target}", table, target, [column], ["id"])
        op.create_index(f"ix_{table}_{column}", table, [column], postgresql_where=sa.text(f"{column} IS NOT NULL"))


def downgrade() -> None:
    for table, column, target in reversed(LINKS):
        op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_constraint(f"fk_{table}_{column}_{target}", table, type_="foreignkey")
        op.drop_column(table, column)
