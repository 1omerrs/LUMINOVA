import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TICKET_STATUSES = ("open", "answered", "closed")
TICKET_CATEGORIES = ("question", "bug", "request", "account", "complaint", "notice")


class SupportTicket(Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("company_id", "number", name="uq_support_tickets_company_number"),
        CheckConstraint("status IN ('open', 'answered', 'closed')", name="ck_support_tickets_status"),
        CheckConstraint("category IN ('question', 'bug', 'request', 'account', 'complaint', 'notice')", name="ck_support_tickets_category"),
        Index("ix_support_tickets_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_support_tickets_company_id_companies"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", name="fk_support_tickets_created_by_users"), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    # True when the LUMINOVA team started the conversation; created_by is then the company owner.
    opened_by_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint("author_kind IN ('customer', 'staff')", name="ck_support_messages_author_kind"),
        Index("ix_support_messages_ticket_id_created_at", "ticket_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("support_tickets.id", name="fk_support_messages_ticket_id_support_tickets"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_support_messages_company_id_companies"), nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", name="fk_support_messages_author_user_id_users"), nullable=False)
    author_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
