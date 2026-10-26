import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_production_orders_company_id_number"),
        Index("ix_production_orders_company_id_created_at", "company_id", "created_at"),
        CheckConstraint("status IN ('planned', 'in_progress', 'completed', 'cancelled')", name="ck_production_orders_status"),
        CheckConstraint("quantity > 0", name="ck_production_orders_quantity"),
        CheckConstraint("(status = 'completed') = (stock_posted_at IS NOT NULL)", name="ck_production_orders_posted"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_production_orders_company_id_companies"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", name="fk_production_orders_product_id_products"), nullable=False)
    sales_order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", name="fk_production_orders_sales_order_id_orders"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", name="fk_production_orders_project_id_projects"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned", server_default="planned")
    planned_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(1000))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stock_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_production_orders_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RecipeItem(Base):
    """One material needed to make a single unit of `product_id`."""

    __tablename__ = "recipe_items"
    __table_args__ = (
        UniqueConstraint("product_id", "material_id", name="uq_recipe_items_product_id_material_id"),
        Index("ix_recipe_items_company_id_product_id", "company_id", "product_id"),
        CheckConstraint("quantity > 0", name="ck_recipe_items_quantity"),
        CheckConstraint("product_id <> material_id", name="ck_recipe_items_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_recipe_items_company_id_companies"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", name="fk_recipe_items_product_id_products"), nullable=False)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", name="fk_recipe_items_material_id_products"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProductionMaterial(Base):
    __tablename__ = "production_materials"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_production_materials_order_id_product_id"),
        CheckConstraint("quantity > 0", name="ck_production_materials_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_production_materials_company_id_companies"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("production_orders.id", name="fk_production_materials_order_id_production_orders"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", name="fk_production_materials_product_id_products"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
