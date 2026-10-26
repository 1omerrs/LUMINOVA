from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

ProductionStatus = Literal["planned", "in_progress", "completed", "cancelled"]
ProductionSort = Literal["-created_at", "planned_date", "number"]


class MaterialInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)


class ProductionInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    planned_date: date | None = None
    note: str | None = Field(default=None, max_length=1000)
    materials: list[MaterialInput] = Field(default_factory=list, max_length=50)
    sales_order_id: UUID | None = None
    project_id: UUID | None = None

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class CancelInput(BaseModel):
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value


class MaterialLine(BaseModel):
    product_id: UUID
    name: str
    sku: str
    unit: str
    quantity: str
    available: str
    short: bool


class ProductionSummaryItem(BaseModel):
    id: UUID
    number: int
    code: str
    product_id: UUID
    product_name: str
    product_sku: str
    unit: str
    quantity: str
    status: ProductionStatus
    planned_date: date | None
    material_count: int
    shortage: bool
    sales_order_id: UUID | None = None
    sales_order_code: str | None = None
    project_id: UUID | None = None
    project_name: str | None = None
    created_at: datetime


class ProductionDetail(ProductionSummaryItem):
    note: str | None
    cancel_reason: str | None
    product_stock: str
    stock_posted: bool
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_by: str | None
    materials: list[MaterialLine]


class ProductionPage(BaseModel):
    items: list[ProductionSummaryItem]
    total: int
    page: int
    page_size: int


class RecipeItemInput(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=4)


class RecipeInput(BaseModel):
    items: list[RecipeItemInput] = Field(default_factory=list, max_length=50)


class RecipeLine(BaseModel):
    product_id: UUID
    name: str
    sku: str
    unit: str
    quantity: str
    deleted: bool = False


class RecipeOut(BaseModel):
    product_id: UUID
    name: str
    unit: str
    items: list[RecipeLine]


class RecipeSummary(BaseModel):
    product_id: UUID
    name: str
    sku: str
    unit: str
    materials: int


class ProductionSummary(BaseModel):
    planned: int
    in_progress: int
    completed: int
    cancelled: int
