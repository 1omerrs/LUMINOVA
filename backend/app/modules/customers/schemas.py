import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

_PHONE = re.compile(r"^\+?[0-9 ()\-]{7,40}$")

CustomerSort = Literal["name", "-name", "created_at", "-created_at"]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class CustomerInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("email", "phone", "note", mode="before")
    @classmethod
    def empty_is_none(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not _PHONE.match(cleaned) or sum(character.isdigit() for character in cleaned) < 7:
            raise ValueError("Geçerli bir telefon numarası girin.")
        return cleaned

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class CustomerItem(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class CustomerPage(BaseModel):
    items: list[CustomerItem]
    total: int
    page: int
    page_size: int


class CustomerMatch(BaseModel):
    id: UUID
    name: str
    email: str | None
    phone: str | None
    reason: str


class OverviewMoney(BaseModel):
    currency: str
    amount: str


class OverviewLink(BaseModel):
    id: UUID
    code: str
    status: str
    status_label: str
    when: date | None = None
    amount: str | None = None
    currency: str | None = None


class OverviewTask(BaseModel):
    id: UUID
    title: str
    status: str
    due_date: date | None
    overdue: bool


class OverviewFinance(BaseModel):
    receivable: list[OverviewMoney]
    collected: list[OverviewMoney]
    overdue: int
    pending: list[OverviewLink]


class OverviewTimeline(BaseModel):
    kind: str
    label: str
    at: datetime
    link: str | None


class CustomerOverview(BaseModel):
    enabled: list[str]
    order_count: int = 0
    open_orders: int = 0
    revenue: list[OverviewMoney] = Field(default_factory=list)
    orders: list[OverviewLink] = Field(default_factory=list)
    open_quotes: int = 0
    quotes: list[OverviewLink] = Field(default_factory=list)
    projects: list[OverviewLink] = Field(default_factory=list)
    open_tasks: list[OverviewTask] = Field(default_factory=list)
    finance: OverviewFinance | None = None
    timeline: list[OverviewTimeline]


class CustomerDetail(BaseModel):
    customer: CustomerItem
    overview: CustomerOverview


class ImportMapping(BaseModel):
    name: int | None = Field(default=None, ge=0)
    email: int | None = Field(default=None, ge=0)
    phone: int | None = Field(default=None, ge=0)
    note: int | None = Field(default=None, ge=0)


class ImportFile(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=3_000_000)


class ImportRequest(ImportFile):
    mapping: ImportMapping
    dry_run: bool = True


class ImportPreview(BaseModel):
    headers: list[str]
    sample: list[list[str]]
    total_rows: int
    mapping: ImportMapping


class ImportDuplicate(BaseModel):
    row: int
    name: str
    reason: str
    existing_id: UUID | None
    existing_name: str | None


class ImportError_(BaseModel):
    row: int
    message: str


class ImportReport(BaseModel):
    total: int
    valid: int = 0
    created: int = 0
    dry_run: bool
    duplicates: list[ImportDuplicate] = Field(default_factory=list)
    errors: list[ImportError_] = Field(default_factory=list)
