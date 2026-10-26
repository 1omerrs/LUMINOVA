from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

OrderStatus = Literal["draft", "confirmed", "fulfilled", "cancelled"]
Currency = Literal["TRY", "USD", "EUR"]
VatRate = Literal[0, 1, 10, 20]
OrderSort = Literal["-created_at", "-order_date", "order_date", "-total", "number"]


class OrderLineInput(BaseModel):
    product_id: UUID | None = None
    description: str = Field(default="", max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=17, decimal_places=2)
    vat_rate: VatRate = 20
    discount_rate: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=5, decimal_places=2)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class OrderInput(BaseModel):
    customer_id: UUID
    currency: Currency = "TRY"
    order_date: date
    note: str | None = Field(default=None, max_length=1000)
    items: list[OrderLineInput] = Field(min_length=1, max_length=100)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class TransitionInput(BaseModel):
    note: str | None = Field(default=None, max_length=300)


class OrderLine(BaseModel):
    id: UUID
    position: int
    product_id: UUID | None
    product_sku: str | None
    product_unit: str | None
    description: str
    quantity: str
    unit_price: str
    vat_rate: int
    discount_rate: str = "0"
    line_discount: str = "0.00"
    line_subtotal: str
    line_vat: str
    line_total: str


class OrderEvent(BaseModel):
    from_status: OrderStatus | None
    to_status: OrderStatus
    note: str | None
    actor: str | None
    created_at: datetime


class OrderSummaryItem(BaseModel):
    id: UUID
    number: int
    code: str
    customer_id: UUID
    customer_name: str
    status: OrderStatus
    currency: Currency
    order_date: date
    total: str
    item_count: int
    created_at: datetime


class StockCheck(BaseModel):
    product_id: UUID
    name: str
    unit: str
    needed: str
    on_hand: str
    reserved_elsewhere: str
    available: str
    short: str
    incoming: str = "0"


class OrderDetail(OrderSummaryItem):
    note: str | None
    subtotal: str
    discount_total: str = "0.00"
    vat_total: str
    stock_posted: bool
    source_quote_id: UUID | None = None
    source_quote_code: str | None = None
    stock_check: list[StockCheck] = Field(default_factory=list)
    automation: list[str] = Field(default_factory=list)
    items: list[OrderLine]
    events: list[OrderEvent]


IncomeOn = Literal["off", "confirmed", "fulfilled"]


class SalesRulesInput(BaseModel):
    income_on: IncomeOn = "off"
    income_due_days: int | None = Field(default=None, ge=0, le=365)
    confirm_template_id: UUID | None = None
    production_on_shortage: bool = False


class SalesRulesOut(SalesRulesInput):
    confirm_template_name: str | None = None
    finance_on: bool
    tasks_on: bool
    production_on: bool = False
    updated_at: datetime | None = None


class OrderPage(BaseModel):
    items: list[OrderSummaryItem]
    total: int
    page: int
    page_size: int


class SalesSummary(BaseModel):
    draft: int
    confirmed: int
    fulfilled: int
    cancelled: int
