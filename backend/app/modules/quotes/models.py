import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MONEY = Numeric(19, 4)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_quotes_company_id_number"),
        UniqueConstraint("order_id", name="uq_quotes_order_id"),
        Index("ix_quotes_company_id_created_at", "company_id", "created_at"),
        CheckConstraint("status IN ('draft', 'sent', 'accepted', 'rejected')", name="ck_quotes_status"),
        CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_quotes_currency"),
        CheckConstraint("valid_until IS NULL OR valid_until >= quote_date", name="ck_quotes_valid_until"),
        CheckConstraint("order_id IS NULL OR status = 'accepted'", name="ck_quotes_order_accepted"),
        CheckConstraint("decided_by IS NULL OR decided_by IN ('staff', 'customer')", name="ck_quotes_decided_by"),
        Index("uq_quotes_share_token_hash", "share_token_hash", unique=True, postgresql_where=text("share_token_hash IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_quotes_company_id_companies"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", name="fk_quotes_customer_id_customers"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY", server_default="TRY")
    quote_date: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(1000))
    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0), server_default="0")
    discount_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0), server_default="0")
    vat_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0), server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0), server_default="0")
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", name="fk_quotes_order_id_orders"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(16))
    customer_note: Mapped[str | None] = mapped_column(String(500))
    # Hash of the token in the customer link; a new send or resend replaces it.
    share_token_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_quotes_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class QuoteItem(Base):
    __tablename__ = "quote_items"
    __table_args__ = (
        Index("ix_quote_items_quote_id_position", "quote_id", "position"),
        CheckConstraint("quantity > 0", name="ck_quote_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_quote_items_unit_price"),
        CheckConstraint("vat_rate IN (0, 1, 10, 20)", name="ck_quote_items_vat_rate"),
        CheckConstraint("discount_rate >= 0 AND discount_rate <= 100", name="ck_quote_items_discount_rate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_quote_items_company_id_companies"), nullable=False)
    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quotes.id", name="fk_quote_items_quote_id_quotes"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id", name="fk_quote_items_product_id_products"))
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal(0), server_default="0")
    line_discount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0), server_default="0")
    line_subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_vat: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
