import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Unit = Literal["adet", "kg", "g", "lt", "ml", "m", "m2", "paket", "kutu"]
MovementKind = Literal["in", "out", "adjustment"]
ProductSort = Literal["-created_at", "name", "-name", "sku", "stock"]

_SKU = re.compile(r"^[A-Za-z0-9._/\-]+$")
Quantity = Field(ge=0, max_digits=15, decimal_places=3)


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    unit: Unit
    min_stock: Decimal = Quantity
    critical_stock: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=3)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("critical_stock", mode="before")
    @classmethod
    def blank_critical(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("sku", mode="before")
    @classmethod
    def clean_sku(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("sku")
    @classmethod
    def check_sku(cls, value: str) -> str:
        if not _SKU.match(value):
            raise ValueError("Stok kodu yalnızca harf, rakam ve . _ - / içerebilir.")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        cleaned = _blank_to_none(value)
        return cleaned.strip() if isinstance(cleaned, str) else cleaned


class ProductCreate(ProductInput):
    initial_stock: Decimal = Field(default=Decimal(0), ge=0, max_digits=15, decimal_places=3)


class MovementInput(BaseModel):
    kind: MovementKind
    quantity: Decimal = Quantity
    note: str | None = Field(default=None, max_length=300)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=80)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        cleaned = _blank_to_none(value)
        return cleaned.strip() if isinstance(cleaned, str) else cleaned


class ProductItem(BaseModel):
    id: UUID
    sku: str
    name: str
    description: str | None
    unit: Unit
    min_stock: str
    critical_stock: str | None = None
    critical_level: str | None = None
    stock_quantity: str
    reserved: str = "0"
    available: str = "0"
    incoming: str = "0"
    low: bool
    critical: bool = False
    created_at: datetime
    updated_at: datetime


class ReorderSuggestion(BaseModel):
    product_id: UUID
    name: str
    sku: str
    unit: str
    stock: str
    reserved: str
    incoming: str
    expected: str
    min_stock: str
    used_last_30_days: str
    days_left: int | None
    suggested: str
    action: Literal["produce", "purchase"]
    reasons: list[str]


class ProductPage(BaseModel):
    items: list[ProductItem]
    total: int
    page: int
    page_size: int


class MovementItem(BaseModel):
    id: UUID
    kind: MovementKind
    quantity: str
    balance_after: str
    note: str | None
    actor: str | None
    created_at: datetime


class MovementPage(BaseModel):
    items: list[MovementItem]
    total: int
    page: int
    page_size: int


class MovementResult(BaseModel):
    product: ProductItem
    movement: MovementItem


class InventorySummary(BaseModel):
    products: int
    low: int
    critical: int = 0
