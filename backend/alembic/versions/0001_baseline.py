"""Baseline migration.

Domain tables arrive with the phase that owns them. This revision starts the
migration chain and records the tenancy rule on the public schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-19
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "COMMENT ON SCHEMA public IS "
        "'LUMINOVA. Tenant-owned rows must include company_id and be read through tenant-scoped queries.'"
    )


def downgrade() -> None:
    op.execute("COMMENT ON SCHEMA public IS NULL")
