import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ORDER_STATUSES = ("draft", "confirmed", "fulfilled", "cancelled")
CURRENCIES = ("TRY", "USD", "EUR")
VAT_RATES = (0, 1, 10, 20)


def _in(column: str, values: tuple[object, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class SalesOrder(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_orders_company_id_number"),
        Index("ix_orders_company_id_created_at", "company_id", "created_at"),
        CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),
        CheckConstraint(_in("currency", CURRENCIES), name="ck_orders_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_orders_company_id_companies"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", name="fk_orders_customer_id_customers"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY", server_default="TRY")
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    vat_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    stock_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_orders_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id_position", "order_id", "position"),
        CheckConstraint("quantity > 0", name="ck_order_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price"),
        CheckConstraint(_in("vat_rate", VAT_RATES), name="ck_order_items_vat_rate"),
        CheckConstraint("discount_rate >= 0 AND discount_rate <= 100", name="ck_order_items_discount_rate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_order_items_company_id_companies"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", name="fk_order_items_order_id_orders"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", name="fk_order_items_product_id_products"))
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal(0), server_default="0")
    line_discount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_vat: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)


class SalesRules(Base):
    __tablename__ = "sales_rules"
    __table_args__ = (
        CheckConstraint("income_on IN ('off', 'confirmed', 'fulfilled')", name="ck_sales_rules_income_on"),
        CheckConstraint("income_due_days IS NULL OR income_due_days BETWEEN 0 AND 365", name="ck_sales_rules_income_due_days"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_sales_rules_company_id_companies"), primary_key=True)
    income_on: Mapped[str] = mapped_column(String(16), nullable=False, default="off", server_default="off")
    income_due_days: Mapped[int | None] = mapped_column(Integer)
    production_on_shortage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    confirm_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("task_templates.id", name="fk_sales_rules_confirm_template_id_task_templates")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_sales_rules_updated_by_users"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OrderStatusEvent(Base):
    __tablename__ = "order_status_events"
    __table_args__ = (Index("ix_order_status_events_order_id_created_at", "order_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_order_status_events_company_id_companies"), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", name="fk_order_status_events_order_id_orders"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_order_status_events_actor_user_id_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
