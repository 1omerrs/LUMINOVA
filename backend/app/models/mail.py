import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

MAIL_KINDS = ("verify_email", "password_reset", "invitation", "notification", "digest", "quote")
MAIL_STATUSES = ("queued", "handed_off", "sent", "failed")


class EmailMessage(Base):
    """Outgoing e-mail. LUMINOVA never talks SMTP itself; the worker hands each message to the n8n mail webhook."""

    __tablename__ = "email_messages"
    __table_args__ = (
        CheckConstraint(f"kind IN {MAIL_KINDS}", name="ck_email_messages_kind"),
        CheckConstraint(f"status IN {MAIL_STATUSES}", name="ck_email_messages_status"),
        Index("ix_email_messages_due", "status", "next_attempt_at"),
        Index("ix_email_messages_created_at", "created_at"),
        Index("ix_email_messages_ref", "ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", name="fk_email_messages_company_id_companies"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_email_messages_user_id_users"))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    ref: Mapped[str | None] = mapped_column(String(80))
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    # Bodies can hold one-time links, so they are cleared once the message reaches a final state.
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(400))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handed_off_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
