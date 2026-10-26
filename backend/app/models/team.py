import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompanyInvitation(Base):
    __tablename__ = "company_invitations"
    __table_args__ = (
        Index("uq_company_invitations_token_hash", "token_hash", unique=True),
        Index(
            "uq_company_invitations_open_email",
            "company_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        CheckConstraint("role IN ('admin', 'member')", name="ck_company_invitations_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_company_invitations_company_id_companies"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_company_invitations_invited_by_users"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_company_invitations_accepted_user_id_users"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Module levels the member receives on acceptance, e.g. {"tasks": "edit"}. Ignored for admins.
    permissions: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class JoinRequest(Base):
    """A person who signed up with the company's join code and waits for a manager."""

    __tablename__ = "join_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_join_requests_status"),
        Index("uq_join_requests_open_user", "user_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_join_requests_company_status", "company_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_join_requests_company_id_companies"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", name="fk_join_requests_user_id_users"), nullable=False)
    position: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", name="fk_join_requests_decided_by_users"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MemberPermission(Base):
    """What a member (role 'member') may do in a module. No row means no access; owners and admins need none."""

    __tablename__ = "member_permissions"
    __table_args__ = (CheckConstraint("level IN ('view', 'edit')", name="ck_member_permissions_level"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", name="fk_member_permissions_company_id_companies"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", name="fk_member_permissions_user_id_users"), primary_key=True)
    module_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
