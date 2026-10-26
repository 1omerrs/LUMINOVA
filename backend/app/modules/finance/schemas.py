from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.modules.finance.models import EXPENSE_CATEGORIES, INCOME_CATEGORIES

RecordKind = Literal["income", "expense"]
RecordStatus = Literal["pending", "partial", "paid", "cancelled"]
PaymentMethod = Literal["cash", "transfer", "card", "check", "other"]
Currency = Literal["TRY", "USD", "EUR"]
RecordSort = Literal["-record_date", "record_date", "-amount", "due_date"]


def _clean(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.split()) or None
    return value


class RecordInput(BaseModel):
    kind: RecordKind
    category: str
    description: str = Field(min_length=2, max_length=200)
    counterparty: str | None = Field(default=None, max_length=160)
    customer_id: UUID | None = None
    order_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=17, decimal_places=2)
    currency: Currency = "TRY"
    record_date: date
    due_date: date | None = None
    status: Literal["pending", "paid"] = "pending"
    paid_on: date | None = None
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("description", "counterparty", mode="before")
    @classmethod
    def clean_text(cls, value: object) -> object:
        return _clean(value)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("category")
    @classmethod
    def category_matches_kind(cls, value: str, info: ValidationInfo) -> str:
        allowed = INCOME_CATEGORIES if info.data.get("kind") == "income" else EXPENSE_CATEGORIES
        if value not in allowed:
            raise ValueError("Bu kayıt türü için geçerli bir kategori seçin.")
        return value


class CancelInput(BaseModel):
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class RecordItem(BaseModel):
    id: UUID
    kind: RecordKind
    category: str
    description: str
    counterparty: str | None
    customer_id: UUID | None
    customer_name: str | None
    order_id: UUID | None
    order_code: str | None
    amount: str
    paid_amount: str = "0.00"
    remaining: str = "0.00"
    currency: Currency
    record_date: date
    due_date: date | None
    status: RecordStatus
    paid_on: date | None
    overdue: bool
    note: str | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime


class Revision(BaseModel):
    revision: int
    action: str
    changes: dict[str, dict[str, str | None]]
    reason: str | None
    actor: str | None
    created_at: datetime


class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=17, decimal_places=2)
    paid_on: date
    method: PaymentMethod = "transfer"
    note: str | None = Field(default=None, max_length=300)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        return _clean(value)


class PaymentItem(BaseModel):
    id: UUID
    amount: str
    paid_on: date
    method: PaymentMethod
    note: str | None
    actor: str | None
    created_at: datetime


class RecordDetail(RecordItem):
    revisions: list[Revision]
    payments: list[PaymentItem] = Field(default_factory=list)


class Balance(BaseModel):
    customer_id: UUID | None
    name: str
    currency: Currency
    open_amount: str
    overdue_amount: str
    records: int
    oldest_due: date | None
    last_payment: date | None


class CashflowWeek(BaseModel):
    week_start: date
    week_end: date
    actual_in: str
    actual_out: str
    expected_in: str
    expected_out: str


class Cashflow(BaseModel):
    currency: Currency
    today: date
    overdue_in: str
    overdue_out: str
    undated_in: str
    undated_out: str
    weeks: list[CashflowWeek]
    opening_amount: str | None = None
    opening_as_of: date | None = None
    cash_now: str | None = None


class BalanceInput(BaseModel):
    currency: Currency = "TRY"
    amount: Decimal = Field(max_digits=17, decimal_places=2)
    as_of: date


class RecordPage(BaseModel):
    items: list[RecordItem]
    total: int
    page: int
    page_size: int
    today: date


class CurrencyTotals(BaseModel):
    currency: Currency
    income: str
    expense: str
    net: str
    receivable: str
    payable: str


class FinanceSummary(BaseModel):
    today: date
    period_from: date
    period_to: date
    totals: list[CurrencyTotals]
    overdue_receivables: int
    overdue_payables: int


class Categories(BaseModel):
    income: list[str]
    expense: list[str]
