import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TASK_STATUSES = ("todo", "in_progress", "done")
TASK_PRIORITIES = ("low", "normal", "high", "urgent")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_company_id_status_due_date", "company_id", "status", "due_date", postgresql_where=text("deleted_at IS NULL")),
        Index("ix_tasks_project_id", "project_id", postgresql_where=text("deleted_at IS NULL AND project_id IS NOT NULL")),
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),
        CheckConstraint(_in("priority", TASK_PRIORITIES), name="ck_tasks_priority"),
        CheckConstraint("(status = 'done') = (completed_at IS NOT NULL)", name="ck_tasks_completed_at"),
        CheckConstraint("duration_days IS NULL OR duration_days BETWEEN 1 AND 365", name="ck_tasks_duration_days"),
        Index(
            "uq_tasks_open_source_key",
            "company_id",
            "source_key",
            unique=True,
            postgresql_where=text("source_key IS NOT NULL AND status <> 'done' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_tasks_company_id_companies"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="todo", server_default="todo")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal", server_default="normal")
    due_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_tasks_assignee_user_id_users"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", name="fk_tasks_project_id_projects"))
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_milestones.id", name="fk_tasks_milestone_id_project_milestones", ondelete="SET NULL")
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", name="fk_tasks_customer_id_customers"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", name="fk_tasks_order_id_orders"))
    template_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task_template_runs.id", name="fk_tasks_template_run_id_task_template_runs"))
    source_key: Mapped[str | None] = mapped_column(String(120))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_tasks_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependencies_pair"),
        CheckConstraint("task_id <> depends_on_id", name="ck_task_dependencies_not_self"),
        Index("ix_task_dependencies_depends_on_id", "depends_on_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_task_dependencies_company_id_companies"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", name="fk_task_dependencies_task_id_tasks"), nullable=False)
    depends_on_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", name="fk_task_dependencies_depends_on_id_tasks"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TaskTemplate(Base):
    __tablename__ = "task_templates"
    __table_args__ = (Index("ix_task_templates_company_id", "company_id", postgresql_where=text("deleted_at IS NULL")),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_task_templates_company_id_companies"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    items: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_task_templates_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutopilotSettings(Base):
    __tablename__ = "autopilot_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_autopilot_settings_company_id_companies"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    kinds: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    default_assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_autopilot_settings_default_assignee_id_users"))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TaskTemplateRun(Base):
    __tablename__ = "task_template_runs"
    __table_args__ = (
        Index("uq_task_template_runs_target", "company_id", "template_id", "target_key", unique=True, postgresql_where=text("target_key IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_task_template_runs_company_id_companies"), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_templates.id", name="fk_task_template_runs_template_id_task_templates"), nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(80))
    task_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_task_template_runs_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())