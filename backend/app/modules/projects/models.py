import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROJECT_STATUSES = ("planned", "active", "on_hold", "completed")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_company_id_status", "company_id", "status", postgresql_where=text("deleted_at IS NULL")),
        CheckConstraint("status IN ('planned', 'active', 'on_hold', 'completed')", name="ck_projects_status"),
        CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="ck_projects_completed_at"),
        CheckConstraint("start_date IS NULL OR due_date IS NULL OR start_date <= due_date", name="ck_projects_dates"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_projects_company_id_companies"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned", server_default="planned")
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", name="fk_projects_customer_id_customers"))
    quote_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quotes.id", name="fk_projects_quote_id_quotes"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", name="fk_projects_order_id_orders"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_templates.id", name="fk_projects_template_id_project_templates"))
    working_days_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    start_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_projects_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectTemplate(Base):
    __tablename__ = "project_templates"
    __table_args__ = (Index("ix_project_templates_company_id", "company_id", postgresql_where=text("deleted_at IS NULL")),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_project_templates_company_id_companies"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    items: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_project_templates_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectMilestone(Base):
    __tablename__ = "project_milestones"
    __table_args__ = (Index("ix_project_milestones_project_id_position", "project_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_project_milestones_company_id_companies"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", name="fk_project_milestones_project_id_projects"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
