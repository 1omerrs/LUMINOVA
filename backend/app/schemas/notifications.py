from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: UUID
    category: str
    title: str
    body: str | None = None
    link: str | None = None
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    unread: int


class PreferenceItem(BaseModel):
    category: str
    label: str
    description: str
    in_app: bool
    in_app_available: bool = True
    email: bool = False
    email_available: bool = False


class PreferenceUpdate(BaseModel):
    in_app: dict[str, bool] = {}
    email: dict[str, bool] = {}
