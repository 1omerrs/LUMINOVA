"""Customers module records.

Revision ID: 0005_customers
Revises: 0004_onboarding
Create Date: 2026-10-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_customers"
down_revision: Union[str, Sequence[str], None] = "0004_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("phone", sa.String(40)),
        sa.Column("note", sa.String(1000)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_customers_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_customers_created_by_users"),
    )
    op.create_index("ix_customers_company_id_created_at", "customers", ["company_id", "created_at"])
    op.create_index(
        "uq_customers_company_id_email",
        "customers",
        ["company_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_customers_company_id_email", table_name="customers")
    op.drop_index("ix_customers_company_id_created_at", table_name="customers")
    op.drop_table("customers")
