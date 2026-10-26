from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["owner", "admin", "member"]
InvitableRole = Literal["admin", "member"]
Level = Literal["view", "edit"]


class InvitationCreate(BaseModel):
    email: EmailStr
    role: InvitableRole = "member"
    permissions: dict[str, Level] = Field(default_factory=dict)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PermissionsUpdate(BaseModel):
    permissions: dict[str, Level]


class RoleUpdate(BaseModel):
    role: InvitableRole


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("first_name", "last_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Bu alan gerekli.")
        return cleaned


class TeamMember(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: Role
    joined_at: datetime
    me: bool
    permissions: dict[str, Level] | None = None


class Invitation(BaseModel):
    id: UUID
    email: str
    role: InvitableRole
    expires_at: datetime
    invited_by: str | None
    created_at: datetime
    email_status: Literal["queued", "handed_off", "sent", "failed"] | None = None
    email_error: str | None = None
    permissions: dict[str, Level] | None = None


class GrantableModule(BaseModel):
    key: str
    name: str
    requires: list[str]


class JoinRequestItem(BaseModel):
    id: UUID
    name: str
    email: str
    position: str | None
    note: str | None
    email_verified: bool
    created_at: datetime


class JoinDecision(BaseModel):
    permissions: dict[str, Level] = Field(default_factory=dict)


class TeamResponse(BaseModel):
    members: list[TeamMember]
    invitations: list[Invitation]
    can_manage: bool
    grantable: list[GrantableModule] = []
    join_code: str | None = None
    join_requests: list[JoinRequestItem] = []


class InvitationCreated(BaseModel):
    invitation: Invitation
    email_sent: Literal[False]
    email_queued: bool = False
    message: str
    invite_path: str | None


class InvitationPreview(BaseModel):
    company_name: str
    email: str
    role: InvitableRole
    invited_by: str | None
    expires_at: datetime
