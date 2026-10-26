import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OPEN_STATUSES = ("pending", "partial")
INCOME_CATEGORIES = ("Satış", "Hizmet", "Diğer gelir")
EXPENSE_CATEGORIES = ("Malzeme", "Kira", "Personel", "Fatura", "Vergi", "Ulaşım", "Pazarlama", "Diğer gider")


class FinancialRecord(Base):
    __tablename__ = "financial_records"
    __table_args__ = (
        Index("ix_financial_records_company_id_record_date", "company_id", "record_date"),
        Index(
            "uq_financial_records_order_id",
            "company_id",
            "order_id",
            unique=True,
            postgresql_where=text("order_id IS NOT NULL AND status <> 'cancelled'"),
        ),
        CheckConstraint("kind IN ('income', 'expense')", name="ck_financial_records_kind"),
        CheckConstraint("status IN ('pending', 'partial', 'paid', 'cancelled')", name="ck_financial_records_status"),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= amount", name="ck_financial_records_paid_amount"),
        CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_financial_records_currency"),
        CheckConstraint("amount > 0", name="ck_financial_records_amount"),
        CheckConstraint("(status = 'paid') = (paid_on IS NOT NULL)", name="ck_financial_records_paid_on"),
        CheckConstraint("order_id IS NULL OR kind = 'income'", name="ck_financial_records_order_income"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_financial_records_company_id_companies"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty: Mapped[str | None] = mapped_column(String(160))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id", name="fk_financial_records_customer_id_customers"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id", name="fk_financial_records_order_id_orders"))
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal(0), server_default="0")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY", server_default="TRY")
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    paid_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(1000))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_financial_records_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CashBalance(Base):
    """What the company held in one currency at the start of `as_of`; cash flow builds on it."""

    __tablename__ = "cash_balances"
    __table_args__ = (CheckConstraint("currency IN ('TRY', 'USD', 'EUR')", name="ck_cash_balances_currency"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_cash_balances_company_id_companies"), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_cash_balances_updated_by_users"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


PAYMENT_METHODS = ("cash", "transfer", "card", "check", "other")


class FinancialPayment(Base):
    __tablename__ = "financial_payments"
    __table_args__ = (
        Index("ix_financial_payments_record_id", "record_id"),
        Index("ix_financial_payments_company_id_paid_on", "company_id", "paid_on"),
        CheckConstraint("amount > 0", name="ck_financial_payments_amount"),
        CheckConstraint("method IN ('cash', 'transfer', 'card', 'check', 'other')", name="ck_financial_payments_method"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_financial_payments_company_id_companies"), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_records.id", name="fk_financial_payments_record_id_financial_records"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="transfer", server_default="transfer")
    note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_financial_payments_created_by_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinancialRecordRevision(Base):
    __tablename__ = "financial_record_revisions"
    __table_args__ = (Index("ix_financial_record_revisions_record_id_revision", "record_id", "revision", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_financial_record_revisions_company_id_companies"), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_records.id", name="fk_financial_record_revisions_record_id_financial_records"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    reason: Mapped[str | None] = mapped_column(String(300))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_financial_record_revisions_actor_user_id_users"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
