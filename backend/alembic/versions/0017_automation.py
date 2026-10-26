"""Webhook endpoints, automation event outbox and deliveries.

Revision ID: 0017_automation
Revises: 0016_project_milestones
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_automation"
down_revision: Union[str, Sequence[str], None] = "0016_project_milestones"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("events", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("secret_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("secret_hint", sa.String(8), nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_webhook_endpoints_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_webhook_endpoints_created_by_users"),
        sa.CheckConstraint("direction IN ('outbound', 'inbound')", name="ck_webhook_endpoints_direction"),
        sa.CheckConstraint("direction = 'inbound' OR url IS NOT NULL", name="ck_webhook_endpoints_url"),
    )
    op.create_index("ix_webhook_endpoints_company_id", "webhook_endpoints", ["company_id"], postgresql_where=sa.text("deleted_at IS NULL"))

    op.create_table(
        "automation_events",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("endpoint_id", UUID),
        sa.Column("external_id", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_automation_events_company_id_companies"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], name="fk_automation_events_endpoint_id_webhook_endpoints"),
        sa.CheckConstraint("direction IN ('outbound', 'inbound')", name="ck_automation_events_direction"),
    )
    op.create_index("ix_automation_events_company_id_created_at", "automation_events", ["company_id", "created_at"])
    op.create_index(
        "uq_automation_events_inbound_request",
        "automation_events",
        ["endpoint_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("endpoint_id", UUID, nullable=False),
        sa.Column("event_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_status_code", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_webhook_deliveries_company_id_companies"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], name="fk_webhook_deliveries_endpoint_id_webhook_endpoints"),
        sa.ForeignKeyConstraint(["event_id"], ["automation_events.id"], name="fk_webhook_deliveries_event_id_automation_events"),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'failed')", name="ck_webhook_deliveries_status"),
    )
    op.create_index("ix_webhook_deliveries_due", "webhook_deliveries", ["next_attempt_at"], postgresql_where=sa.text("status = 'pending'"))
    op.create_index("ix_webhook_deliveries_endpoint_id_created_at", "webhook_deliveries", ["endpoint_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_webhook_deliveries_endpoint_id_created_at", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_due", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("uq_automation_events_inbound_request", table_name="automation_events")
    op.drop_index("ix_automation_events_company_id_created_at", table_name="automation_events")
    op.drop_table("automation_events")
    op.drop_index("ix_webhook_endpoints_company_id", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
