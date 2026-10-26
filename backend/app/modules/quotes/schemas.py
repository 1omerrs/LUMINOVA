from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.modules.sales.schemas import Currency, OrderLine, OrderLineInput

QuoteStatus = Literal["draft", "sent", "accepted", "rejected"]
QuoteSort = Literal["-created_at", "-quote_date", "-total", "number"]


class QuoteInput(BaseModel):
    customer_id: UUID
    currency: Currency = "TRY"
    quote_date: date
    valid_until: date | None = None
    note: str | None = Field(default=None, max_length=1000)
    items: list[OrderLineInput] = Field(min_length=1, max_length=100)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("valid_until")
    @classmethod
    def after_quote_date(cls, value: date | None, info: ValidationInfo) -> date | None:
        issued = info.data.get("quote_date")
        if value is not None and issued is not None and value < issued:
            raise ValueError("Geçerlilik tarihi teklif tarihinden önce olamaz.")
        return value


class QuoteSummaryItem(BaseModel):
    id: UUID
    number: int
    code: str
    customer_id: UUID
    customer_name: str
    status: QuoteStatus
    expired: bool
    currency: Currency
    quote_date: date
    valid_until: date | None
    total: str
    item_count: int
    order_id: UUID | None
    order_code: str | None
    created_at: datetime


class QuoteDetail(QuoteSummaryItem):
    note: str | None
    subtotal: str
    discount_total: str = "0.00"
    vat_total: str
    sent_at: datetime | None
    decided_at: datetime | None
    decided_by: Literal["staff", "customer"] | None = None
    customer_note: str | None = None
    customer_email: str | None = None
    email_status: Literal["queued", "handed_off", "sent", "failed"] | None = None
    email_error: str | None = None
    share_path: str | None = None
    email_notice: str | None = None
    items: list[OrderLine]


def _clean_text(value: object) -> object:
    if isinstance(value, str):
        return value.strip() or None
    return value


class SendInput(BaseModel):
    email: bool = True
    message: str | None = Field(default=None, max_length=1000)

    _message = field_validator("message", mode="before")(_clean_text)


class PublicLine(BaseModel):
    description: str
    quantity: str
    unit: str | None
    unit_price: str
    vat_rate: int
    discount_rate: str
    line_total: str


class PublicQuote(BaseModel):
    company_name: str
    code: str
    customer_name: str
    status: QuoteStatus
    expired: bool
    can_decide: bool
    currency: Currency
    quote_date: date
    valid_until: date | None
    note: str | None
    subtotal: str
    discount_total: str
    vat_total: str
    total: str
    decided_at: datetime | None
    decided_by: Literal["staff", "customer"] | None
    customer_note: str | None
    items: list[PublicLine]


class DecisionInput(BaseModel):
    decision: Literal["accept", "reject"]
    note: str | None = Field(default=None, max_length=500)

    _note = field_validator("note", mode="before")(_clean_text)


class QuotePage(BaseModel):
    items: list[QuoteSummaryItem]
    total: int
    page: int
    page_size: int


class QuoteSummary(BaseModel):
    draft: int
    sent: int
    accepted: int
    rejected: int
    open_value: str
