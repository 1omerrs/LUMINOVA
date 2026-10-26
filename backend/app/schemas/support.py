from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Category = Literal["question", "bug", "request", "account", "complaint", "notice"]
CustomerCategory = Literal["question", "bug", "request", "account", "complaint"]
Status = Literal["open", "answered", "closed"]


def _clean(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Bu alan boş bırakılamaz.")
    return cleaned


class TicketCreate(BaseModel):
    subject: str = Field(max_length=160)
    category: CustomerCategory
    body: str = Field(max_length=5000)

    _subject = field_validator("subject")(_clean)
    _body = field_validator("body")(_clean)


class MessageCreate(BaseModel):
    body: str = Field(max_length=5000)

    _body = field_validator("body")(_clean)


class SupportMessageItem(BaseModel):
    id: UUID
    author_kind: Literal["customer", "staff"]
    author_name: str
    body: str
    created_at: datetime


class TicketItem(BaseModel):
    id: UUID
    code: str
    subject: str
    category: Category
    status: Status
    created_by_name: str
    message_count: int
    last_message_at: datetime
    created_at: datetime
    company_id: UUID | None = None
    company_name: str | None = None
    opened_by_staff: bool = False


class TicketDetail(TicketItem):
    messages: list[SupportMessageItem]
    can_reply: bool


class TicketList(BaseModel):
    items: list[TicketItem]
    open: int
    answered: int
    closed: int


class AdminOverview(BaseModel):
    companies: int
    active_companies: int
    setup_pending: int
    users: int
    signups_30d: int
    open_tickets: int
    answered_tickets: int
    pending_closures: int = 0


class AdminCompany(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    setup_completed: bool
    owner_name: str
    owner_email: str
    members: int
    modules: int
    last_activity_at: datetime | None
    open_tickets: int


class AdminCompanyList(BaseModel):
    items: list[AdminCompany]
    total: int


class StaffMessage(BaseModel):
    subject: str = Field(max_length=160)
    body: str = Field(max_length=5000)

    _subject = field_validator("subject")(_clean)
    _body = field_validator("body")(_clean)


class AdminModule(BaseModel):
    key: str
    name: str
    enabled_at: datetime | None


class AdminPerson(BaseModel):
    name: str
    email: str
    role: str
    joined_at: datetime


class AdminCompanyDetail(AdminCompany):
    sector: str | None
    team_size: str | None
    module_list: list[AdminModule]
    people: list[AdminPerson]
    pending_join_requests: int
    pending_invitations: int


class CompanyDeletion(BaseModel):
    confirm_name: str = Field(min_length=1, max_length=160)
