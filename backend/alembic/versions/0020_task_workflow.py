"""Task dependencies, task templates and template runs.

Revision ID: 0020_task_workflow
Revises: 0019_relations
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_task_workflow"
down_revision: Union[str, Sequence[str], None] = "0019_relations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("depends_on_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_task_dependencies_company_id_companies"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_dependencies_task_id_tasks"),
        sa.ForeignKeyConstraint(["depends_on_id"], ["tasks.id"], name="fk_task_dependencies_depends_on_id_tasks"),
        sa.UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependencies_pair"),
        sa.CheckConstraint("task_id <> depends_on_id", name="ck_task_dependencies_not_self"),
    )
    op.create_index("ix_task_dependencies_depends_on_id", "task_dependencies", ["depends_on_id"])

    op.create_table(
        "task_templates",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("items", JSONB, nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_task_templates_company_id_companies"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_task_templates_created_by_users"),
    )
    op.create_index("ix_task_templates_company_id", "task_templates", ["company_id"], postgresql_where=sa.text("deleted_at IS NULL"))

    op.create_table(
        "task_template_runs",
        sa.Column("id", UUID, primary_key=True, nullable=False),
        sa.Column("company_id", UUID, nullable=False),
        sa.Column("template_id", UUID, nullable=False),
        sa.Column("target_key", sa.String(80)),
        sa.Column("task_count", sa.Integer(), nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_task_template_runs_company_id_companies"),
        sa.ForeignKeyConstraint(["template_id"], ["task_templates.id"], name="fk_task_template_runs_template_id_task_templates"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_task_template_runs_created_by_users"),
    )
    op.create_index(
        "uq_task_template_runs_target",
        "task_template_runs",
        ["company_id", "template_id", "target_key"],
        unique=True,
        postgresql_where=sa.text("target_key IS NOT NULL"),
    )
    op.add_column("tasks", sa.Column("template_run_id", UUID))
    op.create_foreign_key("fk_tasks_template_run_id_task_template_runs", "tasks", "task_template_runs", ["template_run_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_tasks_template_run_id_task_template_runs", "tasks", type_="foreignkey")
    op.drop_column("tasks", "template_run_id")
    op.drop_index("uq_task_template_runs_target", table_name="task_template_runs")
    op.drop_table("task_template_runs")
    op.drop_index("ix_task_templates_company_id", table_name="task_templates")
    op.drop_table("task_templates")
    op.drop_index("ix_task_dependencies_depends_on_id", table_name="task_dependencies")
    op.drop_table("task_dependencies")
