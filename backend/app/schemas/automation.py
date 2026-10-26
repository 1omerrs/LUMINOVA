from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EventType(BaseModel):
    key: str
    label: str
    description: str


class EndpointInput(BaseModel):
    direction: Literal["outbound", "inbound"] = "outbound"
    name: str = Field(min_length=2, max_length=120)
    url: str | None = Field(default=None, max_length=500)
    events: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("url", mode="before")
    @classmethod
    def clean_url(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class EndpointItem(BaseModel):
    id: UUID
    direction: Literal["outbound", "inbound"]
    name: str
    url: str | None
    inbound_path: str | None
    events: list[str]
    active: bool
    secret_hint: str
    last_used_at: datetime | None
    created_at: datetime
    pending: int
    failed: int


class EndpointCreated(BaseModel):
    endpoint: EndpointItem
    secret: str


class DeliveryItem(BaseModel):
    id: UUID
    endpoint_id: UUID
    endpoint_name: str
    event_type: str
    status: Literal["pending", "delivered", "failed"]
    attempts: int
    last_status_code: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class InboundTask(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_date: date | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class InboundNotification(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    body: str | None = Field(default=None, max_length=500)


class InboundRequest(BaseModel):
    action: Literal["task.create", "notification.create"]
    data: dict[str, object]


class InboundResult(BaseModel):
    ok: bool
    action: str
    id: UUID | None = None
    duplicate: bool = False
