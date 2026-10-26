import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

UNITS = ("adet", "kg", "g", "lt", "ml", "m", "m2", "paket", "kutu")
MOVEMENT_KINDS = ("in", "out", "adjustment")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_company_id_created_at", "company_id", "created_at"),
        Index(
            "uq_products_company_id_sku",
            "company_id",
            text("lower(sku)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(f"unit IN ({', '.join(repr(unit) for unit in UNITS)})", name="ck_products_unit"),
        CheckConstraint("min_stock >= 0", name="ck_products_min_stock"),
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_quantity"),
        CheckConstraint("critical_stock IS NULL OR critical_stock >= 0", name="ck_products_critical_stock"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_products_company_id_companies"), nullable=False)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    # None means half of min_stock.
    critical_stock: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_products_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_id_created_at", "product_id", "created_at"),
        Index(
            "uq_stock_movements_company_id_idempotency_key",
            "company_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        CheckConstraint(f"kind IN ({', '.join(repr(kind) for kind in MOVEMENT_KINDS)})", name="ck_stock_movements_kind"),
        CheckConstraint("balance_after >= 0", name="ck_stock_movements_balance_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_stock_movements_company_id_companies"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id", name="fk_stock_movements_product_id_products"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_stock_movements_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
